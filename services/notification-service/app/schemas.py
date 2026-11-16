"""Request/response models for the Notification API."""
import json
from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, StringConstraints

EventType = Literal["INCIDENT_CREATED", "INCIDENT_RESOLVED"]
Severity = Literal["CRITICAL", "WARNING", "INFO"]
NonEmpty = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]

MAX_DETAILS_BYTES = 10_000


def _bounded(value: dict[str, Any] | None) -> dict[str, Any] | None:
    if value is not None and len(json.dumps(value, default=str)) > MAX_DETAILS_BYTES:
        raise ValueError(f"must be at most {MAX_DETAILS_BYTES} bytes as JSON")
    return value


# Facts about the incident (target, failure kind, latest checks, downtime) for richer alerts.
# Used to render the Telegram message; not stored.
Details = Annotated[dict[str, Any] | None, AfterValidator(_bounded)]


class NotificationCreate(BaseModel):
    incident_id: Annotated[NonEmpty, StringConstraints(max_length=36)]
    event_type: EventType
    severity: Severity | None = None
    title: Annotated[NonEmpty, StringConstraints(max_length=200)]
    message: Annotated[NonEmpty, StringConstraints(max_length=2000)]
    details: Details = None


class NotificationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    incident_id: str
    event_type: EventType
    severity: Severity | None
    channel: str
    title: str
    message: str
    delivery_status: str
    read: bool
    created_at: datetime
