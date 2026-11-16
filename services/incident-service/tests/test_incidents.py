"""API tests for /api/v1/incidents."""
API = "/api/v1/incidents"


def events(client, incident_id):
    return [e["event_type"] for e in client.get(f"{API}/{incident_id}/history").json()]


# --- validation -----------------------------------------------------------------------------------


def test_create_incident_rejects_unknown_severity(client):
    response = client.post(
        API, json={"target_id": "target-001", "title": "Application unavailable", "severity": "HUGE"}
    )
    assert response.status_code == 422
    assert response.json()["error"]["details"][0]["field"] == "body.severity"


def test_create_incident_rejects_blank_title(client):
    response = client.post(API, json={"target_id": "t", "title": "   ", "severity": "INFO"})
    assert response.status_code == 422


# --- create ---------------------------------------------------------------------------------------


def test_create_incident(client, notifier):
    response = client.post(
        API,
        json={"target_id": "target-001", "title": "Application unavailable", "severity": "CRITICAL",
              "description": "HTTP health check failed"},
    )
    assert response.status_code == 201
    incident = response.json()
    assert incident["status"] == "OPEN"
    assert incident["resolved_at"] is None
    assert response.headers["location"] == f"{API}/{incident['id']}"

    assert notifier.sent == [{
        "incident_id": incident["id"],
        "event_type": "INCIDENT_CREATED",
        "severity": "CRITICAL",
        "title": "[CRITICAL] Application unavailable",
        "message": "HTTP health check failed",
    }]
    assert events(client, incident["id"]) == ["CREATED", "NOTIFICATION_SENT"]


def test_duplicate_report_returns_existing_incident(client, make_incident, notifier):
    first = make_incident()
    duplicate = {"target_id": "target-001", "title": "Still down", "severity": "CRITICAL"}
    response = client.post(API, json=duplicate)
    assert response.status_code == 200
    assert response.json()["id"] == first["id"]
    assert len(client.get(API).json()) == 1
    assert len(notifier.sent) == 1  # no second notification


def test_acknowledged_incident_still_counts_as_active(client, make_incident):
    first = make_incident()
    client.patch(f"{API}/{first['id']}/status", json={"status": "ACKNOWLEDGED"})
    response = client.post(API, json={"target_id": "target-001", "title": "Down", "severity": "CRITICAL"})
    assert response.status_code == 200
    assert response.json()["id"] == first["id"]


def test_new_incident_after_resolution(client, make_incident):
    first = make_incident()
    client.patch(f"{API}/{first['id']}/status", json={"status": "RESOLVED"})
    second = make_incident()
    assert second["id"] != first["id"]


def test_incident_is_saved_when_notification_service_is_down(client, notifier):
    notifier.down = True
    response = client.post(API, json={"target_id": "t1", "title": "Down", "severity": "CRITICAL"})
    assert response.status_code == 201
    incident_id = response.json()["id"]
    assert client.get(f"{API}/{incident_id}").status_code == 200
    assert events(client, incident_id) == ["CREATED", "NOTIFICATION_FAILED"]


# --- read -----------------------------------------------------------------------------------------


def test_get_unknown_incident_returns_404(client):
    response = client.get(f"{API}/nope")
    assert response.status_code == 404
    assert response.json()["error"]["message"] == "Incident 'nope' not found"


def test_list_filters_and_newest_first(client, make_incident):
    a = make_incident(target_id="a")
    b = make_incident(target_id="b")
    client.patch(f"{API}/{a['id']}/status", json={"status": "RESOLVED"})

    assert [i["id"] for i in client.get(API).json()] == [b["id"], a["id"]]
    assert [i["id"] for i in client.get(API, params={"status": "OPEN"}).json()] == [b["id"]]
    assert [i["id"] for i in client.get(API, params={"target_id": "a"}).json()] == [a["id"]]
    assert client.get(API, params={"status": "BOGUS"}).status_code == 422


# --- status changes -------------------------------------------------------------------------------


def test_resolve_incident(client, make_incident, notifier):
    incident = make_incident()
    response = client.patch(
        f"{API}/{incident['id']}/status", json={"status": "RESOLVED", "note": "Target recovered"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "RESOLVED"
    assert body["resolved_at"] is not None

    assert notifier.sent[-1]["event_type"] == "INCIDENT_RESOLVED"
    assert notifier.sent[-1]["message"] == "Target recovered"
    history = client.get(f"{API}/{incident['id']}/history").json()
    assert [e["event_type"] for e in history] == [
        "CREATED", "NOTIFICATION_SENT", "RESOLVED", "NOTIFICATION_SENT"
    ]
    assert history[2]["message"] == "OPEN -> RESOLVED: Target recovered"


def test_acknowledge_then_resolve(client, make_incident):
    incident = make_incident()
    assert client.patch(f"{API}/{incident['id']}/status", json={"status": "ACKNOWLEDGED"}).status_code == 200
    assert client.patch(f"{API}/{incident['id']}/status", json={"status": "RESOLVED"}).status_code == 200


def test_resolving_twice_is_a_no_op(client, make_incident, notifier):
    incident = make_incident()
    client.patch(f"{API}/{incident['id']}/status", json={"status": "RESOLVED"})
    response = client.patch(f"{API}/{incident['id']}/status", json={"status": "RESOLVED"})
    assert response.status_code == 200
    assert [n["event_type"] for n in notifier.sent] == ["INCIDENT_CREATED", "INCIDENT_RESOLVED"]


def test_resolved_incident_cannot_be_reopened(client, make_incident):
    incident = make_incident()
    client.patch(f"{API}/{incident['id']}/status", json={"status": "RESOLVED"})
    response = client.patch(f"{API}/{incident['id']}/status", json={"status": "OPEN"})
    assert response.status_code == 409
    assert response.json()["error"]["message"] == "Cannot change an incident from RESOLVED to OPEN"


def test_update_unknown_incident_returns_404(client):
    assert client.patch(f"{API}/nope/status", json={"status": "RESOLVED"}).status_code == 404


def test_history_of_unknown_incident_returns_404(client):
    assert client.get(f"{API}/nope/history").status_code == 404
