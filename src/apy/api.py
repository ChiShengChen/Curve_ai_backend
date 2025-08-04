"""FastAPI application exposing pool APY and yield source endpoints."""

from datetime import datetime, timedelta
from typing import Dict, List

from fastapi import FastAPI, HTTPException

from pydantic import BaseModel, Field

from sqlalchemy.orm import Session

from .database import SessionLocal, PoolMetric, init_db
from .services import (
    calculate_total_earning,
    create_deposit_transaction,
    get_deposit_transactions,
    create_withdrawal_transaction,
    get_withdrawal_transactions,
)


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


class DepositRequest(BaseModel):
    """Request body for creating a deposit transaction."""

    amount: float
    asset: str
    from_address: str
    network: str
    gas_fee: float = 0.0
    net_received: float
    status: str = "pending"
    tx_hash: str


class DepositResponse(DepositRequest):
    """Serialized deposit transaction."""

    id: int
    user_id: str
    recorded_at: datetime

    class Config:
        orm_mode = True


class DepositListResponse(BaseModel):
    """Paginated list of deposit transactions."""

    total: int
    items: List[DepositResponse]


class WithdrawalRequest(BaseModel):
    """Request body for creating a withdrawal transaction."""

    amount: float
    asset: str
    to_address: str
    network: str
    gas_fee: float = 0.0
    net_received: float
    status: str = "pending"
    tx_hash: str


class WithdrawalResponse(WithdrawalRequest):
    """Serialized withdrawal transaction."""

    id: int
    user_id: str
    recorded_at: datetime

    class Config:
        orm_mode = True


class WithdrawalListResponse(BaseModel):
    """Paginated list of withdrawal transactions."""

    total: int
    items: List[WithdrawalResponse]


class EarningsRequest(BaseModel):
    """Request body for calculating earnings for a deposit."""

    pool_id: str
    amount: float


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


@app.post("/users/{user_id}/deposits", response_model=DepositResponse)
def post_user_deposit(user_id: str, payload: DepositRequest):
    """Record a new deposit transaction for the user."""

    return create_deposit_transaction(
        user_id=user_id,
        amount=payload.amount,
        asset=payload.asset,
        from_address=payload.from_address,
        network=payload.network,
        gas_fee=payload.gas_fee,
        net_received=payload.net_received,
        status=payload.status,
        tx_hash=payload.tx_hash,
    )


@app.get("/users/{user_id}/deposits", response_model=DepositListResponse)
def get_user_deposits(user_id: str, skip: int = 0, limit: int = 10):
    """Return paginated deposit transactions for the user."""

    records, total = get_deposit_transactions(user_id, skip, limit)
    return DepositListResponse(total=total, items=records)


@app.post("/users/{user_id}/withdrawals", response_model=WithdrawalResponse)
def post_user_withdrawal(user_id: str, payload: WithdrawalRequest):
    """Record a new withdrawal transaction for the user."""

    return create_withdrawal_transaction(
        user_id=user_id,
        amount=payload.amount,
        asset=payload.asset,
        to_address=payload.to_address,
        network=payload.network,
        gas_fee=payload.gas_fee,
        net_received=payload.net_received,
        status=payload.status,
        tx_hash=payload.tx_hash,
    )


@app.get("/users/{user_id}/withdrawals", response_model=WithdrawalListResponse)
def get_user_withdrawals(user_id: str, skip: int = 0, limit: int = 10):
    """Return paginated withdrawal transactions for the user."""

    records, total = get_withdrawal_transactions(user_id, skip, limit)
    return WithdrawalListResponse(total=total, items=records)


@app.post("/users/{user_id}/earnings")
def post_user_earnings(user_id: str, payload: EarningsRequest):
    """Record a user's deposit and return projected earnings."""
    return calculate_total_earning(user_id, payload.pool_id, payload.amount)
