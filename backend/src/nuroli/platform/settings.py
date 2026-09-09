"""Application settings: every ``NUROLI_*`` variable from ARCHITECTURE.md
section 16, typed, defaulted, and validated once at start.

Nothing else reads the environment. Secrets are ``SecretStr`` so ``repr`` and
logs never show them; ``load_settings`` turns validation failures into one
``SettingsError`` that lists every problem with its variable name.
"""

import ipaddress
import json
from typing import Annotated, Literal, Self
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, ValidationError, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

ENV_PREFIX = "NUROLI_"
MIN_SECRET_KEY_CHARS = 32
DATABASE_SCHEME = "postgresql+asyncpg://"


class SettingsError(Exception):
    """Configuration is invalid; ``problems`` lists every issue found."""

    def __init__(self, problems: list[str]) -> None:
        self.problems = problems
        lines = "\n".join(f"  - {problem}" for problem in problems)
        super().__init__(f"configuration invalid ({len(problems)} problem(s)):\n{lines}")


def _http_url(value: str, name: str) -> str:
    parsed = urlsplit(value.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError(f"{name} must be an http or https URL with a host")
    return value.strip().rstrip("/")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix=ENV_PREFIX,
        env_ignore_empty=True,
        extra="ignore",
        frozen=True,
        protected_namespaces=(),
    )

    # Required at start
    public_origin: str
    secret_key: SecretStr
    database_url: SecretStr
    model_base_url: str
    model_name: str = Field(min_length=1)

    # Model connection (section 11.1)
    model_api_key: SecretStr = SecretStr("")
    model_timeout_seconds: int = Field(default=120, gt=0)
    model_first_token_timeout_seconds: int = Field(default=30, gt=0)
    model_max_output_tokens: int = Field(default=2048, gt=0)
    # NoDecode: the raw string reaches the validator below, not pydantic-settings' JSON parser.
    model_extra_headers: Annotated[dict[str, str], NoDecode] = Field(default_factory=dict)

    # Web research (R-07, R-08)
    search_provider: Literal["none", "tavily"] = "none"
    tavily_api_key: SecretStr = SecretStr("")
    tavily_base_url: str = "https://api.tavily.com"

    # Google sign-in
    google_client_id: str = ""
    google_client_secret: SecretStr = SecretStr("")

    # Accounts and sessions (R-14, R-35)
    registration_open: bool = True
    session_ttl_days: int = Field(default=30, gt=0)
    session_cookie_secure: bool = True

    # Limits (R-21)
    max_concurrent_streams_per_user: int = Field(default=1, gt=0)
    max_replies_per_hour: int = Field(default=60, gt=0)
    max_searches_per_hour: int = Field(default=30, gt=0)
    context_budget_chars: int = Field(default=24_000, gt=0)
    max_request_body_bytes: int = Field(default=65_536, gt=0)

    # Logging (section 19)
    log_level: Literal["debug", "info", "warning", "error"] = "info"
    log_format: Literal["json", "text"] = "json"
    trusted_proxy_cidr: str = "172.16.0.0/12"

    @field_validator("public_origin")
    @classmethod
    def _origin_has_no_path(cls, value: str) -> str:
        origin = _http_url(value, "public origin")
        parsed = urlsplit(origin)
        if parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
            raise ValueError("public origin must be scheme and host only, without a path")
        return origin

    @field_validator("model_base_url")
    @classmethod
    def _model_url(cls, value: str) -> str:
        return _http_url(value, "model base URL")

    @field_validator("tavily_base_url")
    @classmethod
    def _tavily_url(cls, value: str) -> str:
        return _http_url(value, "Tavily base URL")

    @field_validator("secret_key")
    @classmethod
    def _secret_key_length(cls, value: SecretStr) -> SecretStr:
        if len(value.get_secret_value()) < MIN_SECRET_KEY_CHARS:
            raise ValueError(f"secret key must have at least {MIN_SECRET_KEY_CHARS} characters")
        return value

    @field_validator("database_url")
    @classmethod
    def _database_url_shape(cls, value: SecretStr) -> SecretStr:
        raw = value.get_secret_value()
        parsed = urlsplit(raw)
        if not raw.startswith(DATABASE_SCHEME) or not parsed.hostname or parsed.path in {"", "/"}:
            raise ValueError(
                f"database URL must look like {DATABASE_SCHEME}user:password@host:5432/dbname"
            )
        return value

    @field_validator("model_extra_headers", mode="before")
    @classmethod
    def _headers_from_json(cls, value: object) -> object:
        if isinstance(value, str):
            if not value.strip():
                return {}
            try:
                value = json.loads(value)
            except ValueError as error:
                raise ValueError("extra headers must be a JSON object of strings") from error
        if not isinstance(value, dict) or not all(
            isinstance(key, str) and isinstance(item, str) for key, item in value.items()
        ):
            raise ValueError("extra headers must be a JSON object of strings")
        return value

    @field_validator("trusted_proxy_cidr")
    @classmethod
    def _cidr(cls, value: str) -> str:
        try:
            ipaddress.ip_network(value, strict=False)
        except ValueError as error:
            raise ValueError("trusted proxy CIDR must be an IPv4 or IPv6 network") from error
        return value

    @model_validator(mode="after")
    def _cross_field_rules(self) -> Self:
        problems: list[str] = []
        if self.search_provider == "tavily" and not self.tavily_api_key.get_secret_value():
            problems.append("NUROLI_SEARCH_PROVIDER=tavily requires NUROLI_TAVILY_API_KEY")
        if bool(self.google_client_id) != bool(self.google_client_secret.get_secret_value()):
            problems.append(
                "NUROLI_GOOGLE_CLIENT_ID and NUROLI_GOOGLE_CLIENT_SECRET must be set together"
            )
        if self.model_first_token_timeout_seconds > self.model_timeout_seconds:
            problems.append(
                "NUROLI_MODEL_FIRST_TOKEN_TIMEOUT_SECONDS cannot exceed "
                "NUROLI_MODEL_TIMEOUT_SECONDS"
            )
        if problems:
            raise ValueError("; ".join(problems))
        return self

    @property
    def model_host(self) -> str:
        return urlsplit(self.model_base_url).hostname or ""

    @property
    def google_enabled(self) -> bool:
        return bool(self.google_client_id)

    @property
    def research_enabled(self) -> bool:
        return self.search_provider == "tavily"

    def secret_values(self) -> list[str]:
        """Secrets the log formatter must never print."""
        values = [
            self.secret_key.get_secret_value(),
            self.database_url.get_secret_value(),
            self.model_api_key.get_secret_value(),
            self.tavily_api_key.get_secret_value(),
            self.google_client_secret.get_secret_value(),
        ]
        password = urlsplit(self.database_url.get_secret_value()).password
        if password:
            values.append(password)
        return [value for value in values if value]


def _problem_lines(error: ValidationError) -> list[str]:
    lines: list[str] = []
    for item in error.errors():
        location = item["loc"]
        message = item["msg"].removeprefix("Value error, ")
        if location:
            lines.append(f"{ENV_PREFIX}{str(location[0]).upper()}: {message}")
        else:
            lines.extend(part.strip() for part in message.split(";"))
    return lines


def load_settings(**overrides: object) -> Settings:
    """Read the environment once; raise SettingsError listing every problem."""
    try:
        return Settings(**overrides)  # type: ignore[arg-type]
    except ValidationError as error:
        raise SettingsError(_problem_lines(error)) from None
