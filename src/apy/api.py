"""FastAPI application exposing pool APY and yield source endpoints."""

from datetime import datetime, timedelta
from typing import Dict, List

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from .database import SessionLocal, PoolMetric, init_db


app = FastAPI(title="Curve APY API")
init_db()


class YieldComponent(BaseModel):
    """Breakdown of APY sources for a snapshot."""

    bribe: float = Field(0.0, description="Bribe APY component")
    trading_fee: float = Field(0.0, description="Trading fee APY component")
    crv_reward: float = Field(0.0, description="CRV reward APY component")
    recorded_at: datetime


class APYSnapshot(YieldComponent):
    """A snapshot including the total APY."""

    apy: float = Field(0.0, description="Total APY")


class APYHistoryResponse(BaseModel):
    """Response schema for APY metrics including history."""

    pool_id: str
    current: APYSnapshot
    history: Dict[str, List[APYSnapshot]]


class YieldSourcesResponse(BaseModel):
    """Response schema for yield source breakdown."""

    pool_id: str
    current: YieldComponent
    history: Dict[str, List[YieldComponent]]


def _get_metrics(session: Session, pool_id: str):
    """Retrieve latest metric and 7/30 day histories for a pool."""

    latest = (
        session.query(PoolMetric)
        .filter(PoolMetric.pool_id == pool_id)
        .order_by(PoolMetric.recorded_at.desc())
        .first()
    )
    if not latest:
        raise HTTPException(status_code=404, detail="Pool not found")

    now = datetime.utcnow()
    seven_days = now - timedelta(days=7)
    thirty_days = now - timedelta(days=30)

    history7 = (
        session.query(PoolMetric)
        .filter(PoolMetric.pool_id == pool_id, PoolMetric.recorded_at >= seven_days)
        .order_by(PoolMetric.recorded_at)
        .all()
    )
    history30 = (
        session.query(PoolMetric)
        .filter(PoolMetric.pool_id == pool_id, PoolMetric.recorded_at >= thirty_days)
        .order_by(PoolMetric.recorded_at)
        .all()
    )
    return latest, history7, history30


@app.get("/pools/{pool_id}/apy", response_model=APYHistoryResponse)
def get_pool_apy(pool_id: str):
    """Return current APY and historical metrics for the given pool."""

    session: Session = SessionLocal()
    try:
        latest, history7, history30 = _get_metrics(session, pool_id)

        def serialize(metric: PoolMetric) -> APYSnapshot:
            return APYSnapshot(
                apy=metric.apy,
                bribe=metric.bribe,
                trading_fee=metric.trading_fee,
                crv_reward=metric.crv_reward,
                recorded_at=metric.recorded_at,
            )

        return APYHistoryResponse(
            pool_id=pool_id,
            current=serialize(latest),
            history={
                "7d": [serialize(m) for m in history7],
                "30d": [serialize(m) for m in history30],
            },
        )
    finally:
        session.close()


@app.get("/pools/{pool_id}/yield-sources", response_model=YieldSourcesResponse)
def get_yield_sources(pool_id: str):
    """Return bribe, trading fee and CRV reward components for a pool."""

    session: Session = SessionLocal()
    try:
        latest, history7, history30 = _get_metrics(session, pool_id)

        def serialize(metric: PoolMetric) -> YieldComponent:
            return YieldComponent(
                bribe=metric.bribe,
                trading_fee=metric.trading_fee,
                crv_reward=metric.crv_reward,
                recorded_at=metric.recorded_at,
            )

        return YieldSourcesResponse(
            pool_id=pool_id,
            current=serialize(latest),
            history={
                "7d": [serialize(m) for m in history7],
                "30d": [serialize(m) for m in history30],
            },
        )
    finally:
        session.close()

