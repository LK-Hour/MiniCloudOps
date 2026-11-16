"""Telegram templates: per severity, per failure kind, safe with any input."""

from datetime import UTC, datetime

import pytest

from app.alert_templates import duration, render

NOW = datetime(2026, 11, 16, 9, 10, 0, tzinfo=UTC)

OUTAGE = {
    "target_name": "Shop API",
    "target_url": "http://shop/health",
    "check_interval_seconds": 30,
    "failure_kind": "http_5xx",
    "error": "HTTP 503",
    "status_code": 503,
    "response_time_ms": 12.4,
    "consecutive_failures": 3,
    "failure_threshold": 3,
    "check_timeout_seconds": 5.0,
    "first_failed_at": "2026-11-16T09:08:30+00:00",
    "recent_checks": [
        {"status": "DOWN", "status_code": 503},
        {"status": "DOWN", "status_code": 503},
        {"status": "DOWN", "status_code": 503},
        {"status": "UP", "status_code": 200},
    ],
    "incident_status": "OPEN",
    "started_at": "2026-11-16T09:09:30+00:00",
}


def opened(**changes):
    details = {**OUTAGE, **changes}
    return render(
        incident_id="1610583c-d91a-4f6c-8932-caacb989baa7",
        event_type="INCIDENT_CREATED",
        severity=changes.pop("severity", "CRITICAL"),
        title="[CRITICAL] Shop API is unavailable",
        message="HTTP health check failed 3 times in a row",
        details=details,
        dashboard_url="http://localhost:3000",
        now=NOW,
    )


def test_critical_outage_shows_every_fact():
    message = opened()
    text = message.text
    assert text.startswith("🔴 <b>CRITICAL · Incident opened</b>\n\n<b>Shop API is unavailable</b>")
    for expected in [
        "Target    Shop API",
        "URL       http://shop/health",
        "Failure   HTTP 503 · Service Unavailable",
        "Response  12 ms",
        "Streak    3 failed checks in a row (threshold 3)",
        "Checked   every 30 s",
        "Failing   09:08:30 UTC · 16 Nov (1 min 30 s ago)",
        "✗ 503  ✗ 503  ✗ 503  ✓ 200",
        "🔎 <b>Likely cause</b>\nThe app reports itself unavailable",
        "🛠 <b>What to check</b>\n• The app's error logs",
        '<a href="http://localhost:3000/#/incidents/1610583c-d91a-4f6c-8932-caacb989baa7">',
    ]:
        assert expected in text, expected
    assert message.silent is False


@pytest.mark.parametrize(
    ("severity", "header", "silent"),
    [
        ("CRITICAL", "🔴 <b>CRITICAL · Incident opened</b>", False),
        ("WARNING", "🟠 <b>WARNING · Incident opened</b>", False),
        ("INFO", "🔵 <b>INFO · Incident opened</b>", True),
    ],
)
def test_style_follows_severity(severity, header, silent):
    message = opened(severity=severity)
    assert message.text.startswith(header)
    assert message.silent is silent


@pytest.mark.parametrize(
    ("changes", "cause", "failure"),
    [
        ({"status_code": 502, "error": "HTTP 502"}, "cannot reach it", "HTTP 502 · Bad Gateway"),
        (
            {"status_code": 404, "error": "HTTP 404", "failure_kind": "http_4xx"},
            "no longer exists",
            "Not Found",
        ),
        (
            {
                "status_code": None,
                "response_time_ms": None,
                "error": "Timed out after 5s",
                "failure_kind": "timeout",
            },
            "did not answer in time",
            "Timed out after 5s",
        ),
        (
            {
                "status_code": None,
                "response_time_ms": None,
                "error": "DNS lookup failed for 'shop'",
                "failure_kind": "dns",
            },
            "container is stopped",
            "DNS lookup failed for &#x27;shop&#x27;",
        ),
        (
            {
                "status_code": None,
                "response_time_ms": None,
                "error": "Connection failed (ConnectError)",
                "failure_kind": "connection",
            },
            "Nothing is accepting connections",
            "Connection failed (ConnectError)",
        ),
        ({"status_code": None, "error": "Connection failed", "failure_kind": "tls"}, "certificate", None),
    ],
)
def test_likely_cause_follows_the_failure(changes, cause, failure):
    text = opened(**changes).text
    assert cause in text
    if failure:
        assert failure in text


def test_timeout_says_how_long_it_waited():
    text = opened(
        status_code=None, response_time_ms=None, failure_kind="timeout", error="Timed out after 5s"
    ).text
    assert "Response  no answer within 5 s" in text


def test_recovery():
    message = render(
        incident_id="1610583c-d91a-4f6c-8932-caacb989baa7",
        event_type="INCIDENT_RESOLVED",
        severity="CRITICAL",
        title="[RESOLVED] Shop API is unavailable",
        message="Target recovered: health check passed",
        details={
            "target_name": "Shop API",
            "target_url": "http://shop/health",
            "status_code": 200,
            "response_time_ms": 35.2,
            "started_at": "2026-11-16T09:05:00+00:00",
            "resolved_at": "2026-11-16T09:09:12+00:00",
            "duration_seconds": 252,
        },
        timezone="Asia/Phnom_Penh",
        now=NOW,
    )
    text = message.text
    assert text.startswith("✅ <b>RESOLVED · Back to normal</b>\n\n<b>Shop API is back up</b>")
    assert "Now       HTTP 200 in 35 ms" in text
    assert "Downtime  4 min 12 s" in text
    assert "Started   16:05:00 +07 · 16 Nov" in text  # shown in the configured time zone
    assert message.silent is True  # good news does not need a sound
    assert "<a href" not in text  # no dashboard URL configured


def test_notification_without_details_falls_back_to_title_and_message():
    text = render(
        incident_id="inc-1",
        event_type="INCIDENT_CREATED",
        severity="WARNING",
        title="[WARNING] Disk almost full",
        message="Created by hand",
        details=None,
    ).text
    assert text.startswith("🟠 <b>WARNING · Incident opened</b>\n\n<b>Disk almost full</b>\nCreated by hand")


def test_everything_from_outside_is_escaped():
    text = opened(target_name="<b>evil</b>", target_url="http://x/?a=<script>", error="<i>").text
    assert "<b>evil</b>" not in text and "&lt;b&gt;evil&lt;/b&gt;" in text
    assert "<script>" not in text


def test_bad_values_do_not_break_rendering():
    text = opened(first_failed_at="not a date", recent_checks=[], consecutive_failures=None).text
    assert "Failing" not in text and "Streak" not in text and "Latest checks" not in text
    assert render(
        incident_id="x",
        event_type="INCIDENT_CREATED",
        severity=None,
        title="t",
        message="m",
        details={"target_url": "http://a/"},
        timezone="Not/AZone",
    ).text.startswith("⚪ <b>ALERT · Incident opened</b>")


@pytest.mark.parametrize(
    ("seconds", "text"), [(0, "0 s"), (59, "59 s"), (60, "1 min"), (252, "4 min 12 s"), (7260, "2 h 1 min")]
)
def test_duration(seconds, text):
    assert duration(seconds) == text
