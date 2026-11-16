"""Request/response models for the Incident Management API."""
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

Severity = Literal["CRITICAL", "WARNING", "INFO"]
IncidentStatus = Literal["OPEN", "ACKNOWLEDGED", "RESOLVED"]
NonEmpty = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class IncidentCreate(BaseModel):
    target_id: Annotated[NonEmpty, StringConstraints(max_length=36)]
    title: Annotated[NonEmpty, StringConstraints(max_length=200)]
    severity: Severity
    description: str | None = Field(default=None, max_length=2000)


class IncidentStatusUpdate(BaseModel):
    status: IncidentStatus
    note: str | None = Field(default=None, max_length=400)


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
