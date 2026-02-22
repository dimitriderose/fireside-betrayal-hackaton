from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    google_cloud_project: str = ""
    google_application_credentials: str = ""
    gemini_api_key: str = ""
    firestore_emulator_host: Optional[str] = None
    narrator_model: str = "gemini-2.5-flash-native-audio-preview-12-2025"
    traitor_model: str = "gemini-2.5-flash"
    narrator_voice: str = "Charon"
    debug: bool = False

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
