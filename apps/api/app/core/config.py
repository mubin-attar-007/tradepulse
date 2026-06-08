"""Typed application settings, loaded from environment / `.env`.

Access via :func:`get_settings` (cached) — never instantiate ``Settings``
directly in app code so the cache and test overrides stay coherent.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- App ---
    app_env: Literal["local", "staging", "production"] = "local"
    app_name: str = "trading-platform"
    log_level: str = "INFO"
    log_json: bool = False

    # --- Security ---
    app_secret_key: str = "dev-only-change-me-please"
    cookie_secure: bool = False
    cookie_domain: str = ""
    session_ttl_seconds: int = 1_209_600  # 14 days
    broker_cred_key: str = ""  # base64 32-byte secretbox key (encrypt broker creds at rest)
    # Shared secret for the POST /internal/tick cron endpoint (worker replacement on
    # free PaaS hosts with no background process). Empty = endpoint disabled (404).
    tick_secret: str = ""

    # --- CORS (credentialed allowlist; NEVER a wildcard) ---
    cors_allow_origins: str = "http://localhost:3000"

    # --- Infra ---
    database_url: str = "postgresql+asyncpg://trading:trading@localhost:5432/trading"
    redis_url: str = "redis://localhost:6379/0"

    # --- Rate limiting ---
    rate_limit_per_minute: int = 120
    max_request_bytes: int = 2_000_000  # reject larger request bodies with 413 (DoS guard)

    # --- Observability ---
    sentry_dsn: str = ""
    metrics_enabled: bool = True
    # Bearer token required to scrape /metrics. Empty → /metrics returns 404 (fail-closed).
    metrics_token: str = ""

    # --- AI (Phase 6): both options are free — Gemini free tier, or local Ollama ---
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.0-flash"
    ollama_base_url: str = "http://localhost:11434"
    ai_default_provider: str = "gemini"  # gemini | ollama

    # --- Market data / brokers ---
    alpaca_api_key: str = ""
    alpaca_api_secret: str = ""
    market_data_timeout_seconds: float = 30.0  # bound external provider calls (anti-DoS)

    # --- Live trading (gated; real money OFF by default) ---
    live_trading_enabled: bool = False

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.cors_allow_origins.split(",") if o.strip()]

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def sync_database_url(self) -> str:
        """Alembic / sync tooling URL (psycopg-less: strip the asyncpg driver)."""
        return self.database_url.replace("+asyncpg", "")


@lru_cache
def get_settings() -> Settings:
    return Settings()
