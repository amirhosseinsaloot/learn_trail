"""Settings validation (ARCHITECTURE.md section 16): typed, defaulted, fail fast."""

import pytest
from tests.conftest import TEST_ENVIRONMENT

from nuroli.platform.settings import Settings, SettingsError, load_settings


def clear_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in TEST_ENVIRONMENT:
        monkeypatch.delenv(key, raising=False)


def test_valid_environment_loads_with_documented_defaults() -> None:
    settings = load_settings()
    assert settings.model_name == "fake-model"
    assert settings.model_host == "localhost"
    assert settings.search_provider == "none"
    assert settings.registration_open is True
    assert settings.session_ttl_days == 30
    assert settings.session_cookie_secure is True
    assert settings.max_concurrent_streams_per_user == 1
    assert settings.max_replies_per_hour == 60
    assert settings.max_searches_per_hour == 30
    assert settings.model_max_output_tokens == 2048
    assert settings.context_budget_chars == 24_000
    assert settings.max_request_body_bytes == 65_536
    assert settings.model_timeout_seconds == 120
    assert settings.model_first_token_timeout_seconds == 30
    assert settings.log_format == "json"
    assert settings.trusted_proxy_cidr == "172.16.0.0/12"
    assert settings.tavily_base_url == "https://api.tavily.com"
    assert settings.model_extra_headers == {}


def test_missing_required_variables_are_all_listed(monkeypatch: pytest.MonkeyPatch) -> None:
    clear_environment(monkeypatch)
    with pytest.raises(SettingsError) as raised:
        load_settings()
    problems = "\n".join(raised.value.problems)
    for name in [
        "NUROLI_PUBLIC_ORIGIN",
        "NUROLI_SECRET_KEY",
        "NUROLI_DATABASE_URL",
        "NUROLI_MODEL_BASE_URL",
        "NUROLI_MODEL_NAME",
    ]:
        assert name in problems
    assert len(raised.value.problems) == 5


def test_empty_value_counts_as_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NUROLI_MODEL_BASE_URL", "")
    with pytest.raises(SettingsError) as raised:
        load_settings()
    assert raised.value.problems == ["NUROLI_MODEL_BASE_URL: Field required"]


@pytest.mark.parametrize(
    ("name", "value", "fragment"),
    [
        ("NUROLI_PUBLIC_ORIGIN", "localhost:8080", "http or https URL"),
        ("NUROLI_PUBLIC_ORIGIN", "https://nuroli.example/app", "without a path"),
        ("NUROLI_MODEL_BASE_URL", "ftp://models.example/v1", "http or https URL"),
        ("NUROLI_MODEL_BASE_URL", "http:///v1", "http or https URL"),
        ("NUROLI_TAVILY_BASE_URL", "api.tavily.com", "http or https URL"),
        ("NUROLI_SECRET_KEY", "too-short", "at least 32 characters"),
        ("NUROLI_DATABASE_URL", "postgresql://nuroli:x@db:5432/nuroli", "postgresql+asyncpg://"),
        ("NUROLI_DATABASE_URL", "postgresql+asyncpg://nuroli:x@db:5432/", "postgresql+asyncpg://"),
        ("NUROLI_MODEL_EXTRA_HEADERS", "not json", "JSON object of strings"),
        ("NUROLI_MODEL_EXTRA_HEADERS", '{"x": 1}', "JSON object of strings"),
        ("NUROLI_TRUSTED_PROXY_CIDR", "not-a-network", "IPv4 or IPv6 network"),
        ("NUROLI_LOG_LEVEL", "verbose", "Input should be"),
        ("NUROLI_LOG_FORMAT", "yaml", "Input should be"),
        ("NUROLI_SEARCH_PROVIDER", "bing", "Input should be"),
        ("NUROLI_SESSION_TTL_DAYS", "0", "greater than 0"),
        ("NUROLI_MAX_REPLIES_PER_HOUR", "-1", "greater than 0"),
        ("NUROLI_MAX_REQUEST_BODY_BYTES", "0", "greater than 0"),
        ("NUROLI_MODEL_TIMEOUT_SECONDS", "0", "greater than 0"),
        ("NUROLI_MODEL_MAX_OUTPUT_TOKENS", "0", "greater than 0"),
        ("NUROLI_CONTEXT_BUDGET_CHARS", "0", "greater than 0"),
        ("NUROLI_MAX_CONCURRENT_STREAMS_PER_USER", "0", "greater than 0"),
        ("NUROLI_MAX_SEARCHES_PER_HOUR", "0", "greater than 0"),
        ("NUROLI_REGISTRATION_OPEN", "maybe", "Input should be a valid boolean"),
    ],
)
def test_invalid_value_is_rejected_with_its_variable_name(
    monkeypatch: pytest.MonkeyPatch, name: str, value: str, fragment: str
) -> None:
    monkeypatch.setenv(name, value)
    with pytest.raises(SettingsError) as raised:
        load_settings()
    assert len(raised.value.problems) == 1
    assert raised.value.problems[0].startswith(f"{name}: ")
    assert fragment in raised.value.problems[0]


def test_tavily_provider_without_key_names_both_variables(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NUROLI_SEARCH_PROVIDER", "tavily")
    with pytest.raises(SettingsError) as raised:
        load_settings()
    assert raised.value.problems == ["NUROLI_SEARCH_PROVIDER=tavily requires NUROLI_TAVILY_API_KEY"]


def test_tavily_provider_with_key_enables_research(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NUROLI_SEARCH_PROVIDER", "tavily")
    monkeypatch.setenv("NUROLI_TAVILY_API_KEY", "tvly-test-only-key")
    assert load_settings().research_enabled is True


def test_google_variables_must_be_set_together(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NUROLI_GOOGLE_CLIENT_ID", "client-id.apps.googleusercontent.com")
    with pytest.raises(SettingsError) as raised:
        load_settings()
    assert "NUROLI_GOOGLE_CLIENT_ID and NUROLI_GOOGLE_CLIENT_SECRET" in raised.value.problems[0]
    monkeypatch.setenv("NUROLI_GOOGLE_CLIENT_SECRET", "test-only-google-secret")
    assert load_settings().google_enabled is True


def test_first_token_timeout_cannot_exceed_total_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NUROLI_MODEL_FIRST_TOKEN_TIMEOUT_SECONDS", "200")
    with pytest.raises(SettingsError) as raised:
        load_settings()
    assert "cannot exceed" in raised.value.problems[0]


def test_cross_field_problems_are_reported_together(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NUROLI_SEARCH_PROVIDER", "tavily")
    monkeypatch.setenv("NUROLI_GOOGLE_CLIENT_ID", "only-the-id")
    with pytest.raises(SettingsError) as raised:
        load_settings()
    assert len(raised.value.problems) == 2


def test_urls_are_normalised_and_headers_parsed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NUROLI_MODEL_BASE_URL", "http://host.docker.internal:11434/v1/")
    monkeypatch.setenv("NUROLI_PUBLIC_ORIGIN", "https://nuroli.example/")
    monkeypatch.setenv("NUROLI_MODEL_EXTRA_HEADERS", '{"HTTP-Referer": "https://nuroli.example"}')
    settings = load_settings()
    assert settings.model_base_url == "http://host.docker.internal:11434/v1"
    assert settings.public_origin == "https://nuroli.example"
    assert settings.model_extra_headers == {"HTTP-Referer": "https://nuroli.example"}


def test_repr_and_str_never_contain_secrets(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NUROLI_MODEL_API_KEY", "sk-test-only-model-key")
    settings = load_settings()
    rendered = repr(settings) + str(settings) + repr(settings.model_dump())
    for secret in settings.secret_values():
        assert secret not in rendered
    assert "sk-test-only-model-key" not in rendered
    assert "test-only-db-password" not in rendered


def test_secret_values_include_the_database_password() -> None:
    settings = load_settings()
    assert "test-only-db-password" in settings.secret_values()
    assert isinstance(settings, Settings)
