"""End-to-end flows from docs/MiniCloudOps.md §3.2 / §12, through the gateway.

The four services talk to each other over REST; these tests check the whole chain:
Target -> Monitoring -> Incident -> Notification, plus the logs it leaves in Loki.
"""
import pytest
from conftest import SERVICES, wait_for

# --- the platform is up ---------------------------------------------------------------------------


def test_gateway_is_healthy(api):
    assert api.get("/health").json()["status"] == "ok"


@pytest.mark.parametrize("path", SERVICES.values(), ids=SERVICES.keys())
def test_every_service_answers_from_its_database(api, path):
    """A list call reaches the service and its own database through the gateway."""
    response = api.get(path, params={"limit": 1})
    assert response.status_code == 200, response.text
    assert isinstance(response.json(), list)


# --- one service, through the gateway -------------------------------------------------------------


def test_target_lifecycle(api, make_target):
    target = make_target("http://demo-app/", name="Integration lifecycle")
    assert api.get(f"/api/v1/targets/{target['id']}").json()["name"] == "Integration lifecycle"

    updated = api.put(f"/api/v1/targets/{target['id']}", json={"enabled": False})
    assert updated.status_code == 200, updated.text
    assert updated.json()["enabled"] is False

    assert api.delete(f"/api/v1/targets/{target['id']}").status_code == 204
    assert api.get(f"/api/v1/targets/{target['id']}").status_code == 404


def test_invalid_target_is_rejected(api):
    response = api.post("/api/v1/targets", json={"name": "", "target_url": "not-a-url", "check_interval": 1})
    assert response.status_code == 422
    fields = {d["field"] for d in response.json()["error"]["details"]}
    assert {"body.name", "body.target_url", "body.check_interval"} <= fields


@pytest.mark.parametrize(
    "url",
    [
        "http://169.254.169.254/latest/meta-data/",  # cloud metadata
        "http://127.0.0.1:8080/",  # loopback
        "http://postgres:5432/",  # MiniOps's own infrastructure
    ],
)
def test_ssrf_targets_are_blocked(api, url):
    response = api.post("/api/v1/targets", json={"name": "SSRF probe", "target_url": url})
    assert response.status_code == 422, response.text


def test_log_api_is_read_only(api):
    assert api.post("/api/v1/logs/labels").status_code == 403


# --- services working together --------------------------------------------------------------------


def _first_scheduled_check(api, policy, target_id: str) -> dict:
    """The scheduler checks a new target on its next tick. Waiting for that check keeps it from
    landing in the middle of a test and counting as an extra failure."""
    return wait_for(
        lambda: (s := api.get(f"/api/v1/monitoring/targets/{target_id}/status")).status_code == 200
        and s.json()["last_checked_at"]
        and s.json(),
        timeout=policy["scheduler_tick_seconds"] + 15,
        what="the first scheduled check",
    )


def _check(api, target_id: str, run_id: str) -> dict:
    """Run a check now (Monitoring) and return the target's monitoring status."""
    headers = {"X-Correlation-ID": run_id}
    result = api.post(f"/api/v1/monitoring/check/{target_id}", headers=headers)
    assert result.status_code == 200, result.text
    return api.get(f"/api/v1/monitoring/targets/{target_id}/status").json()


def test_healthy_target_is_reported_up_to_the_target_service(api, policy, endpoint, make_target):
    target = make_target(endpoint.url)
    status = _first_scheduled_check(api, policy, target["id"])
    assert status["status"] == "UP"
    # Monitoring reports the status back to the Target Service.
    wait_for(lambda: api.get(f"/api/v1/targets/{target['id']}").json()["status"] == "UP", what="status UP")


def test_failure_creates_incident_and_notification_then_recovers(api, policy, endpoint, make_target, run_id):
    threshold = policy["failure_threshold"]
    target = make_target(endpoint.url)
    assert _first_scheduled_check(api, policy, target["id"])["status"] == "UP"

    # 1. The app goes down. Below the threshold there is no incident yet (debounce).
    endpoint.set(mode="down", status_code=503)
    for _ in range(threshold - 1):
        status = _check(api, target["id"], run_id)
        assert status["status"] == "DOWN"
        assert status["open_incident_id"] is None

    # 2. The threshold-th failure opens exactly one incident.
    status = _check(api, target["id"], run_id)
    incident_id = status["open_incident_id"]
    assert incident_id, status
    incident = api.get(f"/api/v1/incidents/{incident_id}").json()
    assert incident["status"] == "OPEN"
    assert incident["target_id"] == target["id"]
    assert incident["severity"] == "CRITICAL"

    # 3. The Incident Service asked the Notification Service to notify.
    created = wait_for(
        lambda: _notification(api, incident_id, "INCIDENT_CREATED"), what="the INCIDENT_CREATED notification"
    )
    assert target["name"] in created["title"]

    # 4. More failures do not open a second incident.
    _check(api, target["id"], run_id)
    incidents = api.get("/api/v1/incidents", params={"target_id": target["id"]}).json()
    assert [i["id"] for i in incidents if i["status"] != "RESOLVED"] == [incident_id]

    # 5. The app recovers: the next passing check resolves the incident and notifies again.
    endpoint.set(mode="healthy")
    status = _check(api, target["id"], run_id)
    assert status["status"] == "UP"
    assert status["consecutive_failures"] == 0
    resolved = wait_for(
        lambda: (i := api.get(f"/api/v1/incidents/{incident_id}").json())["status"] == "RESOLVED" and i,
        what="the incident to resolve",
    )
    assert resolved["resolved_at"]
    wait_for(
        lambda: _notification(api, incident_id, "INCIDENT_RESOLVED"), what="the RESOLVED notification"
    )

    # The incident's timeline records every step.
    events = [e["event_type"] for e in api.get(f"/api/v1/incidents/{incident_id}/history").json()]
    assert events[0] == "CREATED"
    assert {"NOTIFICATION_SENT", "RESOLVED"} <= set(events), events

    # 6. One correlation ID followed the request through the services into Loki.
    services = wait_for(lambda: _services_logging(api, run_id), timeout=90, interval=3, what="logs in Loki")
    assert {"monitoring-service", "incident-service", "notification-service"} <= services, services

    _mark_read(api, incident_id)


def test_slow_target_is_reported_down(api, policy, endpoint, make_target, run_id):
    """A response slower than the check timeout counts as a failure."""
    target = make_target(endpoint.url)
    _first_scheduled_check(api, policy, target["id"])
    endpoint.set(mode="slow", latency_ms=int(policy["check_timeout_seconds"] * 1000) + 1500)
    status = _check(api, target["id"], run_id)
    assert status["status"] == "DOWN"
    assert status["consecutive_failures"] == 1
    assert status["open_incident_id"] is None


# --- helpers --------------------------------------------------------------------------------------


def _notification(api, incident_id: str, event_type: str) -> dict | None:
    notifications = api.get("/api/v1/notifications", params={"incident_id": incident_id}).json()
    return next((n for n in notifications if n["event_type"] == event_type), None)


def _mark_read(api, incident_id: str) -> None:
    """Keep the dashboard's unread count for real incidents only."""
    for n in api.get("/api/v1/notifications", params={"incident_id": incident_id}).json():
        api.patch(f"/api/v1/notifications/{n['id']}/read")


def _services_logging(api, correlation_id: str) -> set[str] | None:
    response = api.get(
        "/api/v1/logs/query_range",
        params={
            "query": f'{{compose_project="miniops"}} |= "{correlation_id}"',
            "limit": 500,
            "since": "15m",
        },
    )
    if response.status_code != 200:
        return None
    services = {s["stream"].get("service") for s in response.json()["data"]["result"]}
    expected = {"monitoring-service", "incident-service", "notification-service"}
    return services if expected <= services else None
