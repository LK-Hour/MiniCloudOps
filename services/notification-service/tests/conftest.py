"""Fixtures: SQLite instead of Postgres."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import models  # noqa: F401  (registers the tables on Base.metadata)
from app.db import Base, get_db
from app.main import app


@pytest.fixture
def client():
    # Not used as a context manager, so the lifespan (real database setup) does not run.
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    def override_get_db():
        db = TestSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()
    engine.dispose()


@pytest.fixture
def make_notification(client):
    def _make(**overrides):
        payload = {
            "incident_id": "inc-1",
            "event_type": "INCIDENT_CREATED",
            "severity": "CRITICAL",
            "title": "[CRITICAL] Demo App is unavailable",
            "message": "HTTP health check failed 3 times in a row",
            **overrides,
        }
        response = client.post("/api/v1/notifications", json=payload)
        assert response.status_code == 201, response.text
        return response.json()

    return _make
