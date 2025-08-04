"""Celery tasks for fetching and storing Curve pool metrics."""

import logging
import os
from datetime import datetime, timedelta
from typing import Dict, List

from sqlalchemy import text

from .curve import fetch_pool_data
from .database import PoolMetric, SessionLocal
from .worker import celery_app


logger = logging.getLogger(__name__)


@celery_app.task(bind=True, autoretry_for=(Exception,), retry_backoff=True, retry_kwargs={"max_retries": 3})
def fetch_all_pool_metrics(self) -> int:
    """Fetch metrics for all pools and store them in the database.

    Returns the number of records inserted.
    """
    pool_metrics: List[Dict[str, float]] = fetch_pool_data()
    session = SessionLocal()
    # Ensure composite index exists for efficient lookups
    try:
        session.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_pool_metrics_pool_id_recorded_at ON pool_metrics (pool_id, recorded_at)"
            )
        )
    except Exception:  # pragma: no cover - best effort
        logger.debug("Index creation skipped", exc_info=True)

    try:
        count = 0
        now = datetime.utcnow()
        dedupe_window = timedelta(minutes=5)

        for metric in pool_metrics:
            existing = (
                session.query(PoolMetric)
                .filter(
                    PoolMetric.pool_id == metric["pool_id"],
                    PoolMetric.recorded_at >= now - dedupe_window,
                    PoolMetric.recorded_at <= now + dedupe_window,
                )
                .first()
            )
            if existing:
                continue

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

        # Optional cleanup of old metrics
        retention_days = int(os.getenv("POOL_METRIC_RETENTION_DAYS", "30"))
        if retention_days > 0:
            expiry = now - timedelta(days=retention_days)
            session.query(PoolMetric).filter(PoolMetric.recorded_at < expiry).delete()

        session.commit()
        return count
    except Exception as exc:  # pragma: no cover - executed on failure
        session.rollback()
        logger.exception("Failed to fetch/store pool metrics")
        raise self.retry(exc=exc)
    finally:
        session.close()
