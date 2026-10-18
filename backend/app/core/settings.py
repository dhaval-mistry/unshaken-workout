"""Environment-backed settings for the API process."""

from functools import lru_cache
from uuid import UUID

from pydantic import Field, HttpUrl, PostgresDsn, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Validated runtime configuration loaded only from explicit environment variables."""

    model_config = SettingsConfigDict(case_sensitive=False, env_file=".env", extra="ignore")

    app_environment: str = Field(
        default="development", pattern="^(development|test|staging|production)$"
    )
    database_url: PostgresDsn
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])
    log_level: str = Field(default="INFO", pattern="^(DEBUG|INFO|WARNING|ERROR|CRITICAL)$")
    # ExerciseDB content is fetched live only. Leaving these unset keeps the catalog disabled.
    exercise_db_base_url: HttpUrl | None = None
    exercise_db_api_key: SecretStr | None = None
    exercise_db_host: str | None = None
    exercise_db_media_enabled: bool = False
    # Temporary identity for local API development; real authentication replaces this.
    development_user_id: UUID | None = None
    development_user_email: str = "local@unshaken.invalid"
    development_user_display_name: str = "Local User"

    @field_validator(
        "exercise_db_base_url", "exercise_db_api_key", "exercise_db_host", mode="before"
    )
    @classmethod
    def empty_optional_provider_setting_is_none(cls, value: object) -> object:
        """Allow safe blank placeholders in `.env.example` without enabling the provider."""

        return None if isinstance(value, str) and not value.strip() else value


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide settings instance after validation."""

    return Settings()
