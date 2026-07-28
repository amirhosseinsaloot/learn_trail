"""What one model call cost and how it went (docs/SPEC.md §17, Phase 5).

The domain shape of a `model_run` row, defined here rather than in `database` for
the same reason every other schema is: `ai_core` produces these facts and must
not import persistence to describe them. The endpoint translates one of these
into a row, field for field.

**Recorded whether or not the answer survived.** A blocked answer still burned
tokens, and a run table that only recorded successes would understate spend by
exactly the amount spent on the answers nobody got.
"""

from __future__ import annotations

from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from ai_core.models.aliases import ModelAlias


class RunStatus(StrEnum):
    """How the call ended.

    `BLOCKED` is separate from `ERROR` on purpose: both produced no usable
    answer, but one is the safety pipeline working and the other is a failure,
    and an operator reading a spike of one would draw the wrong conclusion from
    the other.
    """

    OK = "ok"
    ERROR = "error"
    BLOCKED = "blocked"


class ModelRun(BaseModel):
    """One call through the gateway, as it will be recorded."""

    model_config = ConfigDict(frozen=True)

    #: Which model call this was: `chat.answer`, `summary.generate`,
    #: `safety.judge`. Distinguishes the three reasons this system spends money.
    operation: str = Field(min_length=1)

    #: The trace this happened inside, as 32 hex characters — the join between a
    #: row in the database and the trace that explains it. `None` when the call
    #: ran untraced, which is possible in tests and must not be faked.
    trace_id: str | None = None

    alias: ModelAlias
    #: What actually served it. Both are recorded because both change
    #: independently, and a run that knew only one could answer neither
    #: "what did this role cost" nor "which model got slower".
    provider_model: str

    #: The exact prompt that produced it, e.g. `learning_summary@1`. `None` for
    #: the chat path, which has no prompt version until the prompt library covers
    #: it — recorded as absent rather than as an invented default.
    prompt_version: str | None = None

    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    #: `None` when the provider model is not in the local price table. See
    #: ai_core/models/pricing.py: an unpriced call is not a free call.
    estimated_cost: Decimal | None = None
    latency_ms: int = Field(ge=0)
    status: RunStatus = RunStatus.OK
