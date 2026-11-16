"""API request metrics: labelled by route template, not by the raw path."""
from prometheus_client import REGISTRY


def _count(method: str, route: str, status: str) -> float:
    return REGISTRY.get_sample_value(
        "miniops_api_requests_total", {"method": method, "route": route, "status": status}
    ) or 0.0


def test_requests_are_counted_by_route_template(client):
    route = "/api/v1/targets/{target_id}"
    before = _count("GET", route, "404")
    client.get("/api/v1/targets/does-not-exist")
    client.get("/api/v1/targets/also-missing")
    assert _count("GET", route, "404") == before + 2


def test_health_and_metrics_are_not_counted(client):
    before = _count("GET", "/health", "200")
    client.get("/health")
    assert _count("GET", "/health", "200") == before
