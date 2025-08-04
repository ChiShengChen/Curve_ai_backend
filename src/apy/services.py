"""Service layer for user earnings calculations."""

from datetime import datetime
from typing import Dict, List, Tuple

from sqlalchemy import func
from sqlalchemy.orm import Session

from .database import (
    SessionLocal,
    PoolMetric,
    UserPosition,
    DepositTransaction,
    WithdrawalTransaction,
)


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

        # Historical APY: average across all records for the pool
        avg_apy = (
            session.query(func.avg(PoolMetric.apy))
            .filter(PoolMetric.pool_id == pool_id)
            .scalar()
        ) or 0.0
        projected_earning = total_amount * (avg_apy / 100)

        # Current APR from latest snapshot
        latest = (
            session.query(PoolMetric)
            .filter(PoolMetric.pool_id == pool_id)
            .order_by(PoolMetric.recorded_at.desc())
            .first()
        )
        current_apr = latest.apy if latest and latest.apy is not None else 0.0

        return {
            "user_id": user_id,
            "pool_id": pool_id,
            "total_amount": total_amount,
            "projected_earning": projected_earning,
            "current_apr": current_apr,
        }
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

    session: Session = SessionLocal()
    try:
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
        return deposit
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

    session: Session = SessionLocal()
    try:
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
        return withdrawal
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
    finally:
        session.close()
