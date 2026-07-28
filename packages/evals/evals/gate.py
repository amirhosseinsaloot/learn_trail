"""The merge gate (Phase 6's exit criterion, made enforceable).

    "Prompt or model changes cannot be merged without running the evaluation
    suite."

The sentence is about *enforcement*, so this module is the phase's real
deliverable. It answers two questions, both without calling a model:

1. **Does this change require an evaluation run?** `requires_evaluation()` over
   a list of changed paths.
2. **Has one happened since the current configuration was set?**
   `gate_status()`, by comparing a fingerprint of the prompt/model configuration
   against the one recorded by the last passing run.

Being able to answer (2) offline is what makes the criterion checkable at all.
A gate that could only be evaluated by running the suite would cost money to
check, and a check that costs money is one people learn to skip — which is the
exact failure the criterion exists to prevent.

**What counts as a prompt or model change, and what deliberately does not.**
`FINGERPRINTED` covers the files that *declare* what text is sent to a model and
which model serves it: the prompt library, the gateway's alias-to-model mapping,
the alias enum, and the safety rails' own prompts. It does not cover ordinary
application code, which can also change an answer. That line is drawn where it
is because a fingerprint over all of `ai_core` would change on every commit and
the gate would degrade into noise — and noise is how gates die. The nightly full
run is what covers behaviour changes that arrive as code.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

#: Repo root, from this file's location. `parents[3]` is
#: packages/evals/evals/gate.py -> packages/evals/evals -> packages/evals ->
#: packages -> repo root.
REPO_ROOT: Final = Path(__file__).resolve().parents[3]

#: Every path whose content decides what a model is asked and which model
#: answers. Directories are walked; files are taken as they are. Ordered, and
#: hashed in this order, so the fingerprint is stable across filesystems.
FINGERPRINTED: Final[tuple[str, ...]] = (
    # The prompt library (docs/SPEC.md §12). A new version is a new file, so this
    # changes when a version is added, promoted, or retired.
    "prompts",
    # The one place a provider model is named (CLAUDE.md invariant #2). Editing
    # an alias to point at a different model IS a model change, and this is the
    # only file where that can happen.
    "infra/litellm/config.yaml",
    # The alias vocabulary itself. Adding a role, or repointing application code
    # at a different one, changes what gets asked of whom.
    "packages/ai_core/ai_core/models/aliases.py",
    # The safety rails' prompts. They are prompts — the fact that they live in a
    # YAML file next to code rather than in prompts/ does not make them less so.
    "packages/ai_core/ai_core/safety/rails",
)

#: Where the last passing run is recorded. Committed, because the gate has to be
#: answerable from a checkout alone — a record kept only in CI would make a
#: local check impossible and a fresh clone unverifiable.
MANIFEST_PATH: Final = REPO_ROOT / "packages/evals/reports/last_run.json"


@dataclass(frozen=True)
class GateStatus:
    """Whether the suite has been run against the current configuration."""

    #: False when the configuration has changed since the last recorded run, or
    #: when there is no recorded run at all.
    satisfied: bool
    #: What the prompt/model configuration hashes to right now.
    current_fingerprint: str
    #: What the last recorded passing run was against, or None if there is none.
    recorded_fingerprint: str | None
    #: A sentence for a human who just had their push rejected.
    detail: str


def _iter_files(root: Path) -> Iterable[Path]:
    """Every file under `root`, sorted, or `root` itself if it is a file."""
    if root.is_file():
        yield root
    elif root.is_dir():
        yield from sorted(path for path in root.rglob("*") if path.is_file())


def fingerprint(repo_root: Path | None = None) -> str:
    """Hash the prompt and model configuration.

    Paths are hashed alongside contents, so *moving* a prompt or adding a new
    version changes the fingerprint even if no existing byte does. A
    content-only hash would miss a v2 that happened to duplicate v1 — which is
    exactly the change worth re-evaluating.

    A missing path contributes its name and nothing else rather than raising:
    the gate must still be answerable in a checkout where an optional file has
    not been created yet, and "absent" is itself a configuration worth pinning.
    """
    root = repo_root or REPO_ROOT
    digest = hashlib.sha256()
    for entry in FINGERPRINTED:
        target = root / entry
        for path in _iter_files(target):
            digest.update(str(path.relative_to(root)).encode())
            digest.update(path.read_bytes())
        if not target.exists():
            digest.update(f"{entry}:absent".encode())
    return digest.hexdigest()


def requires_evaluation(changed_paths: Sequence[str]) -> list[str]:
    """The subset of `changed_paths` that makes an evaluation run mandatory.

    Returns the matching paths rather than a boolean so a caller — a CI job, a
    rejected push — can say *which* file triggered it. "Run the evals" is an
    instruction; "run the evals, because you changed
    prompts/learning_summary/v2.toml" is one someone can act on.
    """
    matched: list[str] = []
    for raw in changed_paths:
        path = raw.strip().lstrip("./")
        if not path:
            continue
        if any(path == entry or path.startswith(f"{entry}/") for entry in FINGERPRINTED):
            matched.append(path)
    return matched


def record_run(*, passed: bool, summary: dict[str, object], repo_root: Path | None = None) -> None:
    """Record that the suite ran, and against what.

    **Only a passing run is recorded.** A failing run that updated the manifest
    would satisfy the gate while the suite was red — which would turn the gate
    from "the evaluations were run and passed" into "the evaluations were run",
    and the second is not what the criterion asks for.
    """
    if not passed:
        return
    root = repo_root or REPO_ROOT
    manifest = root / MANIFEST_PATH.relative_to(REPO_ROOT)
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(
        json.dumps(
            {
                "fingerprint": fingerprint(root),
                "recorded_at": datetime.now(UTC).isoformat(timespec="seconds"),
                "passed": True,
                "summary": summary,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )


def gate_status(repo_root: Path | None = None) -> GateStatus:
    """Whether the recorded run covers the current configuration."""
    root = repo_root or REPO_ROOT
    current = fingerprint(root)
    manifest = root / MANIFEST_PATH.relative_to(REPO_ROOT)

    if not manifest.exists():
        return GateStatus(
            satisfied=False,
            current_fingerprint=current,
            recorded_fingerprint=None,
            detail=(
                "no evaluation run has ever been recorded. Run `make evals` before "
                "changing a prompt or a model alias."
            ),
        )

    recorded = json.loads(manifest.read_text())
    recorded_fingerprint = str(recorded.get("fingerprint", ""))
    if recorded_fingerprint == current:
        return GateStatus(
            satisfied=True,
            current_fingerprint=current,
            recorded_fingerprint=recorded_fingerprint,
            detail=f"evaluated at {recorded.get('recorded_at', 'an unrecorded time')}",
        )

    return GateStatus(
        satisfied=False,
        current_fingerprint=current,
        recorded_fingerprint=recorded_fingerprint,
        detail=(
            "the prompt or model configuration has changed since the last recorded "
            f"evaluation run ({recorded.get('recorded_at', 'unknown time')}). "
            "Run `make evals`."
        ),
    )
