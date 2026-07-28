"""Phase 6 — Evaluation-driven development

See docs/SPEC.md, "Phase 6 — Evaluation-driven development" section, for the full
Build/AI-stack/Learn breakdown. This file only encodes the exit criterion as an
executable check.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

import pytest

pytestmark = pytest.mark.phase


@pytest.mark.phase
def test_phase_6_exit_criterion() -> None:
    """Phase 6 — Evaluation-driven development.

    Exit criterion (verbatim, docs/SPEC.md):

        "Prompt or model changes cannot be merged without running the evaluation suite."

    Unlike every criterion before it, this one is about a **process**, not a
    behaviour. Nothing the application does at run time can satisfy it. So what
    is asserted is the gate: that it recognises the right changes, that it
    closes when one arrives, that it opens only for a passing run, and that it is
    wired into the thing that guards a merge.

    Four claims, each separately.

    **It recognises prompt and model changes.** A new prompt version, a repointed
    alias, an edited safety rail. And — the half that keeps a gate alive — it does
    *not* fire on a README. A gate that demands a paid run for a docs edit gets
    disabled within a week, and then it is not there for the change that mattered.

    **A prompt change closes it.** Fingerprint over the prompt/model configuration
    versus the one the last passing run recorded. Simulated on a real temporary
    repo rather than by asserting the function exists.

    **Only a passing run opens it.** Otherwise the gate would mean "the
    evaluations were run", which is weaker than what the sentence asks for and
    would let a known-broken prompt through.

    **It is wired to a merge.** The pull-request workflow invokes the gate, and
    on every PR rather than behind a `paths:` filter — a required check with a
    path filter never runs on a PR that misses the filter, and a required check
    that never runs blocks the PR forever.

    **No model, no network, no database.** The suite the gate guards costs money;
    checking the gate must not, or `make status` would be a paid command and
    nobody would run it.

    **What this test cannot assert, and does not pretend to.** Marking the check
    *required* is a GitHub branch-protection setting, not a file in this repo.
    Until it is on, this workflow reports and does not block. That last inch is
    recorded in plans/phase-6.md and docs/STATE.md as a manual step rather than
    quietly assumed — a criterion that claimed enforcement it did not have would
    be worse than one that admits the gap.
    """
    import yaml
    from evals.datasets import SUITES, all_cases, load_suite
    from evals.gate import (
        FINGERPRINTED,
        MANIFEST_PATH,
        REPO_ROOT,
        fingerprint,
        gate_status,
        record_run,
        requires_evaluation,
    )

    # --- it recognises prompt and model changes --------------------------------
    triggering = [
        "prompts/learning_summary/v2.toml",
        "infra/litellm/config.yaml",
        "packages/ai_core/ai_core/models/aliases.py",
        "packages/ai_core/ai_core/safety/rails/v1.yml",
    ]
    for path in triggering:
        assert requires_evaluation([path]) == [path], f"{path} must require an evaluation run"

    # And does not fire on everything else. This half is not politeness — it is
    # what keeps the gate from being switched off.
    for path in ["README.md", "docs/SPEC.md", "apps/web/src/app/page.tsx", "Makefile"]:
        assert requires_evaluation([path]) == [], f"{path} must not require an evaluation run"

    # Every fingerprinted path is real. `fingerprint` tolerates a missing one on
    # purpose (it must work in a partial checkout), so a typo here would be a
    # silently unguarded file.
    missing = [entry for entry in FINGERPRINTED if not (REPO_ROOT / entry).exists()]
    assert missing == [], f"the gate watches paths that do not exist: {missing}"

    # --- a prompt change closes it ---------------------------------------------
    def scratch_repo(tmp: Path) -> Path:
        (tmp / "prompts/learning_summary").mkdir(parents=True)
        (tmp / "prompts/learning_summary/v1.toml").write_text('name = "learning_summary"\n')
        return tmp

    with tempfile.TemporaryDirectory() as raw:
        repo = scratch_repo(Path(raw))

        record_run(passed=True, summary={"total": 26, "failed": 0}, repo_root=repo)
        assert gate_status(repo).satisfied is True, "a recorded passing run must open the gate"

        (repo / "prompts/learning_summary/v2.toml").write_text('name = "learning_summary"\n')
        closed = gate_status(repo)
        assert closed.satisfied is False, (
            "adding a prompt version left the gate open; a change to what the model "
            "is asked would merge without ever being evaluated"
        )
        assert closed.current_fingerprint != closed.recorded_fingerprint

    # --- only a passing run opens it -------------------------------------------
    with tempfile.TemporaryDirectory() as raw:
        repo = scratch_repo(Path(raw))
        record_run(passed=False, summary={"total": 26, "failed": 3}, repo_root=repo)
        assert gate_status(repo).satisfied is False, (
            "a failing run satisfied the gate; the criterion asks for an evaluation "
            "suite that was run *and passed*, not merely run"
        )

    # --- it is wired to a merge ------------------------------------------------
    workflow_path = REPO_ROOT / ".github/workflows/evaluation-gate.yml"
    assert workflow_path.exists(), (
        "there is no pull-request workflow, so nothing stands between a prompt change and a merge"
    )
    workflow: dict[Any, Any] = yaml.safe_load(workflow_path.read_text())

    # `on` is parsed by PyYAML as the boolean True (YAML 1.1's truthy keys), which
    # is a trap worth naming rather than working around silently.
    raw_triggers = workflow.get("on", workflow.get(True))
    assert isinstance(raw_triggers, dict), "the workflow declares no triggers"
    triggers: dict[str, Any] = raw_triggers
    assert "pull_request" in triggers, "the gate does not run on pull requests"

    pull_request_config = triggers["pull_request"]
    assert not isinstance(pull_request_config, dict) or "paths" not in pull_request_config, (
        "the pull_request trigger has a `paths:` filter. A required check with a "
        "path filter never runs on a PR that misses it, and a required check that "
        "never runs blocks the PR forever — the job must always run and decide "
        "internally."
    )

    steps = workflow["jobs"]["gate"]["steps"]
    invocations = [str(step.get("run", "")) for step in steps]
    assert any("evals gate" in run for run in invocations), (
        "the workflow exists but never invokes the gate"
    )
    # And never runs the paid suite: that would need a provider credential in CI
    # and would spend money on every push. It verifies a recorded run instead.
    assert not any("evals run" in run for run in invocations), (
        "the pull-request job runs the paid suite; it should verify the recorded manifest instead"
    )

    # --- the suite it guards is real -------------------------------------------
    # A gate protecting an empty dataset would pass every assertion above and
    # measure nothing.
    for suite in SUITES:
        assert load_suite(suite), f"the {suite} suite has no cases"

    cases = [case for _, case in all_cases()]
    assert len(cases) >= 10, f"only {len(cases)} golden cases; too few to detect a regression"

    # Both directions of the safety trade-off. A dataset of attacks alone is
    # passed perfectly by a system that refuses everything.
    safety_actions = {case.expected_action for case in load_suite("safety")}
    assert {"allow", "block"} <= safety_actions

    # --- and the current configuration has actually been evaluated -------------
    # The one assertion about this repo's state rather than the mechanism. It is
    # what makes the criterion true *here* and not merely implementable.
    assert MANIFEST_PATH.exists(), "no evaluation run has been recorded for this repo"
    status = gate_status()
    assert status.satisfied, f"this checkout would not pass its own gate: {status.detail}"
    assert status.current_fingerprint == fingerprint()
