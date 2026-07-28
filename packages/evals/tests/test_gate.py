"""Contract for the merge gate and the golden datasets.

No model, no network, no database. This is the half of Phase 6 that has to work
on every commit — the suite it guards costs money, and a gate that cost money to
check would be one people learn to skip, which is the exact failure the exit
criterion exists to prevent.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from evals.datasets import SUITES, EvaluationCase, Turn, all_cases, load_suite
from evals.gate import (
    FINGERPRINTED,
    MANIFEST_PATH,
    REPO_ROOT,
    fingerprint,
    gate_status,
    record_run,
    requires_evaluation,
)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A miniature repo with every fingerprinted path present."""
    (tmp_path / "prompts/learning_summary").mkdir(parents=True)
    (tmp_path / "prompts/learning_summary/v1.toml").write_text('name = "learning_summary"\n')
    (tmp_path / "infra/litellm").mkdir(parents=True)
    (tmp_path / "infra/litellm/config.yaml").write_text("model_list: []\n")
    (tmp_path / "packages/ai_core/ai_core/models").mkdir(parents=True)
    (tmp_path / "packages/ai_core/ai_core/models/aliases.py").write_text("LEARNING_FAST = 1\n")
    (tmp_path / "packages/ai_core/ai_core/safety/rails").mkdir(parents=True)
    (tmp_path / "packages/ai_core/ai_core/safety/rails/v1.yml").write_text("models: []\n")
    return tmp_path


# --- which changes require a run ------------------------------------------------


@pytest.mark.parametrize(
    "changed",
    [
        "prompts/learning_summary/v2.toml",
        "infra/litellm/config.yaml",
        "packages/ai_core/ai_core/models/aliases.py",
        "packages/ai_core/ai_core/safety/rails/v2.yml",
    ],
)
def test_prompt_and_model_changes_require_a_run(changed: str) -> None:
    """The criterion names two kinds of change; these are the files they live in.

    A new prompt version, a repointed alias, a new role, an edited safety rail —
    each changes what a model is asked or which model answers, and each must
    make the suite mandatory.
    """
    assert requires_evaluation([changed]) == [changed]


@pytest.mark.parametrize(
    "changed",
    [
        "README.md",
        "docs/SPEC.md",
        "apps/web/src/app/page.tsx",
        "packages/database/database/models/knowledge.py",
        "packages/evals/datasets/conversations/conv-001-index-vs-primary-key.json",
    ],
)
def test_ordinary_changes_do_not(changed: str) -> None:
    """Over-triggering is how a gate dies.

    A gate that demanded a paid evaluation run for a README edit would be
    disabled within a week, and then it would not be there for the change that
    mattered. Note the dataset case in the list: editing the *measurement* does
    not require re-running it against an unchanged configuration.
    """
    assert requires_evaluation([changed]) == []


def test_the_triggering_file_is_named_not_just_flagged() -> None:
    """ "Run the evals" is an instruction; naming the file makes it actionable."""
    changed = ["README.md", "prompts/learning_summary/v2.toml", "apps/web/package.json"]
    assert requires_evaluation(changed) == ["prompts/learning_summary/v2.toml"]


def test_leading_path_noise_is_tolerated() -> None:
    """`git diff --name-only` and a hand-typed path should agree."""
    assert requires_evaluation(["./prompts/learning_summary/v1.toml"]) == [
        "prompts/learning_summary/v1.toml"
    ]


def test_a_prefix_collision_does_not_trigger() -> None:
    """`prompts_backup/` is not `prompts/`.

    Matching on a bare `startswith` would fire on it, and a gate that triggers on
    unrelated files is the over-triggering failure above by another route.
    """
    assert requires_evaluation(["prompts_backup/old.toml"]) == []


# --- the fingerprint ------------------------------------------------------------


def test_editing_a_prompt_changes_the_fingerprint(repo: Path) -> None:
    before = fingerprint(repo)
    (repo / "prompts/learning_summary/v1.toml").write_text('name = "learning_summary"\nx = 1\n')
    assert fingerprint(repo) != before


def test_repointing_an_alias_changes_the_fingerprint(repo: Path) -> None:
    """A model change, in the one file where a provider model can be named."""
    before = fingerprint(repo)
    (repo / "infra/litellm/config.yaml").write_text("model_list: [{model: openai/gpt-5}]\n")
    assert fingerprint(repo) != before


def test_adding_a_prompt_version_changes_the_fingerprint(repo: Path) -> None:
    """Even when the new file duplicates an existing one byte for byte.

    Paths are hashed alongside contents for this case: a v2 that starts as a copy
    of v1 is still a new version, and it is exactly the change worth evaluating.
    A content-only hash would call it identical.
    """
    before = fingerprint(repo)
    (repo / "prompts/learning_summary/v2.toml").write_text('name = "learning_summary"\n')
    assert fingerprint(repo) != before


def test_unrelated_edits_leave_the_fingerprint_alone(repo: Path) -> None:
    before = fingerprint(repo)
    (repo / "README.md").write_text("hello\n")
    assert fingerprint(repo) == before


def test_the_fingerprint_is_stable_across_calls(repo: Path) -> None:
    # If it were not, the gate would demand a fresh run on every push.
    assert fingerprint(repo) == fingerprint(repo)


# --- the gate itself ------------------------------------------------------------


def test_with_no_recorded_run_the_gate_is_unsatisfied(repo: Path) -> None:
    status = gate_status(repo)
    assert status.satisfied is False
    assert "no evaluation run" in status.detail


def test_a_recorded_run_satisfies_the_gate(repo: Path) -> None:
    record_run(passed=True, summary={"cases": 16}, repo_root=repo)
    assert gate_status(repo).satisfied is True


def test_changing_a_prompt_after_a_run_reopens_the_gate(repo: Path) -> None:
    """The criterion, in one test.

    Run the suite, then change a prompt: the gate closes again, because the
    recorded run no longer describes the configuration that would ship.
    """
    record_run(passed=True, summary={}, repo_root=repo)
    assert gate_status(repo).satisfied is True

    (repo / "prompts/learning_summary/v1.toml").write_text('name = "learning_summary"\nv = 2\n')
    status = gate_status(repo)
    assert status.satisfied is False
    assert "has changed since the last recorded" in status.detail


def test_a_failing_run_does_not_satisfy_the_gate(repo: Path) -> None:
    """Otherwise the gate would mean "the evaluations were run".

    The criterion asks for more than that: a suite that ran and failed has not
    cleared anything, and recording it would let a known-broken prompt through.
    """
    record_run(passed=False, summary={"failed": 3}, repo_root=repo)
    assert gate_status(repo).satisfied is False


def test_the_manifest_is_committed_json(repo: Path) -> None:
    """It has to be readable from a checkout alone.

    A record kept only in CI would make the gate uncheckable locally and a fresh
    clone unverifiable — and `make status` has to be able to answer this without
    a network.
    """
    record_run(passed=True, summary={"cases": 16}, repo_root=repo)
    manifest = repo / MANIFEST_PATH.relative_to(REPO_ROOT)
    recorded = json.loads(manifest.read_text())
    assert recorded["passed"] is True
    assert recorded["fingerprint"] == fingerprint(repo)


def test_every_fingerprinted_path_exists_in_this_repo() -> None:
    """A typo'd path would be silently absent, and the gate would ignore it.

    `fingerprint` tolerates a missing path on purpose — the gate must work in a
    partial checkout — which is precisely why something has to check that these
    ones are real.
    """
    missing = [entry for entry in FINGERPRINTED if not (REPO_ROOT / entry).exists()]
    assert missing == []


# --- the datasets ---------------------------------------------------------------


def test_every_suite_has_cases() -> None:
    for suite in SUITES:
        assert load_suite(suite), f"{suite} has no cases"


def test_case_ids_are_unique_within_a_suite() -> None:
    # `load_suite` raises on duplicates; this asserts it does not have to.
    for suite in SUITES:
        ids = [case.id for case in load_suite(suite)]
        assert len(set(ids)) == len(ids)


def test_every_case_explains_why_it_exists() -> None:
    """docs/SPEC.md §10 says curate, not harvest.

    A case nobody can justify is one nobody will dare delete when it stops
    earning its place, and a dataset of those is how a suite becomes noise.
    """
    unexplained = [case.id for _, case in all_cases() if len(case.notes) < 40]
    assert unexplained == []


def test_every_case_has_a_rubric() -> None:
    """A case with nothing to grade against measures nothing."""
    for suite, case in all_cases():
        has_rubric = bool(case.grading_notes or case.forbidden_claims)
        assert has_rubric, f"{suite}/{case.id} has neither grading notes nor forbidden claims"


def test_safety_cases_state_the_expected_action() -> None:
    """The safety suite grades a *decision*, not prose, so it needs the answer."""
    for case in load_suite("safety"):
        assert case.expected_action is not None, case.id


def test_the_safety_suite_covers_both_kinds_of_failure() -> None:
    """Over-blocking and under-blocking are both failures, and they trade off.

    A suite of attacks alone would be passed perfectly by a system that refuses
    everything — so the dataset has to contain benign cases that must *not* be
    blocked, or tuning the rails has no counterweight.
    """
    actions = {case.expected_action for case in load_suite("safety")}
    assert "block" in actions
    assert "allow" in actions


def test_a_case_with_no_user_turn_is_rejected() -> None:
    case = EvaluationCase(
        id="broken", messages=[Turn(role="assistant", content="hello")], notes="x" * 40
    )
    with pytest.raises(ValueError, match="no user turn"):
        _ = case.question


def test_unknown_fields_are_rejected() -> None:
    """A misspelled key would silently become a case with no rubric."""
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        EvaluationCase.model_validate(
            {"id": "x", "messages": [{"role": "user", "content": "q"}], "grading_note": ["typo"]}
        )
