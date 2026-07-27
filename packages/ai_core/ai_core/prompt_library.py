"""Loading versioned prompts from the top-level `prompts/` directory.

docs/SPEC.md §12: "Do not leave prompts scattered through Python files." Prompts
are lifecycle-managed *content* — name, version, status, template, variables —
so they live as files under `prompts/`, one file per version, and this module is
the only way application code reads them.

The module is `prompt_library.py` rather than a package named `prompts`
deliberately: `packages/ai_core/prompts/` must not exist, because prompt text is
content loaded at runtime and not Python source to import.

**A version is immutable.** Editing a released version in place would make every
recorded `prompt_version` a claim about text that no longer exists — and from
Phase 5 every trace carries one. A changed prompt is a new file.
"""

from __future__ import annotations

import tomllib
from enum import StrEnum
from functools import cache
from pathlib import Path
from typing import Any, Final

from pydantic import BaseModel, ConfigDict, Field

#: Where prompt files live, found by walking up from this module to the repo
#: root. An environment variable overrides it, which is what lets the backend
#: image place them elsewhere without the loader guessing.
PROMPTS_DIR_ENV_VAR: Final = "LEARNTRAIL_PROMPTS_DIR"


class PromptStatus(StrEnum):
    """docs/SPEC.md §12's lifecycle.

    Only `ACTIVE` is loadable by application code. That is the whole point of
    having states: a draft someone is still editing must not be able to reach a
    user's Learning by being the newest file on disk.
    """

    DRAFT = "draft"
    CANDIDATE = "candidate"
    ACTIVE = "active"
    RETIRED = "retired"


class PromptModelSettings(BaseModel):
    """What the prompt asks to be run with."""

    model_config = ConfigDict(frozen=True)

    #: An alias, never a provider model string (CLAUDE.md invariant #2). Kept as
    #: `str` here rather than `ModelAlias` so a prompt file naming an unknown
    #: alias fails at the call site with the alias in the message, rather than
    #: during a TOML parse that cannot say which file it was reading.
    alias: str
    max_tokens: int = Field(default=2000, gt=0)


class PromptTemplate(BaseModel):
    model_config = ConfigDict(frozen=True)

    system: str = Field(min_length=1)
    user: str = Field(min_length=1)


class Prompt(BaseModel):
    """One version of one prompt."""

    model_config = ConfigDict(frozen=True)

    name: str
    version: int = Field(gt=0)
    created_at: str
    status: PromptStatus
    purpose: str
    variables: list[str]
    model_settings: PromptModelSettings
    template: PromptTemplate

    @property
    def identifier(self) -> str:
        """What a trace or an evaluation record stores, e.g. `learning_summary@1`.

        One string rather than two columns so a record cannot carry a name
        without its version.
        """
        return f"{self.name}@{self.version}"

    def render_user(self, **values: str) -> str:
        """Fill the user template, insisting every declared variable is supplied.

        The check is the reason this method exists. `str.format` silently leaves
        an unknown placeholder as literal text, so a typo'd variable name would
        send the model the characters `{transcript}` and produce a confidently
        wrong summary of nothing — with no error anywhere.
        """
        missing = [variable for variable in self.variables if variable not in values]
        if missing:
            raise KeyError(f"{self.identifier}: missing template variable(s) {missing}")
        unexpected = [key for key in values if key not in self.variables]
        if unexpected:
            raise KeyError(f"{self.identifier}: undeclared template variable(s) {unexpected}")
        return self.template.user.format(**values)


def prompts_dir() -> Path:
    """The directory holding prompt files."""
    import os

    override = os.environ.get(PROMPTS_DIR_ENV_VAR)
    if override:
        return Path(override)
    # ai_core/prompt_library.py -> ai_core -> packages/ai_core -> packages -> repo
    return Path(__file__).resolve().parents[3] / "prompts"


@cache
def load_active(name: str) -> Prompt:
    """The active version of a prompt.

    Cached: prompt files do not change while the process runs (a new version is a
    new file, and picking it up is a deploy). Reading and parsing TOML on every
    summary would be pure overhead.

    Raises when there is no active version, rather than falling back to the
    highest-numbered file. "Newest" and "approved for use" are different claims,
    and silently substituting one for the other is how a half-written draft ends
    up generating a user's knowledge.
    """
    directory = prompts_dir() / name
    if not directory.is_dir():
        raise FileNotFoundError(f"no prompt directory for {name!r} at {directory}")

    active: list[Prompt] = []
    for path in sorted(directory.glob("v*.toml")):
        prompt = _parse(path)
        if prompt.status is PromptStatus.ACTIVE:
            active.append(prompt)

    if not active:
        raise LookupError(
            f"{name}: no version has status 'active' in {directory} "
            f"(found {[p.identifier for p in map(_parse, sorted(directory.glob('v*.toml')))]})"
        )
    if len(active) > 1:
        # Ambiguity here is not resolvable by picking one: two active versions
        # means two different prompts could have produced a given record, and
        # the recorded version would not say which.
        raise LookupError(
            f"{name}: more than one active version ({[p.identifier for p in active]}); "
            "exactly one version may be active at a time"
        )
    return active[0]


def _parse(path: Path) -> Prompt:
    """Read one prompt file, validating it into the schema."""
    raw: dict[str, Any] = tomllib.loads(path.read_text(encoding="utf-8"))
    prompt = Prompt.model_validate(raw)
    # The filename carries the version too; disagreement between the two means
    # a copied file whose `version` was not updated, which would silently
    # release the wrong text under a version number that already exists.
    if path.stem != f"v{prompt.version}":
        raise ValueError(f"{path}: filename does not match declared version {prompt.version}")
    return prompt
