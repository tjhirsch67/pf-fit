"""Application configuration via pydantic-settings.

All runtime configuration is read from environment variables (loaded from a local
`.env` during development; injected by Railway in production). Import the singleton
`settings` rather than reading `os.environ` directly so every module sees the same
normalized values.
"""

from functools import lru_cache
from typing import List

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ─── Database ────────────────────────────────────────────────────────────
    database_url: str = ""

    # ─── Auth ────────────────────────────────────────────────────────────────
    secret_key: str = "change-this-secret"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 43200  # 30 days

    # ─── Anthropic ─────────────────────────────────────────────────────────────
    anthropic_api_key: str = ""

    # ─── Email (Mailtrap HTTP API) ─────────────────────────────────────────────
    mailtrap_api_token: str = ""
    from_email: str = "coach@pf-coach.app"
    from_name: str = "PF Coach"

    # ─── App ───────────────────────────────────────────────────────────────────
    app_env: str = "development"
    cors_origins: str = "*"

    @property
    def cors_origins_list(self) -> List[str]:
        """CORS origins as a list. `*` (or empty) means allow all."""
        raw = (self.cors_origins or "").strip()
        if not raw or raw == "*":
            return ["*"]
        return [o.strip() for o in raw.split(",") if o.strip()]

    @property
    def normalized_database_url(self) -> str:
        """Railway sometimes provides `postgres://`; SQLAlchemy needs `postgresql://`."""
        url = self.database_url or ""
        if url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql://", 1)
        return url


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
