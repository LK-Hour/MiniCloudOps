"""Unit tests for the check logic, incident rules and scheduler (app/monitor.py)."""
import asyncio

import httpx
import pytest

from app.probe import probe
from tests.conftest import make_target


def check(monitor, target):
    return asyncio.run(monitor.check_target(target))


def check_n(monitor, target, n):
    return [check(monitor, target) for _ in range(n)]


# --- the HTTP check -------------------------------------------------------------------------------


def test_healthy_target_is_up(monitor):
    result = check(monitor, make_target())
    assert (result.status, result.status_code, result.error) == ("UP", 200, None)
    assert result.response_time_ms is not None


def test_server_error_is_down_with_status_code(monitor, apps):
    apps.set("demo-app", 500)
    result = check(monitor, make_target())
    assert (result.status, result.status_code, result.error) == ("DOWN", 500, "HTTP 500")


def test_unreachable_target_has_no_response_time(monitor, apps):
    apps.set("demo-app", httpx.ConnectError)
    result = check(monitor, make_target())
    assert result.status == "DOWN"
    assert result.response_time_ms is None  # null, never 0
    assert result.error == "Connection failed (ConnectError)"


def test_timeout_is_down(monitor, apps):
    apps.set("demo-app", httpx.ReadTimeout)
    result = check(monitor, make_target())
    assert result.status == "DOWN"
    assert result.error.startswith("Timed out")


def test_redirect_is_not_followed(monitor, apps):
    apps.set("demo-app", 302)
    result = check(monitor, make_target())
    assert (result.status, result.status_code) == ("UP", 302)
    assert len(apps.requests) == 1  # "http://elsewhere/" was never requested


def test_ssrf_is_rechecked_before_each_request(monitor, apps):
    result = check(monitor, make_target(url="http://rebound.example/"))
    assert result.status == "DOWN"
    assert result.error.startswith("Blocked:") and "loopback" in result.error
    assert apps.requests == []  # no request was sent


def test_unresolvable_host_is_down_not_blocked(monitor, apps):
    result = check(monitor, make_target(url="http://stopped-container/"))
    assert result.status == "DOWN"
    assert result.error == "DNS lookup failed for 'stopped-container'"
    assert apps.requests == []


# --- incident rules -------------------------------------------------------------------------------


def test_incident_opens_after_threshold_consecutive_failures(monitor, apps, incident_service):
    apps.set("demo-app", 503)
    target = make_target()
    check_n(monitor, target, 2)
    assert incident_service.opened == []

    check(monitor, target)
    assert len(incident_service.opened) == 1
    incident = incident_service.opened[0]
    assert incident["target_id"] == "t1"
    assert incident["severity"] == "CRITICAL"
    assert incident["title"] == "App t1 is unavailable"
    assert monitor.get_state("t1").open_incident_id == "inc-1"


def test_repeated_failures_do_not_duplicate_the_incident(monitor, apps, incident_service):
    apps.set("demo-app", 503)
    check_n(monitor, make_target(), 6)
    assert len(incident_service.opened) == 1


def test_a_success_resets_the_failure_count(monitor, apps, incident_service):
    target = make_target()
    apps.set("demo-app", 503)
    check_n(monitor, target, 2)
    apps.set("demo-app", 200)
    check(monitor, target)
    apps.set("demo-app", 503)
    check_n(monitor, target, 2)
    assert incident_service.opened == []
    assert monitor.get_state("t1").consecutive_failures == 2


def test_recovery_resolves_the_incident(monitor, apps, incident_service, target_service):
    target = make_target()
    apps.set("demo-app", 503)
    check_n(monitor, target, 3)
    apps.set("demo-app", 200)
    check(monitor, target)

    assert incident_service.resolved == ["inc-1"]
    state = monitor.get_state("t1")
    assert (state.status, state.open_incident_id) == ("UP", None)
    assert target_service.reported[-1] == ("t1", "UP")


def test_incident_service_outage_is_retried_on_next_check(monitor, apps, incident_service):
    target = make_target()
    apps.set("demo-app", 503)
    incident_service.down = True
    check_n(monitor, target, 3)
    assert monitor.get_state("t1").open_incident_id is None  # health check still recorded
    assert len(monitor.history("t1", 10)) == 3

    incident_service.down = False
    check(monitor, target)
    assert len(incident_service.opened) == 1


def test_failed_resolve_is_retried(monitor, apps, incident_service):
    target = make_target()
    apps.set("demo-app", 503)
    check_n(monitor, target, 3)
    apps.set("demo-app", 200)
    incident_service.down = True
    check(monitor, target)
    assert monitor.get_state("t1").open_incident_id == "inc-1"

    incident_service.down = False
    check(monitor, target)
    assert incident_service.resolved == ["inc-1"]


# --- scheduler ------------------------------------------------------------------------------------


def run_ticks(monitor, ticks=1):
    async def scenario():
        for _ in range(ticks):
            await monitor.tick()
            await monitor.wait_for_checks()

    asyncio.run(scenario())


def test_tick_checks_each_enabled_target_once_per_interval(monitor, target_service, apps):
    target_service.add(make_target("t1"))
    target_service.add(make_target("t2", url="http://example.com/"))
    target_service.add(make_target("t3", enabled=False))

    run_ticks(monitor, ticks=3)  # all within one 30s interval
    assert sorted(r.url.host for r in apps.requests) == ["demo-app", "example.com"]
    assert monitor.get_state("t3") is None


def test_tick_skips_round_when_target_service_is_down(monitor, target_service, apps):
    target_service.add(make_target())
    run_ticks(monitor)
    target_service.down = True
    run_ticks(monitor)
    assert monitor.get_state("t1").status == "UP"  # nothing reset


def test_disabled_target_releases_its_incident(monitor, target_service, apps, incident_service):
    target = target_service.add(make_target())
    apps.set("demo-app", 503)
    check_n(monitor, target, 3)
    assert monitor.get_state("t1").open_incident_id == "inc-1"

    target["enabled"] = False
    run_ticks(monitor)
    assert incident_service.resolved == ["inc-1"]
    state = monitor.get_state("t1")
    assert (state.status, state.consecutive_failures, state.open_incident_id) == ("UNKNOWN", 0, None)


def test_target_name_metric_follows_renames():
    from app import metrics

    metrics.set_target_name("t-rename", "Shop")
    metrics.set_target_name("t-rename", "Shop API")
    samples = [
        s.labels["name"]
        for s in metrics.TARGET_INFO.collect()[0].samples
        if s.labels["target_id"] == "t-rename"
    ]
    assert samples == ["Shop API"]


def test_target_names_of_removed_targets_are_dropped():
    from app import metrics

    metrics.set_target_name("t-keep", "Keep")
    metrics.set_target_name("t-gone", "Gone")
    metrics.keep_target_names({"t-keep"})
    ids = {s.labels["target_id"] for s in metrics.TARGET_INFO.collect()[0].samples}
    assert "t-keep" in ids and "t-gone" not in ids


# --- alert details ---------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("outcome", "kind"),
    [
        (503, "http_5xx"),
        (404, "http_4xx"),
        (httpx.ReadTimeout, "timeout"),
        (httpx.ConnectError, "connection"),
        (httpx.RemoteProtocolError, "protocol"),
    ],
)
def test_failures_are_classified(apps, outcome, kind):
    apps.set("demo-app", outcome)
    assert _probe(apps).failure_kind == kind


def test_healthy_probe_has_no_failure_kind(apps):
    assert _probe(apps).failure_kind is None


def test_tls_failure_is_classified(apps):
    def handler(request):
        raise httpx.ConnectError("[SSL: CERTIFICATE_VERIFY_FAILED] certificate has expired", request=request)

    result = asyncio.run(probe("https://demo-app/", timeout=1, transport=httpx.MockTransport(handler)))
    assert result.failure_kind == "tls"
    assert "certificate" not in result.error  # the raw text is never stored


def _probe(apps):
    return asyncio.run(
        probe("http://demo-app/health", timeout=1, transport=httpx.MockTransport(apps.handler))
    )


def test_incident_carries_the_outage_details(monitor, apps, incident_service):
    target = make_target()
    check(monitor, target)  # one healthy check before the outage
    apps.set("demo-app", 503)
    check_n(monitor, target, 3)

    context = incident_service.opened[0]["context"]
    assert context["target_id"] == "t1"
    assert context["target_name"] == "App t1"
    assert context["target_url"] == "http://demo-app/health"
    assert context["failure_kind"] == "http_5xx"
    assert context["status_code"] == 503
    assert context["error"] == "HTTP 503"
    assert context["consecutive_failures"] == 3
    assert context["failure_threshold"] == 3
    assert context["check_interval_seconds"] == 30
    statuses = [c["status"] for c in context["recent_checks"]]
    assert statuses == ["DOWN", "DOWN", "DOWN", "UP"]  # newest first
    assert context["first_failed_at"] == context["recent_checks"][2]["checked_at"]


def test_resolution_carries_the_recovery_details(monitor, apps, incident_service):
    target = make_target()
    apps.set("demo-app", 503)
    check_n(monitor, target, 3)
    apps.set("demo-app", 200)
    check(monitor, target)

    context = incident_service.resolve_contexts[0]
    assert context["target_name"] == "App t1"
    assert context["status_code"] == 200
    assert context["response_time_ms"] is not None
    assert context["recovered_at"]
