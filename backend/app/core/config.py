"""Configuration settings for PrivyDoc backend."""

from pathlib import Path
from typing import List
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    APP_NAME: str = "PrivyDoc"
    APP_VERSION: str = "0.1.0"
    HOST: str = "127.0.0.1"
    PORT: int = 8000
    DEBUG: bool = False
    
    # Restrict CORS to local frontend origins only
    ALLOWED_ORIGINS: List[str] = [
        "http://127.0.0.1:5173",
        "http://localhost:5173",
        "http://127.0.0.1:3000",
        "http://localhost:3000",
    ]
    
    # Ephemeral local storage directories
    BASE_DIR: Path = Path(__file__).resolve().parent.parent.parent
    DATA_DIR: Path = BASE_DIR / "data"
    SESSIONS_DIR: Path = DATA_DIR / "sessions"
    DATABASE_PATH: Path = DATA_DIR / "privydoc.db"
    
    # Upload and session constraints
    MAX_UPLOAD_SIZE_MB: int = 20
    SESSION_TTL_HOURS: int = 24
    
    # Local SLM configuration
    LOCAL_SLM_URL: str = "http://127.0.0.1:11434"
    SLM_MODEL_NAME: str = "qwen2.5:1.5b-instruct"
    SLM_TIMEOUT_SECONDS: float = 5.0


settings = Settings()
