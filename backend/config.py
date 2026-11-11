import os
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_DATA_DIR = BASE_DIR / "data"
DEFAULT_DB_PATH = DEFAULT_DATA_DIR / "videointel.db"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    DATA_DIR: str = str(DEFAULT_DATA_DIR)
    DATABASE_URL: str = f"sqlite+aiosqlite:///{DEFAULT_DB_PATH.as_posix()}"
    YOUTUBE_API_KEY: str = ""
    GEMINI_API_KEY: str = ""
    PROJECT_NAME: str = "VideoIntel Hub"
    VERSION: str = "1.0.0"
    CORS_ORIGINS: str = "*"

    @property
    def cors_origins(self) -> list[str]:
        raw_value = os.getenv("CORS_ORIGINS", self.CORS_ORIGINS)
        values = [part.strip() for part in raw_value.split(",") if part.strip()]
        return values or ["*"]


settings = Settings()
