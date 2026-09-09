"""``Source`` value object and the sanitizer that admits search results.

Limits and rules come from ARCHITECTURE.md sections 4.3 and 17: https only,
bounded lengths, publisher derived from the host, first occurrence of a URL
wins. Pure functions, no I/O.
"""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from urllib.parse import SplitResult, urlsplit

MAX_TITLE_CHARS = 300
MAX_URL_CHARS = 2048
MAX_SNIPPET_CHARS = 500


@dataclass(frozen=True, slots=True)
class Source:
    title: str
    url: str
    publisher: str
    snippet: str


def sanitize_sources(raw: Iterable[Mapping[str, object]]) -> list[Source]:
    """Keep well-formed https results in order; drop the rest silently."""
    sources: list[Source] = []
    seen_urls: set[str] = set()
    for entry in raw:
        source = _sanitize_one(entry)
        if source is None or source.url in seen_urls:
            continue
        seen_urls.add(source.url)
        sources.append(source)
    return sources


def _sanitize_one(entry: Mapping[str, object]) -> Source | None:
    title = _text(entry.get("title"))[:MAX_TITLE_CHARS]
    url = _text(entry.get("url"))
    if not title or not url or len(url) > MAX_URL_CHARS:
        return None
    parsed = _parse_https_url(url)
    if parsed is None or parsed.hostname is None:
        return None
    return Source(
        title=title,
        url=url,
        publisher=_publisher(parsed.hostname),
        snippet=_text(entry.get("snippet"))[:MAX_SNIPPET_CHARS],
    )


def _text(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def _parse_https_url(url: str) -> SplitResult | None:
    try:
        parsed = urlsplit(url)
    except ValueError:
        return None
    # Only https, with a host and without embedded credentials (section 17).
    if parsed.scheme != "https" or not parsed.hostname or parsed.username is not None:
        return None
    return parsed


def _publisher(hostname: str) -> str:
    return hostname.removeprefix("www.")
