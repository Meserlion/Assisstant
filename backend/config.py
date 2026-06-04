from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    api_key: str
    anthropic_api_key: str
    whisper_model: str = "small"
    chroma_db_path: str = "./data/chroma"
    sqlite_db_path: str = "./data/notes.db"
    google_client_id: str = ""
    google_client_secret: str = ""
    google_redirect_uri: str = "https://mcgreeff-assistant.duckdns.org/api/calendar/oauth/callback"
    vapid_private_key: str = ""
    vapid_public_key: str = ""
    vapid_email: str = "christiaangreeff@gmail.com"

    class Config:
        env_file = ".env"


settings = Settings()
