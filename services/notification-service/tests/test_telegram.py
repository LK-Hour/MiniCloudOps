"""Telegram channel: forwarded once per new notification, never blocks or leaks the token."""
import json
import logging

import httpx
import pytest

from app import telegram
from app.config import get_settings

TOKEN = "123456:TEST-secret-token"


@pytest.fixture
def sent():
    """Captures the requests sent to Telegram; answers 200 unless told otherwise."""
    calls: list[httpx.Request] = []
    state = {"status": 200, "body": {"ok": True}}

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(state["status"], json=state["body"])

    telegram.transport = httpx.MockTransport(handler)
    yield calls, state
    telegram.transport = None


@pytest.fixture
def configured(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "telegram_bot_token", TOKEN)
    monkeypatch.setattr(settings, "telegram_chat_id", "-1001")
    return settings


def test_disabled_by_default(client, sent, make_notification):
    make_notification()
    assert sent[0] == []
    assert client.get("/api/v1/notifications/channels").json()["telegram"] == {"enabled": False}


def test_new_notification_is_forwarded(client, sent, configured, make_notification):
    make_notification(title="[CRITICAL] Shop <API> is unavailable")
    calls, _ = sent
    assert len(calls) == 1
    assert calls[0].url.path == f"/bot{TOKEN}/sendMessage"
    body = json.loads(calls[0].content)
    assert body["chat_id"] == "-1001"
    assert body["parse_mode"] == "HTML"
    header, headline = body["text"].split("\n\n")[:2]
    assert header == "🔴 <b>CRITICAL · Incident opened</b>"
    assert headline.startswith("<b>Shop &lt;API&gt; is unavailable</b>")
    assert body["disable_notification"] is False  # critical alerts make a sound
    assert client.get("/api/v1/notifications/channels").json()["telegram"] == {"enabled": True}


def test_duplicate_is_not_forwarded_twice(client, sent, configured, make_notification):
    make_notification()
    again = client.post(
        "/api/v1/notifications",
        json={"incident_id": "inc-1", "event_type": "INCIDENT_CREATED", "title": "t", "message": "m"},
    )
    assert again.status_code == 200
    assert len(sent[0]) == 1


def test_resolved_uses_the_resolved_icon(sent, configured, make_notification):
    make_notification(event_type="INCIDENT_RESOLVED", severity=None)
    assert json.loads(sent[0][0].content)["text"].startswith("✅")


def test_telegram_failure_does_not_fail_the_api_or_log_the_token(sent, configured, make_notification, caplog):
    sent[1].update(status=400, body={"ok": False, "description": "Bad Request: chat not found"})
    with caplog.at_level(logging.INFO):
        stored = make_notification()  # still 201
    assert stored["delivery_status"] == "DELIVERED"
    failures = [r for r in caplog.records if r.getMessage() == "Telegram delivery failed"]
    assert failures and "chat not found" in failures[0].error
    assert TOKEN not in caplog.text


def test_unreachable_telegram_is_reported_without_the_url(configured, caplog):
    def boom(request):
        raise httpx.ConnectError(f"cannot connect to {request.url}")

    telegram.transport = httpx.MockTransport(boom)
    try:
        import asyncio

        ok, error = asyncio.run(telegram.send("hi"))
    finally:
        telegram.transport = None
    assert not ok
    assert error == "Could not reach Telegram (ConnectError)"
    assert TOKEN not in error


def test_test_endpoint(client, sent, configured):
    response = client.post("/api/v1/notifications/channels/telegram/test")
    assert response.status_code == 200
    assert response.json() == {"sent": True}
    sent[1].update(status=401, body={"ok": False, "description": "Unauthorized"})
    response = client.post("/api/v1/notifications/channels/telegram/test")
    assert response.status_code == 502
    assert "Unauthorized" in response.json()["error"]["message"]


def test_test_endpoint_when_not_configured(client):
    assert client.post("/api/v1/notifications/channels/telegram/test").status_code == 409
