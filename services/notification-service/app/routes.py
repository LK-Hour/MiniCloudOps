"""Notification API: /api/v1/notifications (contract from docs/MiniCloudOps.md §5.4)."""
from fastapi import APIRouter, status

from app.errors import not_implemented
from app.schemas import NotificationCreate, NotificationRead

router = APIRouter(prefix="/api/v1/notifications", tags=["notifications"])


@router.get("/", response_model=list[NotificationRead])
def list_notifications(unread_only: bool = False):
    raise not_implemented()


@router.get("/{notification_id}", response_model=NotificationRead)
def get_notification(notification_id: str):
    raise not_implemented()


@router.post("/", response_model=NotificationRead, status_code=status.HTTP_201_CREATED)
def create_notification(payload: NotificationCreate):
    raise not_implemented()


@router.patch("/{notification_id}/read", response_model=NotificationRead)
def mark_as_read(notification_id: str):
    raise not_implemented()
