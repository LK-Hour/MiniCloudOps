"""MiniOps Monitoring Service."""
import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, status
from fastapi.responses import JSONResponse
from prometheus_client import make_asgi_app

from app.clients import IncidentServiceClient, TargetServiceClient
from app.config import Settings, get_settings
from app.db import SessionLocal, database_is_ready, init_db
from app.errors import register_error_handlers
from app.logging_config import setup_logging
from app.middleware import CorrelationIdMiddleware
from app.monitor import Monitor
from app.prometheus import PrometheusClient
from app.routes import router

settings = get_settings()
setup_logging(settings.service_name, settings.log_level)
logger = logging.getLogger(__name__)


def build_monitor(settings: Settings) -> Monitor:
    return Monitor(
        settings=settings,
        session_factory=SessionLocal,
        targets=TargetServiceClient(settings.target_service_url),
        incidents=IncidentServiceClient(settings.incident_service_url),
        prometheus=PrometheusClient(settings.prometheus_url, settings.prometheus_timeout_seconds),
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Service starting")
    init_db()
    app.state.monitor = build_monitor(settings)
    stop = asyncio.Event()
    scheduler = None
    if settings.scheduler_enabled:
        scheduler = asyncio.create_task(app.state.monitor.run_forever(stop))
    yield
    stop.set()
    if scheduler is not None:
        await scheduler
    logger.info("Service shutting down")


app = FastAPI(title="MiniOps Monitoring Service", version="0.1.0", lifespan=lifespan)
app.add_middleware(CorrelationIdMiddleware)
register_error_handlers(app)
app.include_router(router)
app.mount("/metrics", make_asgi_app())


@app.get("/health", tags=["health"])
def liveness() -> dict:
    """Liveness: the process is up. Used by the Docker healthcheck."""
    return {"status": "ok", "service": settings.service_name}


@app.get("/health/ready", tags=["health"])
def readiness():
    """Readiness: the service can reach its database."""
    if database_is_ready():
        return {"status": "ready", "service": settings.service_name}
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content={"status": "unavailable", "service": settings.service_name, "reason": "database"},
    )
