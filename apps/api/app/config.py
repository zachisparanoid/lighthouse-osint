"""Application configuration.

All settings come from environment variables (a single ``.env`` drives the whole
stack). Field names are the lowercased env var names, so ``SECRET_KEY`` -> ``secret_key``.

Security posture: ``secret_key`` and ``fernet_key`` are REQUIRED with no defaults,
so the app refuses to boot if they are missing, and ``fernet_key`` is validated to be
a usable Fernet key. In production the known insecure dev secret is rejected outright.
"""
from __future__ import annotations

from functools import lru_cache

from cryptography.fernet import Fernet
from pydantic import Field, ValidationInfo, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_INSECURE_DEV_SECRET = "dev-only-insecure-change-me-please-0123456789abcdef0123456789abcdef"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ---- Core ----
    lighthouse_env: str = "development"
    log_level: str = "INFO"
    secret_key: str = Field(..., min_length=16)
    fernet_key: str = Field(...)
    access_token_ttl_seconds: int = 900
    refresh_token_ttl_seconds: int = 1_209_600
    totp_issuer: str = "Lighthouse"
    allowed_origins: str = "http://localhost:3000"

    # ---- Auth hardening ----
    max_login_attempts: int = 5
    login_lockout_seconds: int = 900
    bootstrap_admin_email: str | None = None
    bootstrap_admin_password: str | None = None

    # ---- Database ----
    database_url: str = "postgresql+asyncpg://lighthouse:lighthouse@postgres:5432/lighthouse"
    sync_database_url: str = "postgresql+psycopg://lighthouse:lighthouse@postgres:5432/lighthouse"

    # ---- Redis / Celery ----
    redis_url: str = "redis://redis:6379/0"
    celery_broker_url: str = "redis://redis:6379/1"
    celery_result_backend: str = "redis://redis:6379/2"

    # ---- Collection engine ----
    http_user_agent: str = "LighthouseOSINT/1.0 (+https://github.com/your-org/lighthouse; research use)"
    request_timeout_seconds: int = 20
    default_autoexpand_depth: int = 2
    default_node_budget: int = 250
    scope_denylist: str = "localhost,127.0.0.1,*.gov,*.mil"
    circuit_breaker_threshold: int = 5
    circuit_breaker_cooldown_seconds: int = 120

    # ---- Optional global fallback API keys (BYOK is primary) ----
    shodan_api_key: str | None = None
    hibp_api_key: str | None = None
    opencorporates_api_key: str | None = None

    # ---- Reports ----
    reports_dir: str = "/data/reports"

    # ---- derived helpers ----
    @property
    def environment(self) -> str:
        return self.lighthouse_env

    @property
    def is_production(self) -> bool:
        return self.lighthouse_env.lower() in {"production", "prod"}

    @property
    def allowed_origins_list(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]

    @property
    def scope_denylist_list(self) -> list[str]:
        return [d.strip().lower() for d in self.scope_denylist.split(",") if d.strip()]

    def global_key_for(self, service: str) -> str | None:
        """Optional process-wide fallback key for a keyed service (None forces BYOK)."""
        return {
            "shodan": self.shodan_api_key,
            "hibp": self.hibp_api_key,
            "opencorporates": self.opencorporates_api_key,
        }.get(service) or None

    # ---- validators ----
    @field_validator("fernet_key")
    @classmethod
    def _validate_fernet(cls, v: str) -> str:
        try:
            Fernet(v.encode() if isinstance(v, str) else v)
        except Exception as exc:  # noqa: BLE001
            raise ValueError(
                "FERNET_KEY is not a valid Fernet key. Generate one with: "
                "python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
            ) from exc
        return v

    @field_validator("secret_key")
    @classmethod
    def _validate_secret(cls, v: str, info: ValidationInfo) -> str:
        # We cannot see lighthouse_env reliably here (validation order), so guard in
        # `assert_production_safe()` called at startup instead. Just block the empty case.
        if not v or v.strip() == "":
            raise ValueError("SECRET_KEY must be set.")
        return v

    def assert_production_safe(self) -> None:
        """Called on startup. In production, refuse known-insecure defaults."""
        if self.is_production:
            problems = []
            if self.secret_key == _INSECURE_DEV_SECRET:
                problems.append("SECRET_KEY is still the insecure dev default.")
            if len(self.secret_key) < 32:
                problems.append("SECRET_KEY should be >= 32 chars in production.")
            if self.bootstrap_admin_password == "ChangeMe!2024":
                problems.append("BOOTSTRAP_ADMIN_PASSWORD is still the example value.")
            if problems:
                raise RuntimeError(
                    "Refusing to start in production with insecure config:\n  - "
                    + "\n  - ".join(problems)
                )


@lru_cache
def get_settings() -> Settings:
    """Cached settings singleton (env is read once)."""
    return Settings()  # type: ignore[call-arg]


settings = get_settings()
