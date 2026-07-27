"""Contract for the prompt library (docs/SPEC.md §12).

Pure file loading — no model, no database. Most of these assert *refusals*,
because the loader's job is less "find a prompt" than "refuse to run text nobody
approved".
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ai_core.prompt_library import (
    Prompt,
    PromptStatus,
    _parse,
    load_active,
    prompts_dir,
)

VALID = """
name = "example"
version = 1
created_at = "2026-07-27"
status = "{status}"
purpose = "A test prompt."
variables = ["thing"]

[model_settings]
alias = "learning-fast"

[template]
system = "You are terse."
user = "Describe {{thing}}."
"""


def _write(directory: Path, version: int, status: str = "active") -> Path:
    path = directory / f"v{version}.toml"
    path.write_text(VALID.format(status=status).replace("version = 1", f"version = {version}"))
    return path


# --- the real prompt shipped in the repo ---------------------------------------


def test_the_learning_summary_prompt_loads_and_is_active() -> None:
    """The prompt Phase 3 actually runs. Asserted here so a malformed edit fails
    in a fast unit test rather than on the first summary someone requests."""
    prompt = load_active("learning_summary")

    assert prompt.identifier == "learning_summary@1"
    assert prompt.status is PromptStatus.ACTIVE
    # An alias, never a provider model string (CLAUDE.md invariant #2).
    assert prompt.model_settings.alias == "learning-deep"
    assert prompt.variables == ["transcript"]


def test_the_prompts_directory_resolves_to_the_repo_root() -> None:
    # The loader walks up from the installed package. If that arithmetic is ever
    # wrong the failure is a confusing FileNotFoundError at call time.
    assert prompts_dir().name == "prompts"
    assert (prompts_dir() / "learning_summary").is_dir()


# --- rendering -----------------------------------------------------------------


def test_rendering_substitutes_the_declared_variable() -> None:
    prompt = load_active("learning_summary")
    rendered = prompt.render_user(transcript="a conversation")

    assert "{transcript}" not in rendered
    assert "a conversation" in rendered


def test_a_missing_variable_raises_rather_than_rendering_a_placeholder() -> None:
    """The failure this prevents is silent and expensive.

    `str.format` leaves an unmatched placeholder as literal text, so without this
    check the model would receive the characters "{transcript}" and confidently
    summarise nothing at all — a well-formed answer to no question.
    """
    prompt = load_active("learning_summary")
    with pytest.raises(KeyError, match="missing template variable"):
        prompt.render_user()


def test_an_undeclared_variable_raises() -> None:
    # Catches the rename half of the same mistake: the template was updated, the
    # caller was not, and nothing would otherwise say so.
    prompt = load_active("learning_summary")
    with pytest.raises(KeyError, match="undeclared template variable"):
        prompt.render_user(transcript="x", extra="y")


# --- lifecycle -----------------------------------------------------------------


def test_only_an_active_version_is_loadable(
    tmp_path: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A draft must not reach a user's Learning by being the newest file.

    "Newest" and "approved for use" are different claims, and the loader refuses
    to substitute one for the other.
    """
    root = Path(str(tmp_path))
    directory = root / "example"
    directory.mkdir(parents=True)
    _write(directory, 1, status="retired")
    _write(directory, 2, status="draft")

    monkeypatch.setenv("LEARNTRAIL_PROMPTS_DIR", str(root))
    load_active.cache_clear()

    with pytest.raises(LookupError, match="no version has status 'active'"):
        load_active("example")


def test_two_active_versions_are_an_error_not_a_choice(
    tmp_path: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Ambiguity here is not resolvable by picking one.

    Two active versions means a recorded `prompt_version` cannot say which text
    produced a given summary — so the loader refuses rather than guessing.
    """
    root = Path(str(tmp_path))
    directory = root / "example"
    directory.mkdir(parents=True)
    _write(directory, 1)
    _write(directory, 2)

    monkeypatch.setenv("LEARNTRAIL_PROMPTS_DIR", str(root))
    load_active.cache_clear()

    with pytest.raises(LookupError, match="more than one active version"):
        load_active("example")


def test_an_unknown_prompt_names_the_path_it_looked_in(
    tmp_path: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LEARNTRAIL_PROMPTS_DIR", str(tmp_path))
    load_active.cache_clear()

    with pytest.raises(FileNotFoundError, match="no prompt directory"):
        load_active("nonexistent")


def test_a_filename_that_disagrees_with_its_version_is_rejected(tmp_path: Path) -> None:
    """Catches a copied file whose `version` was never updated — which would
    release different text under a version number that already exists, silently
    invalidating every record that cites it."""
    path = tmp_path / "v7.toml"
    path.write_text(VALID.format(status="active"))  # declares version = 1

    with pytest.raises(ValueError, match="does not match declared version"):
        _parse(path)


def test_a_prompt_missing_a_required_field_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "v1.toml"
    path.write_text('name = "x"\nversion = 1\n')

    with pytest.raises(ValueError):
        _parse(path)


def test_identifier_carries_name_and_version_together() -> None:
    """One string, so a record cannot store a name without its version."""
    prompt = Prompt.model_validate(
        {
            "name": "example",
            "version": 3,
            "created_at": "2026-07-27",
            "status": "active",
            "purpose": "p",
            "variables": [],
            "model_settings": {"alias": "learning-fast"},
            "template": {"system": "s", "user": "u"},
        }
    )
    assert prompt.identifier == "example@3"
