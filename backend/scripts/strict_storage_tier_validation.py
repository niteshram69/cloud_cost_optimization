from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import classification_report, confusion_matrix
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Strict validation/training harness for storage tier classification."
    )
    parser.add_argument(
        "--dataset",
        type=Path,
        required=True,
        help="Path to JSON dataset file",
    )
    parser.add_argument(
        "--test-size",
        type=float,
        default=0.2,
        help="Test split size (default: 0.2)",
    )
    parser.add_argument(
        "--random-state",
        type=int,
        default=42,
        help="Random seed (default: 42)",
    )
    return parser.parse_args()


def _extract(container: dict[str, Any], *path: str) -> Any:
    current: Any = container
    for key in path:
        if not isinstance(current, dict) or key not in current:
            raise ValueError(f"Missing required key: {path[-1]}")
        current = current[key]
    return current


def _to_float_strict(value: Any, field_name: str) -> float:
    if value is None:
        raise ValueError(f"Missing numeric value for {field_name}")
    if isinstance(value, str) and not value.strip():
        raise ValueError(f"Missing numeric value for {field_name}")
    try:
        numeric = float(value)
    except Exception as exc:  # pragma: no cover - strict conversion guard
        raise ValueError(f"Invalid numeric value for {field_name}") from exc
    if not np.isfinite(numeric):
        raise ValueError(f"Non-finite numeric value for {field_name}")
    return numeric


def _label_rule(row: pd.Series) -> str:
    if row["requests_30d"] > 40_000 and row["latency_ms"] < 150:
        return "Hot"
    if row["requests_30d"] > 500:
        return "Cold"
    return "Archive"


def load_and_flatten(path: Path) -> pd.DataFrame:
    raw = pd.read_json(path)
    if raw.empty:
        raise ValueError("Dataset is empty")

    rows: list[dict[str, float]] = []
    for index, item in raw.iterrows():
        record: Any = item.to_dict()
        if "record" in record and isinstance(record["record"], dict):
            record = record["record"]
        if not isinstance(record, dict):
            raise ValueError(f"Row {index}: expected object payload")

        requests_30d = _to_float_strict(
            _extract(record, "usage_metrics", "requests_30d"), "requests_30d"
        )
        latency_ms = _to_float_strict(
            _extract(record, "performance_metrics", "avg_latency_ms"), "latency_ms"
        )
        monthly_cost = _to_float_strict(
            _extract(record, "cost_metrics", "monthly_cost_usd"), "monthly_cost"
        )
        object_count = _to_float_strict(
            _extract(record, "storage_metrics", "object_count"), "object_count"
        )

        rows.append(
            {
                "requests_30d": requests_30d,
                "latency_ms": latency_ms,
                "monthly_cost": monthly_cost,
                "object_count": object_count,
            }
        )

    df = pd.DataFrame(rows)
    return df


def assert_feature_integrity(df: pd.DataFrame) -> None:
    print(df["object_count"].describe())

    assert df["object_count"].min() > 0, "object_count is ZERO somewhere"
    assert df["object_count"].max() > 1000, "object_count not realistic"

    df["log_object_count"] = np.log10(df["object_count"] + 1.0)

    print(
        df[
            [
                "requests_30d",
                "latency_ms",
                "monthly_cost",
                "log_object_count",
            ]
        ].describe()
    )

    variance = df[
        [
            "requests_30d",
            "latency_ms",
            "monthly_cost",
            "log_object_count",
        ]
    ].var()
    if (variance <= 0).any():
        bad = variance[variance <= 0].index.tolist()
        raise ValueError(f"Feature collapse detected in columns: {bad}")


def train_and_validate(df: pd.DataFrame, *, test_size: float, random_state: int) -> None:
    df = df.copy()
    df["log_object_count"] = np.log10(df["object_count"] + 1.0)
    df["tier"] = df.apply(_label_rule, axis=1)

    x = df[["requests_30d", "latency_ms", "monthly_cost", "log_object_count"]]
    y = df["tier"]

    x_train_raw, x_test_raw, y_train, y_test = train_test_split(
        x,
        y,
        test_size=test_size,
        random_state=random_state,
        stratify=y,
    )
    scaler = StandardScaler()
    x_train = scaler.fit_transform(x_train_raw)
    x_test = scaler.transform(x_test_raw)
    x_full_scaled = scaler.transform(x)

    model = RandomForestClassifier(
        n_estimators=200,
        max_depth=10,
        random_state=random_state,
        class_weight="balanced_subsample",
    )
    model.fit(x_train, y_train)
    y_pred_test = model.predict(x_test)
    y_pred_full = model.predict(x_full_scaled)

    print("Confusion Matrix:")
    print(confusion_matrix(y_test, y_pred_test, labels=["Hot", "Cold", "Archive"]))
    print("\nClassification Report:")
    print(classification_report(y_test, y_pred_test, digits=4))

    full_counts = (
        pd.Series(y_pred_full)
        .value_counts()
        .reindex(["Hot", "Cold", "Archive"], fill_value=0)
        .astype(int)
        .to_dict()
    )
    total_predictions = int(sum(full_counts.values()))
    if total_predictions != len(df):
        raise ValueError(
            f"Full inference count mismatch: expected {len(df)}, got {total_predictions}"
        )
    print("\nPredicted Counts (Full Dataset):")
    print(full_counts)
    print(f"Total Predicted: {total_predictions}")


def main() -> None:
    args = parse_args()
    dataset_path = args.dataset.expanduser().resolve()
    if not dataset_path.exists():
        raise FileNotFoundError(f"Dataset not found: {dataset_path}")

    df = load_and_flatten(dataset_path)
    assert_feature_integrity(df)
    train_and_validate(df, test_size=args.test_size, random_state=args.random_state)


if __name__ == "__main__":
    main()
