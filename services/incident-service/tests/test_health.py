def test_liveness(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "incident-service"}


def test_correlation_id_is_echoed(client):
    response = client.get("/health", headers={"X-Correlation-ID": "req-test-123"})
    assert response.headers["X-Correlation-ID"] == "req-test-123"


def test_correlation_id_is_generated(client):
    response = client.get("/health")
    assert response.headers["X-Correlation-ID"].startswith("req-")


def test_metrics_endpoint(client):
    response = client.get("/metrics/")
    assert response.status_code == 200
    assert "python_info" in response.text


def test_unknown_route_uses_standard_error(client):
    response = client.get("/does-not-exist")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == 404
