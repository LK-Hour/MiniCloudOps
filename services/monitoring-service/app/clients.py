"""Calls to the Target Service and the Incident Service, over their REST APIs."""
import logging

import httpx

from app.http_client import request_with_retry

logger = logging.getLogger(__name__)

PAGE_SIZE = 500  # the Target Service's maximum page size


class ServiceUnavailable(Exception):
    """The other service could not be reached, or kept failing after retries."""


async def _call(method: str, url: str, **kwargs) -> httpx.Response:
    try:
        return await request_with_retry(method, url, **kwargs)
    except httpx.HTTPError as exc:
        raise ServiceUnavailable(f"{method} {url} failed: {exc}") from exc


def _unexpected(response: httpx.Response) -> ServiceUnavailable:
    request = response.request
    return ServiceUnavailable(f"{request.method} {request.url} returned {response.status_code}")


class TargetServiceClient:
    def __init__(self, base_url: str) -> None:
        self.api = f"{base_url.rstrip('/')}/api/v1/targets"

    async def list_enabled(self) -> list[dict]:
        targets: list[dict] = []
        while True:
            response = await _call(
                "GET", self.api, params={"enabled": "true", "limit": PAGE_SIZE, "offset": len(targets)}
            )
            if response.status_code != 200:
                raise _unexpected(response)
            page = response.json()
            targets.extend(page)
            if len(page) < PAGE_SIZE:
                return targets

    async def get(self, target_id: str) -> dict | None:
        """The target, or None if the Target Service does not know it."""
        response = await _call("GET", f"{self.api}/{target_id}")
        if response.status_code == 404:
            return None
        if response.status_code != 200:
            raise _unexpected(response)
        return response.json()

    async def report_status(self, target_id: str, status: str) -> None:
        """Record UP/DOWN on the target (internal endpoint). Failure is logged, not raised:
        the next check sends the status again."""
        try:
            response = await _call(
                "PATCH", f"{self.api}/{target_id}/status", json={"status": status}, attempts=2
            )
        except ServiceUnavailable as exc:
            logger.warning(
                "Could not report target status", extra={"target_id": target_id, "error": str(exc)}
            )
            return
        if response.status_code not in (200, 404):  # 404: deleted since the check started
            logger.warning(
                "Target Service rejected status update",
                extra={"target_id": target_id, "status_code": response.status_code},
            )


class IncidentServiceClient:
    def __init__(self, base_url: str) -> None:
        self.api = f"{base_url.rstrip('/')}/api/v1/incidents"

    async def open_incident(
        self, *, target_id: str, title: str, severity: str, description: str, context: dict | None = None
    ) -> str:
        """Create the incident and return its id. The Incident Service returns the existing open
        incident instead of a duplicate, so calling this twice for one outage is safe."""
        response = await _call(
            "POST",
            self.api,
            json={
                "target_id": target_id,
                "title": title,
                "severity": severity,
                "description": description,
                "context": context,
            },
        )
        if response.status_code not in (200, 201):
            raise _unexpected(response)
        return response.json()["id"]

    async def resolve_incident(self, incident_id: str, note: str, context: dict | None = None) -> None:
        response = await _call(
            "PATCH",
            f"{self.api}/{incident_id}/status",
            json={"status": "RESOLVED", "note": note, "context": context},
        )
        if response.status_code == 404:  # deleted on the incident side; nothing left to resolve
            logger.warning("Incident to resolve no longer exists", extra={"incident_id": incident_id})
            return
        if response.status_code != 200:
            raise _unexpected(response)
