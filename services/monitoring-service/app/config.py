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

    # Scheduler
    scheduler_enabled: bool = True
    scheduler_tick_seconds: float = 5.0  # how often due targets are looked for
    max_concurrent_checks: int = 10
    check_timeout_seconds: float = 5.0  # timeout for one request to a monitored target
    history_retention_days: int = 7

    # Thresholds (docs/MiniCloudOps.md §7.3)
    default_check_interval_seconds: int = 30
    failure_threshold: int = 3  # consecutive failed checks before an incident is opened
    response_time_threshold_ms: int = 2000

    prometheus_timeout_seconds: float = 2.0

    # SSRF protection, re-checked before every request. Same meaning as in the Target Service.
    ssrf_blocked_hosts: str = (
        "postgres,prometheus,grafana,loki,alloy,cadvisor,node-exporter,gateway,frontend,"
        "target-service,monitoring-service,incident-service,notification-service"
    )
    ssrf_allow_private_networks: bool = True

    @property
    def ssrf_blocked_host_list(self) -> list[str]:
        return [h.strip() for h in self.ssrf_blocked_hosts.split(",") if h.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
