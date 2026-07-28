"""Detecting personal data in text (docs/SPEC.md §8, "PII and secret detection").

Pattern matching, not a model. That is a real limitation and it is chosen
deliberately: a name or an address cannot be recognised by regex, so this finds
only the *structured* identifiers — the ones with a shape. Presidio or an LLM
classifier would find more, at the cost of a large dependency or a model call on
every message.

**It warns; it never blocks.** This is a single-user learning workspace, and the
personal data most likely to appear is the user's own — pasted from a config
file, a log, or an error message they are trying to understand. Blocking that
would refuse to help someone with their own data. docs/SPEC.md §8 lists "PII must
not be copied into an approved learning without warning", and *warning* is the
operative word: the risk this addresses is durable knowledge quietly acquiring a
credential, not the user seeing their own email address.
"""

from __future__ import annotations

import re
from typing import Final, NamedTuple


class PiiPattern(NamedTuple):
    category: str
    description: str
    pattern: re.Pattern[str]


#: Ordered most to least specific. Each is a shape, not a meaning — which is why
#: `category` says what it matched rather than what it means.
PII_PATTERNS: Final[tuple[PiiPattern, ...]] = (
    PiiPattern(
        "api_key",
        "something shaped like an API key or token",
        # Provider-style prefixed keys. Deliberately narrow: a generic "long
        # random string" rule matches git hashes, UUIDs and base64 payloads, and
        # a warning that fires on every commit hash is one nobody reads.
        re.compile(r"\b(?:sk|pk|rk|api|ghp|gho|xox[bapr])[-_][A-Za-z0-9_-]{16,}\b"),
    ),
    PiiPattern(
        "private_key",
        "a private key block",
        re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |PGP )?PRIVATE KEY-----"),
    ),
    PiiPattern(
        "email",
        "an email address",
        re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),
    ),
    PiiPattern(
        "credit_card",
        "a card-shaped number",
        # 13 to 19 digits in groups. Checked by Luhn below, because without it this
        # matches order numbers, timestamps and IDs constantly.
        re.compile(r"\b(?:\d[ -]?){13,19}\b"),
    ),
    PiiPattern(
        "iban",
        "an IBAN",
        re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{10,30}\b"),
    ),
)


def _luhn(digits: str) -> bool:
    """Whether a digit string passes the Luhn checksum.

    The difference between "16 digits" and "a card number". Without it the card
    pattern fires on any long number — and a PII warning that cries wolf trains
    the user to approve past it, which is worse than not warning at all.
    """
    total = 0
    for index, char in enumerate(reversed(digits)):
        value = int(char)
        if index % 2 == 1:
            value *= 2
            if value > 9:
                value -= 9
        total += value
    return total % 10 == 0


def find_pii(text: str) -> list[str]:
    """Categories of personal data found in `text`, in the order listed above.

    Returns categories rather than the matched values on purpose: the caller
    records these in a `safety_event`, and an audit log that quotes the API key
    it found has copied the secret into a second place.
    """
    found: list[str] = []
    for category, _, pattern in PII_PATTERNS:
        for match in pattern.finditer(text):
            if category == "credit_card":
                digits = re.sub(r"\D", "", match.group())
                if not (13 <= len(digits) <= 19 and _luhn(digits)):
                    continue
            found.append(category)
            break
    return found


def describe(categories: list[str]) -> str:
    """A sentence a user can act on."""
    lookup = {pattern.category: pattern.description for pattern in PII_PATTERNS}
    described = [lookup.get(category, category) for category in categories]
    return "this text appears to contain " + ", ".join(described)
