# Curve AI Backend

This project provides a small service that periodically fetches Curve Finance pool
metrics and stores them in a database. A REST API exposes the latest APY along with
historical data for each pool.

## Components

- **Celery worker** (`apy.worker`): schedules a task every 8 hours to retrieve pool
  metrics from the Curve API and store them in the `pool_metrics` table.
- **FastAPI app** (`apy.api`): exposes `GET /pools/{pool_id}/apy` returning current
  APY data plus 7-day and 30-day histories.

## Development

Install dependencies and run the API:

```bash
pip install -e .
uvicorn apy.api:app --reload
```

Start the Celery worker with beat enabled:

```bash
celery -A apy.worker.celery_app worker --beat
```
