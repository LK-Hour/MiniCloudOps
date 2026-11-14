"""Service configuration, read from environment variables (see .env.example)."""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    service_name: str = "monitoring-service"
    log_level: str = "INFO"
    database_url: str = "postgresql+psycopg://miniops:miniops@localhost:5432/monitoring_db"
    http_timeout_seconds: float = 5.0
    http_max_retries: int = 3
    target_service_url: str = "http://target-service:8000"
    incident_service_url: str = "http://incident-service:8000"
    prometheus_url: str = "http://prometheus:9090"
    default_check_interval_seconds: int = 30
    failure_threshold: int = 3
    response_time_threshold_ms: int = 2000


@lru_cache
def get_settings() -> Settings:
    return Settings()
