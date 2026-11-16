"""Calls to the Notification Service."""
import httpx

from app.config import get_settings
from app.http_client import request_with_retry


class NotificationFailed(Exception):
    """The notification could not be delivered to the Notification Service."""


class NotificationClient:
    def __init__(self, base_url: str) -> None:
        self.api = f"{base_url.rstrip('/')}/api/v1/notifications"

    async def send(
        self, *, incident_id: str, event_type: str, severity: str, title: str, message: str
    ) -> None:
        payload = {
            "incident_id": incident_id,
            "event_type": event_type,
            "severity": severity,
            "title": title[:200],
            "message": message,
        }
        try:
            response = await request_with_retry("POST", self.api, json=payload)
        except httpx.HTTPError as exc:
            raise NotificationFailed(str(exc) or type(exc).__name__) from exc
        # 201 = created, 200 = the Notification Service already had it (duplicate suppressed)
        if response.status_code not in (200, 201):
            raise NotificationFailed(f"Notification Service returned {response.status_code}")


def get_notifier() -> NotificationClient:
    """FastAPI dependency. Tests override it with a fake."""
    return NotificationClient(get_settings().notification_service_url)
