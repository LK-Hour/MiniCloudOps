"""API tests for /api/v1/monitoring."""
from datetime import UTC, datetime

from app.prometheus import ContainerUsage, Infrastructure
from tests.conftest import make_target

API = "/api/v1/monitoring"


def test_versioned_health(client):
    response = client.get(f"{API}/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_custom_metrics_are_exposed(client):
    response = client.get(f"{API}/metrics")
    assert response.status_code == 200
    for name in ("miniops_health_check_total", "miniops_active_targets", "miniops_open_incidents"):
        assert name in response.text


# --- manual check ---------------------------------------------------------------------------------


def test_manual_check_records_result(client, target_service):
    target_service.add(make_target())
    response = client.post(f"{API}/check/t1")
    assert response.status_code == 200
    result = response.json()
    assert result["target_id"] == "t1"
    assert result["status"] == "UP"
    assert result["status_code"] == 200
    assert result["response_time_ms"] is not None
    assert target_service.reported == [("t1", "UP")]


def test_manual_check_of_unknown_target_returns_404(client):
    response = client.post(f"{API}/check/nope")
    assert response.status_code == 404
    assert response.json()["error"]["message"] == "Target 'nope' not found"


def test_manual_check_of_disabled_target_returns_409(client, target_service, apps):
    target_service.add(make_target(enabled=False))
    assert client.post(f"{API}/check/t1").status_code == 409
    assert apps.requests == []


def test_manual_check_when_target_service_down_returns_503(client, target_service):
    target_service.down = True
    response = client.post(f"{API}/check/t1")
    assert response.status_code == 503
    assert response.json()["error"]["message"] == "Target Service unavailable"


# --- status ---------------------------------------------------------------------------------------


def test_status_before_first_check_is_unknown(client, target_service):
    target_service.add(make_target())
    body = client.get(f"{API}/targets/t1/status").json()
    assert body["status"] == "UNKNOWN"
    assert body["consecutive_failures"] == 0
    assert body["last_checked_at"] is None


def test_status_after_failures(client, target_service, apps, prometheus):
    target_service.add(make_target())
    apps.set("demo-app", 503)
    client.post(f"{API}/check/t1")
    client.post(f"{API}/check/t1")

    body = client.get(f"{API}/targets/t1/status").json()
    assert body["status"] == "DOWN"
    assert body["consecutive_failures"] == 2
    assert body["last_checked_at"] is not None
    assert body["metrics_available"] is True
    assert body["cpu_percent"] == 12.5
    assert prometheus.asked == ["demo-app"]  # looked up by the URL's host


def test_status_when_prometheus_is_down_reports_null_not_zero(client, target_service, prometheus):
    target_service.add(make_target())
    prometheus.usage = ContainerUsage.unavailable()
    body = client.get(f"{API}/targets/t1/status").json()
    assert body["metrics_available"] is False
    assert body["cpu_percent"] is None
    assert body["memory_percent"] is None


def test_status_of_disabled_target_is_unknown(client, target_service):
    target = target_service.add(make_target())
    client.post(f"{API}/check/t1")
    target["enabled"] = False
    assert client.get(f"{API}/targets/t1/status").json()["status"] == "UNKNOWN"


def test_status_of_unknown_target_returns_404(client):
    assert client.get(f"{API}/targets/nope/status").status_code == 404


# --- history --------------------------------------------------------------------------------------


def test_history_is_newest_first_and_limited(client, target_service, apps):
    target_service.add(make_target())
    client.post(f"{API}/check/t1")
    apps.set("demo-app", 500)
    client.post(f"{API}/check/t1")
    client.post(f"{API}/check/t1")

    history = client.get(f"{API}/targets/t1/history", params={"limit": 2}).json()
    assert [h["status"] for h in history] == ["DOWN", "DOWN"]
    assert len(client.get(f"{API}/targets/t1/history").json()) == 3
    assert client.get(f"{API}/targets/t1/history", params={"limit": 0}).status_code == 422


def test_history_of_unchecked_target_is_empty(client):
    assert client.get(f"{API}/targets/never-checked/history").json() == []


# --- dashboard endpoints --------------------------------------------------------------------------


def test_targets_overview_returns_every_state_with_recent_checks(client, target_service, apps):
    target_service.add(make_target("t1"))
    target_service.add(make_target("t2", url="http://example.com/"))
    for _ in range(3):
        client.post(f"{API}/check/t1")
    apps.set("example.com", 500)
    client.post(f"{API}/check/t2")

    body = {t["target_id"]: t for t in client.get(f"{API}/targets", params={"recent": 2}).json()}
    assert set(body) == {"t1", "t2"}
    assert body["t1"]["status"] == "UP"
    assert len(body["t1"]["recent"]) == 2
    first, second = body["t1"]["recent"]
    assert first["checked_at"] <= second["checked_at"]  # oldest first, for charts
    assert body["t2"]["status"] == "DOWN"
    assert body["t2"]["consecutive_failures"] == 1


def test_targets_overview_is_empty_before_any_check(client):
    assert client.get(f"{API}/targets").json() == []


def test_infrastructure(client):
    body = client.get(f"{API}/infrastructure").json()
    assert body["available"] is True
    assert body["host"]["cpu_percent"] == 7.5
    assert body["host"]["disk_percent"] is None
    assert body["containers"][0]["service"] == "demo-app"
    assert body["services"] == [{"instance": "target-service:8000", "up": True}]


def test_infrastructure_when_prometheus_is_down(client, prometheus):
    prometheus.infra = Infrastructure(available=False, collected_at=datetime.now(UTC))
    body = client.get(f"{API}/infrastructure").json()
    assert body["available"] is False
    assert body["host"]["cpu_percent"] is None  # null, never 0
    assert body["containers"] == []


def test_monitoring_policy_is_exposed_read_only(client):
    body = client.get(f"{API}/config").json()
    assert body["failure_threshold"] == 3
    assert body["default_check_interval_seconds"] == 30
    assert "database_url" not in body  # only the policy, never connection settings
    assert client.put(f"{API}/config", json={}).status_code == 405


# --- time series ----------------------------------------------------------------------------------


def test_check_timeseries_buckets_checks(client, target_service):
    target_service.add(make_target())
    client.post(f"{API}/check/t1")
    body = client.get(f"{API}/timeseries?minutes=30").json()
    assert body["minutes"] == 30
    assert len(body["overall"]) == 60
    assert sum(b["checks"] for b in body["overall"]) == 1
    assert body["targets"][0]["target_id"] == "t1"
    empty = [b for b in body["overall"] if b["checks"] == 0]
    assert all(b["avg_ms"] is None for b in empty)  # gaps stay null, never 0


def test_target_timeseries_only_includes_that_target(client, target_service):
    target_service.add(make_target("t1"))
    target_service.add(make_target("t2"))
    client.post(f"{API}/check/t1")
    client.post(f"{API}/check/t2")
    body = client.get(f"{API}/targets/t1/timeseries").json()
    assert [t["target_id"] for t in body["targets"]] == ["t1"]


def test_infrastructure_history(client):
    body = client.get(f"{API}/infrastructure/history?minutes=60").json()
    assert body["available"] is True
    assert body["host"]["cpu"][1]["v"] == 9.0
    assert "demo-app" in body["containers"]


def test_target_resources(client, target_service):
    target_service.add(make_target())
    body = client.get(f"{API}/targets/t1/resources").json()
    assert body["cpu"][0]["v"] == 2.0
    assert body["memory"] == []
    assert client.get(f"{API}/targets/nope/resources").status_code == 404


def test_timeseries_rejects_silly_windows(client):
    assert client.get(f"{API}/timeseries?minutes=1").status_code == 422
