"""incident_db tables: incidents, incident_events.

target_id refers to a target owned by the Target Service (no cross-database FK).
"""
import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base

ACTIVE_CONDITION = text("status <> 'RESOLVED'")


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(UTC)


class Incident(Base):
    __tablename__ = "incidents"
    __table_args__ = (
        # At most one unresolved incident per target, enforced by the database too, so two
        # simultaneous reports of the same outage cannot both create one.
        Index(
            "uq_incidents_one_active_per_target",
            "target_id",
            unique=True,
            postgresql_where=ACTIVE_CONDITION,
            sqlite_where=ACTIVE_CONDITION,
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    target_id: Mapped[str] = mapped_column(String(36), index=True)
    title: Mapped[str] = mapped_column(String(200))
    severity: Mapped[str] = mapped_column(String(20))  # CRITICAL | WARNING | INFO
    # OPEN | ACKNOWLEDGED | RESOLVED
    status: Mapped[str] = mapped_column(String(20), default="OPEN", index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, index=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class IncidentEvent(Base):
    """Timeline of an incident: what happened to it and when."""

    __tablename__ = "incident_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    incident_id: Mapped[str] = mapped_column(ForeignKey("incidents.id", ondelete="CASCADE"), index=True)
    # CREATED | ACKNOWLEDGED | RESOLVED | NOTIFICATION_SENT | NOTIFICATION_FAILED
    event_type: Mapped[str] = mapped_column(String(40))
    message: Mapped[str] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
