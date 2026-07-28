"""Estimating what a model call cost (docs/SPEC.md §17, `model_run.estimated_cost`).

**Estimated is the operative word, and it is the column's name for a reason.**
This is a local price table, not a bill. It will drift from what the provider
actually charges the moment prices change, and it knows nothing about cached
input tokens, batch discounts or the provider's own rounding. What it is good for
is the question the Phase 5 criterion actually asks — "was this answer expensive
as well as poor" — and for noticing that a routing change tripled the bill.

**An unknown model costs `None`, never `0`.** A zero would be a claim that the
call was free, and it would silently deflate every total that summed it. `None`
says "not priced here", which is the truth and which a query can filter on.

Keyed by the *provider* model, not the alias: the alias is a role and its
provider model changes underneath it (that is the point of infra/litellm's
indirection), so pricing by alias would quietly misprice the moment one is
repointed. It also means adding a provider to the gateway config and forgetting
to price it produces `None` rather than the previous model's price.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Final

#: USD per million tokens, (input, output). Current as of 2026-07-28 for the
#: models infra/litellm/config.yaml configures. Prefixes, not exact ids, because
#: providers append dated suffixes (`gpt-4o-mini-2024-07-18`) and pinning the
#: full string would silently stop matching on the next snapshot.
PRICES: Final[dict[str, tuple[Decimal, Decimal]]] = {
    "gpt-4o-mini": (Decimal("0.15"), Decimal("0.60")),
    "gpt-4o": (Decimal("2.50"), Decimal("10.00")),
}

_PER_MILLION: Final = Decimal(1_000_000)


def estimate_cost(provider_model: str, input_tokens: int, output_tokens: int) -> Decimal | None:
    """What this call probably cost in USD, or `None` if the model is not priced.

    Longest-prefix match, so `gpt-4o-mini-2024-07-18` prices as `gpt-4o-mini`
    rather than as `gpt-4o` — which a shortest or first match would get wrong, and
    wrong by a factor of sixteen.
    """
    matches = [key for key in PRICES if provider_model.startswith(key)]
    if not matches:
        return None
    input_price, output_price = PRICES[max(matches, key=len)]
    return (input_price * input_tokens + output_price * output_tokens) / _PER_MILLION
