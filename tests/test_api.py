from datetime import datetime

from fastapi.testclient import TestClient

from apy.api import app


def test_get_pool_apy(monkeypatch):
    now = datetime.utcnow()

    class DummyMetric:
        def __init__(self):
            self.apy = 1.0
            self.bribe = 0.1
            self.trading_fee = 0.2
            self.crv_reward = 0.3
            self.recorded_at = now

    def fake_history(pool_id: str, start=None, end=None):
        return [DummyMetric()]

    monkeypatch.setattr("apy.api.get_pool_apy_history", fake_history)

    client = TestClient(app)
    response = client.get("/pools/sample/apy")
    assert response.status_code == 200
    data = response.json()
    assert data["pool_id"] == "sample"
    assert data["current"]["apy"] == 1.0
    assert len(data["history"]) == 1
