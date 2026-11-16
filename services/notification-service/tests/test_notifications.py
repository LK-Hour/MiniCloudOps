"""API tests for /api/v1/notifications."""
API = "/api/v1/notifications"


def test_create_notification_requires_fields(client):
    response = client.post(API, json={})
    assert response.status_code == 422
    fields = {d["field"] for d in response.json()["error"]["details"]}
    assert {"body.incident_id", "body.event_type", "body.title", "body.message"} <= fields


def test_create_notification(client):
    response = client.post(
        API,
        json={"incident_id": "inc-1", "event_type": "INCIDENT_CREATED", "severity": "CRITICAL",
              "title": "Down", "message": "Health check failed"},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["channel"] == "dashboard"
    assert body["delivery_status"] == "DELIVERED"
    assert body["read"] is False
    assert body["severity"] == "CRITICAL"
    assert response.headers["location"] == f"{API}/{body['id']}"


def test_same_incident_event_is_not_duplicated(client, make_notification):
    first = make_notification()
    response = client.post(
        API, json={"incident_id": "inc-1", "event_type": "INCIDENT_CREATED", "title": "Again", "message": "x"}
    )
    assert response.status_code == 200
    assert response.json()["id"] == first["id"]
    assert len(client.get(API).json()) == 1


def test_created_and_resolved_are_separate_notifications(client, make_notification):
    make_notification()
    make_notification(event_type="INCIDENT_RESOLVED", title="[RESOLVED] Demo App", message="Recovered")
    assert len(client.get(API).json()) == 2


def test_get_notification(client, make_notification):
    created = make_notification()
    assert client.get(f"{API}/{created['id']}").json() == created


def test_get_unknown_notification_returns_404(client):
    response = client.get(f"{API}/nope")
    assert response.status_code == 404
    assert response.json()["error"]["message"] == "Notification 'nope' not found"


def test_mark_as_read_is_idempotent(client, make_notification):
    created = make_notification()
    for _ in range(2):
        response = client.patch(f"{API}/{created['id']}/read")
        assert response.status_code == 200
        assert response.json()["read"] is True


def test_mark_unknown_as_read_returns_404(client):
    assert client.patch(f"{API}/nope/read").status_code == 404


def test_list_newest_first_with_filters(client, make_notification):
    a = make_notification(incident_id="inc-a")
    b = make_notification(incident_id="inc-b")
    client.patch(f"{API}/{a['id']}/read")

    assert [n["id"] for n in client.get(API).json()] == [b["id"], a["id"]]
    assert [n["id"] for n in client.get(API, params={"unread_only": True}).json()] == [b["id"]]
    assert [n["id"] for n in client.get(API, params={"incident_id": "inc-a"}).json()] == [a["id"]]
    assert client.get(API, params={"limit": 501}).status_code == 422
