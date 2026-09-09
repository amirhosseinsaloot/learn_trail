"""Sanitizing search results into Source value objects (ARCHITECTURE.md section 4.3, 17)."""

from collections.abc import Mapping

import pytest

from nuroli.shared_kernel.source import (
    MAX_SNIPPET_CHARS,
    MAX_TITLE_CHARS,
    MAX_URL_CHARS,
    Source,
    sanitize_sources,
)


def raw_source(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "title": "Learning transfer",
        "url": "https://www.example.org/articles/transfer?ref=1",
        "snippet": "Transfer happens when knowledge applies to a new context.",
    }
    base.update(overrides)
    return base


def test_well_formed_result_becomes_a_source_with_host_publisher() -> None:
    [source] = sanitize_sources([raw_source()])
    assert source == Source(
        title="Learning transfer",
        url="https://www.example.org/articles/transfer?ref=1",
        publisher="example.org",
        snippet="Transfer happens when knowledge applies to a new context.",
    )


def test_source_is_immutable() -> None:
    [source] = sanitize_sources([raw_source()])
    with pytest.raises(AttributeError):
        source.title = "changed"  # type: ignore[misc]


@pytest.mark.parametrize(
    "url",
    [
        "http://example.org/plain",
        "javascript:alert(1)",
        "data:text/html;base64,PHNjcmlwdD4=",
        "ftp://example.org/file",
        "example.org/no-scheme",
        "https:///missing-host",
        "https://user:secret@example.org/with-credentials",
        "not a url at all",
        "",
    ],
)
def test_non_https_or_malformed_urls_are_dropped(url: str) -> None:
    assert sanitize_sources([raw_source(url=url)]) == []


def test_url_longer_than_limit_is_dropped() -> None:
    too_long = "https://example.org/" + "a" * MAX_URL_CHARS
    assert sanitize_sources([raw_source(url=too_long)]) == []
    at_limit = "https://example.org/" + "a" * (MAX_URL_CHARS - len("https://example.org/"))
    assert len(sanitize_sources([raw_source(url=at_limit)])) == 1


@pytest.mark.parametrize("title", [None, "", "   ", 42])
def test_missing_or_blank_title_drops_the_result(title: object) -> None:
    assert sanitize_sources([raw_source(title=title)]) == []


def test_title_is_truncated_to_the_limit() -> None:
    [source] = sanitize_sources([raw_source(title="t" * (MAX_TITLE_CHARS + 50))])
    assert len(source.title) == MAX_TITLE_CHARS


def test_snippet_is_truncated_and_missing_snippet_becomes_empty() -> None:
    [long_snippet] = sanitize_sources([raw_source(snippet="s" * (MAX_SNIPPET_CHARS + 1))])
    assert len(long_snippet.snippet) == MAX_SNIPPET_CHARS
    [no_snippet] = sanitize_sources([raw_source(snippet=None)])
    assert no_snippet.snippet == ""
    [non_text] = sanitize_sources([raw_source(snippet=["x"])])
    assert non_text.snippet == ""


def test_surrounding_whitespace_is_stripped_before_limits_apply() -> None:
    [source] = sanitize_sources(
        [raw_source(title="  padded  ", snippet="\n text \n", url="  https://example.org/x ")]
    )
    assert (source.title, source.snippet, source.url) == ("padded", "text", "https://example.org/x")


def test_private_hosts_are_allowed_when_https() -> None:
    [source] = sanitize_sources([raw_source(url="https://10.0.0.5:8443/internal")])
    assert source.publisher == "10.0.0.5"


def test_duplicate_urls_keep_the_first_result_only() -> None:
    first = raw_source(title="first")
    second = raw_source(title="second")
    third = raw_source(title="third", url="https://example.org/other")
    result = sanitize_sources([first, second, third])
    assert [source.title for source in result] == ["first", "third"]


def test_order_is_preserved_and_bad_entries_are_skipped_in_place() -> None:
    entries: list[Mapping[str, object]] = [
        raw_source(title="a", url="https://a.example/"),
        {"not": "a source"},
        raw_source(title="b", url="https://b.example/"),
    ]
    assert [source.title for source in sanitize_sources(entries)] == ["a", "b"]


def test_no_results_gives_no_sources() -> None:
    assert sanitize_sources([]) == []
