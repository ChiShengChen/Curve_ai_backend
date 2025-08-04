"""FastAPI application exposing pool APY and yield source endpoints."""

from datetime import datetime, timedelta
from typing import Dict, List, Generator

from fastapi import Depends, FastAPI, HTTPException

from pydantic import BaseModel, Field, confloat

from sqlalchemy.orm import Session

from .auth import verify_user
from .database import SessionLocal, PoolMetric, init_db
from .services import (
    calculate_total_earning,
    get_user_positions,
    create_deposit_transaction,
    get_deposit_transactions,
    create_withdrawal_transaction,
    get_withdrawal_transactions,
    create_rebalance_action,
    get_rebalance_actions,
    create_fund_deployment,
    get_fund_deployments,
    create_risk_adjustment,
    get_risk_adjustments,
)


app = FastAPI(title="Curve APY API")
init_db()


def get_db() -> Generator[Session, None, None]:
    """Provide a transactional scope around a series of operations."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


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

    amount: confloat(gt=0)
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

    amount: confloat(gt=0)
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


class RebalanceActionRequest(BaseModel):
    """Request body for recording a rebalance action."""

    old_pool: str
    new_pool: str
    old_apy: float
    new_apy: float
    strategy: str
    action_type: str
    moved_amount: float
    asset_type: str
    new_allocation: float
    gas_cost: float = 0.0


class RebalanceActionResponse(BaseModel):
    """Serialized rebalance action."""

    id: int
    user_id: str
    old_pool: str
    new_pool: str
    old_apy: float
    new_apy: float
    strategy: str
    action_type: str
    moved_amount: float
    asset_type: str
    new_allocation: float
    gas_cost: float
    executed_at: datetime

    class Config:
        orm_mode = True


class RebalanceListResponse(BaseModel):
    """Paginated list of rebalance actions."""

    total: int
    items: List[RebalanceActionResponse]


class RiskAdjustmentRequest(BaseModel):
    """Request body for recording a risk adjustment."""

    pool_id: str
    total_volatility: float
    trigger_event: str
    action_taken: str
    reallocated_amount: float
    asset_type: str
    old_risk_score: float
    new_risk_score: float


class RiskAdjustmentResponse(BaseModel):
    """Serialized risk adjustment record."""

    id: int
    user_id: str
    pool_id: str
    total_volatility: float
    trigger_event: str
    action_taken: str
    reallocated_amount: float
    asset_type: str
    old_risk_score: float
    new_risk_score: float
    recorded_at: datetime

    class Config:
        orm_mode = True


class RiskAdjustmentListResponse(BaseModel):
    """Paginated list of risk adjustments."""

    total: int
    items: List[RiskAdjustmentResponse]


class DeploymentRequest(BaseModel):
    """Request body for recording a fund deployment."""

    strategy: str
    risk_level: str
    expected_apy: float
    tx_fee: float = 0.0
    status: str = "pending"


class DeploymentResponse(BaseModel):
    """Serialized fund deployment."""

    id: int
    user_id: str
    strategy: str
    risk_level: str
    expected_apy: float
    tx_fee: float
    status: str
    executed_at: datetime

    class Config:
        orm_mode = True


class DeploymentListResponse(BaseModel):
    """Paginated list of fund deployments."""

    total: int
    items: List[DeploymentResponse]


class UserPositionItem(BaseModel):
    """Representation of a user's holdings in a pool."""

    pool_id: str
    amount: float
    projected_earning: float
    current_apr: float


class UserPositionsResponse(BaseModel):
    """Aggregated response for all user positions."""

    user_id: str
    total_amount: float
    total_projected_earning: float
    positions: List[UserPositionItem]


class EarningsRequest(BaseModel):
    """Request body for calculating earnings for a deposit."""

    pool_id: str = Field(..., description="Pool identifier")
    amount: confloat(gt=0) = Field(..., description="Amount to deposit")


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
def get_pool_apy(pool_id: str, db: Session = Depends(get_db)):
    """Return current APY and historical metrics for the given pool."""

    latest, history7, history30 = _get_metrics(db, pool_id)

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


@app.get("/pools/{pool_id}/yield-sources", response_model=YieldSourcesResponse)
def get_yield_sources(pool_id: str, db: Session = Depends(get_db)):
    """Return bribe, trading fee and CRV reward components for a pool."""

    latest, history7, history30 = _get_metrics(db, pool_id)

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


@app.post(
    "/users/{user_id}/deposits",
    response_model=DepositResponse,
    dependencies=[Depends(verify_user)],
)
def post_user_deposit(
    user_id: str, payload: DepositRequest, db: Session = Depends(get_db)
):
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


@app.get(
    "/users/{user_id}/deposits",
    response_model=DepositListResponse,
    dependencies=[Depends(verify_user)],
)
def get_user_deposits(
    user_id: str, skip: int = 0, limit: int = 10, db: Session = Depends(get_db)
):
    """Return paginated deposit transactions for the user."""

    records, total = get_deposit_transactions(user_id, skip, limit)
    return DepositListResponse(total=total, items=records)


@app.post(
    "/users/{user_id}/withdrawals",
    response_model=WithdrawalResponse,
    dependencies=[Depends(verify_user)],
)
def post_user_withdrawal(
    user_id: str, payload: WithdrawalRequest, db: Session = Depends(get_db)
):
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


@app.get(
    "/users/{user_id}/withdrawals",
    response_model=WithdrawalListResponse,
    dependencies=[Depends(verify_user)],
)
def get_user_withdrawals(
    user_id: str, skip: int = 0, limit: int = 10, db: Session = Depends(get_db)
):
    """Return paginated withdrawal transactions for the user."""

    records, total = get_withdrawal_transactions(user_id, skip, limit)
    return WithdrawalListResponse(total=total, items=records)


@app.post(
    "/users/{user_id}/deployments",
    response_model=DeploymentResponse,
    dependencies=[Depends(verify_user)],
)
def post_user_deployment(
    user_id: str, payload: DeploymentRequest, db: Session = Depends(get_db)
):
    """Record a new fund deployment for the user."""

    return create_fund_deployment(
        user_id=user_id,
        strategy=payload.strategy,
        risk_level=payload.risk_level,
        expected_apy=payload.expected_apy,
        tx_fee=payload.tx_fee,
        status=payload.status,
    )


@app.get(
    "/users/{user_id}/deployments",
    response_model=DeploymentListResponse,
    dependencies=[Depends(verify_user)],
)
def get_user_deployments(
    user_id: str,
    skip: int = 0,
    limit: int = 10,
    status: str | None = None,
    strategy: str | None = None,
    risk_level: str | None = None,
    db: Session = Depends(get_db),
):
    """Return paginated fund deployments for the user with optional filters."""

    records, total = get_fund_deployments(
        user_id,
        skip=skip,
        limit=limit,
        status=status,
        strategy=strategy,
        risk_level=risk_level,
    )
    return DeploymentListResponse(total=total, items=records)


@app.get(
    "/users/{user_id}/positions",
    response_model=UserPositionsResponse,
    dependencies=[Depends(verify_user)],
)
def get_user_positions_endpoint(
    user_id: str, db: Session = Depends(get_db)
) -> UserPositionsResponse:
    """Return aggregated positions and earnings for the user."""

    return get_user_positions(user_id)


@app.post(
    "/users/{user_id}/rebalances",
    response_model=RebalanceActionResponse,
    dependencies=[Depends(verify_user)],
)
def post_user_rebalance(
    user_id: str, payload: RebalanceActionRequest, db: Session = Depends(get_db)
):
    """Record a new rebalance action for the user."""

    return create_rebalance_action(
        user_id=user_id,
        old_pool=payload.old_pool,
        new_pool=payload.new_pool,
        old_apy=payload.old_apy,
        new_apy=payload.new_apy,
        strategy=payload.strategy,
        action_type=payload.action_type,
        moved_amount=payload.moved_amount,
        asset_type=payload.asset_type,
        new_allocation=payload.new_allocation,
        gas_cost=payload.gas_cost,
    )


@app.get(
    "/users/{user_id}/rebalances",
    response_model=RebalanceListResponse,
    dependencies=[Depends(verify_user)],
)
def get_user_rebalances(
    user_id: str, skip: int = 0, limit: int = 10, db: Session = Depends(get_db)
):
    """Return paginated rebalance actions for the user."""

    records, total = get_rebalance_actions(user_id, skip, limit)
    return RebalanceListResponse(total=total, items=records)


@app.post(
    "/users/{user_id}/risk-adjustments",
    response_model=RiskAdjustmentResponse,
    dependencies=[Depends(verify_user)],
)
def post_user_risk_adjustment(
    user_id: str, payload: RiskAdjustmentRequest, db: Session = Depends(get_db)
):
    """Record a new risk adjustment for the user."""

    return create_risk_adjustment(
        user_id=user_id,
        pool_id=payload.pool_id,
        total_volatility=payload.total_volatility,
        trigger_event=payload.trigger_event,
        action_taken=payload.action_taken,
        reallocated_amount=payload.reallocated_amount,
        asset_type=payload.asset_type,
        old_risk_score=payload.old_risk_score,
        new_risk_score=payload.new_risk_score,
    )


@app.get(
    "/users/{user_id}/risk-adjustments",
    response_model=RiskAdjustmentListResponse,
    dependencies=[Depends(verify_user)],
)
def get_user_risk_adjustments(
    user_id: str, skip: int = 0, limit: int = 10, db: Session = Depends(get_db)
):
    """Return paginated risk adjustment records for the user."""

    records, total = get_risk_adjustments(user_id, skip, limit)
    return RiskAdjustmentListResponse(total=total, items=records)


@app.post(
    "/users/{user_id}/earnings",
    dependencies=[Depends(verify_user)],
)
def post_user_earnings(
    user_id: str, payload: EarningsRequest, db: Session = Depends(get_db)
) -> Dict[str, float]:
    """Record a user's deposit and return projected earnings."""
    return calculate_total_earning(user_id, payload.pool_id, payload.amount)
