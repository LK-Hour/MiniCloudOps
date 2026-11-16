"""Integration tests run against a live stack through the gateway, like the dashboard does.

    make demo          # the full stack plus the sandbox app the failure tests break on purpose
    make integration

Every test cleans up the targets and sandbox endpoints it creates. Incidents stay in the history
(the Incident Service keeps a permanent record by design).
"""
import os
import time
import uuid
from collections.abc import Callable

import httpx
import pytest

GATEWAY_URL = os.getenv("GATEWAY_URL", "http://localhost:8080")
# One list endpoint per service: answering it needs the service and its database.
SERVICES = {
    "target": "/api/v1/targets",
    "monitoring": "/api/v1/monitoring/targets",
    "incident": "/api/v1/incidents",
    "notification": "/api/v1/notifications",
}


@pytest.fixture(scope="session")
def api() -> httpx.Client:
    client = httpx.Client(base_url=GATEWAY_URL, timeout=15)
    try:
        client.get("/health").raise_for_status()
    except httpx.HTTPError:
        pytest.skip(f"MiniOps stack is not running at {GATEWAY_URL} (start it with `make demo`)")
    yield client
    client.close()


@pytest.fixture(scope="session")
def policy(api) -> dict:
    return api.get("/api/v1/monitoring/config").raise_for_status().json()


@pytest.fixture(scope="session")
def sandbox(api) -> None:
    """The sandbox app (docker compose --profile demo); failure tests need it."""
    try:
        ok = api.get("/api/v1/lab/health").status_code == 200
    except httpx.HTTPError:
        ok = False
    if not ok:
        pytest.skip("Sandbox app is not running (start the stack with `make demo`)")


@pytest.fixture
def run_id() -> str:
    """Tags every request of one test (X-Correlation-ID) so its logs can be found in Loki."""
    return f"it-{uuid.uuid4().hex[:8]}"


@pytest.fixture
def make_target(api, run_id):
    """Registers targets and deletes them after the test."""
    created: list[str] = []

    def _make(url: str, **fields) -> dict:
        body = {"name": f"Integration {run_id}", "target_url": url, "check_interval": 3600, **fields}
        response = api.post("/api/v1/targets", json=body, headers={"X-Correlation-ID": run_id})
        assert response.status_code == 201, response.text
        target = response.json()
        created.append(target["id"])
        return target

    yield _make
    for target_id in created:
        api.delete(f"/api/v1/targets/{target_id}")


@pytest.fixture
def endpoint(api, sandbox, run_id):
    """A sandbox endpoint whose health the test controls: endpoint.set(mode="down")."""

    class Endpoint:
        name = run_id
        url = f"http://demo-app/{run_id}/health"

        def set(self, **config) -> None:
            response = api.put(f"/api/v1/lab/endpoints/{self.name}", json=config)
            assert response.status_code == 200, response.text

    sandbox_endpoint = Endpoint()
    sandbox_endpoint.set(mode="healthy")
    yield sandbox_endpoint
    api.delete(f"/api/v1/lab/endpoints/{sandbox_endpoint.name}")


def wait_for(
    probe: Callable[[], object], *, timeout: float = 20, interval: float = 0.5, what: str = "condition"
):
    """Poll until probe() returns something truthy, and return it."""
    deadline = time.monotonic() + timeout
    while True:
        value = probe()
        if value:
            return value
        if time.monotonic() > deadline:
            raise AssertionError(f"Timed out after {timeout:.0f} s waiting for {what}")
        time.sleep(interval)
