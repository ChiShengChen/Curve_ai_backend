"""Database setup for storing pool metrics."""

import os
from datetime import datetime
from sqlalchemy import create_engine, Column, Integer, Float, String, DateTime
from sqlalchemy.orm import sessionmaker, declarative_base

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///curve.db")

engine = create_engine(DATABASE_URL, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
Base = declarative_base()


class PoolMetric(Base):
    """SQLAlchemy model for a snapshot of pool metrics."""

    __tablename__ = "pool_metrics"

    id = Column(Integer, primary_key=True, index=True)
    pool_id = Column(String, index=True, nullable=False)
    apy = Column(Float)
    bribe = Column(Float)
    trading_fee = Column(Float)
    crv_reward = Column(Float)
    recorded_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class UserPosition(Base):
    """Track per-user deposits into pools."""

    __tablename__ = "user_positions"

    user_id = Column(String, primary_key=True)
    pool_id = Column(String, primary_key=True)
    amount = Column(Float, default=0.0)
    last_updated = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class DepositTransaction(Base):
    """Record on-chain deposit transactions for a user."""

    __tablename__ = "deposit_transactions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String, index=True, nullable=False)
    amount = Column(Float, nullable=False)
    asset = Column(String, nullable=False)
    from_address = Column(String, nullable=False)
    network = Column(String, nullable=False)
    gas_fee = Column(Float, default=0.0)
    net_received = Column(Float, nullable=False)
    status = Column(String, default="pending")
    tx_hash = Column(String, unique=True, index=True, nullable=False)
    recorded_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class WithdrawalTransaction(Base):
    """Record on-chain withdrawal transactions for a user."""

    __tablename__ = "withdrawal_transactions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String, index=True, nullable=False)
    amount = Column(Float, nullable=False)
    asset = Column(String, nullable=False)
    to_address = Column(String, nullable=False)
    network = Column(String, nullable=False)
    gas_fee = Column(Float, default=0.0)
    net_received = Column(Float, nullable=False)
    status = Column(String, default="pending")
    tx_hash = Column(String, unique=True, index=True, nullable=False)
    recorded_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class RebalanceAction(Base):
    """Record strategy-driven rebalance actions for a user."""

    __tablename__ = "rebalance_actions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String, index=True, nullable=False)
    old_pool = Column(String, nullable=False)
    new_pool = Column(String, nullable=False)
    old_apy = Column(Float, nullable=False)
    new_apy = Column(Float, nullable=False)
    strategy = Column(String, nullable=False)
    action_type = Column(String, nullable=False)
    moved_amount = Column(Float, nullable=False)
    asset_type = Column(String, nullable=False)
    new_allocation = Column(Float, nullable=False)
    gas_cost = Column(Float, default=0.0)
    executed_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class FundDeployment(Base):
    """Record fund deployments initiated for a user."""

    __tablename__ = "fund_deployments"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String, index=True, nullable=False)
    strategy = Column(String, nullable=False)
    risk_level = Column(String, nullable=False)
    expected_apy = Column(Float, nullable=False)
    tx_fee = Column(Float, default=0.0)
    status = Column(String, default="pending")
    executed_at = Column(DateTime, default=datetime.utcnow, nullable=False)


def init_db() -> None:
    """Create database tables if they do not exist."""
    Base.metadata.create_all(bind=engine)
