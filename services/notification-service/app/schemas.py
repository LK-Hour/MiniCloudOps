"""Request/response models for the Notification API."""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

EventType = Literal["INCIDENT_CREATED", "INCIDENT_RESOLVED"]


class NotificationCreate(BaseModel):
    incident_id: str
    event_type: EventType
    title: str = Field(min_length=1, max_length=200)
    message: str = Field(min_length=1)


class NotificationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    incident_id: str
    event_type: EventType
    channel: str
    title: str
    message: str
    delivery_status: str
    read: bool
    created_at: datetime
