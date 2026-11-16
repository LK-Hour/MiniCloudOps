"""Fixtures: SQLite instead of Postgres, fakes for the other services, fake monitored apps."""
import socket
from datetime import UTC, datetime

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import models  # noqa: F401  (registers the tables on Base.metadata)
from app.clients import ServiceUnavailable
from app.config import Settings
from app.db import Base
from app.main import app
from app.monitor import Monitor
from app.prometheus import ContainerUsage, Infrastructure
from app.routes import get_monitor

FAKE_DNS = {
    "demo-app": ["172.18.0.10"],
    "example.com": ["93.184.216.34"],
    "postgres": ["172.18.0.2"],
    "rebound.example": ["127.0.0.1"],  # was public at registration, now points at loopback
}


def fake_resolver(host: str, port: int) -> list[str]:
    try:
        return FAKE_DNS[host]
    except KeyError:
        raise socket.gaierror(f"unknown host {host}") from None


def make_target(target_id="t1", url="http://demo-app/health", **extra) -> dict:
    return {"id": target_id, "name": f"App {target_id}", "target_url": url, "enabled": True,
            "check_interval": 30, "status": "UNKNOWN", **extra}


class FakeTargetService:
    def __init__(self):
        self.targets: dict[str, dict] = {}
        self.reported: list[tuple[str, str]] = []
        self.down = False

    def add(self, target: dict) -> dict:
        self.targets[target["id"]] = target
        return target

    async def list_enabled(self):
        if self.down:
            raise ServiceUnavailable("target-service down")
        return [t for t in self.targets.values() if t["enabled"]]

    async def get(self, target_id):
        if self.down:
            raise ServiceUnavailable("target-service down")
        return self.targets.get(target_id)

    async def report_status(self, target_id, status):
        self.reported.append((target_id, status))


class FakeIncidentService:
    def __init__(self):
        self.opened: list[dict] = []
        self.resolved: list[str] = []
        self.down = False

    async def open_incident(self, **incident):
        if self.down:
            raise ServiceUnavailable("incident-service down")
        self.opened.append(incident)
        return f"inc-{len(self.opened)}"

    async def resolve_incident(self, incident_id, note):
        if self.down:
            raise ServiceUnavailable("incident-service down")
        self.resolved.append(incident_id)


class FakePrometheus:
    def __init__(self):
        self.usage = ContainerUsage(available=True, cpu_percent=12.5, memory_percent=3.1)
        self.asked: list[str | None] = []
        self.infra = Infrastructure(
            available=True,
            collected_at=datetime.now(UTC),
            host={"cpu_percent": 7.5, "memory_percent": 40.0, "memory_total_bytes": 8e9,
                  "disk_percent": None, "uptime_seconds": 3600.0},
            containers=[{"service": "demo-app", "cpu_percent": 0.1, "memory_bytes": 5e6}],
            services=[{"instance": "target-service:8000", "up": True}],
            alerts=[],
        )

    async def container_usage(self, service):
        self.asked.append(service)
        return self.usage

    async def infrastructure(self):
        return self.infra


class FakeApps:
    """Monitored applications behind an httpx.MockTransport. Set `responses[host]` to an int
    status code, or to an exception class to simulate a network failure."""

    def __init__(self):
        self.responses: dict[str, object] = {"demo-app": 200, "example.com": 200}
        self.requests: list[httpx.Request] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        outcome = self.responses.get(request.url.host, httpx.ConnectError)
        if isinstance(outcome, int):
            headers = {"Location": "http://elsewhere/"} if 300 <= outcome < 400 else {}
            return httpx.Response(outcome, headers=headers)
        raise outcome("simulated", request=request)

    def set(self, host: str, outcome) -> None:
        self.responses[host] = outcome


@pytest.fixture
def session_factory():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    yield sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    engine.dispose()


@pytest.fixture
def target_service():
    return FakeTargetService()


@pytest.fixture
def incident_service():
    return FakeIncidentService()


@pytest.fixture
def prometheus():
    return FakePrometheus()


@pytest.fixture
def apps():
    return FakeApps()


@pytest.fixture
def settings():
    return Settings(failure_threshold=3, max_concurrent_checks=5, scheduler_enabled=False)


@pytest.fixture
def monitor(settings, session_factory, target_service, incident_service, prometheus, apps):
    return Monitor(
        settings=settings,
        session_factory=session_factory,
        targets=target_service,
        incidents=incident_service,
        prometheus=prometheus,
        resolver=fake_resolver,
        transport=httpx.MockTransport(apps.handler),
    )


@pytest.fixture
def client(monitor):
    # Not used as a context manager, so the lifespan (real database, scheduler) does not run.
    app.dependency_overrides[get_monitor] = lambda: monitor
    yield TestClient(app)
    app.dependency_overrides.clear()
