import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from apy.apy_calc import calculate_compound_apy
from apy.database import Base, PoolMetric
from apy import services


@pytest.fixture
def session_local(monkeypatch):
    """Provide an isolated in-memory database for each test."""
    engine = create_engine("sqlite:///:memory:", future=True)
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    Base.metadata.create_all(bind=engine)
    monkeypatch.setattr(services, "SessionLocal", TestingSessionLocal)
    return TestingSessionLocal


def test_calculate_compound_apy_no_data():
    assert calculate_compound_apy([]) == 0.0


def test_calculate_compound_apy_negative_returns():
    result = calculate_compound_apy([-10.0, -5.0])
    assert result == pytest.approx(-14.5, rel=1e-3)


def test_service_calculate_total_earning_no_metrics(session_local):
    res = services.calculate_total_earning("u1", "p1", 100.0)
    assert res["projected_earning"] == 0.0
    summary = services.get_user_positions("u1")
    assert summary["total_projected_earning"] == 0.0


def test_service_negative_returns(session_local):
    session = session_local()
    session.add_all([
        PoolMetric(pool_id="p1", apy=-10.0),
        PoolMetric(pool_id="p1", apy=-5.0),
    ])
    session.commit()
    session.close()

    res = services.calculate_total_earning("u2", "p1", 100.0)
    assert res["projected_earning"] == pytest.approx(-14.5, rel=1e-3)

    summary = services.get_user_positions("u2")
    assert summary["total_projected_earning"] == pytest.approx(-14.5, rel=1e-3)
