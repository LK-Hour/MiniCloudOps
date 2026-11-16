"""Incident Management API: /api/v1/incidents (contract from docs/MiniCloudOps.md §5.3).

Rules:
  - At most one unresolved (OPEN or ACKNOWLEDGED) incident per target. Reporting the same outage
    again returns the existing incident with 200 instead of creating a duplicate.
  - Status moves forward only: OPEN -> ACKNOWLEDGED -> RESOLVED, or OPEN -> RESOLVED.
    Setting the status an incident already has is a no-op, so retried calls are safe.
  - The incident is committed first. The Notification Service is called afterwards, in the
    background; if it is down, the incident stays saved and the failure is recorded in its history.
"""
import logging
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, Query, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.db import SessionLocal, get_db
from app.errors import ApiError
from app.logging_config import correlation_id_var
from app.models import Incident, IncidentEvent
from app.notifications import NotificationClient, NotificationFailed, get_notifier
from app.schemas import (
    IncidentCreate,
    IncidentEventRead,
    IncidentRead,
    IncidentStatus,
    IncidentStatusUpdate,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/incidents", tags=["incidents"])

ACTIVE_STATUSES = ("OPEN", "ACKNOWLEDGED")
ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "OPEN": {"ACKNOWLEDGED", "RESOLVED"},
    "ACKNOWLEDGED": {"RESOLVED"},
    "RESOLVED": set(),
}


def get_session_factory() -> Callable[[], Session]:
    """Sessions for work that outlives the request (notifications). Tests override it."""
    return SessionLocal


DbSession = Annotated[Session, Depends(get_db)]
Notifier = Annotated[NotificationClient, Depends(get_notifier)]
SessionFactory = Annotated[Callable[[], Session], Depends(get_session_factory)]


def _get_or_404(db: Session, incident_id: str) -> Incident:
    incident = db.get(Incident, incident_id)
    if incident is None:
        raise ApiError(status.HTTP_404_NOT_FOUND, f"Incident '{incident_id}' not found")
    return incident


def _active_incident(db: Session, target_id: str) -> Incident | None:
    query = select(Incident).where(Incident.target_id == target_id, Incident.status.in_(ACTIVE_STATUSES))
    return db.scalars(query).first()


async def _notify(
    session_factory: Callable[[], Session],
    notifier: NotificationClient,
    correlation_id: str | None,
    *,
    incident_id: str,
    event_type: str,
    severity: str,
    title: str,
    message: str,
    details: dict | None = None,
) -> None:
    """Background task: tell the Notification Service, then record the outcome in the history."""
    correlation_id_var.set(correlation_id)  # the request's context is gone by the time this runs
    extra = {"incident_id": incident_id, "event_type": event_type}
    try:
        await notifier.send(
            incident_id=incident_id,
            event_type=event_type,
            severity=severity,
            title=title,
            message=message,
            details=details,
        )
        event = IncidentEvent(incident_id=incident_id, event_type="NOTIFICATION_SENT", message=event_type)
        logger.info("Notification sent", extra=extra)
    except NotificationFailed as exc:
        event = IncidentEvent(
            incident_id=incident_id,
            event_type="NOTIFICATION_FAILED",
            message=f"{event_type}: {exc}"[:500],
        )
        logger.error("Notification failed; incident is still saved", extra={**extra, "error": str(exc)})

    try:
        with session_factory() as db:
            db.add(event)
            db.commit()
    except SQLAlchemyError:
        logger.exception("Could not record notification outcome", extra=extra)


def _timing(incident: Incident) -> dict:
    """When the incident started and, once resolved, how long it lasted."""
    timing = {"incident_status": incident.status, "started_at": _iso(incident.created_at)}
    if incident.resolved_at:
        timing["resolved_at"] = _iso(incident.resolved_at)
        lasted = _aware(incident.resolved_at) - _aware(incident.created_at)
        timing["duration_seconds"] = round(lasted.total_seconds())
    return timing


def _aware(moment: datetime) -> datetime:
    return moment if moment.tzinfo else moment.replace(tzinfo=UTC)  # SQLite drops the zone


def _iso(moment: datetime) -> str:
    return _aware(moment).isoformat()


@router.get("", response_model=list[IncidentRead])
def list_incidents(
    db: DbSession,
    status_filter: Annotated[IncidentStatus | None, Query(alias="status")] = None,
    target_id: str | None = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    """Newest first."""
    query = select(Incident).order_by(Incident.created_at.desc(), Incident.id).limit(limit).offset(offset)
    if status_filter:
        query = query.where(Incident.status == status_filter)
    if target_id:
        query = query.where(Incident.target_id == target_id)
    return db.scalars(query).all()


@router.get("/{incident_id}", response_model=IncidentRead)
def get_incident(incident_id: str, db: DbSession):
    return _get_or_404(db, incident_id)


@router.post(
    "",
    response_model=IncidentRead,
    status_code=status.HTTP_201_CREATED,
    responses={200: {"description": "An unresolved incident already exists for this target; returned as is"}},
)
def create_incident(
    payload: IncidentCreate,
    db: DbSession,
    background: BackgroundTasks,
    notifier: Notifier,
    session_factory: SessionFactory,
    response: Response,
):
    existing = _active_incident(db, payload.target_id)
    if existing is None:
        incident = Incident(**payload.model_dump(exclude={"context"}), status="OPEN")
        db.add(incident)
        db.flush()  # assigns the id for the event below
        db.add(IncidentEvent(incident_id=incident.id, event_type="CREATED", message=payload.title))
        try:
            db.commit()
        except IntegrityError:  # a concurrent request created it first
            db.rollback()
            existing = _active_incident(db, payload.target_id)
            if existing is None:
                raise
    if existing is not None:
        logger.info(
            "Duplicate incident suppressed",
            extra={"incident_id": existing.id, "target_id": payload.target_id},
        )
        response.status_code = status.HTTP_200_OK
        return existing

    db.refresh(incident)
    response.headers["Location"] = f"{router.prefix}/{incident.id}"
    logger.warning(
        "Incident created",
        extra={"incident_id": incident.id, "target_id": incident.target_id, "severity": incident.severity},
    )
    background.add_task(
        _notify,
        session_factory,
        notifier,
        correlation_id_var.get(),
        incident_id=incident.id,
        event_type="INCIDENT_CREATED",
        severity=incident.severity,
        title=f"[{incident.severity}] {incident.title}",
        message=incident.description or incident.title,
        details={**(payload.context or {}), **_timing(incident)},
    )
    return incident


@router.patch("/{incident_id}/status", response_model=IncidentRead)
def update_incident_status(
    incident_id: str,
    payload: IncidentStatusUpdate,
    db: DbSession,
    background: BackgroundTasks,
    notifier: Notifier,
    session_factory: SessionFactory,
):
    incident = _get_or_404(db, incident_id)
    if payload.status == incident.status:
        return incident  # already there; makes retries harmless
    if payload.status not in ALLOWED_TRANSITIONS[incident.status]:
        raise ApiError(
            status.HTTP_409_CONFLICT,
            f"Cannot change an incident from {incident.status} to {payload.status}",
            [{"field": "body.status", "message": f"Allowed: {sorted(ALLOWED_TRANSITIONS[incident.status])}"}],
        )

    old_status = incident.status
    incident.status = payload.status
    if payload.status == "RESOLVED":
        incident.resolved_at = datetime.now(UTC)
    message = f"{old_status} -> {payload.status}" + (f": {payload.note}" if payload.note else "")
    db.add(IncidentEvent(incident_id=incident.id, event_type=payload.status, message=message))
    db.commit()
    db.refresh(incident)
    logger.info(
        "Incident status changed",
        extra={"incident_id": incident.id, "old_status": old_status, "new_status": payload.status},
    )

    if payload.status == "RESOLVED":
        background.add_task(
            _notify,
            session_factory,
            notifier,
            correlation_id_var.get(),
            incident_id=incident.id,
            event_type="INCIDENT_RESOLVED",
            severity=incident.severity,
            title=f"[RESOLVED] {incident.title}",
            message=payload.note or "The incident has been resolved.",
            details={**(payload.context or {}), **_timing(incident)},
        )
    return incident


@router.get("/{incident_id}/history", response_model=list[IncidentEventRead])
def incident_history(incident_id: str, db: DbSession):
    """Oldest first, as a timeline."""
    _get_or_404(db, incident_id)
    query = (
        select(IncidentEvent)
        .where(IncidentEvent.incident_id == incident_id)
        .order_by(IncidentEvent.created_at, IncidentEvent.id)
    )
    return db.scalars(query).all()
