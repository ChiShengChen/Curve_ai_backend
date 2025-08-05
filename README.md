# Curve AI Backend

The **Curve AI Backend** is a small service that synchronizes metrics from the
public [Curve Finance API](https://api.curve.fi/api/getPools/ethereum/main),
persists them in a database, and exposes a REST interface for querying pool
performance and tracking user activity.  The goal is to provide a ready‑to‑use
foundation for applications that need historical APY data and simple accounting
of deposits, withdrawals, rebalances and other strategy events.

---

## Architecture

| Component | Description |
| --- | --- |
| **FastAPI application** (`apy.api`) | Serves public endpoints for pool metrics and protected endpoints for user actions.  Rate limiting is handled by **SlowAPI** and Prometheus counters record request statistics. |
| **Celery worker** (`apy.worker`) | Periodically runs `fetch_all_pool_metrics` to collect APY, bribe, trading fee and CRV reward metrics.  The default schedule runs every 8 hours but can be changed via configuration. |
| **Service layer** (`apy.services`) | Implements business logic such as calculating projected earnings, aggregating positions and persisting user actions.  Prometheus counters track each type of event. |
| **Database** (`apy.database`) | Uses SQLAlchemy models for `pool_metrics`, user transactions and actions.  Tables are created automatically on startup. |
| **Authentication** (`apy.auth`) | Simple bearer‑token scheme.  Tokens are loaded from the `API_TOKENS` environment variable and each token is bound to a user id. |

### Configuration

Configuration values (database URL, Redis URL, task schedule and API title) are
defined in `apy.config` and sourced from environment variables.

### Metrics and Rate Limiting

* **SlowAPI** enforces `5/minute` and `100/hour` limits on sensitive user‑write
  endpoints.
* **Prometheus** counters track API calls and service events allowing external
  monitoring.

---

## Getting Started

Install dependencies and run the development server:

```bash
pip install -e .
uvicorn apy.api:app --reload
```

Run the Celery worker with beat to refresh pool metrics on a schedule:

```bash
celery -A apy.worker.celery_app worker --beat
```

Apply database migrations (Alembic is configured but the ORM can create tables
automatically on first run):

```bash
alembic upgrade head
```

---

## Authentication

All `/users/{user_id}/*` endpoints require a bearer token.  Configure tokens as
comma‑separated `user:token` pairs:

```bash
export API_TOKENS="alice:alice-token,bob:bob-token"
```

Requests must include the token in the `Authorization` header:

```bash
curl -H "Authorization: Bearer alice-token" \
     http://localhost:8000/users/alice/positions
```

Tokens may only access resources for their own user; otherwise `403 Forbidden`
is returned.

---

## API Overview

### Pool Endpoints

| Endpoint | Description |
| --- | --- |
| `GET /pools` | List available pool identifiers. |
| `GET /pools/{pool_id}/apy` | Return latest APY snapshot and history for the pool. |
| `GET /pools/{pool_id}/yield-sources` | Return bribe, trading fee and CRV reward breakdown. |

#### Example

```bash
curl http://localhost:8000/pools/sample/apy
```

```json
{
  "pool_id": "sample",
  "current": {
    "apy": 1.0,
    "bribe": 0.1,
    "trading_fee": 0.2,
    "crv_reward": 0.3,
    "recorded_at": "2024-01-01T00:00:00Z"
  },
  "history": [ { ... same as current ... } ]
}
```

### User Endpoints

All routes below require authentication.

| Endpoint | Purpose |
| --- | --- |
| `POST /users/{user_id}/deposits` | Log a deposit transaction. |
| `GET /users/{user_id}/deposits` | List recorded deposits with pagination. |
| `POST /users/{user_id}/withdrawals` | Log a withdrawal transaction. |
| `GET /users/{user_id}/withdrawals` | List withdrawals. |
| `POST /users/{user_id}/deployments` | Record a fund deployment action. |
| `GET /users/{user_id}/deployments` | List deployments with optional filters. |
| `POST /users/{user_id}/rebalances` | Record a strategy rebalance. |
| `GET /users/{user_id}/rebalances` | List rebalance actions. |
| `POST /users/{user_id}/risk-adjustments` | Record a risk‑driven adjustment. |
| `GET /users/{user_id}/risk-adjustments` | List risk adjustments. |
| `GET /users/{user_id}/positions` | Aggregated holdings and projected earnings. |
| `POST /users/{user_id}/earnings` | Update a position by depositing and return new totals. |

#### Sample deposit

```bash
curl -X POST http://localhost:8000/users/alice/deposits \
  -H "Authorization: Bearer alice-token" \
  -H "Content-Type: application/json" \
  -d '{
        "amount": 100.0,
        "asset": "USDC",
        "from_address": "0xabc",
        "network": "ethereum",
        "gas_fee": 0.5,
        "net_received": 99.5,
        "status": "completed",
        "tx_hash": "0xdeadbeef"
      }'
```

Expected response:

```json
{
  "id": 1,
  "user_id": "alice",
  "amount": 100.0,
  "asset": "USDC",
  "from_address": "0xabc",
  "network": "ethereum",
  "gas_fee": 0.5,
  "net_received": 99.5,
  "status": "completed",
  "tx_hash": "0xdeadbeef",
  "recorded_at": "2024-01-01T00:00:00Z"
}
```

#### Sample positions query

```bash
curl -H "Authorization: Bearer alice-token" \
     http://localhost:8000/users/alice/positions
```

```json
{
  "user_id": "alice",
  "total_amount": 100.0,
  "total_projected_earning": 1.0,
  "positions": [
    {
      "pool_id": "sample",
      "amount": 100.0,
      "projected_earning": 1.0,
      "current_apr": 1.0
    }
  ]
}
```

---

## API Wrapper

`apy.curve` wraps the public Curve Finance API and normalizes its output:

```python
from apy.curve import fetch_pool_data

for pool in fetch_pool_data():
    print(pool["pool_id"], pool["apy"])
```

Each element includes the pool identifier plus APY and its yield components
(`bribe`, `trading_fee`, `crv_reward`).

---

## Contributing & Development

To run the test suite:

```bash
pytest
```

Feel free to open issues or submit pull requests for improvements.

