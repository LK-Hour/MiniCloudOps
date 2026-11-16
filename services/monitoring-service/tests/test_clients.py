"""The real HTTP clients against a mock transport: retries, pagination, Prometheus parsing."""
import asyncio

import httpx
import pytest

from app import http_client
from app.clients import IncidentServiceClient, ServiceUnavailable, TargetServiceClient
from app.prometheus import PrometheusClient


@pytest.fixture
def transport(monkeypatch):
    """Route outbound service calls to `handler` and make retry backoff instant."""
    calls: list[httpx.Request] = []
    holder = {"handler": None}

    def dispatch(request):
        calls.append(request)
        return holder["handler"](request)

    async def no_sleep(_):
        return None

    monkeypatch.setattr(http_client, "transport", httpx.MockTransport(dispatch))
    monkeypatch.setattr(http_client.asyncio, "sleep", no_sleep)

    def use(handler):
        holder["handler"] = handler
        return calls

    return use


def test_open_incident_retries_then_gives_up(transport):
    calls = transport(lambda request: httpx.Response(503))
    client = IncidentServiceClient("http://incident-service:8000")
    with pytest.raises(ServiceUnavailable):
        asyncio.run(client.open_incident(target_id="t1", title="x", severity="CRITICAL", description="d"))
    assert len(calls) == 3  # HTTP_MAX_RETRIES


def test_unresolvable_host_is_not_retried(transport):
    """A stopped container's name doesn't resolve; retrying only adds DNS timeouts."""
    import socket

    def handler(request):
        try:
            raise socket.gaierror(-2, "Name or service not known")
        except socket.gaierror as exc:
            raise httpx.ConnectError("[Errno -2] Name or service not known", request=request) from exc

    calls = transport(handler)
    client = IncidentServiceClient("http://incident-service:8000")
    with pytest.raises(ServiceUnavailable):
        asyncio.run(client.open_incident(target_id="t1", title="x", severity="CRITICAL", description="d"))
    assert len(calls) == 1


def test_connection_refused_is_still_retried(transport):
    def handler(request):
        raise httpx.ConnectError("[Errno 111] Connection refused", request=request)

    calls = transport(handler)
    client = IncidentServiceClient("http://incident-service:8000")
    with pytest.raises(ServiceUnavailable):
        asyncio.run(client.open_incident(target_id="t1", title="x", severity="CRITICAL", description="d"))
    assert len(calls) == 3


def test_open_incident_succeeds_after_a_transient_error(transport):
    responses = iter([httpx.Response(502), httpx.Response(201, json={"id": "inc-9"})])
    calls = transport(lambda request: next(responses))
    client = IncidentServiceClient("http://incident-service:8000")
    incident_id = asyncio.run(
        client.open_incident(target_id="t1", title="x", severity="CRITICAL", description="d")
    )
    assert incident_id == "inc-9"
    assert len(calls) == 2
    assert calls[0].url.path == "/api/v1/incidents"


def test_list_enabled_reads_every_page(transport):
    def handler(request):
        offset = int(request.url.params["offset"])
        assert request.url.params["enabled"] == "true"
        count = 500 if offset == 0 else 3
        return httpx.Response(200, json=[{"id": f"t{offset + i}"} for i in range(count)])

    transport(handler)
    targets = asyncio.run(TargetServiceClient("http://target-service:8000").list_enabled())
    assert len(targets) == 503


def test_get_target_returns_none_for_404(transport):
    transport(lambda request: httpx.Response(404, json={"error": {}}))
    assert asyncio.run(TargetServiceClient("http://target-service:8000").get("nope")) is None


def test_report_status_never_raises(transport):
    calls = transport(lambda request: httpx.Response(503))
    asyncio.run(TargetServiceClient("http://target-service:8000").report_status("t1", "DOWN"))
    assert len(calls) == 2
    assert calls[0].method == "PATCH" and calls[0].url.path == "/api/v1/targets/t1/status"


# --- Prometheus -----------------------------------------------------------------------------------


def prom(handler):
    return PrometheusClient("http://prometheus:9090", timeout=1, transport=httpx.MockTransport(handler))


def vector(value):
    result = [] if value is None else [{"metric": {}, "value": [0, value]}]
    return httpx.Response(200, json={"status": "success", "data": {"resultType": "vector", "result": result}})


def test_prometheus_values_are_parsed():
    queries = []

    def handler(request):
        queries.append(request.url.params["query"])
        return vector("12.3456" if "cpu" in request.url.params["query"] else "4.5")

    usage = asyncio.run(prom(handler).container_usage("demo-app"))
    assert (usage.available, usage.cpu_percent, usage.memory_percent) == (True, 12.35, 4.5)
    assert all('container_label_com_docker_compose_service="demo-app"' in q for q in queries)


def test_no_container_data_is_null_not_zero():
    usage = asyncio.run(prom(lambda request: vector(None)).container_usage("example.com"))
    assert (usage.available, usage.cpu_percent, usage.memory_percent) == (True, None, None)


def test_prometheus_down_is_unavailable():
    def handler(request):
        raise httpx.ConnectError("refused", request=request)

    usage = asyncio.run(prom(handler).container_usage("demo-app"))
    assert (usage.available, usage.cpu_percent, usage.memory_percent) == (False, None, None)


def test_unsafe_host_is_never_put_into_a_query():
    def handler(request):
        raise AssertionError("Prometheus must not be queried")

    usage = asyncio.run(prom(handler).container_usage('x"} or vector(1) #'))
    assert (usage.available, usage.cpu_percent) == (True, None)


def test_infrastructure_combines_host_containers_services_and_alerts():
    def handler(request):
        if request.url.path.endswith("/alerts"):
            alert = {"labels": {"alertname": "HighHostMemory", "severity": "warning"}, "state": "firing",
                     "annotations": {"summary": "Host memory above 85%"}, "activeAt": "2026-11-16T00:00:00Z"}
            return httpx.Response(200, json={"status": "success", "data": {"alerts": [alert]}})
        query = request.url.params["query"]
        label = "container_label_com_docker_compose_service"
        if query.startswith("sum by"):
            series = [{"metric": {label: "demo-app"}, "value": [0, "1.5" if "cpu" in query else "2048"]}]
            return httpx.Response(200, json={"status": "success", "data": {"result": series}})
        if query.startswith("up{"):
            series = [{"metric": {"instance": "b:8000"}, "value": [0, "0"]},
                      {"metric": {"instance": "a:8000"}, "value": [0, "1"]}]
            return httpx.Response(200, json={"status": "success", "data": {"result": series}})
        if "filesystem" in query:
            return vector(None)
        return vector("50")

    infra = asyncio.run(prom(handler).infrastructure())
    assert infra.available is True
    assert infra.host["cpu_percent"] == 50.0
    assert infra.host["disk_percent"] is None
    assert infra.containers == [{"service": "demo-app", "cpu_percent": 1.5, "memory_bytes": 2048.0}]
    assert infra.services == [{"instance": "a:8000", "up": True}, {"instance": "b:8000", "up": False}]
    assert infra.alerts[0]["name"] == "HighHostMemory" and infra.alerts[0]["state"] == "firing"


def test_infrastructure_when_prometheus_is_down():
    def handler(request):
        raise httpx.ConnectError("refused", request=request)

    infra = asyncio.run(prom(handler).infrastructure())
    assert (infra.available, infra.host, infra.containers) == (False, {}, [])
