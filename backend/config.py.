
import os
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Central configuration for VideoIntel Hub.

    Secrets must be provided through environment variables,
    never hardcoded into source files.
    """

    app_name: str = "VideoIntel Hub API"
    app_version: str = "1.0.0"
    environment: str = "development"

    # Gemini configuration
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash"

    # Database
    database_url: str = "sqlite:///./videointel.db"

    # Backend security
    api_secret_key: str = ""
    allowed_origins: str = (
        "https://tsachin4615-afk.github.io"
    )

    # Research limits
    max_videos_per_batch: int = 10
    max_research_sources: int = 8

    # Application settings
    debug: bool = False

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"
    )

    @property
    def cors_origins(self) -> list[str]:
        return [
            origin.strip()
            for origin in self.allowed_origins.split(",")
            if origin.strip()
        ]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
