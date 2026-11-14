"""Request/response models for the Incident Management API."""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Severity = Literal["CRITICAL", "WARNING", "INFO"]
IncidentStatus = Literal["OPEN", "ACKNOWLEDGED", "RESOLVED"]


class IncidentCreate(BaseModel):
    target_id: str
    title: str = Field(min_length=1, max_length=200)
    severity: Severity
    description: str | None = None


class IncidentStatusUpdate(BaseModel):
    status: IncidentStatus
    note: str | None = Field(default=None, max_length=500)


class IncidentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    target_id: str
    title: str
    severity: Severity
    status: IncidentStatus
    description: str | None
    created_at: datetime
    resolved_at: datetime | None


class IncidentEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    incident_id: str
    event_type: str
    message: str
    created_at: datetime
