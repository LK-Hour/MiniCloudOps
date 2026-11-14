"""Service configuration, read from environment variables (see .env.example)."""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    service_name: str = "incident-service"
    log_level: str = "INFO"
    database_url: str = "postgresql+psycopg://miniops:miniops@localhost:5432/incident_db"
    http_timeout_seconds: float = 5.0
    http_max_retries: int = 3
    notification_service_url: str = "http://notification-service:8000"


@lru_cache
def get_settings() -> Settings:
    return Settings()
