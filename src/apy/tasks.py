"""Celery tasks for fetching and storing Curve pool metrics."""

import logging
import os
from datetime import datetime, timedelta
from typing import Dict, List

from prometheus_client import Counter, Gauge
from sqlalchemy import text

from .curve import fetch_pool_data
from .onchain import fetch_onchain_pool_data
from .database import PoolMetric, SessionLocal
from .worker import celery_app


logger = logging.getLogger(__name__)

# Counter to track how many pool metrics are persisted
METRIC_INSERT_COUNTER = Counter(
    "pool_metrics_inserted_total", "Total pool metrics inserted"
)

# Gauges and counters to record the status of upstream data sources
DATA_SOURCE_STATUS = Gauge(
    "pool_metric_data_source_status",
    "Status of pool metric data sources (1=success,0=failed)",
    ["source"],
)
DATA_SOURCE_FAILURE_COUNTER = Counter(
    "pool_metric_data_source_failures_total",
    "Total number of failures for each pool metric data source",
    ["source"],
)


# Use manual retry handling to get finer control over exceptions
@celery_app.task(bind=True, max_retries=3, default_retry_delay=60)
def fetch_all_pool_metrics(self) -> int:
    """Fetch metrics for all pools and store them in the database.

    Returns the number of records inserted.
    """
    logger.info("fetching pool metrics")
    pool_metrics: List[Dict[str, float]] = []

    try:
        pool_metrics = fetch_onchain_pool_data()
        if not pool_metrics:
            raise ValueError("empty on-chain result")
        DATA_SOURCE_STATUS.labels(source="onchain").set(1)
        DATA_SOURCE_STATUS.labels(source="api").set(0)
    except Exception:  # pragma: no cover - network failure
        logger.warning("on-chain data fetch failed, falling back to Curve API", exc_info=True)
        DATA_SOURCE_STATUS.labels(source="onchain").set(0)
        DATA_SOURCE_FAILURE_COUNTER.labels(source="onchain").inc()
        pool_metrics = fetch_pool_data()
        if pool_metrics:
            DATA_SOURCE_STATUS.labels(source="api").set(1)
        else:
            DATA_SOURCE_STATUS.labels(source="api").set(0)
            DATA_SOURCE_FAILURE_COUNTER.labels(source="api").inc()
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
        inserted = 0
        updated = 0
        now = datetime.utcnow()

        for metric in pool_metrics:
            # allow incoming data to provide its own timestamp, defaulting to now
            recorded_at = metric.get("recorded_at", now)
            existing = (
                session.query(PoolMetric)
                .filter(
                    PoolMetric.pool_id == metric["pool_id"],
                    PoolMetric.recorded_at == recorded_at,
                )
                .first()
            )
            if existing:
                existing.apy = metric.get("apy")
                existing.bribe = metric.get("bribe")
                existing.trading_fee = metric.get("trading_fee")
                existing.crv_reward = metric.get("crv_reward")
                updated += 1
            else:
                session.add(
                    PoolMetric(
                        pool_id=metric["pool_id"],
                        apy=metric.get("apy"),
                        bribe=metric.get("bribe"),
                        trading_fee=metric.get("trading_fee"),
                        crv_reward=metric.get("crv_reward"),
                        recorded_at=recorded_at,
                    )
                )
                inserted += 1

        # Optional cleanup of old metrics
        retention_days = int(os.getenv("POOL_METRIC_RETENTION_DAYS", "30"))
        if retention_days > 0:
            expiry = now - timedelta(days=retention_days)
            session.query(PoolMetric).filter(PoolMetric.recorded_at < expiry).delete()

        session.commit()
        METRIC_INSERT_COUNTER.inc(inserted)
        logger.info("inserted %d and updated %d pool metrics", inserted, updated)
        return inserted
    except Exception as exc:  # pragma: no cover - executed on failure
        session.rollback()
        logger.exception("Failed to fetch/store pool metrics")
        raise self.retry(exc=exc)
    finally:
        session.close()
