"""Celery application with a periodic task to update pool metrics."""

from celery import Celery

from .config import settings


celery_app = Celery(
    "apy",
    broker=settings.redis_url,
    backend=settings.redis_url,
)

celery_app.conf.beat_schedule = {
    "fetch-pool-metrics": {
        "task": "apy.tasks.fetch_all_pool_metrics",
        "schedule": settings.schedule_frequency,
    }
}
celery_app.conf.timezone = "UTC"
