"""Monitoring API: /api/v1/monitoring (contract from docs/MiniCloudOps.md §5.2).

The checks themselves run in app/monitor.py, on a schedule or through POST /check/{id}.
"""
import asyncio
import logging
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response, status
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from app.clients import ServiceUnavailable
from app.config import get_settings
from app.errors import ApiError
from app.monitor import Monitor, StateSnapshot, host_of
from app.prometheus import ContainerUsage, SeriesSet
from app.schemas import (
    CheckTimeseries,
    HealthCheckResult,
    HostStats,
    InfrastructureHistory,
    InfrastructureRead,
    MonitoringPolicy,
    RecentCheck,
    ResourceHistory,
    SeriesPoint,
    TargetOverview,
    TargetStatus,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/monitoring", tags=["monitoring"])


def get_monitor(request: Request) -> Monitor:
    """The Monitor built at startup. Tests override this dependency."""
    return request.app.state.monitor


MonitorDep = Annotated[Monitor, Depends(get_monitor)]


async def _fetch_target(monitor: Monitor, target_id: str) -> dict | None:
    """The target from the Target Service; None if unknown. 503 if the Target Service is down."""
    try:
        return await monitor.targets.get(target_id)
    except ServiceUnavailable as exc:
        logger.warning("Target Service unavailable", extra={"target_id": target_id, "error": str(exc)})
        raise ApiError(status.HTTP_503_SERVICE_UNAVAILABLE, "Target Service unavailable") from exc


def _not_found(target_id: str) -> ApiError:
    return ApiError(status.HTTP_404_NOT_FOUND, f"Target '{target_id}' not found")


@router.get("/health")
def service_health() -> dict:
    return {"status": "ok", "service": get_settings().service_name}


@router.get("/config", response_model=MonitoringPolicy)
def monitoring_policy():
    """Thresholds and intervals in effect. Change them with environment variables (see .env.example)."""
    settings = get_settings()
    return MonitoringPolicy(**{name: getattr(settings, name) for name in MonitoringPolicy.model_fields})


@router.get("/targets", response_model=list[TargetOverview])
def targets_overview(
    monitor: MonitorDep,
    recent: Annotated[int, Query(ge=0, le=100, description="Latest checks to include per target")] = 20,
):
    """State of every target this service has checked, in one call (no per-target requests)."""
    return [
        TargetOverview(
            target_id=state.target_id,
            status=state.status,
            consecutive_failures=state.consecutive_failures,
            last_checked_at=state.last_checked_at,
            last_response_time_ms=state.last_response_time_ms,
            open_incident_id=state.open_incident_id,
            recent=[RecentCheck.model_validate(c) for c in checks],
        )
        for state, checks in monitor.overview(recent)
    ]


@router.get("/infrastructure", response_model=InfrastructureRead)
async def infrastructure(monitor: MonitorDep):
    """Host and container usage, MiniOps service status and firing alerts, from Prometheus."""
    infra = await monitor.prometheus.infrastructure()
    return InfrastructureRead(
        available=infra.available,
        collected_at=infra.collected_at,
        host=HostStats(**infra.host),
        containers=infra.containers,
        services=infra.services,
        alerts=infra.alerts,
    )


MinutesQuery = Annotated[int, Query(ge=5, le=1440, description="Window length, in minutes")]


def _points(series: SeriesSet, name: str) -> list[SeriesPoint]:
    return [SeriesPoint(t=datetime.fromtimestamp(t, UTC), v=v) for t, v in series.series.get(name, [])]


@router.get("/timeseries", response_model=CheckTimeseries)
def checks_timeseries(monitor: MonitorDep, minutes: MinutesQuery = 60):
    """Response time and failures over time, for all targets together and for each one."""
    return CheckTimeseries(minutes=minutes, **monitor.timeseries(minutes))


@router.get("/infrastructure/history", response_model=InfrastructureHistory)
async def infrastructure_history(monitor: MonitorDep, minutes: MinutesQuery = 60):
    """Host CPU/memory/disk and the busiest containers' CPU over time, from Prometheus."""
    host, containers = await asyncio.gather(
        monitor.prometheus.host_history(minutes), monitor.prometheus.containers_history(minutes)
    )
    return InfrastructureHistory(
        available=host.available and containers.available,
        minutes=minutes,
        step_seconds=host.step_seconds,
        host={name: _points(host, name) for name in host.series},
        containers={name: _points(containers, name) for name in containers.series},
    )


@router.get("/targets/{target_id}/timeseries", response_model=CheckTimeseries)
def target_timeseries(target_id: str, monitor: MonitorDep, minutes: MinutesQuery = 60):
    """One target's checks grouped over time. Served from this service's data, like /history."""
    data = monitor.timeseries(minutes, target_id=target_id)
    return CheckTimeseries(minutes=minutes, **data)


@router.get("/targets/{target_id}/resources", response_model=ResourceHistory)
async def target_resources(target_id: str, monitor: MonitorDep, minutes: MinutesQuery = 60):
    """One target's container CPU and memory over time (empty outside Docker Compose)."""
    target = await _fetch_target(monitor, target_id)
    if target is None:
        raise _not_found(target_id)
    series = await monitor.prometheus.container_history(host_of(target["target_url"]), minutes)
    return ResourceHistory(
        available=series.available,
        minutes=minutes,
        step_seconds=series.step_seconds,
        cpu=_points(series, "cpu"),
        memory=_points(series, "memory"),
    )


@router.get("/targets/{target_id}/status", response_model=TargetStatus)
async def target_status(target_id: str, monitor: MonitorDep):
    target = await _fetch_target(monitor, target_id)
    if target is None:
        raise _not_found(target_id)

    state = monitor.get_state(target_id) or StateSnapshot.unknown(target_id)
    if not target["enabled"]:
        state = StateSnapshot.unknown(target_id)  # not monitored, so any old result is stale
    usage: ContainerUsage = await monitor.container_usage(target)
    return TargetStatus(
        target_id=target_id,
        status=state.status,
        consecutive_failures=state.consecutive_failures,
        last_checked_at=state.last_checked_at,
        last_response_time_ms=state.last_response_time_ms,
        open_incident_id=state.open_incident_id,
        metrics_available=usage.available,
        cpu_percent=usage.cpu_percent,
        memory_percent=usage.memory_percent,
    )


@router.get("/targets/{target_id}/history", response_model=list[HealthCheckResult])
def target_history(
    target_id: str,
    monitor: MonitorDep,
    limit: Annotated[int, Query(ge=1, le=500, description="Newest checks first")] = 50,
):
    # Served from this service's own data, so history stays readable after a target is deleted.
    return monitor.history(target_id, limit)


@router.get("/metrics")
def prometheus_metrics() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@router.post("/check/{target_id}", response_model=HealthCheckResult)
async def trigger_check(target_id: str, monitor: MonitorDep):
    target = await _fetch_target(monitor, target_id)
    if target is None:
        raise _not_found(target_id)
    if not target["enabled"]:
        raise ApiError(status.HTTP_409_CONFLICT, f"Target '{target_id}' is disabled; enable it to check it")
    return await monitor.check_target(target)
