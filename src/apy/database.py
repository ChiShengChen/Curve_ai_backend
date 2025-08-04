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


def init_db() -> None:
    """Create database tables if they do not exist."""
    Base.metadata.create_all(bind=engine)
