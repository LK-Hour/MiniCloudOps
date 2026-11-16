"""Request middleware: correlation IDs, request logging and request metrics."""
import logging
import time
import uuid

from prometheus_client import Counter, Histogram
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from app.logging_config import correlation_id_var

CORRELATION_HEADER = "X-Correlation-ID"
_QUIET_PATHS = {"/health", "/health/ready", "/metrics"}

logger = logging.getLogger("app.request")

# Labelled by route template (/api/v1/targets/{target_id}), never the raw path, to bound cardinality.
API_REQUESTS = Counter(
    "miniops_api_requests_total", "API requests handled", ["method", "route", "status"]
)
API_LATENCY = Histogram(
    "miniops_api_request_duration_seconds", "API request handling time", ["method", "route"]
)


def _route(request: Request) -> str:
    route = request.scope.get("route")
    return getattr(route, "path", None) or "unmatched"


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    """Reuse the caller's X-Correlation-ID (or create one) and log each request."""

    async def dispatch(self, request: Request, call_next):
        correlation_id = request.headers.get(CORRELATION_HEADER) or f"req-{uuid.uuid4().hex[:12]}"
        token = correlation_id_var.set(correlation_id)
        start = time.perf_counter()
        try:
            response = await call_next(request)
            if request.url.path not in _QUIET_PATHS:
                route = _route(request)
                API_REQUESTS.labels(request.method, route, str(response.status_code)).inc()
                API_LATENCY.labels(request.method, route).observe(time.perf_counter() - start)
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
            API_REQUESTS.labels(request.method, _route(request), "500").inc()
            logger.exception(
                "Request failed", extra={"method": request.method, "path": request.url.path}
            )
            raise
        finally:
            correlation_id_var.reset(token)
