from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional, List


class Settings(BaseSettings):
    google_cloud_project: str = ""
    google_application_credentials: str = ""
    gemini_api_key: str = ""
    firestore_emulator_host: Optional[str] = None
    narrator_model: str = "gemini-2.5-flash-native-audio-preview-12-2025"
    traitor_model: str = "gemini-2.5-flash"
    narrator_preview_model: str = "gemini-2.5-flash-preview-tts"  # TTS via generate_content
    narrator_voice: str = "Charon"
    # CORS origins — set ALLOWED_ORIGINS env var for production (comma-separated)
    allowed_origins: List[str] = [
        "http://localhost:5173",
        "http://localhost:3000",
        "http://127.0.0.1:5173",
    ]
    # Extra production origin (e.g. Cloud Run URL); appended to allowed_origins
    extra_origin: str = ""
    debug: bool = False

    # Pydantic v2 style (replaces deprecated inner class Config)
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_ignore_empty=True,
    )


settings = Settings()
