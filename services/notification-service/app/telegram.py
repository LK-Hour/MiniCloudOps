"""Telegram channel: forwards each new notification to a Telegram chat through a bot.

Optional. It is on when TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID are both set (see .env.example).
The dashboard stays the source of truth: a notification is stored first, then sent to Telegram in
the background, so a slow or unreachable Telegram never delays or fails the Incident Service's call.

The bot token is a secret and sits in the request URL, so neither the URL nor httpx's own error
text (which can contain it) is ever logged. Only the outcome and Telegram's error description are.
"""
import html
import logging

import httpx
from prometheus_client import Counter

from app.config import get_settings

logger = logging.getLogger(__name__)

API = "https://api.telegram.org"
ICONS = {"CRITICAL": "🔴", "WARNING": "🟠", "INFO": "🔵"}
RESOLVED_ICON = "✅"

# Tests replace this with an httpx.MockTransport so no real network is used.
transport: httpx.AsyncBaseTransport | None = None

deliveries = Counter(
    "miniops_telegram_deliveries_total",
    "Notifications forwarded to Telegram, by result",
    ["result"],  # sent | failed
)


def is_enabled() -> bool:
    settings = get_settings()
    return bool(settings.telegram_bot_token and settings.telegram_chat_id)


def format_message(*, title: str, message: str, event_type: str, severity: str | None) -> str:
    """Telegram HTML: a status icon, the bold title, then the details."""
    icon = RESOLVED_ICON if event_type == "INCIDENT_RESOLVED" else ICONS.get(severity or "", "⚪")
    lines = [f"{icon} <b>{html.escape(title)}</b>", html.escape(message)]
    dashboard = get_settings().dashboard_url
    if dashboard:
        lines.append(f'<a href="{html.escape(dashboard, quote=True)}">Open MiniOps</a>')
    return "\n\n".join(lines)


async def send(text: str) -> tuple[bool, str | None]:
    """Send one message. Returns (sent, error) and never raises."""
    settings = get_settings()
    if not (settings.telegram_bot_token and settings.telegram_chat_id):
        return False, "Telegram is not configured"
    url = f"{API}/bot{settings.telegram_bot_token}/sendMessage"
    payload = {
        "chat_id": settings.telegram_chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    error: str | None = None
    try:
        async with httpx.AsyncClient(
            timeout=settings.http_timeout_seconds, transport=transport, trust_env=False
        ) as client:
            response = await client.post(url, json=payload)
        if response.status_code == 200:
            deliveries.labels("sent").inc()
            return True, None
        try:
            error = f"Telegram answered {response.status_code}: {response.json().get('description', '')}"
        except ValueError:
            error = f"Telegram answered {response.status_code}"
    except httpx.HTTPError as exc:
        error = f"Could not reach Telegram ({type(exc).__name__})"
    deliveries.labels("failed").inc()
    return False, error


async def forward(
    *, notification_id: str, title: str, message: str, event_type: str, severity: str | None
) -> None:
    """Background task run after a notification is stored."""
    if not is_enabled():
        return
    text = format_message(title=title, message=message, event_type=event_type, severity=severity)
    sent, error = await send(text)
    if sent:
        logger.info("Notification sent to Telegram", extra={"notification_id": notification_id})
    else:
        logger.warning(
            "Telegram delivery failed", extra={"notification_id": notification_id, "error": error}
        )
