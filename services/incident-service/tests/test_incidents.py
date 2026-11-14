def test_create_incident_rejects_unknown_severity(client):
    response = client.post(
        "/api/v1/incidents/",
        json={"target_id": "target-001", "title": "Application unavailable", "severity": "HUGE"},
    )
    assert response.status_code == 422
    assert response.json()["error"]["details"][0]["field"] == "body.severity"
