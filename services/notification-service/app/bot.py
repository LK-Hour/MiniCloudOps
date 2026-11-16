"""Telegram bot commands: /status, /menu, /targets, /incidents, /check, /services, /quiet, /help.

MiniOps runs locally, so Telegram cannot call it (a webhook needs a public HTTPS address). Instead
the bot long-polls getUpdates: one request waits up to 25 s for new messages. It runs as a background
task of the Notification Service, which already owns the Telegram channel.

Only the configured TELEGRAM_CHAT_ID is answered: anyone can find a bot and message it, and the
bot can acknowledge and resolve incidents. Other chats are ignored and logged.
"""

import asyncio
import logging
import re
import time
import uuid
from datetime import UTC, datetime, timedelta
from html import unescape

from prometheus_client import Counter

from app import bot_views as views
from app import platform, telegram
from app.config import get_settings
from app.logging_config import correlation_id_var

logger = logging.getLogger(__name__)

POLL_SECONDS = 25
STALE_SECONDS = 120  # commands sent while the service was down are not answered late
QUIET_MAX_MINUTES = 24 * 60
NAVIGATION = {"menu", "status", "targets", "incidents", "services", "help"}

commands_total = Counter("miniops_telegram_commands_total", "Bot commands and button presses", ["command"])


def _clock() -> views.Clock:
    return views.Clock(get_settings().alert_timezone)


def _plain(html_text: str) -> str:
    return unescape(re.sub(r"<[^>]+>", "", html_text))


def _is_owner(chat: dict | None) -> bool:
    return chat is not None and str(chat.get("id")) == str(get_settings().telegram_chat_id)


# --- Telegram calls -------------------------------------------------------------------------------


async def reply(chat_id, view: views.View, *, reply_to: int | None = None) -> None:
    payload = {
        "chat_id": chat_id,
        "text": view.text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
        "reply_markup": {"inline_keyboard": view.buttons},
    }
    if reply_to:
        payload["reply_parameters"] = {"message_id": reply_to, "allow_sending_without_reply": True}
    ok, _, error = await telegram.api_call("sendMessage", payload)
    if not ok:
        logger.warning("Bot reply failed", extra={"error": error})


async def edit(chat_id, message_id: int, view: views.View) -> None:
    """Replace a menu message in place, so navigating does not flood the chat."""
    ok, _, error = await telegram.api_call(
        "editMessageText",
        {
            "chat_id": chat_id,
            "message_id": message_id,
            "text": view.text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
            "reply_markup": {"inline_keyboard": view.buttons},
        },
    )
    if not ok and "not modified" not in (error or ""):
        await reply(chat_id, view)  # too old to edit, or deleted: send it fresh


async def toast(callback_id: str, text: str = "", *, alert: bool = False) -> None:
    await telegram.api_call(
        "answerCallbackQuery", {"callback_query_id": callback_id, "text": text[:200], "show_alert": alert}
    )


# --- screens that need data -----------------------------------------------------------------------


async def build(name: str, arg: str | None = None) -> views.View:
    clock = _clock()
    if name == "menu":
        return views.menu(telegram.quiet_until(), clock)
    if name == "help":
        return views.help_view()
    if name == "services":
        return views.services(await platform.service_health(), clock)
    if name == "status":
        snap, health = await asyncio.gather(platform.snapshot(), platform.service_health())
        return views.status(snap, health, telegram.quiet_until(), clock)
    if name == "targets":
        return views.targets(await platform.snapshot(), clock)
    if name == "incidents":
        return views.incidents(await platform.snapshot(), clock)
    if name == "target" and arg:
        snap, history = await asyncio.gather(platform.snapshot(), platform.recent_checks(arg))
        return views.target(snap, arg, history, clock)
    return views.unknown_command()


def _set_quiet(arg: str | None) -> str:
    if arg and arg.lower() in {"off", "stop", "0"}:
        telegram.set_quiet(None)
        return "🔔 Alerts will make a sound again."
    try:
        minutes = int(arg) if arg else 30
    except ValueError:
        return "Use <code>/quiet 30</code> for 30 minutes, or <code>/quiet off</code>."
    minutes = max(1, min(minutes, QUIET_MAX_MINUTES))
    until = datetime.now(UTC) + timedelta(minutes=minutes)
    telegram.set_quiet(until)
    return (
        f"🔕 Alerts arrive <b>without sound</b> until {_clock().time(until)} ({minutes} min). "
        "They still arrive. <code>/quiet off</code> to undo."
    )


async def _check(target_id: str) -> tuple[str, str]:
    """Run a check now. Returns (message HTML, short plain summary for a toast)."""
    snap = await platform.snapshot()
    target = snap.target(target_id)
    name = target["name"] if target else target_id[:8]
    result = await platform.check_now(target_id)
    text = views.check_result(name, result.ok, result.message, result.data)
    return text, _plain(text)


async def _set_incident(incident_id: str, status: str, user: dict | None) -> tuple[bool, str]:
    who = (user or {}).get("first_name") or "Telegram"
    verb = "Acknowledged" if status == "ACKNOWLEDGED" else "Resolved"
    result = await platform.set_incident_status(incident_id, status, f"{verb} in Telegram by {who}")
    if not result.ok:
        return False, f"⚠️ {result.message}"
    title = (result.data or {}).get("title", incident_id[:8])
    icon = "✅" if status == "ACKNOWLEDGED" else "✔"
    return True, f"{icon} {verb}: {title}"


# --- commands -------------------------------------------------------------------------------------


async def on_command(message: dict) -> None:
    chat_id = message["chat"]["id"]
    text = (message.get("text") or "").strip()
    if not text.startswith("/"):
        await reply(chat_id, views.View("Send /menu to see what I can do.", [views.BACK]))
        return
    head, _, rest = text.partition(" ")
    command = head[1:].split("@", 1)[0].lower()  # "/status@MiniOpsBot" in groups
    arg = rest.strip() or None
    commands_total.labels(
        command if command in dict(views.COMMANDS) or command == "start" else "unknown"
    ).inc()
    logger.info("Bot command", extra={"command": command})

    if command in {"start", "menu"}:
        await reply(chat_id, await build("menu"))
    elif command in NAVIGATION:
        await reply(chat_id, await build(command))
    elif command == "quiet":
        await reply(chat_id, views.View(_set_quiet(arg), [views.BACK]))
    elif command == "check":
        await _check_command(chat_id, arg)
    else:
        await reply(chat_id, views.unknown_command())


async def _check_command(chat_id, query: str | None) -> None:
    snap = await platform.snapshot()
    if snap.targets is None:
        await reply(chat_id, views.View("⚠️ The Target Service is unavailable.", [views.BACK]))
        return
    matches = []
    if query:
        q = query.lower()
        exact = [t for t in snap.targets if t["name"].lower() == q]
        matches = exact or [t for t in snap.targets if q in t["name"].lower()]
    if len(matches) != 1:
        await reply(chat_id, views.choose_target(snap, query or ""))
        return
    target = matches[0]
    text, _ = await _check(target["id"])
    await reply(
        chat_id,
        views.View(
            text,
            [
                [
                    views.button("🔄 Check again", f"chk:{target['id']}"),
                    views.button("🔍 Details", f"tgt:{target['id']}"),
                ]
            ],
        ),
    )


# --- buttons --------------------------------------------------------------------------------------


async def on_button(query: dict) -> None:
    data = query.get("data") or ""
    message = query.get("message") or {}
    chat_id = message.get("chat", {}).get("id")
    message_id = message.get("message_id")
    kind, _, arg = data.partition(":")
    commands_total.labels(f"button:{kind}").inc()

    if data in NAVIGATION:
        await toast(query["id"])
        await edit(chat_id, message_id, await build(data))
    elif kind == "tgt":
        await toast(query["id"])
        await edit(chat_id, message_id, await build("target", arg))
    elif kind == "chk":  # a press is answered once, so the toast carries the result
        _, summary = await _check(arg)
        await toast(query["id"], summary)
        await edit(chat_id, message_id, await build("target", arg))
    elif kind in {"ack", "res"}:
        ok, text = await _set_incident(
            arg, "ACKNOWLEDGED" if kind == "ack" else "RESOLVED", query.get("from")
        )
        await toast(query["id"], text, alert=not ok)
        await edit(chat_id, message_id, await build("incidents"))
    elif kind == "a-ack":  # pressed under an alert: keep the alert, answer below it
        ok, text = await _set_incident(arg, "ACKNOWLEDGED", query.get("from"))
        await toast(query["id"], text, alert=not ok)
        if ok:
            await _drop_button(chat_id, message_id, message, data)
            await reply(chat_id, views.View(text, []), reply_to=message_id)
    elif kind == "a-chk":
        text, summary = await _check(arg)
        await toast(query["id"], summary)
        await reply(
            chat_id,
            views.View(
                text,
                [[views.button("🔄 Check again", f"a-chk:{arg}"), views.button("🔍 Details", f"tgt:{arg}")]],
            ),
            reply_to=message_id,
        )
    elif kind == "quiet":
        text = _set_quiet(arg)
        await toast(query["id"], _plain(text))
        await edit(chat_id, message_id, await build("menu"))
    else:
        await toast(query["id"], "This button is no longer supported.")


async def _drop_button(chat_id, message_id: int, message: dict, data: str) -> None:
    """Remove one button from a message, keeping the rest."""
    keyboard = (message.get("reply_markup") or {}).get("inline_keyboard") or []
    remaining = [[b for b in row if b.get("callback_data") != data] for row in keyboard]
    remaining = [row for row in remaining if row]
    await telegram.api_call(
        "editMessageReplyMarkup",
        {"chat_id": chat_id, "message_id": message_id, "reply_markup": {"inline_keyboard": remaining}},
    )


# --- the loop -------------------------------------------------------------------------------------


async def handle(update: dict) -> None:
    correlation_id_var.set(f"tg-{update.get('update_id', uuid.uuid4().hex[:8])}")
    if "callback_query" in update:
        query = update["callback_query"]
        if not _is_owner((query.get("message") or {}).get("chat")):
            logger.warning(
                "Bot button from an unknown chat ignored", extra={"user_id": query.get("from", {}).get("id")}
            )
            await toast(query["id"], "This bot is private.", alert=True)
            return
        await on_button(query)
    elif "message" in update:
        message = update["message"]
        if not _is_owner(message.get("chat")):
            logger.warning(
                "Bot message from an unknown chat ignored",
                extra={"chat_id": message.get("chat", {}).get("id")},
            )
            return
        if time.time() - message.get("date", 0) > STALE_SECONDS:
            return
        await on_command(message)


async def register_commands() -> None:
    """The list Telegram shows when you type "/" in the chat."""
    ok, _, error = await telegram.api_call(
        "setMyCommands", {"commands": [{"command": c, "description": d} for c, d in views.COMMANDS]}
    )
    if not ok:
        logger.warning("Could not register bot commands", extra={"error": error})


async def run() -> None:
    """Poll for updates until cancelled. Survives Telegram outages with backoff."""
    await register_commands()
    logger.info("Telegram bot listening for commands")
    offset: int | None = None
    delay = 1.0
    while True:
        payload = {"timeout": POLL_SECONDS, "allowed_updates": ["message", "callback_query"]}
        if offset is not None:
            payload["offset"] = offset
        ok, updates, error = await telegram.api_call("getUpdates", payload, timeout=POLL_SECONDS + 10)
        if not ok:
            logger.warning("Telegram polling failed; retrying", extra={"error": error, "retry_in_s": delay})
            await asyncio.sleep(delay)
            delay = min(delay * 2, 60)
            continue
        delay = 1.0
        for update in updates or []:
            offset = update["update_id"] + 1
            try:
                await handle(update)
            except Exception:  # one bad update must not stop the bot
                logger.exception("Bot update failed")
