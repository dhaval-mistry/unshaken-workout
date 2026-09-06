"""Environment-backed settings for the API process."""

from functools import lru_cache

from pydantic import Field, PostgresDsn
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Validated runtime configuration loaded only from explicit environment variables."""

    model_config = SettingsConfigDict(case_sensitive=False, env_file=".env", extra="ignore")

    app_environment: str = Field(default="development", pattern="^(development|test|staging|production)$")
    database_url: PostgresDsn
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])
    log_level: str = Field(default="INFO", pattern="^(DEBUG|INFO|WARNING|ERROR|CRITICAL)$")


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide settings instance after validation."""

    return Settings()
