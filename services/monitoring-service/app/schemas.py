"""Request/response models for the Monitoring API."""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

HealthStatus = Literal["UP", "DOWN", "UNKNOWN"]


class HealthCheckResult(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    target_id: str
    status: Literal["UP", "DOWN"]
    status_code: int | None = None
    response_time_ms: float | None = Field(None, description="null when no response arrived")
    error: str | None = None
    checked_at: datetime


class TargetStatus(BaseModel):
    target_id: str
    status: HealthStatus = Field(description="UNKNOWN until the first check, or while disabled")
    consecutive_failures: int
    last_checked_at: datetime | None
    last_response_time_ms: float | None
    open_incident_id: str | None = Field(description="Incident opened for the current outage, if any")
    metrics_available: bool = Field(description="false when Prometheus could not be reached")
    cpu_percent: float | None = Field(description="Container CPU, % of one core. null = no data")
    memory_percent: float | None = Field(description="Container memory, % of host memory. null = no data")


class MonitoringPolicy(BaseModel):
    """Effective monitoring settings. Set through environment variables, read-only here."""

    default_check_interval_seconds: int
    failure_threshold: int
    response_time_threshold_ms: int
    check_timeout_seconds: float
    scheduler_tick_seconds: float
    history_retention_days: int
    ssrf_allow_private_networks: bool


class RecentCheck(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    status: Literal["UP", "DOWN"]
    response_time_ms: float | None
    checked_at: datetime


class TargetOverview(BaseModel):
    """Monitoring state of one target, for dashboards. No Prometheus data, so it is cheap."""

    target_id: str
    status: HealthStatus
    consecutive_failures: int
    last_checked_at: datetime | None
    last_response_time_ms: float | None
    open_incident_id: str | None
    recent: list[RecentCheck] = Field(description="Latest checks, oldest first")


class HostStats(BaseModel):
    cpu_percent: float | None = None
    memory_percent: float | None = None
    memory_total_bytes: float | None = None
    disk_percent: float | None = None
    uptime_seconds: float | None = None


class ContainerStats(BaseModel):
    service: str
    cpu_percent: float | None
    memory_bytes: float | None


class ServiceScrape(BaseModel):
    instance: str
    up: bool


class Alert(BaseModel):
    name: str
    severity: str | None
    state: str | None
    summary: str | None
    active_at: str | None


class InfrastructureRead(BaseModel):
    available: bool = Field(description="false when Prometheus could not be reached; the rest is empty")
    collected_at: datetime
    host: HostStats
    containers: list[ContainerStats]
    services: list[ServiceScrape]
    alerts: list[Alert]


class SeriesPoint(BaseModel):
    t: datetime
    v: float


class InfrastructureHistory(BaseModel):
    """Host and container usage over a window, for time-series charts."""

    available: bool = Field(description="false when Prometheus could not be reached; series are empty")
    minutes: int
    step_seconds: int
    host: dict[str, list[SeriesPoint]] = Field(description="cpu, memory, disk: % over time")
    containers: dict[str, list[SeriesPoint]] = Field(description="CPU % of one core, busiest services")


class ResourceHistory(BaseModel):
    """One target's container usage over a window."""

    available: bool
    minutes: int
    step_seconds: int
    cpu: list[SeriesPoint] = Field(description="% of one core")
    memory: list[SeriesPoint] = Field(description="% of host memory")


class Bucket(BaseModel):
    t: datetime = Field(description="Start of the bucket")
    checks: int
    failures: int
    avg_ms: float | None = Field(description="Mean response time of checks that got a response; null if none")
    max_ms: float | None


class TargetSeries(BaseModel):
    target_id: str
    buckets: list[Bucket]


class CheckTimeseries(BaseModel):
    """Health checks aggregated into equal time buckets: all targets together, and each target."""

    minutes: int
    bucket_seconds: int
    overall: list[Bucket]
    targets: list[TargetSeries]
