"""The HTTP health check itself: one GET request, timed."""
import time
from dataclasses import dataclass
from typing import Literal

import httpx

USER_AGENT = "MiniOps-Monitor/0.1"


@dataclass(frozen=True)
class ProbeResult:
    status: Literal["UP", "DOWN"]
    status_code: int | None = None
    response_time_ms: float | None = None  # None when no response arrived
    error: str | None = None


async def probe(
    url: str, *, timeout: float, transport: httpx.AsyncBaseTransport | None = None
) -> ProbeResult:
    """GET `url`. Any 2xx or 3xx answer is UP; a 4xx/5xx answer, timeout or connection error is DOWN.

    Redirects are not followed: a redirect could point at an internal address that the SSRF
    check never saw. The body is never read, so a large response costs nothing.
    Proxy environment variables are ignored for the same reason.
    """
    start = time.perf_counter()
    try:
        async with httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=False,
            trust_env=False,
            transport=transport,
            headers={"User-Agent": USER_AGENT},
        ) as client:
            async with client.stream("GET", url) as response:
                elapsed_ms = round((time.perf_counter() - start) * 1000, 2)
                code = response.status_code
    except httpx.TimeoutException:
        return ProbeResult("DOWN", error=f"Timed out after {timeout:g}s")
    except httpx.RequestError as exc:
        return ProbeResult("DOWN", error=f"Connection failed ({type(exc).__name__})")

    if 200 <= code < 400:
        return ProbeResult("UP", status_code=code, response_time_ms=elapsed_ms)
    return ProbeResult("DOWN", status_code=code, response_time_ms=elapsed_ms, error=f"HTTP {code}")
