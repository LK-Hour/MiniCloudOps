"""Service configuration, read from environment variables (see .env.example)."""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    service_name: str = "notification-service"
    log_level: str = "INFO"
    database_url: str = "postgresql+psycopg://miniops:miniops@localhost:5432/notification_db"
    http_timeout_seconds: float = 5.0
    http_max_retries: int = 3
    # Optional Telegram channel: both must be set to turn it on.
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    # Linked from each Telegram message (empty: no link).
    dashboard_url: str = "http://localhost:3000"
    # Time zone for times shown in alerts, e.g. Asia/Phnom_Penh (IANA name).
    alert_timezone: str = "UTC"
    # Telegram bot commands (/status, /menu, ...) by long polling; needs the token and chat ID too.
    telegram_commands_enabled: bool = True
    # The bot reads these services to answer commands.
    target_service_url: str = "http://target-service:8000"
    monitoring_service_url: str = "http://monitoring-service:8000"
    incident_service_url: str = "http://incident-service:8000"


@lru_cache
def get_settings() -> Settings:
    return Settings()
