# Pricing Ingestion and Versioning Architecture

Date: 2026-02-17

## 1. Objectives
- Keep pricing deterministic and auditable.
- Keep recommendations reproducible months later.
- Support AWS, GCP, Azure with canonical tier mapping.

## 2. Provider Ingestion Jobs

### AWS Job
- Source: AWS Pricing API (`GetProducts`) and S3 pricing offer feed.
- Pull cadence: daily snapshot + manual trigger.
- Extract:
  - region
  - native tier
  - storage price per GB
  - retrieval price per GB
  - minimum duration days

### Azure Job
- Source: Azure Retail Prices API.
- Pull cadence: daily snapshot + manual trigger.
- Extract:
  - arm region
  - blob tier (`Hot`, `Cool`, `Archive`)
  - storage and retrieval prices
  - minimum duration days

### GCP Job
- Source: Cloud Billing Catalog API.
- Pull cadence: daily snapshot + manual trigger.
- Extract:
  - service region
  - storage class (`Standard`, `Nearline`, `Coldline`, `Archive`)
  - storage and retrieval prices
  - minimum duration days

## 3. Normalization Rules
- Map provider tiers to canonical classes via lookup table:
  - `HOT`, `COLD`, `ARCHIVE`
- Unknown tier is rejected with warning event.
- Price rows are immutable after insert.

## 4. Pricing Version Table

```sql
CREATE TABLE pricing_versions (
  version_id UUID PRIMARY KEY,
  provider TEXT NOT NULL,
  region TEXT NOT NULL,
  storage_tier TEXT NOT NULL,
  canonical_tier TEXT NOT NULL,
  price_per_gb NUMERIC(18,8) NOT NULL,
  retrieval_cost NUMERIC(18,8) NOT NULL DEFAULT 0,
  minimum_duration_days INTEGER NOT NULL DEFAULT 0,
  currency TEXT NOT NULL DEFAULT 'USD',
  effective_date DATE NOT NULL,
  created_at TIMESTAMP NOT NULL DEFAULT NOW(),
  UNIQUE(provider, region, storage_tier, effective_date)
);
```

Indexes:
- `(provider, region, canonical_tier, effective_date DESC)`
- `(version_id)`

## 5. Reproducibility Contract
- Every recommendation stores `pricing_version` (`version_id` or date-tag).
- Recompute endpoint requires explicit pricing version.
- No in-place price updates.

## 6. Deterministic Cost Formula

```text
monthly_cost = storage_gb * storage_price_per_gb + retrieval_gb * retrieval_price_per_gb
```

Constraints:
- Same input + same pricing version => same cost output.
- Cost assumptions are returned with recommendations:
  - retrieval assumption
  - egress included/excluded
  - minimum duration penalties

## 7. Backfill Strategy
- Backfill jobs ingest historical prices to `pricing_versions`.
- Historical recommendation replay uses original `pricing_version`.
- Dashboard exposes “pricing_version used” on every recommendation.

## 8. Failure Handling
- If a provider ingestion fails:
  - mark run as `FAILED`
  - keep prior versions intact
  - no partial overwrite
- Alerts:
  - provider ingestion failure
  - stale pricing version age threshold exceeded
  - normalization reject rate spike
