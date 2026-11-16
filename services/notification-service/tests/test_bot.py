"""Telegram bot: commands, buttons, access control, quiet mode. Telegram and the other MiniOps
services are both faked with httpx.MockTransport."""

import asyncio
import json
import time
from datetime import UTC, datetime, timedelta

import httpx
import pytest

from app import bot, bot_views, platform, telegram
from app.config import get_settings

OWNER = "424242"
NOW = datetime.now(UTC)

TARGETS = [
    {
        "id": "t-shop",
        "name": "Shop API",
        "target_url": "http://shop/health",
        "enabled": True,
        "status": "DOWN",
        "check_interval": 30,
    },
    {
        "id": "t-blog",
        "name": "Blog",
        "target_url": "http://blog/",
        "enabled": True,
        "status": "UP",
        "check_interval": 60,
    },
    {
        "id": "t-old",
        "name": "Old <site>",
        "target_url": "http://old/",
        "enabled": False,
        "status": "UNKNOWN",
        "check_interval": 60,
    },
]
STATES = [
    {
        "target_id": "t-shop",
        "status": "DOWN",
        "consecutive_failures": 4,
        "last_checked_at": (NOW - timedelta(seconds=20)).isoformat(),
        "last_response_time_ms": 8.0,
        "open_incident_id": "inc-1111-aaaa",
        "recent": [],
    },
    {
        "target_id": "t-blog",
        "status": "UP",
        "consecutive_failures": 0,
        "last_checked_at": NOW.isoformat(),
        "last_response_time_ms": 41.6,
        "open_incident_id": None,
        "recent": [],
    },
]
INCIDENT = {
    "id": "inc-1111-aaaa",
    "target_id": "t-shop",
    "title": "Shop API is unavailable",
    "severity": "CRITICAL",
    "status": "OPEN",
    "created_at": (NOW - timedelta(minutes=3)).isoformat(),
}


class FakeMiniOps:
    """The Target, Monitoring and Incident services."""

    def __init__(self):
        self.calls: list[httpx.Request] = []
        self.down: set[str] = set()

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.calls.append(request)
        host, path = request.url.host, request.url.path
        if host.split("-")[0] in self.down:
            raise httpx.ConnectError("down", request=request)
        if path.endswith("/health/ready"):
            return httpx.Response(200, json={"status": "ready"})
        if host == "target-service" and path == "/api/v1/targets":
            return httpx.Response(200, json=TARGETS)
        if host == "monitoring-service" and path == "/api/v1/monitoring/targets":
            return httpx.Response(200, json=STATES)
        if host == "monitoring-service" and path.endswith("/history"):
            return httpx.Response(200, json=[{"status": "DOWN", "status_code": 503, "error": "HTTP 503"}] * 3)
        if host == "monitoring-service" and path.startswith("/api/v1/monitoring/check/"):
            return httpx.Response(
                200,
                json={
                    "target_id": path.rsplit("/", 1)[1],
                    "status": "UP",
                    "status_code": 200,
                    "response_time_ms": 33.3,
                    "checked_at": NOW.isoformat(),
                },
            )
        if host == "incident-service" and path == "/api/v1/incidents":
            status = request.url.params.get("status")
            return httpx.Response(200, json=[INCIDENT] if status == "OPEN" else [])
        if host == "incident-service" and path.endswith("/status"):
            body = json.loads(request.content)
            return httpx.Response(200, json={**INCIDENT, "status": body["status"]})
        return httpx.Response(404, json={"error": {"message": "not found"}})


class FakeTelegram:
    def __init__(self):
        self.calls: list[tuple[str, dict]] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        method = request.url.path.rsplit("/", 1)[1]
        self.calls.append((method, json.loads(request.content)))
        return httpx.Response(200, json={"ok": True, "result": {"message_id": 99}})

    def sent(self, method="sendMessage") -> list[dict]:
        return [p for m, p in self.calls if m == method]


@pytest.fixture
def tg(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "telegram_bot_token", "123:secret")
    monkeypatch.setattr(settings, "telegram_chat_id", OWNER)
    monkeypatch.setattr(settings, "alert_timezone", "UTC")
    fake_tg, fake_ops = FakeTelegram(), FakeMiniOps()
    telegram.transport = httpx.MockTransport(fake_tg.handler)
    platform.transport = httpx.MockTransport(fake_ops.handler)
    telegram.set_quiet(None)
    yield fake_tg, fake_ops
    telegram.transport = platform.transport = None
    telegram.set_quiet(None)


def message(text: str, chat: str = OWNER, age: float = 0) -> dict:
    return {
        "update_id": 1,
        "message": {
            "message_id": 5,
            "date": int(time.time() - age),
            "chat": {"id": int(chat)},
            "text": text,
            "from": {"id": 1, "first_name": "Kim"},
        },
    }


def press(data: str, chat: str = OWNER, keyboard=None) -> dict:
    return {
        "update_id": 2,
        "callback_query": {
            "id": "cb1",
            "data": data,
            "from": {"id": 1, "first_name": "Kim"},
            "message": {
                "message_id": 7,
                "chat": {"id": int(chat)},
                "reply_markup": {"inline_keyboard": keyboard or []},
            },
        },
    }


def run(update):
    asyncio.run(bot.handle(update))


# --- access ---------------------------------------------------------------------------------------


def test_strangers_are_ignored(tg):
    fake_tg, fake_ops = tg
    run(message("/status", chat="999"))
    assert fake_tg.calls == [] and fake_ops.calls == []


def test_strangers_pressing_buttons_are_refused(tg):
    fake_tg, fake_ops = tg
    run(press("ack:inc-1111-aaaa", chat="999"))
    assert fake_tg.sent("answerCallbackQuery")[0]["text"] == "This bot is private."
    assert fake_ops.calls == []  # nothing was acknowledged


def test_old_commands_are_not_answered_late(tg):
    run(message("/status", age=600))
    assert tg[0].calls == []


# --- commands -------------------------------------------------------------------------------------


def test_status(tg):
    run(message("/status"))
    text = tg[0].sent()[0]["text"]
    assert "🟢 1 up · 🔴 1 down · ⏸ 1 paused" in text
    assert "🚨 1 open · 👀 0 acknowledged" in text
    assert "✅ 4/4 healthy" in text
    assert "🔴 Shop API · 4 failed checks" in text


def test_status_when_a_service_is_down(tg):
    tg[1].down.add("incident")
    run(message("/status"))
    text = tg[0].sent()[0]["text"]
    assert "Incidents  ⚠️ unavailable" in text
    assert "incident service unreachable" in text
    assert "⚠️ 3/4 healthy" in text


def test_menu_and_start_show_buttons(tg):
    for command in ("/menu", "/start"):
        run(message(command))
    for sent in tg[0].sent():
        labels = [b["text"] for row in sent["reply_markup"]["inline_keyboard"] for b in row]
        assert {"📊 Status", "📋 Targets", "🚨 Incidents", "🩺 Services", "🔕 Quiet 30 min"} <= set(labels)


def test_targets_are_listed_worst_first_and_escaped(tg):
    run(message("/targets"))
    text = tg[0].sent()[0]["text"]
    assert text.index("Shop API") < text.index("Blog") < text.index("Old &lt;site&gt;")
    assert "<site>" not in text
    assert "42 ms" in text  # Blog's response time


def test_incidents_have_action_buttons(tg):
    run(message("/incidents"))
    sent = tg[0].sent()[0]
    data = [b["callback_data"] for row in sent["reply_markup"]["inline_keyboard"] for b in row]
    assert "ack:inc-1111-aaaa" in data and "res:inc-1111-aaaa" in data


def test_check_by_name_runs_a_check(tg):
    run(message("/check shop"))
    checks = [c for c in tg[1].calls if c.url.path == "/api/v1/monitoring/check/t-shop"]
    assert len(checks) == 1 and checks[0].method == "POST"
    assert "🟢 <b>Shop API</b> is UP: HTTP 200 in 33 ms" in tg[0].sent()[0]["text"]


def test_check_without_a_match_offers_the_targets(tg):
    run(message("/check nothing"))
    sent = tg[0].sent()[0]
    assert "No target matches" in sent["text"]
    data = [b["callback_data"] for row in sent["reply_markup"]["inline_keyboard"] for b in row]
    assert "chk:t-shop" in data and "chk:t-old" not in data  # paused targets are not offered


def test_command_with_bot_name_suffix(tg):
    run(message("/help@MiniOpsBot"))
    assert "/status" in tg[0].sent()[0]["text"]


def test_unknown_command_shows_help(tg):
    run(message("/dance"))
    assert "I don't know that command" in tg[0].sent()[0]["text"]


# --- buttons --------------------------------------------------------------------------------------


def test_navigation_edits_the_message_in_place(tg):
    run(press("targets"))
    assert tg[0].sent("editMessageText")[0]["message_id"] == 7
    assert tg[0].sent() == []


def test_acknowledge_button_records_who_did_it(tg):
    run(press("ack:inc-1111-aaaa"))
    patch = next(c for c in tg[1].calls if c.method == "PATCH")
    assert json.loads(patch.content) == {"status": "ACKNOWLEDGED", "note": "Acknowledged in Telegram by Kim"}
    assert tg[0].sent("answerCallbackQuery")[0]["text"].startswith("✅ Acknowledged")


def test_acknowledge_from_an_alert_removes_only_that_button(tg):
    keyboard = [
        [
            {"text": "✅ Acknowledge", "callback_data": "a-ack:inc-1111-aaaa"},
            {"text": "▶ Check now", "callback_data": "a-chk:t-shop"},
        ]
    ]
    run(press("a-ack:inc-1111-aaaa", keyboard=keyboard))
    markup = tg[0].sent("editMessageReplyMarkup")[0]["reply_markup"]["inline_keyboard"]
    assert markup == [[{"text": "▶ Check now", "callback_data": "a-chk:t-shop"}]]
    assert tg[0].sent()[0]["reply_parameters"]["message_id"] == 7  # answered below the alert


def test_check_button_reports_the_result_in_the_toast(tg):
    run(press("chk:t-shop"))
    toasts = tg[0].sent("answerCallbackQuery")
    assert len(toasts) == 1  # Telegram accepts one answer per press
    assert toasts[0]["text"] == "🟢 Shop API is UP: HTTP 200 in 33 ms"


# --- quiet mode and alerts ------------------------------------------------------------------------


def test_quiet_makes_alerts_silent_but_still_sent(tg):
    run(message("/quiet 45"))
    assert telegram.quiet_until() is not None
    assert "without sound" in tg[0].sent()[0]["text"]

    asyncio.run(
        telegram.forward(
            notification_id="n1",
            incident_id="inc-2",
            title="[CRITICAL] X is down",
            message="m",
            event_type="INCIDENT_CREATED",
            severity="CRITICAL",
        )
    )
    alert = tg[0].sent()[-1]
    assert alert["disable_notification"] is True

    run(message("/quiet off"))
    assert telegram.quiet_until() is None


def test_quiet_rejects_nonsense(tg):
    run(message("/quiet soon"))
    assert telegram.quiet_until() is None
    assert "/quiet 30" in tg[0].sent()[0]["text"]


def test_alerts_carry_action_buttons(tg):
    asyncio.run(
        telegram.forward(
            notification_id="n1",
            incident_id="inc-2",
            title="[CRITICAL] X is down",
            message="m",
            event_type="INCIDENT_CREATED",
            severity="CRITICAL",
            details={"target_id": "t-x", "target_url": "http://x/"},
        )
    )
    keyboard = tg[0].sent()[-1]["reply_markup"]["inline_keyboard"]
    data = [b["callback_data"] for row in keyboard for b in row]
    assert data == ["a-ack:inc-2", "a-chk:t-x", "status"]


def test_no_alert_buttons_when_commands_are_off(tg, monkeypatch):
    monkeypatch.setattr(get_settings(), "telegram_commands_enabled", False)
    assert telegram.alert_buttons("INCIDENT_CREATED", "inc-2", {"target_id": "t"}) is None


def test_commands_are_registered_with_telegram(tg):
    asyncio.run(bot.register_commands())
    commands = tg[0].sent("setMyCommands")[0]["commands"]
    assert [c["command"] for c in commands] == [name for name, _ in bot_views.COMMANDS]


def test_polling_survives_a_bad_update(tg, monkeypatch):
    """One failing update is logged and skipped; the next one is still handled."""
    updates = [{"update_id": 10, "message": "not a dict"}, message("/help") | {"update_id": 11}]
    handled = []

    async def fake_api_call(method, payload, timeout=None):
        if method == "getUpdates":
            if handled:  # second poll: stop the loop
                raise asyncio.CancelledError
            handled.append(payload)
            return True, updates, None
        tg[0].calls.append((method, payload))
        return True, {}, None

    monkeypatch.setattr(telegram, "api_call", fake_api_call)
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(bot.run())
    assert any("/status" in p.get("text", "") for m, p in tg[0].calls if m == "sendMessage")
