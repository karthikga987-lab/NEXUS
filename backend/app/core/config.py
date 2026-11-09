from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    database_url: str = "sqlite:///./nexus.db"
    cors_origins: list[str] = ["http://localhost:5173"]

    gemini_api_key: str | None = None  # NEW

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

settings = Settings()