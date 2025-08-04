"""Celery tasks for fetching and storing Curve pool metrics."""

from datetime import datetime
from typing import List, Dict

from .worker import celery_app
from .curve import fetch_pool_data
from .database import SessionLocal, PoolMetric


@celery_app.task
def fetch_all_pool_metrics() -> int:
    """Fetch metrics for all pools and store them in the database.

    Returns the number of records inserted.
    """
    pool_metrics: List[Dict[str, float]] = fetch_pool_data()
    session = SessionLocal()
    try:
        count = 0
        now = datetime.utcnow()
        for metric in pool_metrics:
            session.add(
                PoolMetric(
                    pool_id=metric["pool_id"],
                    apy=metric.get("apy"),
                    bribe=metric.get("bribe"),
                    trading_fee=metric.get("trading_fee"),
                    crv_reward=metric.get("crv_reward"),
                    recorded_at=now,
                )
            )
            count += 1
        session.commit()
        return count
    finally:
        session.close()
