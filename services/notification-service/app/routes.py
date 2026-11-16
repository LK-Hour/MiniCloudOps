"""Notification API: /api/v1/notifications (contract from docs/MiniCloudOps.md §5.4).

One notification per incident event: the Incident Service may retry a call, so a second
POST for the same incident_id + event_type returns the stored notification with 200.
"""
import logging
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, Query, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import telegram
from app.db import get_db
from app.errors import ApiError
from app.models import Notification, dedup_key
from app.schemas import NotificationCreate, NotificationRead

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/notifications", tags=["notifications"])

DbSession = Annotated[Session, Depends(get_db)]


def _get_or_404(db: Session, notification_id: str) -> Notification:
    notification = db.get(Notification, notification_id)
    if notification is None:
        raise ApiError(status.HTTP_404_NOT_FOUND, f"Notification '{notification_id}' not found")
    return notification


def _by_key(db: Session, key: str) -> Notification | None:
    return db.scalars(select(Notification).where(Notification.dedup_key == key)).first()


@router.get("", response_model=list[NotificationRead])
def list_notifications(
    db: DbSession,
    unread_only: bool = False,
    incident_id: str | None = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    """Newest first."""
    query = (
        select(Notification)
        .order_by(Notification.created_at.desc(), Notification.id)
        .limit(limit)
        .offset(offset)
    )
    if unread_only:
        query = query.where(Notification.read.is_(False))
    if incident_id:
        query = query.where(Notification.incident_id == incident_id)
    return db.scalars(query).all()


@router.get("/channels", tags=["channels"])
def list_channels() -> dict:
    """Where notifications are delivered. The dashboard is always on; Telegram when configured."""
    return {"dashboard": {"enabled": True}, "telegram": {"enabled": telegram.is_enabled()}}


@router.post("/channels/telegram/test", tags=["channels"])
async def test_telegram() -> dict:
    """Send a test message, to check the bot token and chat ID."""
    if not telegram.is_enabled():
        raise ApiError(
            status.HTTP_409_CONFLICT,
            "Telegram is not configured: set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID",
        )
    sent, error = await telegram.send("✅ <b>MiniOps test message</b>\n\nTelegram alerts are working.")
    if not sent:
        raise ApiError(status.HTTP_502_BAD_GATEWAY, error or "Telegram delivery failed")
    return {"sent": True}


@router.get("/{notification_id}", response_model=NotificationRead)
def get_notification(notification_id: str, db: DbSession):
    return _get_or_404(db, notification_id)


@router.post(
    "",
    response_model=NotificationRead,
    status_code=status.HTTP_201_CREATED,
    responses={200: {"description": "Already notified for this incident event; returned as is"}},
)
def create_notification(
    payload: NotificationCreate, db: DbSession, response: Response, background: BackgroundTasks
):
    key = dedup_key(payload.incident_id, payload.event_type)
    existing = _by_key(db, key)
    if existing is None:
        notification = Notification(**payload.model_dump(), dedup_key=key, delivery_status="DELIVERED")
        db.add(notification)
        try:
            db.commit()
        except IntegrityError:  # a concurrent request stored it first
            db.rollback()
            existing = _by_key(db, key)
            if existing is None:
                raise
    if existing is not None:
        logger.info(
            "Duplicate notification suppressed", extra={"notification_id": existing.id, "dedup_key": key}
        )
        response.status_code = status.HTTP_200_OK
        return existing

    db.refresh(notification)
    response.headers["Location"] = f"{router.prefix}/{notification.id}"
    logger.info(
        "Notification stored",
        extra={
            "notification_id": notification.id,
            "incident_id": notification.incident_id,
            "event_type": notification.event_type,
        },
    )
    # Only new notifications are forwarded: a retried call must not send a second message.
    background.add_task(
        telegram.forward,
        notification_id=notification.id,
        title=notification.title,
        message=notification.message,
        event_type=notification.event_type,
        severity=notification.severity,
    )
    return notification


@router.patch("/{notification_id}/read", response_model=NotificationRead)
def mark_as_read(notification_id: str, db: DbSession):
    notification = _get_or_404(db, notification_id)
    if not notification.read:
        notification.read = True
        db.commit()
        db.refresh(notification)
    return notification
