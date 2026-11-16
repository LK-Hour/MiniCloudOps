"""monitoring_db tables: health_checks, target_states.

target_id refers to a target owned by the Target Service (no cross-database FK).
"""
import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(UTC)


class HealthCheck(Base):
    """One health check of one target. This is the history the API serves."""

    __tablename__ = "health_checks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    target_id: Mapped[str] = mapped_column(String(36), index=True)
    status: Mapped[str] = mapped_column(String(10))  # UP | DOWN
    status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # NULL when no response arrived (timeout, refused). Never stored as 0.
    response_time_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    error: Mapped[str | None] = mapped_column(String(500), nullable=True)
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, index=True)


class TargetState(Base):
    """Latest known state of a target, used to count failures and track its open incident."""

    __tablename__ = "target_states"

    target_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    status: Mapped[str] = mapped_column(String(10), default="UNKNOWN")  # UP | DOWN | UNKNOWN
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0)
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_response_time_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    # Incident opened for the current outage, so it is opened once and resolved on recovery.
    open_incident_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
