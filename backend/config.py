import os
from pathlib import Path
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    DATA_DIR: str = os.getenv("DATA_DIR", str(Path(__file__).resolve().parent.parent / "data"))
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///../data/videointel.db")
    YOUTUBE_API_KEY: str = ""
    GEMINI_API_KEY: str = ""

    class Config:
        env_file = ".env"
        extra = "ignore"

settings = Settings()
