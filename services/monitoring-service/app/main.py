"""MiniOps Monitoring Service."""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, status
from fastapi.responses import JSONResponse
from prometheus_client import make_asgi_app

from app.config import get_settings
from app.db import database_is_ready, init_db
from app.errors import register_error_handlers
from app.logging_config import setup_logging
from app.middleware import CorrelationIdMiddleware
from app.routes import router

settings = get_settings()
setup_logging(settings.service_name, settings.log_level)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    logger.info("Service starting")
    init_db()
    yield
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
