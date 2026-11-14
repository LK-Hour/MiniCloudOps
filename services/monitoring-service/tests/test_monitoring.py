def test_versioned_health(client):
    response = client.get("/api/v1/monitoring/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_custom_metrics_are_exposed(client):
    response = client.get("/api/v1/monitoring/metrics")
    assert response.status_code == 200
    assert "miniops_active_targets" in response.text
    assert "miniops_open_incidents" in response.text
