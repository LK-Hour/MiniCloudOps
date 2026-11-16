"""Request/response models for the Notification API."""
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, StringConstraints

EventType = Literal["INCIDENT_CREATED", "INCIDENT_RESOLVED"]
Severity = Literal["CRITICAL", "WARNING", "INFO"]
NonEmpty = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class NotificationCreate(BaseModel):
    incident_id: Annotated[NonEmpty, StringConstraints(max_length=36)]
    event_type: EventType
    severity: Severity | None = None
    title: Annotated[NonEmpty, StringConstraints(max_length=200)]
    message: Annotated[NonEmpty, StringConstraints(max_length=2000)]


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
