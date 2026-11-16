"""Infrastructure metrics from Prometheus (cAdvisor data), per monitored container.

A target is matched to a container by its URL host: http://demo-app/health -> the Docker Compose
service "demo-app". Targets outside Docker Compose have no container data.

Unavailable data is reported as None, never 0 (docs/MiniCloudOps.md §3.3).
"""
import asyncio
import logging
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime

import httpx

from app.http_client import outbound_headers

logger = logging.getLogger(__name__)

# Compose service names only. Anything else is never put into a PromQL query.
_SERVICE_NAME = re.compile(r"^[a-z0-9][a-z0-9_.-]{0,62}$")
_LABEL = "container_label_com_docker_compose_service"


@dataclass(frozen=True)
class ContainerUsage:
    available: bool  # False: Prometheus could not be asked, so the values mean nothing
    cpu_percent: float | None = None  # % of one CPU core
    memory_percent: float | None = None  # % of host memory

    @classmethod
    def unavailable(cls) -> "ContainerUsage":
        return cls(available=False)


@dataclass(frozen=True)
class Infrastructure:
    """Platform-wide view for the dashboard. Every number is None when there is no data."""

    available: bool
    collected_at: datetime
    host: dict = field(default_factory=dict)
    containers: list[dict] = field(default_factory=list)
    services: list[dict] = field(default_factory=list)
    alerts: list[dict] = field(default_factory=list)


_BY_SERVICE = f"sum by ({_LABEL})"
_HOST_QUERIES = {
    "cpu_percent": '100 * (1 - avg(rate(node_cpu_seconds_total{mode="idle"}[1m])))',
    "memory_percent": "(1 - sum(node_memory_MemAvailable_bytes) / sum(node_memory_MemTotal_bytes)) * 100",
    "memory_total_bytes": "sum(node_memory_MemTotal_bytes)",
    "disk_percent": (
        '100 * (1 - max(node_filesystem_avail_bytes{mountpoint="/"})'
        ' / max(node_filesystem_size_bytes{mountpoint="/"}))'
    ),
    "uptime_seconds": "max(node_time_seconds - node_boot_time_seconds)",
}
_CONTAINER_QUERIES = {
    "cpu_percent": f'{_BY_SERVICE} (rate(container_cpu_usage_seconds_total{{{_LABEL}!=""}}[1m])) * 100',
    "memory_bytes": f'{_BY_SERVICE} (container_memory_working_set_bytes{{{_LABEL}!=""}})',
}
_SERVICES_QUERY = 'up{job="miniops-services"}'


def _number(raw: str) -> float | None:
    value = float(raw)
    return round(value, 2) if value == value else None  # NaN -> None


class PrometheusClient:
    def __init__(self, base_url: str, timeout: float, transport: httpx.AsyncBaseTransport | None = None):
        self.query_url = f"{base_url.rstrip('/')}/api/v1/query"
        self.timeout = timeout
        self.transport = transport

    async def container_usage(self, service: str | None) -> ContainerUsage:
        if not service or not _SERVICE_NAME.match(service):
            return ContainerUsage(available=True)  # nothing to look up; Prometheus itself is fine
        selector = f'{{{_LABEL}="{service}"}}'
        cpu_query = f"sum(rate(container_cpu_usage_seconds_total{selector}[1m])) * 100"
        memory_query = (
            f"sum(container_memory_working_set_bytes{selector}) / scalar(max(machine_memory_bytes)) * 100"
        )
        try:
            async with httpx.AsyncClient(
                timeout=self.timeout, transport=self.transport, trust_env=False, headers=outbound_headers()
            ) as client:
                cpu, memory = await asyncio.gather(
                    self._scalar(client, cpu_query), self._scalar(client, memory_query)
                )
        except (httpx.HTTPError, ValueError, KeyError) as exc:
            logger.warning("Prometheus unavailable", extra={"error": str(exc) or type(exc).__name__})
            return ContainerUsage.unavailable()
        return ContainerUsage(available=True, cpu_percent=cpu, memory_percent=memory)

    async def infrastructure(self) -> Infrastructure:
        """Host usage, per-container usage, MiniOps service scrape status and firing alerts."""
        now = datetime.now(UTC)
        try:
            async with httpx.AsyncClient(
                timeout=self.timeout, transport=self.transport, trust_env=False, headers=outbound_headers()
            ) as client:
                host_values = await asyncio.gather(*(self._scalar(client, q) for q in _HOST_QUERIES.values()))
                cpu, memory, up, alerts = await asyncio.gather(
                    self._vector(client, _CONTAINER_QUERIES["cpu_percent"]),
                    self._vector(client, _CONTAINER_QUERIES["memory_bytes"]),
                    self._vector(client, _SERVICES_QUERY),
                    self._alerts(client),
                )
        except (httpx.HTTPError, ValueError, KeyError) as exc:
            logger.warning("Prometheus unavailable", extra={"error": str(exc) or type(exc).__name__})
            return Infrastructure(available=False, collected_at=now)

        containers: dict[str, dict] = {}
        for metric_name, series in (("cpu_percent", cpu), ("memory_bytes", memory)):
            for labels, value in series:
                name = labels.get(_LABEL)
                if name:
                    empty = {"service": name, "cpu_percent": None, "memory_bytes": None}
                    row = containers.setdefault(name, empty)
                    row[metric_name] = value
        services = sorted(
            ({"instance": labels.get("instance", "?"), "up": value == 1} for labels, value in up),
            key=lambda s: s["instance"],
        )
        return Infrastructure(
            available=True,
            collected_at=now,
            host=dict(zip(_HOST_QUERIES, host_values, strict=True)),
            containers=sorted(containers.values(), key=lambda c: c["service"]),
            services=services,
            alerts=alerts,
        )

    async def _query(self, client: httpx.AsyncClient, query: str) -> list[dict]:
        response = await client.get(self.query_url, params={"query": query})
        response.raise_for_status()
        body = response.json()
        if body.get("status") != "success":
            raise ValueError(f"Prometheus query failed: {body.get('error')}")
        return body["data"]["result"]

    async def _scalar(self, client: httpx.AsyncClient, query: str) -> float | None:
        result = await self._query(client, query)
        if not result:
            return None  # no such series: no data, which is not the same as 0
        return _number(result[0]["value"][1])

    async def _vector(self, client: httpx.AsyncClient, query: str) -> list[tuple[dict, float | None]]:
        return [(r["metric"], _number(r["value"][1])) for r in await self._query(client, query)]

    async def _alerts(self, client: httpx.AsyncClient) -> list[dict]:
        response = await client.get(self.query_url.replace("/query", "/alerts"))
        response.raise_for_status()
        return [
            {
                "name": a["labels"].get("alertname", "?"),
                "severity": a["labels"].get("severity"),
                "state": a.get("state"),  # pending | firing
                "summary": a.get("annotations", {}).get("summary"),
                "active_at": a.get("activeAt"),
            }
            for a in response.json()["data"]["alerts"]
        ]
