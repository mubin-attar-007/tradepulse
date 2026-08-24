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
    # Signs research-graph approval tokens (app/modules/ai/graph/approval.py),
    # which are an HMAC over the strategy hash, dataset fingerprint, plan hash and
    # risk-policy version. Rotating this key invalidates every outstanding
    # approval — which is the correct behaviour, but is a real operational effect
    # rather than the no-op an earlier comment here claimed.
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
    # Base URL of the deployed frontend (used to build password-reset links in email).
    frontend_url: str = "http://localhost:3000"

    # --- Email for password reset (unset => link is logged; set for real Gmail SMTP delivery) ---
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_user: str = ""  # Gmail address — enables real delivery
    smtp_password: str = ""  # Google App Password (16 chars) — see .env.example
    email_from: str = ""  # From-address; defaults to smtp_user

    # --- Infra ---
    database_url: str = "postgresql+asyncpg://trading:trading@localhost:5432/trading"
    redis_url: str = "redis://localhost:6379/0"

    # --- Rate limiting ---
    rate_limit_per_minute: int = 120
    max_request_bytes: int = 2_000_000  # reject larger request bodies with 413 (DoS guard)
    # X-Forwarded-For is attacker-controlled unless a proxy WE control appended the
    # value we read, so it is trusted only when explicitly switched on. Default OFF:
    # locally (and in tests) the socket peer IS the client, and trusting the header
    # there would hand every caller an unlimited rate-limit budget for free.
    trust_proxy_headers: bool = False
    # How many proxies sit between the internet and this process. The client IP is
    # the Nth-from-the-right XFF entry, because each trusted hop appends the address
    # it received the request from; everything to the LEFT of that is client-supplied.
    # 1 = a single reverse proxy (Caddy / Render / HF Spaces). 2 = e.g. Cloudflare -> Caddy.
    trusted_proxy_hops: int = 1

    # --- Observability ---
    sentry_dsn: str = ""
    metrics_enabled: bool = True
    # Bearer token required to scrape /metrics. Empty → /metrics returns 404 (fail-closed).
    metrics_token: str = ""

    # --- AI (Phase 6): both options are free — Gemini free tier, or local Ollama ---
    # --- AI ------------------------------------------------------------------
    # Local-FIRST by default. The chain is tried in order; a profile whose
    # credential is missing is skipped rather than failing the request, so a fresh
    # clone with no keys still has a working AI surface (the deterministic
    # compiler) instead of a 500.
    ai_profile_chain_raw: str = "local-balanced,local-small,deterministic"
    # Hard policy, not a preference: when true, no request may leave the machine,
    # whatever else is configured. Research prompts contain the user's own ideas.
    ai_local_only: bool = False
    ai_timeout_seconds: float = 180.0
    # Ceiling on ONE request, so a runaway loop cannot spend the daily budget.
    ai_max_tokens_per_request: int = 4096
    # Bounded repair. Measured: a local 3B model converges (4 -> 3 -> 1 errors)
    # but does not always finish inside two rounds, so an operator running a small
    # local model may raise this, trading latency for first-pass success.
    ai_max_repairs: int = 2
    ai_daily_user_tokens: int = 200_000
    ai_daily_global_tokens: int = 5_000_000

    # Ollama (local). `ollama_model` overrides whatever the profile names, so an
    # operator who pulled a different model does not have to edit code.
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = ""

    # Any OpenAI-compatible endpoint: llama.cpp, LM Studio, vLLM, Groq, OpenRouter.
    ai_openai_base_url: str = ""
    ai_openai_api_key: str = ""
    ai_openai_model: str = ""
    # Whether that endpoint is on this machine. Governs the local-only policy, so
    # it must be declared rather than guessed from the URL.
    ai_openai_is_local: bool = False

    # Gemini (remote, optional).
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.0-flash"

    # --- Market data / brokers ---
    alpaca_api_key: str = ""
    alpaca_api_secret: str = ""
    market_data_timeout_seconds: float = 30.0  # bound external provider calls (anti-DoS)

    # --- Live trading (gated; real money OFF by default) ---
    live_trading_enabled: bool = False

    def model_post_init(self, _context: object) -> None:
        """Shout about production settings that silently break a user-facing flow.

        These are not crash-worthy (the app runs fine; the *user* is the one who
        loses), which is exactly why they go unnoticed — a reset link pointing at
        localhost and an unconfigured SMTP look identical to "working" from the
        operator's side. Emitting them at import time puts them in the first page
        of the deploy log, next to the startup line.
        """
        problems = self.production_config_warnings()
        if not problems:
            return
        from app.core.logging import get_logger  # deferred: logging imports this module

        logger = get_logger("config")
        for problem in problems:
            logger.warning("insecure_production_config", problem=problem)

    def production_config_warnings(self) -> list[str]:
        """Production misconfigurations worth shouting about (empty outside production)."""
        if not self.is_production:
            return []
        problems: list[str] = []
        if "localhost" in self.frontend_url or "127.0.0.1" in self.frontend_url:
            problems.append(
                f"FRONTEND_URL is still {self.frontend_url!r}: password-reset emails will "
                "link to localhost and be unusable. Set it to the deployed web origin."
            )
        if not self.smtp_user or not self.smtp_password:
            problems.append(
                "SMTP_USER/SMTP_PASSWORD are unset: no password-reset email can be sent. "
                "The reset link is written to the application log instead, which means "
                "reset is broken for users and live tokens land in your log store."
            )
        if self.metrics_enabled and not self.metrics_token:
            problems.append(
                "METRICS_ENABLED is on but METRICS_TOKEN is empty: /metrics is fail-closed "
                "(404), so nothing can scrape it. Set METRICS_TOKEN or disable metrics."
            )
        if not self.cookie_secure:
            problems.append(
                "COOKIE_SECURE is false in production: session cookies are sent over plain HTTP."
            )
        return problems

    @property
    def ai_profile_chain(self) -> list[str]:
        return [name.strip() for name in self.ai_profile_chain_raw.split(",") if name.strip()]

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
