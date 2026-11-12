from urllib.parse import urlsplit

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    database_url: str = "sqlite:///./nexus.db"
    cors_origins: list[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]

    @field_validator("cors_origins")
    @classmethod
    def include_localhost_alias_for_loopback_dev(cls, origins: list[str]) -> list[str]:
        # The local frontend may be opened through either loopback hostname.
        # Do not broaden an explicitly configured non-local deployment allowlist.
        hosts = {urlsplit(origin).hostname for origin in origins}
        if (
            "http://localhost:5173" in origins
            and hosts.issubset({"localhost", "127.0.0.1"})
        ):
            return list(dict.fromkeys([*origins, "http://127.0.0.1:5173"]))
        return origins

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

settings = Settings()
