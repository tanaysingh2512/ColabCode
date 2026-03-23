from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_name: str = "CollabCode"
    environment: Literal["development", "test", "production"] = "development"
    api_prefix: str = "/api/v1"
    database_url: str = "postgresql+asyncpg://collabcode:collabcode@localhost:5432/collabcode"
    redis_url: str = "redis://localhost:6379/0"
    redis_enabled: bool = True
    cors_origins: str = Field(default="http://localhost:5173")
    public_frontend_url: str = "http://localhost:5173"
    snapshot_debounce_seconds: float = 2.0
    code_timeout_seconds: float = 5.0
    max_execution_output_chars: int = 8000
    document_state_key: str = "code"
    database_startup_timeout_seconds: float = 45.0
    database_retry_interval_seconds: float = 2.0
    auth_secret_key: str = "development-secret-change-me"
    auth_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24 * 7
    password_reset_token_expire_minutes: int = 30

    @property
    def cors_origins_list(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
