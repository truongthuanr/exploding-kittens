from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "exploding-kittens-backend"
    app_env: str = "development"
    host: str = "127.0.0.1"
    port: int = 8000
    debug: bool = True
    database_url: str = "postgresql://postgres:postgres@db:5432/boardgame"
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:3000"])
    socket_io_path: str = "socket.io"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="APP_",
        case_sensitive=False,
        extra="ignore",
    )

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, value: str | list[str]) -> list[str]:
        if isinstance(value, list):
            return value
        return [item.strip() for item in value.split(",") if item.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
