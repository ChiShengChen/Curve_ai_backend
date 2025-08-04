"""FastAPI application exposing pool APY endpoints."""

from datetime import datetime, timedelta
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .database import SessionLocal, PoolMetric, init_db
from .services import calculate_total_earning

app = FastAPI(title="Curve APY API")
init_db()


@app.get("/pools/{pool_id}/apy")
def get_pool_apy(pool_id: str):
    """Return current APY and historical metrics for the given pool."""
    session: Session = SessionLocal()
    try:
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

        def serialize(metric: PoolMetric):
            return {
                "apy": metric.apy,
                "bribe": metric.bribe,
                "trading_fee": metric.trading_fee,
                "crv": metric.crv,
                "recorded_at": metric.recorded_at.isoformat(),
            }

        return {
            "pool_id": pool_id,
            "current": serialize(latest),
            "history": {
                "7d": [serialize(m) for m in history7],
                "30d": [serialize(m) for m in history30],
            },
        }
    finally:
        session.close()


class EarningsRequest(BaseModel):
    pool_id: str
    amount: float


@app.post("/users/{user_id}/earnings")
def post_user_earnings(user_id: str, payload: EarningsRequest):
    """Record a user's deposit and return projected earnings."""
    return calculate_total_earning(user_id, payload.pool_id, payload.amount)
