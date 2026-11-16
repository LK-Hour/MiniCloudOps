"""Telegram channel: forwards each new notification to a Telegram chat through a bot.

Optional. It is on when TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID are both set (see .env.example).
The dashboard stays the source of truth: a notification is stored first, then sent to Telegram in
the background, so a slow or unreachable Telegram never delays or fails the Incident Service's call.

The bot token is a secret and sits in the request URL, so neither the URL nor httpx's own error
text (which can contain it) is ever logged. Only the outcome and Telegram's error description are.
"""
import logging
from datetime import UTC, datetime

import httpx
from prometheus_client import Counter

from app import alert_templates
from app.config import get_settings

logger = logging.getLogger(__name__)

API = "https://api.telegram.org"

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


def format_message(
    *,
    incident_id: str,
    title: str,
    message: str,
    event_type: str,
    severity: str | None,
    details: dict | None = None,
) -> alert_templates.Message:
    """The Telegram text for one notification (see app/alert_templates.py)."""
    settings = get_settings()
    return alert_templates.render(
        incident_id=incident_id,
        event_type=event_type,
        severity=severity,
        title=title,
        message=message,
        details=details,
        dashboard_url=settings.dashboard_url,
        timezone=settings.alert_timezone,
    )


async def api_call(
    method: str, payload: dict, *, timeout: float | None = None
) -> tuple[bool, object | None, str | None]:
    """Call one Bot API method. Returns (ok, result, error) and never raises.

    The token is in the URL, so the URL and httpx's error text are never logged or returned.
    """
    settings = get_settings()
    if not settings.telegram_bot_token:
        return False, None, "Telegram is not configured"
    url = f"{API}/bot{settings.telegram_bot_token}/{method}"
    try:
        async with httpx.AsyncClient(
            timeout=timeout or settings.http_timeout_seconds, transport=transport, trust_env=False
        ) as client:
            response = await client.post(url, json=payload)
    except httpx.HTTPError as exc:
        return False, None, f"Could not reach Telegram ({type(exc).__name__})"
    try:
        body = response.json()
    except ValueError:
        return False, None, f"Telegram answered {response.status_code}"
    if response.status_code == 200 and body.get("ok"):
        return True, body.get("result"), None
    return False, None, f"Telegram answered {response.status_code}: {body.get('description', '')}"


async def send(
    text: str, *, silent: bool = False, buttons: list[list[dict]] | None = None, chat_id: str | None = None
) -> tuple[bool, str | None]:
    """Send one message to the configured chat. Returns (sent, error) and never raises."""
    settings = get_settings()
    if not (settings.telegram_bot_token and settings.telegram_chat_id):
        return False, "Telegram is not configured"
    payload = {
        "chat_id": chat_id or settings.telegram_chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
        "disable_notification": silent,
    }
    if buttons:
        payload["reply_markup"] = {"inline_keyboard": buttons}
    ok, _, error = await api_call("sendMessage", payload)
    deliveries.labels("sent" if ok else "failed").inc()
    return ok, error


# --- quiet mode (/quiet in the bot) -----------------------------------------------------------------
# Alerts keep arriving, without sound. Kept in memory: a restart turns sound back on.

_quiet_until: datetime | None = None


def quiet_until() -> datetime | None:
    if _quiet_until and _quiet_until <= datetime.now(UTC):
        set_quiet(None)
    return _quiet_until


def set_quiet(until: datetime | None) -> None:
    global _quiet_until
    _quiet_until = until


def alert_buttons(event_type: str, incident_id: str, details: dict | None) -> list[list[dict]] | None:
    """Action buttons under an alert. Only when the bot is listening for presses."""
    if not get_settings().telegram_commands_enabled:
        return None
    if event_type == "INCIDENT_RESOLVED":
        return [[{"text": "📊 Status", "callback_data": "status"}]]
    row = [{"text": "✅ Acknowledge", "callback_data": f"a-ack:{incident_id}"}]
    target_id = (details or {}).get("target_id")
    if target_id:
        row.append({"text": "▶ Check now", "callback_data": f"a-chk:{target_id}"})
    return [row, [{"text": "📊 Status", "callback_data": "status"}]]


async def forward(
    *,
    notification_id: str,
    incident_id: str,
    title: str,
    message: str,
    event_type: str,
    severity: str | None,
    details: dict | None = None,
) -> None:
    """Background task run after a notification is stored."""
    if not is_enabled():
        return
    rendered = format_message(
        incident_id=incident_id,
        title=title,
        message=message,
        event_type=event_type,
        severity=severity,
        details=details,
    )
    sent, error = await send(
        rendered.text,
        silent=rendered.silent or quiet_until() is not None,
        buttons=alert_buttons(event_type, incident_id, details),
    )
    if sent:
        logger.info("Notification sent to Telegram", extra={"notification_id": notification_id})
    else:
        logger.warning(
            "Telegram delivery failed", extra={"notification_id": notification_id, "error": error}
        )
