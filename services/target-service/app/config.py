"""Service configuration, read from environment variables (see .env.example)."""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    service_name: str = "target-service"
    log_level: str = "INFO"
    database_url: str = "postgresql+psycopg://miniops:miniops@localhost:5432/target_db"
    http_timeout_seconds: float = 5.0
    http_max_retries: int = 3

    # SSRF protection (see app/url_safety.py). Hostnames that targets may never point at.
    ssrf_blocked_hosts: str = (
        "postgres,prometheus,grafana,loki,alloy,cadvisor,node-exporter,gateway,frontend,"
        "target-service,monitoring-service,incident-service,notification-service"
    )
    # Docker Compose apps live on private addresses, so these are allowed unless switched off.
    ssrf_allow_private_networks: bool = True

    @property
    def ssrf_blocked_host_list(self) -> list[str]:
        return [h.strip() for h in self.ssrf_blocked_hosts.split(",") if h.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
