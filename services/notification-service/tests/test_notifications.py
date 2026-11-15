def test_create_notification_requires_fields(client):
    response = client.post("/api/v1/notifications", json={})
    assert response.status_code == 422
    fields = {d["field"] for d in response.json()["error"]["details"]}
    assert {"body.incident_id", "body.event_type", "body.title", "body.message"} <= fields
