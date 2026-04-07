# CostIntel Pipeline Engineering Backlog (Execution-Ready)

Date: 2026-02-17
Owner: Platform Architecture

## EPIC A - Core APIs

### A-1 Billing Ingestion API
- Goal: Ingest provider billing exports and storage usage in a normalized, auditable format.
- API endpoints:
  - `POST /api/v1/ingest/billing`
- Input schema:
  - `provider` (`AWS|GCP|AZURE`)
  - `resource_id` (string, required)
  - `storage_class` (string, required)
  - `region` (string, required)
  - `size_gb` (number, required, `>0`)
  - `request_count_30d` (integer, required, `>=0`)
  - `pricing_version` (string, optional)
  - `monthly_cost` (number, optional, accepted only for official billing exports)
  - `event_timestamp` (RFC3339, required)
- Output schema:
  - `ingestion_id`, `status`, `normalized_record_id`, `warnings[]`
- Validation rules:
  - Reject missing `size_gb`.
  - Reject invalid/old timestamps outside retention policy.
  - Reject unsupported provider and malformed region.
  - Require idempotency key header.
- Error handling:
  - `400` validation
  - `401/403` auth/tenant boundary
  - `409` duplicate idempotency key
  - `500` internal processing failure with trace id
- Acceptance criteria:
  - Duplicate delivery returns stable idempotent response.
  - Raw payload is immutably stored.
  - Normalized payload is queryable by tenant/resource/time.

### A-2 Classification API
- Goal: Classify storage temperature using derived features and platform-derived cost.
- API endpoints:
  - `POST /api/v1/classify/storage`
- Input schema:
  - `resource_id`, `cloud_provider`, `region`, `storage_class`
  - `size_mb`, `access_count_30d`, `creation_date`, `last_access_date`
  - optional `retrieval_gb_30d`, `historical_volatility`
- Output schema:
  - `predicted_temperature`
  - `ml_probability`
  - `confidence_score`
  - `feature_snapshot`
  - `derived_cost` (`current_monthly_cost`)
  - `decision_trace[]`
- Validation rules:
  - Datetime must be valid RFC3339.
  - `size_mb` and `access_count_30d` required.
  - Missing derived feature must be imputed by deterministic fallback.
- Error handling:
  - `400` invalid feature values
  - `422` schema errors
  - `503` classifier unavailable
- Acceptance criteria:
  - No classification failure due to missing client-supplied cost.
  - Output includes explainable feature values and cost derivation note.

### A-3 Recommendation API
- Goal: Return cost-optimized recommendation with confidence/risk/audit trace.
- API endpoints:
  - `GET /api/v1/recommendations`
- Output schema:
  - `resource_id`, `predicted_temperature`, `confidence`
  - `current_cloud`, `current_tier`
  - `recommended_cloud`, `recommended_tier`
  - `current_monthly_cost`, `optimized_monthly_cost`, `estimated_savings`
  - `pricing_version`
  - `final_action` (`CROSS_CLOUD_MOVE|SAME_CLOUD_DOWNGRADE|ADVISORY_ONLY`)
  - `risk_level`
  - `decision_trace[]`
- Validation rules:
  - Recommendation must reference immutable pricing version id.
  - `optimized_monthly_cost` must be deterministic from published formula.
- Error handling:
  - `404` no recommendation context
  - `409` pricing version missing/inactive
- Acceptance criteria:
  - Same input + same pricing version => same recommendation.
  - Explainability payload always present.

### A-4 Migration Workflow API
- Goal: Execute controlled migration lifecycle with approval gates.
- API endpoints:
  - `POST /api/v1/migrations`
  - `POST /api/v1/migrations/{id}/approve`
  - `POST /api/v1/migrations/{id}/dry-run`
  - `POST /api/v1/migrations/{id}/execute`
  - `POST /api/v1/migrations/{id}/rollback-ready`
- Input schema:
  - `resource_id`, `source_cloud`, `target_cloud`, `target_tier`, `strategy`, `approved_by`
- Output schema:
  - `migration_id`, `state`, `state_history[]`, `risk_level`, `rollback_plan[]`, `audit_ref`
- Validation rules:
  - State transitions must follow lifecycle graph.
  - Execute is blocked unless state is `DRY_RUN` and `approved` true.
- Error handling:
  - `403` missing approver role
  - `409` invalid transition
- Acceptance criteria:
  - All transitions emit immutable audit records.
  - Rollback visibility always present.

## EPIC B - Pricing Intelligence

### B-1 AWS/GCP/Azure Pricing Ingestion Jobs
- Goal: Pull pricing from official APIs on schedule.
- API/Jobs:
  - Scheduled jobs + manual triggers for each provider.
- Input/output:
  - Input: provider config, region scope, currency.
  - Output: normalized tier rows + ingestion run record.
- Validation rules:
  - Reject malformed API responses.
  - Reject non-positive pricing values.
- Error handling:
  - Retry with backoff.
  - Preserve previous pricing version on failure.
- Acceptance criteria:
  - Successful job writes versioned records and run metadata.

### B-2 Pricing Normalization
- Goal: Normalize provider-specific tiers to canonical `HOT/COLD/ARCHIVE`.
- Validation rules:
  - Mapping must come from DB lookup table.
  - Unknown tiers are dropped with warning log.
- Acceptance criteria:
  - Canonical mapping is editable without code change.

### B-3 Pricing Version Table
- Goal: Persist immutable pricing snapshots for reproducibility.
- Table:
  - `pricing_versions` with provider/region/tier/rates/effective date.
- Acceptance criteria:
  - Recommendations store referenced `pricing_version`.
  - Historical reports remain reproducible.

### B-4 Backfill and Reproducibility Logic
- Goal: Recompute historical recommendations using old pricing versions.
- Acceptance criteria:
  - Replay endpoint reproduces past outputs bit-for-bit for same inputs/version.

## EPIC C - ML and Decision Engine

### C-1 Feature Validation Layer
- Goal: Validate and impute required features safely.
- Rules:
  - No hard failure for missing derived features (`monthly_cost`, optional `latency_ms`).
  - Hard failure only for required primitives (`size`, timestamps, access count).
- Acceptance criteria:
  - Uploads with sparse but valid metadata still classify.

### C-2 Confidence Scoring Math
- Goal: Replace probability-only confidence with blended confidence.
- Formula:
  - `0.6*ml_probability + 0.25*rule_agreement + 0.15*cost_signal_strength`
- Acceptance criteria:
  - Output includes each component in explainability payload.

### C-3 Rule Override Engine
- Goal: Enforce deterministic safety rules over ML output.
- Rules:
  - HOT never to ARCHIVE.
  - Confidence bands gate allowed action type.
- Acceptance criteria:
  - Rule trace contains triggering rule ids.

### C-4 Explainability Payloads
- Goal: Produce finance-safe decision traces.
- Acceptance criteria:
  - Every recommendation has cost assumptions, pricing version, and step trace.

## EPIC D - Migration Workflow Engine

### D-1 Lifecycle State Machine
- Goal: Implement states and strict transition guards.
- States:
  - `DRAFT -> APPROVED -> DRY_RUN -> EXECUTING -> VERIFIED -> COMPLETED`
  - Failure path: `FAILED -> ROLLBACK_READY`
- Acceptance criteria:
  - Invalid transitions rejected with `409`.

### D-2 Approval and Audit Logging
- Goal: Require human approval and immutable event log.
- Acceptance criteria:
  - Approval actor, timestamp, reason are mandatory.

### D-3 Dry-Run Simulation
- Goal: Simulate migration impact before execution.
- Output:
  - object parity estimate, transfer time, risk score, rollback steps.
- Acceptance criteria:
  - Dry-run required before execution endpoint unlocks.

### D-4 Rollback Visibility
- Goal: Expose rollback plan for all migrations, including manual rollbacks.
- Acceptance criteria:
  - UI/API always returns rollback checklist.

## EPIC E - Security and IAM

### E-1 Read-Only Cloud Integrations
- Goal: Define least-privilege roles/service principals.
- Acceptance criteria:
  - No write/delete permissions in policy documents.

### E-2 Credential Rotation
- Goal: Rotate integration secrets and invalidate stale credentials.
- Acceptance criteria:
  - Rotation audit trail and last-rotated timestamp exposed.

### E-3 Least-Privilege Enforcement
- Goal: Validate integration policy does not exceed allowed permissions.
- Acceptance criteria:
  - Policy linting pipeline blocks over-privileged roles.

### E-4 Tenant Isolation
- Goal: Ensure strict per-tenant access boundaries.
- Acceptance criteria:
  - Cross-tenant resource access tests fail by default.

## EPIC F - Observability and Dashboards

### F-1 Metrics Ingestion
- Goal: Emit Prometheus-compatible metrics for pricing, classification, and migrations.
- Acceptance criteria:
  - Metrics include tenant labels and lifecycle states.

### F-2 User Dashboard (FinOps persona)
- Goal: Business-readable savings and recommendation view.
- Acceptance criteria:
  - No internal ML jargon in user panels.

### F-3 Admin Dashboard (Platform persona)
- Goal: Deep observability and decision diagnostics.
- Acceptance criteria:
  - Confidence distribution and rule override rate visible.

### F-4 Alerting
- Goal: Add alert definitions for ingestion failures, pricing drift, migration failures.
- Acceptance criteria:
  - Alert rules defined and testable in non-prod.
