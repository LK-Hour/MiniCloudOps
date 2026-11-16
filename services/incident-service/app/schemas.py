"""Request/response models for the Incident Management API."""
import json
from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, StringConstraints

Severity = Literal["CRITICAL", "WARNING", "INFO"]
IncidentStatus = Literal["OPEN", "ACKNOWLEDGED", "RESOLVED"]
NonEmpty = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]

MAX_CONTEXT_BYTES = 8000


def _bounded(value: dict[str, Any] | None) -> dict[str, Any] | None:
    if value is not None and len(json.dumps(value, default=str)) > MAX_CONTEXT_BYTES:
        raise ValueError(f"must be at most {MAX_CONTEXT_BYTES} bytes as JSON")
    return value


# Facts from the caller (target, failure kind, latest checks) passed on to the notification.
# Not stored: the incident record stays the same; only the alert gets richer.
Context = Annotated[dict[str, Any] | None, AfterValidator(_bounded)]


class IncidentCreate(BaseModel):
    target_id: Annotated[NonEmpty, StringConstraints(max_length=36)]
    title: Annotated[NonEmpty, StringConstraints(max_length=200)]
    severity: Severity
    description: str | None = Field(default=None, max_length=2000)
    context: Context = None


class IncidentStatusUpdate(BaseModel):
    status: IncidentStatus
    note: str | None = Field(default=None, max_length=400)
    context: Context = None


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
