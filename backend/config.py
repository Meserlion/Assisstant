from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    api_key: str
    anthropic_api_key: str
    whisper_model: str = "small"
    chroma_db_path: str = "./data/chroma"
    sqlite_db_path: str = "./data/notes.db"

    class Config:
        env_file = ".env"


settings = Settings()
