"""Calls from the Telegram bot to the other MiniOps services (internal network, no gateway).

Reads are best effort: a service that is down yields `None` and the bot says so, instead of failing
the whole answer. Actions (check now, acknowledge, resolve) return a short result to show the user.
"""

import asyncio
import logging
from dataclasses import dataclass, field

import httpx

from app.config import get_settings
from app.http_client import outbound_headers

logger = logging.getLogger(__name__)

# Tests replace this with an httpx.MockTransport so no real network is used.
transport: httpx.AsyncBaseTransport | None = None

SERVICES = ("target", "monitoring", "incident", "notification")


@dataclass
class Snapshot:
    """Everything the status views need, fetched at once. A field is None when its service is down."""

    targets: list[dict] | None = None
    states: dict[str, dict] | None = None  # target_id -> monitoring state
    incidents: list[dict] | None = None  # active only (OPEN or ACKNOWLEDGED)
    errors: list[str] = field(default_factory=list)

    def target(self, target_id: str) -> dict | None:
        return next((t for t in self.targets or [] if t["id"] == target_id), None)


@dataclass
class ActionResult:
    ok: bool
    message: str
    data: dict | None = None


def _urls() -> dict[str, str]:
    s = get_settings()
    return {
        "target": s.target_service_url.rstrip("/"),
        "monitoring": s.monitoring_service_url.rstrip("/"),
        "incident": s.incident_service_url.rstrip("/"),
        "notification": "http://127.0.0.1:8000",
    }


def _client(timeout: float | None = None) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        timeout=timeout or get_settings().http_timeout_seconds,
        transport=transport,
        trust_env=False,
        headers=outbound_headers(),
    )


async def _get(client: httpx.AsyncClient, service: str, path: str, errors: list[str], **params):
    try:
        response = await client.get(f"{_urls()[service]}{path}", params=params or None)
    except httpx.HTTPError as exc:
        errors.append(f"{service} service unreachable")
        logger.warning("Bot read failed", extra={"service": service, "error": type(exc).__name__})
        return None
    if response.status_code != 200:
        errors.append(f"{service} service answered {response.status_code}")
        return None
    return response.json()


async def snapshot() -> Snapshot:
    """Targets, their monitoring state and active incidents, fetched concurrently."""
    errors: list[str] = []
    async with _client() as client:
        targets, states, open_, acked = await asyncio.gather(
            _get(client, "target", "/api/v1/targets", errors, limit=500),
            _get(client, "monitoring", "/api/v1/monitoring/targets", errors, recent=5),
            _get(client, "incident", "/api/v1/incidents", errors, status="OPEN", limit=100),
            _get(client, "incident", "/api/v1/incidents", errors, status="ACKNOWLEDGED", limit=100),
        )
    incidents = None
    if open_ is not None and acked is not None:
        incidents = sorted(open_ + acked, key=lambda i: i["created_at"], reverse=True)
    return Snapshot(
        targets=targets,
        states={s["target_id"]: s for s in states} if states is not None else None,
        incidents=incidents,
        errors=sorted(set(errors)),
    )


async def service_health() -> dict[str, bool]:
    """Readiness of each MiniOps service (it answers and reaches its database)."""

    async def ready(client: httpx.AsyncClient, service: str) -> bool:
        try:
            return (await client.get(f"{_urls()[service]}/health/ready")).status_code == 200
        except httpx.HTTPError:
            return False

    async with _client(timeout=3) as client:
        results = await asyncio.gather(*(ready(client, s) for s in SERVICES))
    return dict(zip(SERVICES, results, strict=True))


async def recent_checks(target_id: str, limit: int = 5) -> list[dict] | None:
    async with _client() as client:
        return await _get(
            client, "monitoring", f"/api/v1/monitoring/targets/{target_id}/history", [], limit=limit
        )


async def check_now(target_id: str) -> ActionResult:
    url = f"{_urls()['monitoring']}/api/v1/monitoring/check/{target_id}"
    try:
        async with _client(timeout=get_settings().http_timeout_seconds + 10) as client:
            response = await client.post(url)
    except httpx.HTTPError:
        return ActionResult(False, "The Monitoring Service is unreachable.")
    if response.status_code == 200:
        return ActionResult(True, "Checked.", response.json())
    return ActionResult(False, _error_message(response))


async def set_incident_status(incident_id: str, status: str, note: str) -> ActionResult:
    url = f"{_urls()['incident']}/api/v1/incidents/{incident_id}/status"
    try:
        async with _client() as client:
            response = await client.patch(url, json={"status": status, "note": note})
    except httpx.HTTPError:
        return ActionResult(False, "The Incident Service is unreachable.")
    if response.status_code == 200:
        return ActionResult(True, "Done.", response.json())
    return ActionResult(False, _error_message(response))


def _error_message(response: httpx.Response) -> str:
    try:
        return response.json()["error"]["message"]
    except (ValueError, KeyError, TypeError):
        return f"The service answered {response.status_code}."
