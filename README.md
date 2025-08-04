# Curve AI Backend

This project provides a small service that periodically fetches Curve Finance pool
metrics and stores them in a database. A REST API exposes the latest APY along with
historical data for each pool.

## Components

- **Celery worker** (`apy.worker`): schedules a task every 8 hours to retrieve pool
  metrics from the Curve API and store them in the `pool_metrics` table.
- **FastAPI app** (`apy.api`): exposes `GET /pools/{pool_id}/apy` returning current
  APY data plus 7-day and 30-day histories.
- **Curve API wrapper** (`apy.curve`): helper client that normalizes data from the
  public Curve Finance API.

## API Wrapper

The module `apy.curve` serves as a lightweight client around the public
[Curve Finance API](https://api.curve.fi/api/getPools/ethereum/main). It retrieves
raw pool data and normalizes the most common metrics so they are easy to consume by
the rest of the service or by external scripts.

```python
from apy.curve import fetch_pool_data

for pool in fetch_pool_data():
    print(pool["pool_id"], pool["apy"])
```

Each item in the returned list contains the pool identifier along with its APY,
bribe, trading fee and CRV reward components.

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
