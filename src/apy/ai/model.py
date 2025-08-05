"""Basic regression model for predicting pool APY.

This module defines a lightweight wrapper around a scikit-learn
``LinearRegression`` model.  It provides helper methods for training,
serializing and loading the model so that it can be used by the service
layer to make APY forecasts or rebalance suggestions.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List

import joblib
import numpy as np
from sklearn.linear_model import LinearRegression

# Default location where the trained model is stored.
MODEL_PATH = Path(__file__).resolve().with_name("model.joblib")


@dataclass
class PoolAPYModel:
    """Wrapper for a scikit-learn regression model."""

    model: LinearRegression

    def train(self, X: Iterable[List[float]], y: Iterable[float]) -> None:
        """Fit the regression model using the provided dataset."""
        X_arr = np.asarray(list(X))
        y_arr = np.asarray(list(y))
        self.model.fit(X_arr, y_arr)

    def predict(self, features: List[float]) -> float:
        """Predict APY given pool feature inputs."""
        X_arr = np.asarray([features])
        return float(self.model.predict(X_arr)[0])

    def save(self, path: Path = MODEL_PATH) -> None:
        """Persist the trained model to disk."""
        path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(self.model, path)

    @classmethod
    def load(cls, path: Path = MODEL_PATH) -> "PoolAPYModel":
        """Load a previously trained model from disk."""
        model = joblib.load(path)
        return cls(model)


def load_default_model() -> PoolAPYModel:
    """Convenience helper to load the default model."""
    return PoolAPYModel.load(MODEL_PATH)
