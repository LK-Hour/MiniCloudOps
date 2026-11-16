"""Outbound HTTP to other MiniOps services: timeouts, retries with backoff, correlation ID."""
import asyncio
import logging
import socket

import httpx

from app.config import get_settings
from app.logging_config import correlation_id_var
from app.middleware import CORRELATION_HEADER

logger = logging.getLogger(__name__)

# Tests replace this with an httpx.MockTransport so no real network is used.
transport: httpx.AsyncBaseTransport | None = None


def is_dns_failure(exc: BaseException) -> bool:
    """True when the host name did not resolve: in Docker, the container is stopped or gone.

    Retrying a moment later cannot help, and each lookup of a missing name can take seconds.
    """
    seen = set()
    while exc is not None and id(exc) not in seen:
        if isinstance(exc, socket.gaierror):
            return True
        seen.add(id(exc))
        exc = exc.__cause__ or exc.__context__
    return False


def outbound_headers() -> dict[str, str]:
    correlation_id = correlation_id_var.get()
    return {CORRELATION_HEADER: correlation_id} if correlation_id else {}


async def request_with_retry(
    method: str, url: str, *, attempts: int | None = None, **kwargs
) -> httpx.Response:
    """Call another service, retrying network errors and 5xx with exponential backoff.

    Returns the response for any status below 500 (the caller decides what a 4xx means).
    Raises the last error once every attempt has failed, or at once if the host does not resolve.
    """
    settings = get_settings()
    attempts = attempts or settings.http_max_retries
    headers = {**outbound_headers(), **kwargs.pop("headers", {})}
    last_error: Exception | None = None

    async with httpx.AsyncClient(
        timeout=settings.http_timeout_seconds, transport=transport, trust_env=False
    ) as client:
        for attempt in range(1, attempts + 1):
            try:
                response = await client.request(method, url, headers=headers, **kwargs)
                if response.status_code < 500:
                    return response
                last_error = httpx.HTTPStatusError(
                    f"Server error {response.status_code}", request=response.request, response=response
                )
            except httpx.RequestError as exc:
                last_error = exc
            logger.warning(
                "Service call failed",
                extra={"url": url, "attempt": attempt, "max_attempts": attempts, "error": str(last_error)},
            )
            if is_dns_failure(last_error):
                break
            if attempt < attempts:
                await asyncio.sleep(0.5 * 2 ** (attempt - 1))

    raise last_error  # type: ignore[misc]
