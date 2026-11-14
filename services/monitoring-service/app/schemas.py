"""Request/response models for the Monitoring API."""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

HealthStatus = Literal["UP", "DOWN", "UNKNOWN"]


class HealthCheckResult(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    target_id: str
    status: HealthStatus
    status_code: int | None = None
    response_time_ms: float | None = None
    error: str | None = None
    checked_at: datetime


class TargetStatus(BaseModel):
    target_id: str
    status: HealthStatus
    consecutive_failures: int
    last_checked_at: datetime | None
    cpu_percent: float | None = None  # None = metrics temporarily unavailable
    memory_percent: float | None = None
