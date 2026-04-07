# CostIntel Pipeline: Enterprise Implementation Report

Last updated: 2026-02-17

## 1. Executive Summary

This report documents what is already implemented in the platform, where the implementation encountered delivery blockers, and how each blocker was resolved without breaking existing APIs.

Current status:
- Platform is running end-to-end (backend + frontend).
- Ingestion, classification, pricing comparison, and recommendation flows are active.
- Enterprise trust features were added: explainable traces, pricing versioning, grouped recommendations, migration advisory metadata, and admin drill-down.
- Confidence policy was corrected to avoid medium-confidence savings loss.
- Execution artifacts for implementation planning are now available:
  - `docs/enterprise_execution_backlog.md`
  - `docs/openapi/costintel_platform_v1.yaml`
  - `docs/pricing_ingestion_versioning.md`
  - `docs/iam_readonly_mapping.md`
  - `infra/terraform/readonly/`
  - `dashboards/grafana/user_finops_dashboard.json`
  - `dashboards/grafana/admin_platform_dashboard.json`

## 2. Current Architecture (Implemented)

Flow in production:

1. Data ingestion (manual upload/API/integration)
2. Feature extraction + metadata classification (Hot/Cold/Archive with confidence)
3. Live pricing ingestion (Azure/AWS/GCP) with versioned storage
4. Pricing normalization into canonical tiers
5. Deterministic price comparison
6. Safety override logic
7. Recommendation + migration advisory
8. User/Admin dashboards + Prometheus metrics

Key backend modules:
- `backend/app/services/ingestion_service.py`
- `backend/app/services/metadata_classifier_service.py`
- `backend/app/services/pricing_intelligence_service.py`
- `backend/app/services/dashboard_service.py`
- `backend/app/services/admin_service.py`
- `backend/app/services/canonical_tier_mapping_service.py`

Key frontend modules:
- `frontend/app/dashboard/page.tsx`
- `frontend/app/admin/page.tsx`
- `frontend/lib/api.ts`
- `frontend/lib/types.ts`

## 3. Phase 1: UX Separation (Implemented)

### 3.1 User Dashboard (Executive view)

Implemented components:
- KPI cards: total storage cost, estimated monthly savings, temperature split, pricing version
- Grouped recommendations (collapsible)
- Before/after cost visibility
- Top savings opportunities table
- Migration risk summary
- Billing preview card (non-blocking)

Shared data shown:
- Cost totals, savings, recommended provider/tier, confidence %, pricing version

Hidden from user view:
- Raw feature vectors
- Full rule engine internals
- API-level trace payloads and debug internals

User-facing explanation example (implemented style):
- "Move `bucket-001` to `Cool Blob` to reduce monthly cost from `$142.35` to `$21.07` using pricing version `2026-02-17`."

### 3.2 Admin/Advanced View

Implemented components:
- User management + user detail drill-down
- API keys, auth activity, usage stats, data ingested
- Recommendations/migrations/webhooks/billing status
- System health + classification confidence metrics
- Pricing version health

Admin trace example (implemented style):
- `ML Prediction: AZURE Cool Blob`
- `Logic Check: Confidence is Medium`
- `Final Decision: Confidence is moderate... Downgrading to Standard-IA...`

## 4. Phase 2: Pricing Intelligence Hardening (Partially Implemented)

### 4.1 Implemented

- Region-aware live ingestion:
  - Azure retail prices
  - AWS S3 offer file
  - GCP billing catalog
- Pricing versioning and immutable history:
  - no overwrite behavior
  - recommendation references `pricing_version`
- Canonical mapping moved to DB lookup:
  - `canonical_tier_mappings` table + bootstrap defaults
- Explicit assumptions attached to decisions/recommendations:
  - monthly access rate
  - egress costs excluded
  - minimum storage duration honored

Pricing decision schema (implemented payload fields):
- `resource_id`
- `data_temperature`
- `current_cloud`, `current_tier`
- `recommended_cloud`, `recommended_tier`
- `current_monthly_cost`, `optimized_monthly_cost`, `estimated_savings_percent`
- `pricing_version`
- `candidates[]`
- `cost_assumptions{}`
- `explanation`

### 4.2 Not Fully Implemented Yet

- Explicit numeric early-deletion penalty calculation in decision engine
- Retrieval sensitivity band outputs as first-class API fields (low/medium/high band)
- Confidence adjustment based on pricing-volatility/risk scoring

These are tracked as next hardening increments.

## 5. Phase 3: Scenario Simulation (Design Ready, Not Yet Implemented)

Proposed model (next increment):
- Scenario types:
  - do-nothing baseline
  - access frequency x2
  - provider price +/- X%
- Inputs:
  - resource, temperature, size, retrieval pattern, region preference, price-change factor
- Outputs:
  - per-scenario monthly/yearly cost
  - delta vs baseline
  - confidence impact
  - recommendation priority delta
- UX:
  - side-by-side comparison cards
  - non-destructive "simulation only" status

## 6. Phase 4: Migration as Workflow (Partially Implemented)

### 6.1 Implemented

- Recommendation payload includes migration advisory:
  - strategy
  - suggested tool
  - risk level
  - estimated time
  - execution steps
  - lifecycle path
- Lifecycle path exposed in payload:
  - `PLANNED -> APPROVED -> DRY_RUN -> EXECUTING -> COMPLETED -> ROLLED_BACK`

### 6.2 Pending for Full Workflow Enforcement

- Persisted migration state machine transitions with strict transition guards
- Explicit approval entities with RBAC policy per transition
- Immutable per-step audit event logs

## 7. Confidence Policy Update (Implemented)

New matrix implemented in recommendation flow:

1. High confidence (`> 80%`)
   - Action: `MOVE_TO_PREDICTED_TIER`
2. Medium confidence (`50% - 80%`)
   - Action: `MOVE_TO_STANDARD_IA`
3. Low confidence (`< 50%`)
   - Action: `RETAIN`

Decision trace block now follows this exact structure:
- `[Resource ID]`
- `ACTION: ...`
- `Confidence: ...%`
- `Savings Potential: $.../mo`
- `Rule Trace:`
  - ML Prediction
  - Logic Check
  - Final Decision

Implementation location:
- `backend/app/services/dashboard_service.py`

## 8. Walls Encountered and Fixes

### Wall 1: Dashboard timeout / network errors

Symptom:
- Dashboard failed with timeout errors under partial backend slowness.

Root cause:
- Frontend request timeout too tight and all-or-nothing loading behavior.

Fix:
- Increased API timeout in frontend client.
- Switched dashboard loading to partial-resilient behavior (`Promise.allSettled`) with warning banners.

Where fixed:
- `frontend/lib/api.ts`
- `frontend/app/dashboard/page.tsx`

---

### Wall 2: JSON upload completed but dashboard stayed empty

Symptom:
- Uploaded JSON appeared processed, but cost/recommendation metrics remained empty.

Root cause:
- Nested `cost_metrics`/payload extraction was inconsistent for certain upload shapes.

Fix:
- Normalized nested field extraction and fallback mapping in ingestion pipeline.

Where fixed:
- `backend/app/services/ingestion_service.py`

---

### Wall 3: Canonical tier mapping hardcoded

Symptom:
- Mapping logic existed in code branches, reducing auditability and configurability.

Root cause:
- No authoritative DB mapping table.

Fix:
- Added `canonical_tier_mappings` table and mapping service.
- Added bootstrap default seeding.
- Updated AWS/Azure/GCP normalization logic to resolve canonical tier via DB lookup.

Where fixed:
- `backend/app/models/canonical_tier_mapping.py`
- `backend/app/services/canonical_tier_mapping_service.py`
- `backend/app/services/platform_bootstrap_service.py`
- `backend/app/services/pricing_intelligence_service.py`

---

### Wall 4: Recommendation noise (too many near-duplicate rows)

Symptom:
- Dashboard overwhelmed users with resource-level recommendations.

Root cause:
- No grouped recommendation layer in user flow.

Fix:
- Added grouped recommendation API and collapsible grouped UI section.

Where fixed:
- `backend/app/services/dashboard_service.py`
- `backend/app/api/dashboard.py`
- `frontend/app/dashboard/page.tsx`
- `frontend/lib/api.ts`
- `frontend/lib/types.ts`

---

### Wall 5: Medium-confidence opportunities were blocked

Symptom:
- Savings opportunities in medium confidence band were often retained.

Root cause:
- Threshold/rule drift from intended policy.

Fix:
- Enforced matrix:
  - `>80`: predicted tier
  - `50-80`: Standard-IA safe fallback
  - `<50`: retain
- Updated trace messaging to make decisions explicit.

Where fixed:
- `backend/app/services/dashboard_service.py`

---

### Wall 6: Ingestion failures for sparse metadata (`latency_ms` / `monthly_cost` / `object_count`)

Symptom:
- Uploads failed with errors like:
  - `Missing required feature 'latency_ms'`
  - missing monthly cost for classification
  - missing object count in file-level metadata

Root cause:
- Feature extraction treated several derived fields as hard-required even when they can be computed safely.

Fix:
- Added optional feature extraction + deterministic fallbacks:
  - `latency_ms`: alias extraction + imputed fallback
  - `monthly_cost`: derived from `size_mb` + `storage_class` rate registry
  - `object_count`: fallback to `1` when not provided in file-level records
- Preserved strict validation for truly required primitives (size/access/timestamps).

Where fixed:
- `backend/app/services/ingestion_service.py`

---

### Wall 7: GCP pricing sync intermittently failing in non-configured environments

Symptom:
- GCP ingestion returned upstream authorization errors.

Root cause:
- Missing/invalid GCP billing API key in runtime configuration.

Fix:
- API surfaces controlled failure response (`502` with explicit sync error) and does not corrupt existing pricing state.
- Documented requirement for `GCP_BILLING_API_KEY`.

Where fixed/handled:
- `backend/app/services/pricing_intelligence_service.py`
- `backend/app/api/pricing.py`

## 9. API Additions and Contracts (Implemented)

New/updated endpoints:
- `GET /api/recommendations`
  - now includes feature snapshot, trace block, pricing assumptions, migration advisory
- `GET /api/recommendations/grouped`
  - grouped impact/risk view for executive UX
- `GET /api/pricing/version/latest`
- `POST /api/pricing/decision`
  - includes `cost_assumptions`
- `GET /api/pricing/opportunities/top`

## 10. Runbook Validation Performed

Validation done:
- backend compile check passed
- frontend lint and build passed
- live endpoint smoke tests passed for:
  - auth login
  - dashboard summary
  - recommendations (detailed + grouped)
  - pricing decision endpoint
  - pricing opportunities

Runtime services:
- Backend: `http://127.0.0.1:8001`
- Frontend: `http://127.0.0.1:3000`

## 11. Recommended Next Enterprise Increments

1. Add formal pricing penalty engine (early-deletion + min-duration) with explicit line-item output.
2. Add scenario simulation endpoints/UI for side-by-side planning.
3. Persist migration lifecycle transitions and approval logs as immutable audit events.
4. Add tenant-level policy controls for confidence thresholds and allowed target tiers.
