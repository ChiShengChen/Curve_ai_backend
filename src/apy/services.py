"""Service layer for user earnings calculations."""

import logging
from datetime import datetime
from typing import Dict, List, Tuple

from fastapi import HTTPException
from prometheus_client import Counter
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from .database import (
    SessionLocal,
    PoolMetric,
    UserPosition,
    DepositTransaction,
    WithdrawalTransaction,
    RebalanceAction,
    FundDeployment,
    RiskAdjustment,
)
from .apy_calc import calculate_compound_apy
from .ai.model import PoolAPYModel, MODEL_PATH
from .blockchain import verify_transaction


logger = logging.getLogger(__name__)

# Prometheus counters for key service events
DEPOSIT_COUNTER = Counter(
    "deposit_transactions_total", "Total deposit transactions created"
)
WITHDRAWAL_COUNTER = Counter(
    "withdrawal_transactions_total", "Total withdrawal transactions created"
)
REBALANCE_COUNTER = Counter(
    "rebalance_actions_total", "Total rebalance actions created"
)
DEPLOYMENT_COUNTER = Counter(
    "fund_deployments_total", "Total fund deployments created"
)
RISK_ADJUST_COUNTER = Counter(
    "risk_adjustments_total", "Total risk adjustments created"
)


def _handle_service_error(session: Session, exc: Exception) -> None:
    """Rollback transaction and raise HTTP exception for service errors."""
    session.rollback()
    logger.exception("service layer error", exc_info=exc)
    if isinstance(exc, SQLAlchemyError):
        raise HTTPException(status_code=500, detail="Database error") from exc
    raise HTTPException(status_code=400, detail=str(exc)) from exc


def get_pool_ids() -> List[str]:
    """Return all distinct pool identifiers in the database."""

    session: Session = SessionLocal()
    try:
        rows = session.query(PoolMetric.pool_id).distinct().all()
        return [row[0] for row in rows]
    except Exception as exc:
        _handle_service_error(session, exc)
    finally:
        session.close()


def get_pool_apy_history(
    pool_id: str, start: datetime | None = None, end: datetime | None = None
) -> List[PoolMetric]:
    """Retrieve APY metrics for a pool within an optional date range."""

    session: Session = SessionLocal()
    try:
        if start and end and start > end:
            raise HTTPException(status_code=400, detail="start must be before end")

        query = session.query(PoolMetric).filter(PoolMetric.pool_id == pool_id)
        if start:
            query = query.filter(PoolMetric.recorded_at >= start)
        if end:
            query = query.filter(PoolMetric.recorded_at <= end)

        metrics = query.order_by(PoolMetric.recorded_at).all()
        if not metrics:
            raise HTTPException(status_code=404, detail="Pool not found")
        return metrics
    except Exception as exc:
        _handle_service_error(session, exc)
    finally:
        session.close()


def calculate_total_earning(user_id: str, pool_id: str, amount: float) -> Dict[str, float]:
    """Update user deposit and calculate projected earnings.

    Parameters
    ----------
    user_id: str
        Identifier of the user.
    pool_id: str
        Identifier of the pool being deposited to.
    amount: float
        Amount the user is depositing.

    Returns
    -------
    dict
        Dictionary containing total_amount, projected_earning and current_apr.
    """
    logger.info(
        "calculate earning user=%s pool=%s amount=%s", user_id, pool_id, amount
    )
    session: Session = SessionLocal()
    try:
        # Update or create the user's position
        position = (
            session.query(UserPosition)
            .filter(
                UserPosition.user_id == user_id,
                UserPosition.pool_id == pool_id,
            )
            .first()
        )
        now = datetime.utcnow()
        if position:
            position.amount += amount
            position.last_updated = now
        else:
            position = UserPosition(
                user_id=user_id,
                pool_id=pool_id,
                amount=amount,
                last_updated=now,
            )
            session.add(position)
        session.commit()

        total_amount = position.amount

        # Historical APY: compounded across all records for the pool
        rows = (
            session.query(PoolMetric.apy)
            .filter(PoolMetric.pool_id == pool_id)
            .order_by(PoolMetric.recorded_at)
            .all()
        )
        apy_series = [r[0] for r in rows if r[0] is not None]
        compounded_apy = calculate_compound_apy(apy_series)
        projected_earning = total_amount * (compounded_apy / 100)

        # Current APR from latest snapshot
        latest = (
            session.query(PoolMetric)
            .filter(PoolMetric.pool_id == pool_id)
            .order_by(PoolMetric.recorded_at.desc())
            .first()
        )
        current_apr = latest.apy if latest and latest.apy is not None else 0.0

        result = {
            "user_id": user_id,
            "pool_id": pool_id,
            "total_amount": total_amount,
            "projected_earning": projected_earning,
            "current_apr": current_apr,
        }
        logger.info(
            "calculated earning user=%s pool=%s projected=%s",
            user_id,
            pool_id,
            projected_earning,
        )
        return result
    except Exception as exc:
        _handle_service_error(session, exc)
    finally:
        session.close()


def get_user_positions(user_id: str) -> Dict[str, object]:
    """Aggregate a user's positions with projected earnings and APR.

    Parameters
    ----------
    user_id: str
        Identifier of the user.

    Returns
    -------
    dict
        Summary containing per-pool positions and overall totals.
    """
    session: Session = SessionLocal()
    try:
        positions = (
            session.query(UserPosition)
            .filter(UserPosition.user_id == user_id)
            .all()
        )

        items: List[Dict[str, float]] = []
        total_amount = 0.0
        total_earning = 0.0

        for pos in positions:
            rows = (
                session.query(PoolMetric.apy)
                .filter(PoolMetric.pool_id == pos.pool_id)
                .order_by(PoolMetric.recorded_at)
                .all()
            )
            apy_series = [r[0] for r in rows if r[0] is not None]
            compounded_apy = calculate_compound_apy(apy_series)
            projected = pos.amount * (compounded_apy / 100)

            latest = (
                session.query(PoolMetric)
                .filter(PoolMetric.pool_id == pos.pool_id)
                .order_by(PoolMetric.recorded_at.desc())
                .first()
            )
            current_apr = latest.apy if latest and latest.apy is not None else 0.0

            items.append(
                {
                    "pool_id": pos.pool_id,
                    "amount": pos.amount,
                    "projected_earning": projected,
                    "current_apr": current_apr,
                }
            )
            total_amount += pos.amount
            total_earning += projected

        return {
            "user_id": user_id,
            "total_amount": total_amount,
            "total_projected_earning": total_earning,
            "positions": items,
        }
    except Exception as exc:
        _handle_service_error(session, exc)
    finally:
        session.close()


def create_deposit_transaction(
    user_id: str,
    amount: float,
    asset: str,
    from_address: str,
    network: str,
    gas_fee: float,
    net_received: float,
    status: str,
    tx_hash: str,
):
    """Persist a new deposit transaction for the given user."""

    logger.info(
        "create deposit user=%s amount=%s asset=%s", user_id, amount, asset
    )
    session: Session = SessionLocal()
    try:
        # Verify the transaction on-chain before recording it.  This prevents
        # storing bogus hashes and ensures the transaction has actually been
        # mined successfully.
        if not verify_transaction(tx_hash, network):
            raise ValueError("transaction not found or not confirmed")

        deposit = DepositTransaction(
            user_id=user_id,
            amount=amount,
            asset=asset,
            from_address=from_address,
            network=network,
            gas_fee=gas_fee,
            net_received=net_received,
            status=status,
            tx_hash=tx_hash,
        )
        session.add(deposit)
        session.commit()
        session.refresh(deposit)
        DEPOSIT_COUNTER.inc()
        logger.info(
            "created deposit id=%s user=%s amount=%s", deposit.id, user_id, amount
        )
        return deposit
    except Exception as exc:
        _handle_service_error(session, exc)
    finally:
        session.close()


def get_deposit_transactions(
    user_id: str, skip: int = 0, limit: int = 10
) -> Tuple[List[DepositTransaction], int]:
    """Retrieve paginated deposit transactions for a user."""

    session: Session = SessionLocal()
    try:
        query = session.query(DepositTransaction).filter(DepositTransaction.user_id == user_id)
        total = query.count()
        records = (
            query.order_by(DepositTransaction.recorded_at.desc())
            .offset(skip)
            .limit(limit)
            .all()
        )
        return records, total
    except Exception as exc:
        _handle_service_error(session, exc)
    finally:
        session.close()


def create_withdrawal_transaction(
    user_id: str,
    amount: float,
    asset: str,
    to_address: str,
    network: str,
    gas_fee: float,
    net_received: float,
    status: str,
    tx_hash: str,
):
    """Persist a new withdrawal transaction for the given user."""

    logger.info(
        "create withdrawal user=%s amount=%s asset=%s", user_id, amount, asset
    )
    session: Session = SessionLocal()
    try:
        # Validate the on-chain transaction prior to recording to avoid
        # persisting invalid or pending withdrawals.
        if not verify_transaction(tx_hash, network):
            raise ValueError("transaction not found or not confirmed")

        withdrawal = WithdrawalTransaction(
            user_id=user_id,
            amount=amount,
            asset=asset,
            to_address=to_address,
            network=network,
            gas_fee=gas_fee,
            net_received=net_received,
            status=status,
            tx_hash=tx_hash,
        )
        session.add(withdrawal)
        session.commit()
        session.refresh(withdrawal)
        WITHDRAWAL_COUNTER.inc()
        logger.info(
            "created withdrawal id=%s user=%s amount=%s",
            withdrawal.id,
            user_id,
            amount,
        )
        return withdrawal
    except Exception as exc:
        _handle_service_error(session, exc)
    finally:
        session.close()


def get_withdrawal_transactions(
    user_id: str, skip: int = 0, limit: int = 10
) -> Tuple[List[WithdrawalTransaction], int]:
    """Retrieve paginated withdrawal transactions for a user."""

    session: Session = SessionLocal()
    try:
        query = session.query(WithdrawalTransaction).filter(
            WithdrawalTransaction.user_id == user_id
        )
        total = query.count()
        records = (
            query.order_by(WithdrawalTransaction.recorded_at.desc())
            .offset(skip)
            .limit(limit)
            .all()
        )
        return records, total
    except Exception as exc:
        _handle_service_error(session, exc)
    finally:
        session.close()


def create_rebalance_action(
    user_id: str,
    old_pool: str,
    new_pool: str,
    old_apy: float,
    new_apy: float,
    strategy: str,
    action_type: str,
    moved_amount: float,
    asset_type: str,
    new_allocation: float,
    gas_cost: float,
    executed_at: datetime | None = None,
):
    """Persist a new rebalance action for the given user."""

    logger.info(
        "create rebalance user=%s old_pool=%s new_pool=%s",
        user_id,
        old_pool,
        new_pool,
    )
    session: Session = SessionLocal()
    try:
        action = RebalanceAction(
            user_id=user_id,
            old_pool=old_pool,
            new_pool=new_pool,
            old_apy=old_apy,
            new_apy=new_apy,
            strategy=strategy,
            action_type=action_type,
            moved_amount=moved_amount,
            asset_type=asset_type,
            new_allocation=new_allocation,
            gas_cost=gas_cost,
            executed_at=executed_at or datetime.utcnow(),
        )
        session.add(action)
        session.commit()
        session.refresh(action)
        REBALANCE_COUNTER.inc()
        logger.info(
            "created rebalance id=%s user=%s", action.id, user_id
        )
        return action
    except Exception as exc:
        _handle_service_error(session, exc)
    finally:
        session.close()


def get_rebalance_actions(
    user_id: str, skip: int = 0, limit: int = 10
) -> Tuple[List[RebalanceAction], int]:
    """Retrieve paginated rebalance actions for a user."""

    session: Session = SessionLocal()
    try:
        query = session.query(RebalanceAction).filter(RebalanceAction.user_id == user_id)
        total = query.count()
        records = (
            query.order_by(RebalanceAction.executed_at.desc())
            .offset(skip)
            .limit(limit)
            .all()
        )
        return records, total
    except Exception as exc:
        _handle_service_error(session, exc)
    finally:
        session.close()


def create_fund_deployment(
    user_id: str,
    strategy: str,
    risk_level: str,
    expected_apy: float,
    tx_fee: float,
    status: str,
    executed_at: datetime | None = None,
):
    """Persist a fund deployment record for the given user."""

    logger.info(
        "create deployment user=%s strategy=%s risk=%s",
        user_id,
        strategy,
        risk_level,
    )
    session: Session = SessionLocal()
    try:
        deployment = FundDeployment(
            user_id=user_id,
            strategy=strategy,
            risk_level=risk_level,
            expected_apy=expected_apy,
            tx_fee=tx_fee,
            status=status,
            executed_at=executed_at or datetime.utcnow(),
        )
        session.add(deployment)
        session.commit()
        session.refresh(deployment)
        DEPLOYMENT_COUNTER.inc()
        logger.info(
            "created deployment id=%s user=%s", deployment.id, user_id
        )
        return deployment
    except Exception as exc:
        _handle_service_error(session, exc)
    finally:
        session.close()


def get_fund_deployments(
    user_id: str,
    skip: int = 0,
    limit: int = 10,
    status: str | None = None,
    strategy: str | None = None,
    risk_level: str | None = None,
) -> Tuple[List[FundDeployment], int]:
    """Retrieve paginated fund deployments for a user with optional filters."""

    session: Session = SessionLocal()
    try:
        query = session.query(FundDeployment).filter(FundDeployment.user_id == user_id)
        if status:
            query = query.filter(FundDeployment.status == status)
        if strategy:
            query = query.filter(FundDeployment.strategy == strategy)
        if risk_level:
            query = query.filter(FundDeployment.risk_level == risk_level)
        total = query.count()
        records = (
            query.order_by(FundDeployment.executed_at.desc())
            .offset(skip)
            .limit(limit)
            .all()
        )
        return records, total
    except Exception as exc:
        _handle_service_error(session, exc)
    finally:
        session.close()


def create_risk_adjustment(
    user_id: str,
    pool_id: str,
    total_volatility: float,
    trigger_event: str,
    action_taken: str,
    reallocated_amount: float,
    asset_type: str,
    old_risk_score: float,
    new_risk_score: float,
    recorded_at: datetime | None = None,
):
    """Persist a risk adjustment entry for the given user."""

    logger.info(
        "create risk adjustment user=%s pool=%s", user_id, pool_id
    )
    session: Session = SessionLocal()
    try:
        adjustment = RiskAdjustment(
            user_id=user_id,
            pool_id=pool_id,
            total_volatility=total_volatility,
            trigger_event=trigger_event,
            action_taken=action_taken,
            reallocated_amount=reallocated_amount,
            asset_type=asset_type,
            old_risk_score=old_risk_score,
            new_risk_score=new_risk_score,
            recorded_at=recorded_at or datetime.utcnow(),
        )
        session.add(adjustment)
        session.commit()
        session.refresh(adjustment)
        RISK_ADJUST_COUNTER.inc()
        logger.info(
            "created risk adjustment id=%s user=%s",
            adjustment.id,
            user_id,
        )
        return adjustment
    except Exception as exc:
        _handle_service_error(session, exc)
    finally:
        session.close()


def get_risk_adjustments(
    user_id: str, skip: int = 0, limit: int = 10
) -> Tuple[List[RiskAdjustment], int]:
    """Retrieve paginated risk adjustments for a user."""

    session: Session = SessionLocal()
    try:
        query = session.query(RiskAdjustment).filter(RiskAdjustment.user_id == user_id)
        total = query.count()
        records = (
            query.order_by(RiskAdjustment.recorded_at.desc())
            .offset(skip)
            .limit(limit)
            .all()
        )
        return records, total
    except Exception as exc:
        _handle_service_error(session, exc)
    finally:
        session.close()


def _load_trained_model() -> PoolAPYModel:
    """Helper to load the persisted regression model."""
    try:
        return PoolAPYModel.load(MODEL_PATH)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=500, detail="model file not found") from exc


def predict_pool_apy(pool_id: str) -> float:
    """Predict the APY for the latest snapshot of the given pool."""

    session: Session = SessionLocal()
    try:
        latest = (
            session.query(PoolMetric)
            .filter(PoolMetric.pool_id == pool_id)
            .order_by(PoolMetric.recorded_at.desc())
            .first()
        )
        if not latest:
            raise HTTPException(status_code=404, detail="Pool not found")
        features = [
            latest.bribe or 0.0,
            latest.trading_fee or 0.0,
            latest.crv_reward or 0.0,
        ]
        model = _load_trained_model()
        return model.predict(features)
    except Exception as exc:
        _handle_service_error(session, exc)
    finally:
        session.close()


def suggest_rebalance(user_id: str) -> Dict[str, object]:
    """Suggest a pool for the user based on predicted APYs."""

    session: Session = SessionLocal()
    try:
        positions = (
            session.query(UserPosition)
            .filter(UserPosition.user_id == user_id)
            .all()
        )
        if not positions:
            raise HTTPException(status_code=404, detail="User has no positions")

        pool_ids = [row[0] for row in session.query(PoolMetric.pool_id).distinct().all()]
        model = _load_trained_model()

        predictions: Dict[str, float] = {}
        for pid in pool_ids:
            latest = (
                session.query(PoolMetric)
                .filter(PoolMetric.pool_id == pid)
                .order_by(PoolMetric.recorded_at.desc())
                .first()
            )
            if not latest:
                continue
            features = [
                latest.bribe or 0.0,
                latest.trading_fee or 0.0,
                latest.crv_reward or 0.0,
            ]
            predictions[pid] = model.predict(features)

        best_pool = max(predictions, key=predictions.get)
        top_position = max(positions, key=lambda p: p.amount)
        current_pool = top_position.pool_id
        current_pred = predictions.get(current_pool, 0.0)

        return {
            "user_id": user_id,
            "current_pool": current_pool,
            "current_predicted_apy": current_pred,
            "recommended_pool": best_pool,
            "recommended_apy": predictions[best_pool],
        }
    except Exception as exc:
        _handle_service_error(session, exc)
    finally:
        session.close()
