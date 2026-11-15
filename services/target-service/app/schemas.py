"""Request/response models for the Target Management API."""
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, StringConstraints

# Version 1 monitors HTTP endpoints only. New check types get added here and in the Monitoring Service.
TargetType = Literal["http"]
TargetStatus = Literal["UP", "DOWN", "UNKNOWN"]
TargetName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
CheckInterval = Annotated[int, Field(ge=10, le=3600, description="Seconds between health checks")]


class TargetCreate(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "name": "Example API",
                "target_url": "http://demo-app/",
                "type": "http",
                "check_interval": 30,
                "enabled": True,
            }
        }
    )

    name: TargetName
    # Syntax is checked here; SSRF rules (internal hosts and addresses) are checked in the route.
    target_url: HttpUrl
    type: TargetType = "http"
    check_interval: CheckInterval = 30
    enabled: bool = True


class TargetUpdate(BaseModel):
    """Every field is optional; only the fields sent are changed."""

    name: TargetName | None = None
    target_url: HttpUrl | None = None
    type: TargetType | None = None
    check_interval: CheckInterval | None = None
    enabled: bool | None = None


class TargetStatusUpdate(BaseModel):
    status: TargetStatus


class TargetRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    target_url: str
    type: str
    check_interval: int
    enabled: bool
    status: TargetStatus
    created_at: datetime
    updated_at: datetime
