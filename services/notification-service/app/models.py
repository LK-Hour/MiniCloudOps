"""notification_db tables: notifications.

incident_id refers to an incident owned by the Incident Service (no cross-database FK).
"""
import uuid
from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(UTC)


def dedup_key(incident_id: str, event_type: str) -> str:
    return f"{incident_id}:{event_type}"


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    incident_id: Mapped[str] = mapped_column(String(36), index=True)
    event_type: Mapped[str] = mapped_column(String(40))  # INCIDENT_CREATED | INCIDENT_RESOLVED
    severity: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # Stored = delivered to the dashboard. Telegram, when configured, is a best-effort copy (app/telegram.py).
    channel: Mapped[str] = mapped_column(String(20), default="dashboard")
    title: Mapped[str] = mapped_column(String(200))
    message: Mapped[str] = mapped_column(Text)
    delivery_status: Mapped[str] = mapped_column(String(20), default="DELIVERED")
    read: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    # incident_id + event_type; the unique constraint stops duplicate notifications.
    dedup_key: Mapped[str] = mapped_column(String(100), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, index=True)
