"""End-to-end flow from docs/MiniCloudOps.md §3.2 / §12. Needs the stack running (`make up`)."""
import pytest


def test_gateway_is_healthy(api):
    assert api.get("/health").json()["status"] == "ok"


def test_monitoring_service_reachable_through_gateway(api):
    response = api.get("/api/v1/monitoring/health")
    assert response.status_code == 200


@pytest.mark.skip(reason="TODO: enable once the Target, Monitoring and Incident services are implemented")
def test_failure_creates_incident_and_notification(api):
    # 1. Register a target that points at an unreachable URL.
    # 2. Trigger checks until the failure threshold is reached.
    # 3. Assert an OPEN incident exists for the target.
    # 4. Assert a notification exists for that incident.
    ...
