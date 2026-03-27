"""
Centralized application configuration.

All secrets and tunables are loaded from environment variables via Pydantic Settings.
The application will REFUSE TO START if required secrets are missing.
"""

from functools import lru_cache
from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables.

    Required env vars (no defaults — app crashes on startup if missing):
        - AUTH_SECRET_KEY
        - DOWNLOAD_TOKEN_SECRET_KEY

    Optional env vars (safe defaults provided):
        - DATABASE_URL
        - REDIS_URL
        - CORS_ORIGINS
        - MAX_STORAGE_BYTES
        - CHUNK_SIZE_BYTES
        - RATE_LIMIT_CAPACITY
        - RATE_LIMIT_REFILL_RATE
        - DOWNLOAD_TOKEN_EXPIRE_MINUTES
        - AUTH_TOKEN_EXPIRE_MINUTES
    """

    # ── Secrets (NO defaults — will crash if missing) ─────────────────────
    auth_secret_key: str = Field(..., description="JWT secret for auth tokens")
    download_token_secret_key: str = Field(..., description="JWT secret for download tokens")
    jwt_algorithm: str = Field(default="HS256")

    # ── Infrastructure ────────────────────────────────────────────────────
    database_url: str = Field(
        default="postgresql+asyncpg://postgres:postgrespassword@db:5432/mycloud"
    )
    redis_url: str = Field(default="redis://redis:6379/0")

    # ── CORS ──────────────────────────────────────────────────────────────
    cors_origins: str = Field(
        default="http://localhost:5173",
        description="Comma-separated list of allowed CORS origins"
    )

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    # ── Storage ───────────────────────────────────────────────────────────
    max_storage_bytes: int = Field(
        default=5 * 1024 * 1024 * 1024,  # 5 GB
        description="Maximum storage per user in bytes"
    )
    chunk_size_bytes: int = Field(
        default=5 * 1024 * 1024,  # 5 MB
        description="Maximum allowed chunk size in bytes"
    )

    # ── Rate Limiting ─────────────────────────────────────────────────────
    rate_limit_capacity: int = Field(default=10, description="Token bucket capacity")
    rate_limit_refill_rate: int = Field(default=5, description="Tokens per second refill rate")

    # ── Token Expiry ──────────────────────────────────────────────────────
    download_token_expire_minutes: int = Field(default=60)
    auth_token_expire_minutes: int = Field(default=1440, description="24 hours")

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}


@lru_cache()
def get_settings() -> Settings:
    """Singleton settings instance. Cached for the lifetime of the process."""
    return Settings()


# Module-level convenience alias.
# This will crash on import if required env vars are missing — which is the desired behavior.
settings = get_settings()
