"""Outbound HTTP to other MiniOps services: timeouts, retries with backoff, correlation ID."""
import asyncio
import logging

import httpx

from app.config import get_settings
from app.logging_config import correlation_id_var
from app.middleware import CORRELATION_HEADER

logger = logging.getLogger(__name__)


def outbound_headers() -> dict[str, str]:
    correlation_id = correlation_id_var.get()
    return {CORRELATION_HEADER: correlation_id} if correlation_id else {}


async def request_with_retry(method: str, url: str, **kwargs) -> httpx.Response:
    """Call another service, retrying network errors and 5xx with exponential backoff."""
    settings = get_settings()
    headers = {**outbound_headers(), **kwargs.pop("headers", {})}
    last_error: Exception | None = None

    async with httpx.AsyncClient(timeout=settings.http_timeout_seconds) as client:
        for attempt in range(1, settings.http_max_retries + 1):
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
                extra={"url": url, "attempt": attempt, "error": str(last_error)},
            )
            if attempt < settings.http_max_retries:
                await asyncio.sleep(0.5 * 2 ** (attempt - 1))

    raise last_error  # type: ignore[misc]
