"""API tests for /api/v1/targets."""
API = "/api/v1/targets"


# --- validation -----------------------------------------------------------------------------------


def test_register_target_rejects_invalid_payload(client):
    response = client.post(API, json={"name": "", "target_url": "not-a-url"})
    assert response.status_code == 422
    body = response.json()["error"]
    assert body["message"] == "Request validation failed"
    fields = {d["field"] for d in body["details"]}
    assert {"body.name", "body.target_url"} <= fields


def test_check_interval_has_lower_bound(client):
    response = client.post(
        API, json={"name": "Example API", "target_url": "http://demo-app/", "check_interval": 1}
    )
    assert response.status_code == 422


def test_unsupported_type_is_rejected(client):
    response = client.post(API, json={"name": "X", "target_url": "http://demo-app/", "type": "docker"})
    assert response.status_code == 422


# --- create and read ------------------------------------------------------------------------------


def test_register_target(client):
    response = client.post(
        API,
        json={"name": "  Example API  ", "target_url": "http://demo-app/health", "check_interval": 30},
    )
    assert response.status_code == 201
    target = response.json()
    assert target["name"] == "Example API"  # whitespace trimmed
    assert target["target_url"] == "http://demo-app/health"
    assert target["type"] == "http"
    assert target["enabled"] is True
    assert target["status"] == "UNKNOWN"
    assert response.headers["location"] == f"{API}/{target['id']}"


def test_get_target(client, make_target):
    target = make_target()
    response = client.get(f"{API}/{target['id']}")
    assert response.status_code == 200
    assert response.json() == target


def test_get_unknown_target_returns_404(client):
    response = client.get(f"{API}/does-not-exist")
    assert response.status_code == 404
    assert response.json()["error"]["message"] == "Target 'does-not-exist' not found"


def test_duplicate_name_is_rejected_case_insensitively(client, make_target):
    make_target(name="Demo App")
    response = client.post(API, json={"name": "demo app", "target_url": "http://example.com/"})
    assert response.status_code == 409
    assert response.json()["error"]["details"][0]["field"] == "body.name"


def test_list_targets_and_filter_by_enabled(client, make_target):
    first = make_target(name="One")
    make_target(name="Two", enabled=False)

    all_targets = client.get(API).json()
    assert [t["name"] for t in all_targets] == ["One", "Two"]

    enabled = client.get(API, params={"enabled": "true"}).json()
    assert [t["id"] for t in enabled] == [first["id"]]


def test_list_targets_pagination(client, make_target):
    for i in range(3):
        make_target(name=f"T{i}")
    page = client.get(API, params={"limit": 2, "offset": 1}).json()
    assert [t["name"] for t in page] == ["T1", "T2"]
    assert client.get(API, params={"limit": 0}).status_code == 422


# --- update, enable/disable, delete ---------------------------------------------------------------


def test_update_target_changes_only_sent_fields(client, make_target):
    target = make_target(check_interval=30)
    response = client.put(f"{API}/{target['id']}", json={"check_interval": 60})
    assert response.status_code == 200
    updated = response.json()
    assert updated["check_interval"] == 60
    assert updated["name"] == target["name"]
    assert updated["target_url"] == target["target_url"]


def test_update_url_resets_status(client, make_target):
    target = make_target()
    client.patch(f"{API}/{target['id']}/status", json={"status": "UP"})
    updated = client.put(f"{API}/{target['id']}", json={"target_url": "http://example.com/"}).json()
    assert updated["target_url"] == "http://example.com/"
    assert updated["status"] == "UNKNOWN"


def test_update_to_unsafe_url_is_rejected(client, make_target):
    target = make_target()
    response = client.put(f"{API}/{target['id']}", json={"target_url": "http://127.0.0.1/"})
    assert response.status_code == 422
    assert client.get(f"{API}/{target['id']}").json()["target_url"] == "http://demo-app/"


def test_update_to_existing_name_is_rejected(client, make_target):
    make_target(name="One")
    two = make_target(name="Two")
    assert client.put(f"{API}/{two['id']}", json={"name": "ONE"}).status_code == 409
    assert client.put(f"{API}/{two['id']}", json={"name": "Two"}).status_code == 200  # own name is fine


def test_update_unknown_target_returns_404(client):
    assert client.put(f"{API}/nope", json={"check_interval": 60}).status_code == 404


def test_disable_and_enable(client, make_target):
    target = make_target()
    client.patch(f"{API}/{target['id']}/status", json={"status": "UP"})

    disabled = client.patch(f"{API}/{target['id']}/disable").json()
    assert disabled["enabled"] is False
    assert disabled["status"] == "UNKNOWN"  # no checks while disabled

    enabled = client.patch(f"{API}/{target['id']}/enable").json()
    assert enabled["enabled"] is True


def test_enable_unknown_target_returns_404(client):
    assert client.patch(f"{API}/nope/enable").status_code == 404


def test_delete_target(client, make_target):
    target = make_target()
    response = client.delete(f"{API}/{target['id']}")
    assert response.status_code == 204
    assert response.content == b""
    assert client.get(f"{API}/{target['id']}").status_code == 404
    assert client.delete(f"{API}/{target['id']}").status_code == 404


# --- status (internal, used by the Monitoring Service) --------------------------------------------


def test_update_status(client, make_target):
    target = make_target()
    response = client.patch(f"{API}/{target['id']}/status", json={"status": "DOWN"})
    assert response.status_code == 200
    assert response.json()["status"] == "DOWN"


def test_update_status_rejects_unknown_value(client, make_target):
    target = make_target()
    assert client.patch(f"{API}/{target['id']}/status", json={"status": "BROKEN"}).status_code == 422


# --- SSRF -----------------------------------------------------------------------------------------


def test_register_rejects_internal_url_with_standard_error(client):
    response = client.post(API, json={"name": "Metadata", "target_url": "http://169.254.169.254/latest/"})
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["message"] == "Target URL is not allowed"
    assert error["details"][0]["field"] == "body.target_url"
    assert "link-local" in error["details"][0]["message"]
    assert client.get(API).json() == []  # nothing was saved


def test_register_rejects_miniops_infrastructure(client):
    response = client.post(API, json={"name": "DB", "target_url": "http://postgres:5432/"})
    assert response.status_code == 422
