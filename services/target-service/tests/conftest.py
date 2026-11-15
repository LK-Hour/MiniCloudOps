import socket

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import models  # noqa: F401  (registers the tables on Base.metadata)
from app.db import Base, get_db
from app.main import app
from app.routes import get_resolver

# Fake DNS: unit tests must not depend on the network.
FAKE_DNS = {
    "demo-app": ["172.18.0.10"],
    "example.com": ["93.184.216.34"],
    "postgres": ["172.18.0.2"],
    "sneaky.example": ["127.0.0.1"],
    "metadata-alias.example": ["169.254.169.254"],
    "mixed.example": ["93.184.216.34", "10.0.0.5"],
}


def fake_resolver(host: str, port: int) -> list[str]:
    try:
        return FAKE_DNS[host]
    except KeyError:
        raise socket.gaierror(f"unknown host {host}") from None


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
    app.dependency_overrides[get_resolver] = lambda: fake_resolver
    yield TestClient(app)
    app.dependency_overrides.clear()
    engine.dispose()


@pytest.fixture
def make_target(client):
    def _make(**overrides):
        payload = {"name": "Demo App", "target_url": "http://demo-app/", **overrides}
        response = client.post("/api/v1/targets", json=payload)
        assert response.status_code == 201, response.text
        return response.json()

    return _make
