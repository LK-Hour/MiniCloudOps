"""Fixtures: SQLite instead of Postgres and a fake Notification Service."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import models  # noqa: F401  (registers the tables on Base.metadata)
from app.db import Base, get_db
from app.main import app
from app.notifications import NotificationFailed, get_notifier
from app.routes import get_session_factory


class FakeNotifier:
    def __init__(self):
        self.sent: list[dict] = []
        self.down = False

    async def send(self, **notification):
        if self.down:
            raise NotificationFailed("notification-service down")
        self.sent.append(notification)


@pytest.fixture
def notifier():
    return FakeNotifier()


@pytest.fixture
def client(notifier):
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
    app.dependency_overrides[get_session_factory] = lambda: TestSession
    app.dependency_overrides[get_notifier] = lambda: notifier
    yield TestClient(app)
    app.dependency_overrides.clear()
    engine.dispose()


@pytest.fixture
def make_incident(client):
    def _make(**overrides):
        payload = {
            "target_id": "target-001",
            "title": "Application unavailable",
            "severity": "CRITICAL",
            "description": "HTTP health check failed",
            **overrides,
        }
        response = client.post("/api/v1/incidents", json=payload)
        assert response.status_code == 201, response.text
        return response.json()

    return _make
