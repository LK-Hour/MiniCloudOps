"""Request middleware: correlation IDs and request logging."""
import logging
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from app.logging_config import correlation_id_var

CORRELATION_HEADER = "X-Correlation-ID"
_QUIET_PATHS = {"/health", "/health/ready", "/metrics"}

logger = logging.getLogger("app.request")


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    """Reuse the caller's X-Correlation-ID (or create one) and log each request."""

    async def dispatch(self, request: Request, call_next):
        correlation_id = request.headers.get(CORRELATION_HEADER) or f"req-{uuid.uuid4().hex[:12]}"
        token = correlation_id_var.set(correlation_id)
        start = time.perf_counter()
        try:
            response = await call_next(request)
            if request.url.path not in _QUIET_PATHS:
                logger.log(
                    logging.ERROR if response.status_code >= 500 else logging.INFO,
                    "Request completed",
                    extra={
                        "method": request.method,
                        "path": request.url.path,
                        "status_code": response.status_code,
                        "duration_ms": round((time.perf_counter() - start) * 1000, 2),
                    },
                )
            response.headers[CORRELATION_HEADER] = correlation_id
            return response
        except Exception:
            logger.exception(
                "Request failed", extra={"method": request.method, "path": request.url.path}
            )
            raise
        finally:
            correlation_id_var.reset(token)
