"""Celery application with a periodic task to update pool metrics."""

from celery import Celery

celery_app = Celery(
    "apy",
    broker="redis://localhost:6379/0",
    backend="redis://localhost:6379/0",
)

celery_app.conf.beat_schedule = {
    "fetch-pool-metrics": {
        "task": "apy.tasks.fetch_all_pool_metrics",
        # every 8 hours
        "schedule": 60 * 60 * 8,
    }
}
celery_app.conf.timezone = "UTC"
