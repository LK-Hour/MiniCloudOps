"""monitoring_db tables: health_checks, metric_snapshots, monitoring_configurations.

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
    __tablename__ = "health_checks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    target_id: Mapped[str] = mapped_column(String(36), index=True)
    status: Mapped[str] = mapped_column(String(10))  # UP | DOWN
    status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    response_time_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    error: Mapped[str | None] = mapped_column(String(500), nullable=True)
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, index=True)


class MetricSnapshot(Base):
    __tablename__ = "metric_snapshots"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    target_id: Mapped[str] = mapped_column(String(36), index=True)
    # NULL means "metrics unavailable" (e.g. Prometheus down) — never store 0 for that.
    cpu_percent: Mapped[float | None] = mapped_column(Float, nullable=True)
    memory_percent: Mapped[float | None] = mapped_column(Float, nullable=True)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class MonitoringConfiguration(Base):
    __tablename__ = "monitoring_configurations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    target_id: Mapped[str] = mapped_column(String(36), unique=True)
    failure_threshold: Mapped[int] = mapped_column(Integer, default=3)
    response_time_threshold_ms: Mapped[int] = mapped_column(Integer, default=2000)
    cpu_threshold_percent: Mapped[float] = mapped_column(Float, default=80.0)
    memory_threshold_percent: Mapped[float] = mapped_column(Float, default=85.0)
