import os
from pathlib import Path
from pydantic_settings import BaseSettings

BASE_DIR = Path(__file__).resolve().parent.parent

class Settings(BaseSettings):
    PROJECT_NAME: str = "VideoIntel Hub"
    VERSION: str = "1.0.0"
    
    # API Keys
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    YOUTUBE_API_KEY: str = os.getenv("YOUTUBE_API_KEY", "")
    
    # Storage
    DATA_DIR: Path = BASE_DIR / "data"
    DATABASE_URL: str = f"sqlite+aiosqlite:///{BASE_DIR}/data/videointel.db"
    VIDEOS_JSON_PATH: Path = BASE_DIR / "videos.json"
    
    # Operational
    CORS_ORIGINS: list[str] = ["*"]
    DEFAULT_TRANSCRIPT_LANGUAGES: list[str] = ["en", "hi"]
    MAX_DISCOVERY_PER_CHANNEL: int = 5

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

settings = Settings()
