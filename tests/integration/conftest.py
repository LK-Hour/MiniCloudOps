import os

import httpx
import pytest

GATEWAY_URL = os.getenv("GATEWAY_URL", "http://localhost:8080")


@pytest.fixture(scope="session")
def api() -> httpx.Client:
    client = httpx.Client(base_url=GATEWAY_URL, timeout=10)
    try:
        client.get("/health").raise_for_status()
    except httpx.HTTPError:
        pytest.skip(f"MiniOps stack is not running at {GATEWAY_URL} (start it with `make up`)")
    yield client
    client.close()
