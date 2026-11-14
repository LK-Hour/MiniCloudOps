import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client() -> TestClient:
    # Not used as a context manager, so the lifespan (DB setup) does not run.
    return TestClient(app)
