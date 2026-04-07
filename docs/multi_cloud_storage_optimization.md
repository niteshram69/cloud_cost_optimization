# Multi-Cloud Storage Optimization Platform (Rule + ML)

## What Changed
The platform now includes a production-oriented v2 architecture focused on metadata-driven optimization and explainable decisions for AWS, GCP, and Azure object storage.

### New Module Layout
- `app/collectors/`: Event-driven and batch metadata ingestion, access-log normalization.
- `app/feature_engineering/`: Deterministic feature extraction from object metadata/access behavior.
- `app/rules_engine/`: Explicit threshold-based HOT/COLD/ARCHIVE policy classifier.
- `app/ml_engine/`: RandomForest-based adaptive classifier with confidence scoring.
- `app/pricing_engine/`: Region-aware pricing normalization and FX conversion.
- `app/decision_engine/`: Hybrid fallback logic, cross-cloud option ranking, explainable outputs.
- `app/migration_engine/`: Dry-run/enforced migration with checksums, rollback, audit logs, throttling.
- `app/api/`: `/api/v2` endpoints for optimize/train/dashboards.
- `app/dashboards/`: Admin and client analytics aggregation.

## Design Decisions

### 1. Metadata Collection (No Content Reads)
- Uses event-driven processing (`EventDrivenCollector`) to reduce polling/API overhead.
- Uses batch inventory ingestion (`InventoryBatchCollector`) for legacy backfills.
- Uses access logs (`AccessLogCollector`) to derive 30/90-day frequency and read/write behavior.
- No file-body parsing is performed at any stage.

### 2. Hybrid Classification
- Rule baseline (`RuleBasedStorageClassifier`) applies explicit thresholds:
  - days since last access
  - access frequency (30d/90d)
  - object size
  - read/write ratio
- ML layer (`StorageMLClassifier`) predicts HOT/COLD/ARCHIVE with confidence.
- Fallback strategy:
  - if `ml_confidence >= threshold`, ML result is used.
  - otherwise, rule-based result is used with fallback explanation.

### 3. Multi-Cloud Cost Engine
- Pricing catalog (`pricing_catalog.json`) supports:
  - AWS: `S3_STANDARD`, `S3_IA`, `S3_GLACIER`, `S3_DEEP_ARCHIVE`
  - GCP: `STANDARD`, `NEARLINE`, `COLDLINE`, `ARCHIVE`
  - Azure: `HOT`, `COOL`, `ARCHIVE`
- Cost model normalizes:
  - storage cost per GB-month
  - retrieval cost
  - minimum retention
  - early deletion penalty
  - data egress
- Region-aware pricing with default fallback by provider.

### 4. Region + Currency Awareness
- Regions are selectable per provider via `allowed_regions` request field.
- FX conversion is centralized in `CurrencyConverter` with daily snapshot semantics.
- Static provider is default; contract is pluggable for external FX sources.

### 5. Decision Engine
- Produces per-object recommendation with:
  - selected class and source (`rule_based`/`ml`)
  - confidence and fallback details
  - current option cost vs recommended option cost
  - ranked alternatives for transparency
- Supports modes:
  - `dry_run`
  - `enforced` (triggers migration when beneficial)

### 6. Migration Engine
- Supports dry-run and enforced migration paths.
- Safety controls:
  - checksum validation
  - rollback on checksum failure/exception
  - JSON-line audit trail
  - semaphore-based parallelism + operation rate throttling
- Uses official SDK patterns with lazy imports:
  - `boto3` (AWS)
  - `google-cloud-storage` (GCP)
  - `azure-storage-blob` (Azure)
- Install SDK extra when enforced migrations are required:
  - `poetry install -E migration-sdks`

## API Endpoints

### Optimize Objects
`POST /api/v2/optimize`

- Input includes `inventory`, optional `access_events`, `mode`, `currency`, `allowed_regions`.
- Output includes summary and per-object decisions with full cost breakdown.

### Train ML Classifier
`POST /api/v2/ml/train`

- Trains RandomForest model from labeled feature rows.
- Persists model to `ML_MODEL_PATH` when enabled.

### Dashboards
- `GET /api/v2/dashboards/admin`
- `GET /api/v2/dashboards/client/{tenant_id}`

## Sample Decision Output (JSON)

```json
{
  "object_id": "aws://finops-bucket/logs/2025-archive-01.gz",
  "classification": {
    "selected_class": "ARCHIVE",
    "source": "ml",
    "confidence": 0.91,
    "rule_confidence": 0.78,
    "ml_confidence": 0.91,
    "fallback_used": false,
    "reasoning": [
      "ML confidence 0.910 >= threshold 0.750; using ML class ARCHIVE"
    ]
  },
  "current": {
    "provider": "aws",
    "region": "us-east-1",
    "tier": "S3_STANDARD",
    "monthly_cost": 126.82
  },
  "recommended": {
    "provider": "azure",
    "region": "eastus",
    "tier": "ARCHIVE",
    "monthly_cost": 18.77
  },
  "estimated_monthly_savings": 108.05,
  "estimated_yearly_savings": 1296.60,
  "action": "migrate",
  "mode": "dry_run"
}
```

## ML Training Pipeline Example

CLI example:

```bash
python -m app.ml_engine.training_pipeline \
  --dataset ./data/labeled_storage_features.csv \
  --output ./artifacts/storage_temperature_model.joblib
```

## Metrics and Grafana

Prometheus metrics exposed at `/metrics` include:
- `costintel_storage_cost_usd{provider,region}`
- `costintel_savings_usd_total{tenant_id}`
- `costintel_objects_per_data_class{data_class}`
- `costintel_migration_operations_total{status}`
- `costintel_ml_confidence_score`
- `costintel_classification_drift_score`

Sample dashboard JSON:
- `dashboards/grafana/storage_optimization_dashboard.json`

## Security, Scale, and Audit Notes
- Tenant IDs are carried across ingestion, decisioning, and dashboard aggregation.
- Migration audit logs are append-only JSONL (`MIGRATION_AUDIT_LOG_PATH`).
- Migration throughput controls prevent aggressive cross-cloud transfer spikes.
- For production hardening, wire report storage and migrations to persistent infra with tenant RBAC and KMS-backed secret management.
