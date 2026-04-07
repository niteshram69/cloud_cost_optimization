"""Example ML training pipeline for enterprise adoption.

Input CSV columns:
- object_id
- tenant_id
- provider
- region
- current_tier
- object_size_gb
- days_since_last_access
- access_frequency_30d
- access_frequency_90d
- read_write_ratio
- storage_growth_trend_gb_30d
- access_pattern_entropy
- read_count_30d
- write_count_30d
- read_count_90d
- write_count_90d
- label (HOT|COLD|ARCHIVE)
"""

from __future__ import annotations

import argparse
import csv

from app.decision_engine.types import DataTemperature
from app.feature_engineering.models import FeatureVector
from app.ml_engine.model import MLTrainingSummary, StorageMLClassifier


REQUIRED_COLUMNS = {
    "object_id",
    "tenant_id",
    "provider",
    "region",
    "current_tier",
    "object_size_gb",
    "days_since_last_access",
    "access_frequency_30d",
    "access_frequency_90d",
    "read_write_ratio",
    "storage_growth_trend_gb_30d",
    "access_pattern_entropy",
    "read_count_30d",
    "write_count_30d",
    "read_count_90d",
    "write_count_90d",
    "label",
}


def _load_labeled_dataset(dataset_path: str) -> tuple[list[FeatureVector], list[DataTemperature]]:
    with open(dataset_path, "r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        missing = REQUIRED_COLUMNS.difference(set(reader.fieldnames or []))
        if missing:
            raise ValueError(f"dataset missing columns: {sorted(missing)}")

        features: list[FeatureVector] = []
        labels: list[DataTemperature] = []

        for row in reader:
            feature = FeatureVector(
                tenant_id=row["tenant_id"],
                object_id=row["object_id"],
                provider=row["provider"],
                region=row["region"],
                bucket=row.get("bucket", "unknown"),
                current_tier=row["current_tier"],
                object_size_gb=float(row["object_size_gb"]),
                days_since_last_access=float(row["days_since_last_access"]),
                access_frequency_30d=float(row["access_frequency_30d"]),
                access_frequency_90d=float(row["access_frequency_90d"]),
                read_write_ratio=float(row["read_write_ratio"]),
                storage_growth_trend_gb_30d=float(row["storage_growth_trend_gb_30d"]),
                access_pattern_entropy=float(row["access_pattern_entropy"]),
                read_count_30d=int(float(row["read_count_30d"])),
                write_count_30d=int(float(row["write_count_30d"])),
                read_count_90d=int(float(row["read_count_90d"])),
                write_count_90d=int(float(row["write_count_90d"])),
            )
            label = DataTemperature(str(row["label"]).upper())
            features.append(feature)
            labels.append(label)

    return features, labels


def train_model_from_csv(dataset_path: str, output_model_path: str) -> MLTrainingSummary:
    """Train a RandomForest model from a labeled CSV and persist artifact."""
    features, labels = _load_labeled_dataset(dataset_path)
    classifier = StorageMLClassifier()
    summary = classifier.train(features=features, labels=labels)
    classifier.save(output_model_path)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Train storage lifecycle ML model")
    parser.add_argument("--dataset", required=True, help="Path to labeled CSV dataset")
    parser.add_argument("--output", required=True, help="Path to output model artifact")
    args = parser.parse_args()

    summary = train_model_from_csv(args.dataset, args.output)
    print(
        {
            "model_version": summary.model_version,
            "samples": summary.n_samples,
            "accuracy": summary.accuracy,
        }
    )


if __name__ == "__main__":
    main()
