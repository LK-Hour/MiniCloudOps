"""Monitoring API: /api/v1/monitoring (contract from docs/MiniCloudOps.md §5.2).

TODO: background scheduler that, for each enabled target:
  1. fetches targets from the Target Service,
  2. runs the HTTP check and records a HealthCheck + metrics,
  3. queries Prometheus for CPU/memory (None when unavailable, never 0),
  4. reports results to the Incident Service via app.http_client.request_with_retry.
"""
from fastapi import APIRouter, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from app import metrics  # noqa: F401  (registers the custom metrics)
from app.config import get_settings
from app.errors import not_implemented
from app.schemas import HealthCheckResult, TargetStatus

router = APIRouter(prefix="/api/v1/monitoring", tags=["monitoring"])


@router.get("/health")
def service_health() -> dict:
    return {"status": "ok", "service": get_settings().service_name}


@router.get("/targets/{target_id}/status", response_model=TargetStatus)
def target_status(target_id: str):
    raise not_implemented()


@router.get("/targets/{target_id}/history", response_model=list[HealthCheckResult])
def target_history(target_id: str, limit: int = 50):
    raise not_implemented()


@router.get("/metrics")
def prometheus_metrics() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@router.post("/check/{target_id}", response_model=HealthCheckResult)
async def trigger_check(target_id: str):
    raise not_implemented()
