# Enterprise FinOps Upgrade Design (Bucket Aggregation + Billing Export + Confidence Decay)

## 1. Updated System Architecture (Text-Based)

```text
Object Ingestion (REST/File/Webhook/API)
  -> Normalize + Validate + Idempotency
  -> Object Projection (StorageRecord)
  -> Bucket Object Ref Upsert (BucketObjectReference)
  -> Bucket Aggregate Refresh (BucketAggregate)
       - KPI metrics
       - ML classification at bucket level
       - object trace references
  -> Recommendation Upsert (Recommendation.resource_name = bucket_id)

Billing Export Ingestion (Admin read-only)
  -> AWS CUR rows / GCP BigQuery export rows
  -> Storage-scope filter (skip non-storage lines)
  -> SKU -> canonical tier mapping
  -> Normalized billing write (BillingUsageRecord)
  -> Idempotency hash guard + replay-safe run ledger (BillingIngestionRun)
  -> Bucket billing overrides (actual_monthly_cost_usd, usage_quantity, pricing_version)

Dashboard / Recommendation Runtime
  -> Primary unit: BucketAggregate
  -> Pricing comparison against latest multi-cloud pricing tables
  -> Confidence decay (volume/time/billing factors)
  -> Policy action band (HIGH/MEDIUM/LOW)
  -> Explainable recommendation payload with bucket drilldown
```

## 2. Canonical Bucket Aggregation Schema

### 2.1 Canonical Tables

- `bucket_object_references`
  - key: `(user_id, bucket_id, cloud_provider, region, storage_class, resource_name)`
  - fields: `size_gb`, `requests_30d`, `estimated_monthly_cost_usd`, `feature_snapshot`, `last_observed_at`
  - purpose: bucket -> object traceability and drilldown fidelity.

- `bucket_aggregates`
  - key: `(user_id, bucket_id, cloud_provider, region, storage_class)`
  - required metrics:
    - `total_objects`
    - `total_size_gb`
    - `avg_object_size_gb`
    - `total_requests_30d`
    - `avg_requests_per_object`
    - `estimated_monthly_cost_usd`
  - billing override fields:
    - `actual_monthly_cost_usd`
    - `usage_quantity`
    - `pricing_version`
    - `has_real_billing`
  - explainability fields:
    - `object_references` (sample list)
    - `temperature`, `classification_confidence`, `observation_days`

### 2.2 Aggregation SQL / Pseudocode

```sql
-- canonical aggregation per bucket cost unit
SELECT
  user_id,
  bucket_id,
  cloud_provider,
  region,
  storage_class,
  COUNT(*)                         AS total_objects,
  SUM(size_gb)                     AS total_size_gb,
  AVG(size_gb)                     AS avg_object_size_gb,
  SUM(requests_30d)                AS total_requests_30d,
  AVG(requests_30d)                AS avg_requests_per_object,
  SUM(estimated_monthly_cost_usd)  AS estimated_monthly_cost_usd
FROM bucket_object_references
WHERE user_id = :user_id
GROUP BY user_id, bucket_id, cloud_provider, region, storage_class;
```

```python
# ingestion-time pseudocode
upsert(bucket_object_references, object_row)
agg = aggregate_bucket(object_row.bucket_key)
agg.temperature, agg.classification_confidence = metadata_classifier.classify(agg.features)
agg.actual_monthly_cost_usd = billing_override_if_available(agg.bucket_key)
upsert(bucket_aggregates, agg)
upsert(recommendations, key=bucket_id)
```

### 2.3 Backward Compatibility Strategy

- Object-level ingestion remains unchanged (`StorageRecord` still written).
- Existing recommendation APIs are unchanged (same endpoints and core fields).
- New recommendation fields are additive (`bucket_id`, `optimization_unit`, `bucket_metrics`, `object_references`, confidence trace fields).
- If no bucket aggregates exist, runtime automatically falls back to object-level behavior.

## 3. Billing Ingestion Schemas (AWS + GCP)

## 3.1 Flow Diagrams

### AWS CUR (hourly)

```text
CUR export row
  -> storage-scope filter (S3-only line items)
  -> parse usage/cost/region/storage_class/bucket
  -> map SKU text -> canonical tier (HOT/COLD/ARCHIVE)
  -> normalized BillingUsageRecord insert (idempotent hash)
  -> BillingIngestionRun counters + status
  -> BucketAggregate actual cost override refresh
```

### GCP BigQuery Billing Export (daily/hourly)

```text
BQ export row
  -> storage-scope filter (Cloud Storage SKUs)
  -> parse usage/cost/region/storage_class/bucket
  -> map SKU description -> canonical tier
  -> normalized BillingUsageRecord insert (idempotent hash)
  -> BillingIngestionRun counters + status
  -> BucketAggregate actual cost override refresh
```

## 3.2 Canonical Normalized Billing Schema

- `billing_ingestion_runs`
  - idempotency and replay ledger
  - key: `(user_id, provider, source_type, idempotency_key)`
  - counters: `records_seen`, `records_inserted`, `skipped_non_storage`
  - time window: `window_start`, `window_end`

- `billing_usage_records`
  - key: `(user_id, provider, source_record_hash)`
  - fields:
    - source identity: `provider`, `source_type`, `billing_account_id`, `project_id`
    - resource identity: `bucket_id`, `region`, `storage_class`, `canonical_tier`
    - SKU identity: `sku_id`, `sku_description`
    - usage: `usage_start`, `usage_end`, `usage_quantity`, `usage_unit`
    - cost: `cost_usd`, `currency`
    - reference: `pricing_version`, `source_payload`

## 3.3 SKU -> Canonical Tier Mapping Logic

- Archive tier tokens: `archive`, `glacier`, `deep archive`
- Cold tier tokens: `standard-ia`, `one zone-ia`, `nearline`, `coldline`, `cool`, `infrequent`
- Else default to hot tier.

## 3.4 Synthetic vs Real Validation

```sql
SELECT
  b.bucket_id,
  b.cloud_provider,
  b.estimated_monthly_cost_usd,
  b.actual_monthly_cost_usd,
  CASE
    WHEN b.actual_monthly_cost_usd IS NULL OR b.actual_monthly_cost_usd = 0 THEN NULL
    ELSE (b.estimated_monthly_cost_usd - b.actual_monthly_cost_usd) / b.actual_monthly_cost_usd
  END AS variance_ratio
FROM bucket_aggregates b
WHERE b.user_id = :user_id;
```

## 3.5 Safety Controls

- Read-only ingestion API accepts export rows only; no mutating cloud APIs are called.
- Non-storage billing lines are rejected before persistence.
- Currency guard enforces USD-only normalization for `actual_monthly_cost_usd` safety.
- Idempotency hash prevents duplicate billing writes.
- Replay support via `idempotency_key` and run window metadata.
- Source payload retained for audit traceability.

## 4. Confidence Decay Math + Code

## 4.1 Math

```text
confidence_final = confidence_ml * volume_factor * time_factor * billing_factor
```

- `volume_factor`
  - `> 1 TB` => `1.00`
  - `100–1000 GB` => `0.85`
  - `< 100 GB` => `0.60`

- `time_factor`
  - `> 90 days` => `1.00`
  - `30–90 days` => `0.80`
  - `< 30 days` => `0.60`

- `billing_factor`
  - real billing present => `1.00`
  - estimated only => `0.75`

## 4.2 Policy Effects

- `confidence_final > 0.80` => `MOVE_TO_PREDICTED_TIER`
- `0.50 <= confidence_final <= 0.80` => `MOVE_TO_STANDARD_IA`
- `< 0.50` => `RETAIN`

## 4.3 Implementation Notes

Implemented in `backend/app/services/confidence_scoring_service.py`:

- `ConfidenceDecayInputs`
- `ConfidenceDecayResult`
- `apply_confidence_decay(...)`

Integrated in `DashboardService.get_recommendations(...)` with additive fields:

- `confidence_base_score`
- `confidence_decay`
- `confidence_message`
- `decision_trace`

## 5. Example Recommendation Payloads (Before / After)

## 5.1 Before (Object Unit)

```json
{
  "id": 101,
  "resource_name": "object-0001.parquet",
  "current_tier": "STANDARD",
  "recommended_tier": "ARCHIVE",
  "recommended_provider": "AWS",
  "confidence_score": 0.91
}
```

## 5.2 After (Bucket Unit, Backward Compatible)

```json
{
  "id": 501,
  "resource_name": "finance-prod-archive-bucket",
  "bucket_id": "finance-prod-archive-bucket",
  "optimization_unit": "BUCKET",
  "current_tier": "STANDARD",
  "recommended_tier": "Standard-IA",
  "recommended_provider": "AWS",
  "confidence_base_score": 0.88,
  "confidence_score": 0.56,
  "confidence_decay": {
    "volume_factor": 0.85,
    "time_factor": 0.8,
    "billing_factor": 0.75
  },
  "confidence_message": "Confidence downgraded due to dataset coverage constraints.",
  "bucket_metrics": {
    "total_objects": 19024,
    "total_size_gb": 620.3,
    "actual_monthly_cost_usd": 1824.22,
    "has_real_billing": true
  },
  "object_references": [
    "ledger/2025/10/part-001.parquet",
    "ledger/2025/10/part-002.parquet"
  ]
}
```

## 6. Production Rollout Validation Checklist

- Schema
  - `bucket_object_references`, `bucket_aggregates`, `billing_ingestion_runs`, `billing_usage_records` created.
  - unique/index constraints validated.

- Ingestion
  - object ingest still writes `StorageRecord` and `IngestedRecord`.
  - bucket aggregate populated per object ingest.
  - recommendation key is `bucket_id` for primary optimization.

- Billing
  - AWS CUR import with storage-only rows completes idempotently.
  - GCP export import with storage SKUs completes idempotently.
  - replay with same `idempotency_key` does not duplicate rows.
  - non-storage lines are counted as `skipped_non_storage`.

- Accuracy
  - bucket `actual_monthly_cost_usd` overrides synthetic estimate when present.
  - synthetic-vs-real variance report generated and reviewed.

- Explainability / Audit
  - recommendation includes decision trace and confidence decay factors.
  - bucket-level payload includes drilldown object references.
  - billing run metadata and source payload retained.

- Backward Compatibility
  - existing endpoints unchanged.
  - existing required response fields preserved.
  - object-level fallback works when bucket aggregates are unavailable.
