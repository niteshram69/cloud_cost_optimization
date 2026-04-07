"""ML classifier for adaptive storage temperature prediction."""

from __future__ import annotations

from dataclasses import dataclass

import joblib
import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, classification_report

from app.decision_engine.types import DataTemperature
from app.feature_engineering.models import FeatureVector

_LABEL_TO_CLASS = {
    0: DataTemperature.HOT,
    1: DataTemperature.COLD,
    2: DataTemperature.ARCHIVE,
}
_CLASS_TO_LABEL = {value: key for key, value in _LABEL_TO_CLASS.items()}


@dataclass(slots=True)
class MLPredictionResult:
    """Prediction output for a single feature vector."""

    predicted_class: DataTemperature
    confidence: float
    class_probabilities: dict[str, float]
    model_version: str


@dataclass(slots=True)
class MLTrainingSummary:
    """Training summary returned by the model training pipeline."""

    model_version: str
    n_samples: int
    accuracy: float
    classes: list[str]
    report: dict


class StorageMLClassifier:
    """RandomForest classifier for HOT/COLD/ARCHIVE prediction."""

    VERSION = "rf-v1"

    def __init__(self, model: RandomForestClassifier | None = None):
        self.model = model or RandomForestClassifier(
            n_estimators=300,
            max_depth=16,
            min_samples_leaf=3,
            class_weight="balanced_subsample",
            random_state=42,
            n_jobs=-1,
        )
        self._is_trained = False

    @property
    def is_trained(self) -> bool:
        """Return whether the model has been trained."""
        return self._is_trained

    def train(self, features: list[FeatureVector], labels: list[DataTemperature]) -> MLTrainingSummary:
        """Fit the model from in-memory feature vectors."""
        if len(features) != len(labels):
            raise ValueError("features and labels must have equal length")
        if len(features) < 20:
            raise ValueError("at least 20 labeled samples are required for model training")

        x = np.array([feature.ml_columns() for feature in features], dtype=float)
        y = np.array([_CLASS_TO_LABEL[label] for label in labels], dtype=int)

        self.model.fit(x, y)
        self._is_trained = True

        y_pred = self.model.predict(x)
        accuracy = float(accuracy_score(y, y_pred))
        report = classification_report(y, y_pred, output_dict=True, zero_division=0)

        return MLTrainingSummary(
            model_version=self.VERSION,
            n_samples=len(features),
            accuracy=accuracy,
            classes=[c.value for c in DataTemperature],
            report=report,
        )

    def predict(self, feature: FeatureVector) -> MLPredictionResult:
        """Predict class and confidence for one object."""
        if not self._is_trained:
            raise RuntimeError("ML model is not trained")

        x = np.array([feature.ml_columns()], dtype=float)
        label_idx = int(self.model.predict(x)[0])
        probabilities = self.model.predict_proba(x)[0]

        class_probs = {
            _LABEL_TO_CLASS[idx].value: float(prob)
            for idx, prob in enumerate(probabilities)
        }

        confidence = max(class_probs.values()) if class_probs else 0.0
        predicted_class = _LABEL_TO_CLASS[label_idx]

        return MLPredictionResult(
            predicted_class=predicted_class,
            confidence=confidence,
            class_probabilities=class_probs,
            model_version=self.VERSION,
        )

    def save(self, model_path: str) -> None:
        """Persist model with metadata."""
        artifact = {
            "version": self.VERSION,
            "model": self.model,
            "is_trained": self._is_trained,
        }
        joblib.dump(artifact, model_path)

    @classmethod
    def load(cls, model_path: str) -> "StorageMLClassifier":
        """Load model artifact from disk."""
        artifact = joblib.load(model_path)
        classifier = cls(model=artifact["model"])
        classifier._is_trained = bool(artifact.get("is_trained", True))
        return classifier
