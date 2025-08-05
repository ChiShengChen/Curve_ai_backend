"""Script for training the pool APY prediction model."""

from __future__ import annotations

from sqlalchemy.orm import Session
from sklearn.linear_model import LinearRegression

from ..database import SessionLocal, PoolMetric
from .model import PoolAPYModel, MODEL_PATH


def _fetch_training_data(session: Session):
    """Retrieve features and targets from the database."""
    rows = (
        session.query(
            PoolMetric.bribe,
            PoolMetric.trading_fee,
            PoolMetric.crv_reward,
            PoolMetric.apy,
        )
        .filter(
            PoolMetric.bribe.isnot(None),
            PoolMetric.trading_fee.isnot(None),
            PoolMetric.crv_reward.isnot(None),
            PoolMetric.apy.isnot(None),
        )
        .all()
    )
    X = [[r[0], r[1], r[2]] for r in rows]
    y = [r[3] for r in rows]
    return X, y


def train_and_save_model() -> None:
    """Train the regression model and persist it to disk."""
    session: Session = SessionLocal()
    try:
        X, y = _fetch_training_data(session)
        if not X:
            raise RuntimeError("No training data available")
        model = PoolAPYModel(LinearRegression())
        model.train(X, y)
        model.save(MODEL_PATH)
    finally:
        session.close()


if __name__ == "__main__":
    train_and_save_model()
