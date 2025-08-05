import pytest
from fastapi.testclient import TestClient

from apy.api import app
from prometheus_client import REGISTRY, CollectorRegistry

@pytest.fixture(scope="module")
def client():
    # Clear existing collectors to avoid duplicate metric registration during tests
    collectors = list(REGISTRY._collector_to_names)
    for collector in collectors:
        REGISTRY.unregister(collector)
    return TestClient(app)
