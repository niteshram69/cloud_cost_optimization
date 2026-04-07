from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import random

try:
    import numpy as np
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.metrics import accuracy_score, classification_report, confusion_matrix
    from sklearn.model_selection import train_test_split
    from sklearn.preprocessing import StandardScaler
except Exception:  # pragma: no cover - optional runtime guard
    np = None  # type: ignore[assignment]
    RandomForestClassifier = None  # type: ignore[assignment]
    train_test_split = None  # type: ignore[assignment]
    accuracy_score = None  # type: ignore[assignment]
    classification_report = None  # type: ignore[assignment]
    confusion_matrix = None  # type: ignore[assignment]
    StandardScaler = None  # type: ignore[assignment]

from backend.app.models import DataTemperature


@dataclass(slots=True)
class MetadataFeatures:
    requests_30d: float
    latency_ms: float
    monthly_cost: float
    object_count: float


@dataclass(slots=True)
class MetadataTrainingSummary:
    model_version: str
    train_samples: int
    validation_samples: int
    accuracy: float
    labels: list[str]
    confusion_matrix: list[list[int]]
    classification_report: dict[str, dict | float]


@dataclass(slots=True)
class MetadataClassification:
    selected: DataTemperature
    ml_predicted: DataTemperature
    ml_confidence: float
    source: str
    baseline: DataTemperature


class MetadataTemperatureClassifier:
    """Hybrid metadata classifier: ML-first with deterministic fallback."""

    VERSION = "metadata-rf-v3-log-object-count"

    def __init__(
        self,
        *,
        synthetic_samples: int = 1000,
        random_state: int = 42,
        confidence_threshold: float = 0.65,
    ) -> None:
        self._synthetic_samples = max(300, synthetic_samples)
        self._random_state = random_state
        self._confidence_threshold = confidence_threshold
        self._rng = random.Random(random_state)
        self._label_to_temp = {
            "Hot": DataTemperature.HOT,
            "Cold": DataTemperature.COLD,
            "Archive": DataTemperature.ARCHIVE,
        }
        self._model = None
        self._scaler = None
        self._is_trained = False
        self._training_summary: MetadataTrainingSummary | None = None
        if (
            RandomForestClassifier is not None
            and np is not None
            and train_test_split is not None
            and StandardScaler is not None
        ):
            self._model = RandomForestClassifier(
                n_estimators=200,
                max_depth=10,
                class_weight="balanced_subsample",
                min_samples_leaf=2,
                random_state=random_state,
            )
            self._scaler = StandardScaler()
        self.train()

    @property
    def training_summary(self) -> MetadataTrainingSummary | None:
        return self._training_summary

    def train(self) -> MetadataTrainingSummary | None:
        if (
            self._model is None
            or self._scaler is None
            or np is None
            or train_test_split is None
            or accuracy_score is None
            or classification_report is None
            or confusion_matrix is None
        ):
            self._is_trained = False
            self._training_summary = None
            return None
        x, y = self._build_synthetic_training_data(self._synthetic_samples)
        self._validate_training_inputs(x=x, y=y)
        x_train_raw, x_test_raw, y_train, y_test = train_test_split(
            x,
            y,
            test_size=0.2,
            random_state=self._random_state,
            stratify=y,
        )
        x_train = self._scaler.fit_transform(x_train_raw)
        x_test = self._scaler.transform(x_test_raw)

        self._model.fit(x_train, y_train)
        self._is_trained = True
        y_pred = self._model.predict(x_test)
        labels = ["Hot", "Cold", "Archive"]
        matrix = confusion_matrix(y_test, y_pred, labels=labels)
        summary = MetadataTrainingSummary(
            model_version=self.VERSION,
            train_samples=int(len(x_train_raw)),
            validation_samples=int(len(x_test_raw)),
            accuracy=float(accuracy_score(y_test, y_pred)),
            labels=labels,
            confusion_matrix=[[int(cell) for cell in row] for row in matrix.tolist()],
            classification_report=classification_report(y_test, y_pred, labels=labels, output_dict=True, zero_division=0),
        )
        self._training_summary = summary
        return summary

    def _validate_training_inputs(self, *, x, y) -> None:
        if np is None:
            return
        if x.ndim != 2 or x.shape[1] != 4:
            raise ValueError(f"Training matrix must be shape [n,4], got {x.shape}")
        if x.shape[0] < 100:
            raise ValueError(f"Training matrix has too few rows: {x.shape[0]}")
        if y.ndim != 1 or y.shape[0] != x.shape[0]:
            raise ValueError(f"Label vector shape mismatch: x={x.shape}, y={y.shape}")
        if not np.isfinite(x).all():
            raise ValueError("Training matrix contains non-finite values")
        if y.dtype.kind in {"f", "i", "u"} and not np.isfinite(y).all():
            raise ValueError("Label vector contains non-finite values")

        # Assert real feature variance to avoid collapsed models.
        std = np.std(x, axis=0)
        if (std <= 0).any():
            raise ValueError(f"Feature collapse detected (zero variance): std={std.tolist()}")

        # x[:,3] is log10(object_count+1); if it is <=0 everywhere, object_count is broken.
        if float(np.max(x[:, 3])) <= 0.0:
            raise ValueError("Invalid object_count feature: log_object_count max must be > 0")

        classes = set(str(item) for item in y.tolist())
        missing_classes = {"Hot", "Cold", "Archive"} - classes
        if missing_classes:
            raise ValueError(f"Training labels missing classes: {sorted(missing_classes)}")

    def classify(self, features: MetadataFeatures) -> MetadataClassification:
        validated = self._validate_features(features)
        baseline = self._baseline_rule(validated)
        if not self._is_trained:
            return MetadataClassification(
                selected=baseline,
                ml_predicted=baseline,
                ml_confidence=0.0,
                source="rule_fallback",
                baseline=baseline,
            )

        if self._scaler is None:
            return MetadataClassification(
                selected=baseline,
                ml_predicted=baseline,
                ml_confidence=0.0,
                source="rule_fallback",
                baseline=baseline,
            )
        vector = np.array([self._model_features(validated)], dtype=float)
        vector_scaled = self._scaler.transform(vector)
        probs = self._model.predict_proba(vector_scaled)[0]
        pred_idx = int(np.argmax(probs))
        ml_label = str(self._model.classes_[pred_idx])
        ml_temp = self._label_to_temp.get(ml_label, baseline)
        confidence = float(probs[pred_idx])
        selected = ml_temp if confidence >= self._confidence_threshold else baseline
        source = "ml" if confidence >= self._confidence_threshold else "rule_fallback"
        return MetadataClassification(
            selected=selected,
            ml_predicted=ml_temp,
            ml_confidence=min(0.999, max(0.0, confidence)),
            source=source,
            baseline=baseline,
        )

    def _validate_features(self, features: MetadataFeatures) -> MetadataFeatures:
        requests = self._assert_finite_non_negative("requests_30d", features.requests_30d)
        latency = self._assert_finite_non_negative("latency_ms", features.latency_ms)
        monthly = self._assert_finite_non_negative("monthly_cost", features.monthly_cost)
        object_count = self._assert_finite_positive("object_count", features.object_count)
        return MetadataFeatures(
            requests_30d=requests,
            latency_ms=latency,
            monthly_cost=monthly,
            object_count=object_count,
        )

    def _baseline_rule(self, features: MetadataFeatures) -> DataTemperature:
        if features.requests_30d > 40_000 and features.latency_ms < 150:
            return DataTemperature.HOT
        if features.requests_30d > 500:
            return DataTemperature.COLD
        return DataTemperature.ARCHIVE

    def _model_features(self, features: MetadataFeatures) -> list[float]:
        object_count = float(features.object_count)
        # Critical normalization fix: object_count magnitude was collapsing predictions to a single class.
        log_object_count = float(np.log10(object_count + 1.0)) if np is not None else 0.0
        return [
            float(features.requests_30d),
            float(features.latency_ms),
            float(features.monthly_cost),
            log_object_count,
        ]

    @staticmethod
    def _assert_finite_non_negative(name: str, value: float) -> float:
        numeric = float(value)
        if np is not None and not np.isfinite(numeric):
            raise ValueError(f"Feature '{name}' must be finite, got {numeric!r}")
        if numeric < 0:
            raise ValueError(f"Feature '{name}' must be >= 0, got {numeric!r}")
        return numeric

    @staticmethod
    def _assert_finite_positive(name: str, value: float) -> float:
        numeric = float(value)
        if np is not None and not np.isfinite(numeric):
            raise ValueError(f"Feature '{name}' must be finite, got {numeric!r}")
        if numeric <= 0:
            raise ValueError(f"Feature '{name}' must be > 0, got {numeric!r}")
        return numeric

    def _build_synthetic_training_data(self, n: int):
        if np is None:
            raise RuntimeError("numpy is required for synthetic training data generation")
        # Keep training distribution balanced and explicit to reduce class bias.
        hot_count = int(n * 0.4)
        cold_count = int(n * 0.4)
        archive_count = max(1, n - hot_count - cold_count)
        rows: list[list[float]] = []
        labels: list[str] = []
        rows.extend(self._generate_rows(category="Hot", count=hot_count))
        labels.extend(["Hot"] * hot_count)
        rows.extend(self._generate_rows(category="Cold", count=cold_count))
        labels.extend(["Cold"] * cold_count)
        rows.extend(self._generate_rows(category="Archive", count=archive_count))
        labels.extend(["Archive"] * archive_count)

        bundle = list(zip(rows, labels))
        self._rng.shuffle(bundle)
        shuffled_rows = [item[0] for item in bundle]
        shuffled_labels = [item[1] for item in bundle]
        return np.array(shuffled_rows, dtype=float), np.array(shuffled_labels, dtype=object)

    def _generate_rows(self, *, category: str, count: int) -> list[list[float]]:
        rows: list[list[float]] = []
        for _ in range(count):
            if category == "Hot":
                requests_30d = self._rng.uniform(40_500, 180_000)
                latency_ms = self._rng.uniform(30, 145)
                monthly_cost = self._rng.uniform(250, 5000)
                object_count = self._rng.uniform(100, 5_000_000_000)
            elif category == "Cold":
                requests_30d = self._rng.uniform(600, 40_000)
                latency_ms = self._rng.uniform(120, 1800)
                monthly_cost = self._rng.uniform(20, 2200)
                object_count = self._rng.uniform(100, 8_000_000_000)
            else:
                requests_30d = self._rng.uniform(0, 500)
                latency_ms = self._rng.uniform(400, 4500)
                monthly_cost = self._rng.uniform(1, 600)
                object_count = self._rng.uniform(500, 12_000_000_000)
            rows.append(
                [
                    float(max(requests_30d, 0.0)),
                    float(max(latency_ms, 0.0)),
                    float(max(monthly_cost, 0.0)),
                    float(np.log10(max(object_count, 0.0) + 1.0)),
                ]
            )
        return rows


@lru_cache(maxsize=1)
def get_metadata_classifier() -> MetadataTemperatureClassifier:
    return MetadataTemperatureClassifier()
