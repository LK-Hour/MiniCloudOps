def test_register_target_rejects_invalid_payload(client):
    response = client.post("/api/v1/targets/", json={"name": "", "target_url": "not-a-url"})
    assert response.status_code == 422
    body = response.json()["error"]
    assert body["message"] == "Request validation failed"
    fields = {d["field"] for d in body["details"]}
    assert {"body.name", "body.target_url"} <= fields


def test_check_interval_has_lower_bound(client):
    response = client.post(
        "/api/v1/targets/",
        json={"name": "Example API", "target_url": "http://app-server:8000/health", "check_interval": 1},
    )
    assert response.status_code == 422
