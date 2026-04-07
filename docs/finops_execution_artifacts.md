# 1. Engineering Tickets (JIRA-Ready)

## A. ML & Decision Engine

### MLD-001 — Enforce Decision-State Machine in Optimizer
- Description: Implement authoritative decision-state transitions (`EXPLORATORY`, `PREDICTED`, `FALLBACK`, `NO_OP`, `BLOCKED`) and prohibit side-channel state mutation.
- Acceptance Criteria:
  - Optimizer emits one terminal state per decision.
  - Illegal transitions are rejected with deterministic error codes.
  - Unit tests cover all valid and invalid transitions.
  - Decision state is persisted and returned in all optimization APIs.
- Dependencies: None.
- Risk: HIGH.

### MLD-002 — Decision-Aware Pricing Clamp Enforcement
- Description: Clamp pricing outputs after decision resolution; prevent exploratory math from leaking to final payload for non-predicted states.
- Acceptance Criteria:
  - For `FALLBACK`, `NO_OP`, `BLOCKED`, `after_cost_usd == before_cost_usd`.
  - `savings_usd == 0` for non-predicted states.
  - `percent_change == null` for non-predicted states.
  - Regression tests verify no negative savings/percentages.
- Dependencies: MLD-001.
- Risk: HIGH.

### MLD-003 — Multiplicative Confidence Decay Derivation + Persistence
- Description: Replace ad-hoc confidence with formal multiplicative model and persist full factor trace.
- Acceptance Criteria:
  - Formula implemented exactly:
    `confidence_final = base * data_window * billing_realism * aggregation * migration_risk`.
  - Worked example (`0.99 -> ~0.59`) documented and test-asserted.
  - `confidence_trace` persisted and returned in API payload.
- Dependencies: MLD-001.
- Risk: HIGH.

### MLD-004 — Migration Risk Factor Integration
- Description: Inject cross-cloud and access-pattern penalties into confidence model.
- Acceptance Criteria:
  - Cross-cloud + high-access receives stronger penalty than same-cloud.
  - Factor values and thresholds are configurable.
  - Factor appears in `confidence_trace` and audit logs.
- Dependencies: MLD-003.
- Risk: MEDIUM.

### MLD-005 — Fallback Semantics as Safety, Not Optimization
- Description: Encode fallback outcomes as cost-neutral safety actions.
- Acceptance Criteria:
  - Fallback decisions always emit `savings_usd=0`.
  - Fallback reasons include `Safety fallback due to confidence decay`.
  - Priority for fallback derived from risk level, not savings.
- Dependencies: MLD-001, MLD-002.
- Risk: HIGH.

### MLD-006 — Drift-Aware Decision Blocking
- Description: Compare used vs latest pricing version and block execution when drift detected.
- Acceptance Criteria:
  - Drift check performed for every optimization decision.
  - Drift sets `decision_state=BLOCKED` and suppresses savings.
  - Drift reason included in `pricing_trace` and `guardrail_trace`.
- Dependencies: PRC-002.
- Risk: HIGH.

## B. Pricing & Billing

### PRC-001 — Pricing Version Metadata Contract
- Description: Every pricing result must include `pricing_version`, `pricing_source`, and `pricing_confidence`.
- Acceptance Criteria:
  - Fields are non-null in optimization responses.
  - Confidence enum constrained to `REAL|EXPORT|ESTIMATE`.
  - Contract tests validate schema.
- Dependencies: API-001.
- Risk: MEDIUM.

### PRC-002 — Latest Pricing Registry Service
- Description: Build read model for latest provider pricing versions with staleness metadata.
- Acceptance Criteria:
  - `GET /pricing/versions` returns latest + historical versions.
  - Versions keyed by provider and date.
  - Staleness classification (`IN_SYNC|DRIFTED`) exposed.
- Dependencies: None.
- Risk: MEDIUM.

### PRC-003 — Billing Realism Classifier
- Description: Determine billing realism (`REAL|EXPORT|ESTIMATE`) from billing pipeline provenance.
- Acceptance Criteria:
  - REAL only when reconciled billing data is present.
  - EXPORT when provider catalog exists without realized billing.
  - ESTIMATE default for synthetic/proxy assumptions.
- Dependencies: PRC-001.
- Risk: MEDIUM.

### PRC-004 — Pricing Clamp Integration Tests
- Description: Add explicit tests for non-negative savings and percent suppression rules.
- Acceptance Criteria:
  - Test matrix covers every `decision_state`.
  - Negative savings and negative percentages are impossible in payload output.
- Dependencies: MLD-002.
- Risk: LOW.

## C. Optimization Orchestration

### ORC-001 — Migration Lifecycle State Machine Engine
- Description: Implement migration lifecycle states (`PLANNED`, `APPROVED`, `DRY_RUN`, `EXECUTING`, `COMPLETED`, `ROLLED_BACK`, `BLOCKED`) with strict transition rules.
- Acceptance Criteria:
  - Transition table enforced server-side.
  - Execution allowed only from `APPROVED`.
  - Rollback supported from `EXECUTING` and `COMPLETED`.
- Dependencies: MLD-001.
- Risk: HIGH.

### ORC-002 — Mid-Flight Confidence Recheck
- Description: Recompute confidence before and during execution; block when confidence floor drops.
- Acceptance Criteria:
  - Execution transitions to `BLOCKED` when confidence falls below policy floor.
  - Guardrail and confidence traces recorded for block event.
- Dependencies: MLD-003, ORC-001.
- Risk: HIGH.

### ORC-003 — First-Class Rollback Workflow
- Description: Add explicit rollback planning and operation APIs with verifiable state transitions.
- Acceptance Criteria:
  - `POST /migrations/{id}/rollback` supported.
  - Rollback emits immutable event with operator identity and reason.
- Dependencies: ORC-001.
- Risk: HIGH.

### ORC-004 — Cross-Cloud Guardrail Policy Pack
- Description: Parameterize egress, latency, and hot-data archival guardrails.
- Acceptance Criteria:
  - Guardrails configurable per tenant/environment.
  - Violations force `BLOCKED` or conservative fallback.
  - `guardrail_trace` includes triggered rule IDs.
- Dependencies: MLD-001.
- Risk: HIGH.

## D. API Platform

### API-001 — OpenAPI 3.1 Decision Contract
- Description: Publish OpenAPI spec including mandatory safety/trace fields.
- Acceptance Criteria:
  - Endpoints documented: optimize, optimization fetch, migration approve/execute/rollback, pricing versions, confidence explain.
  - `decision_state`, `confidence_trace`, `pricing_trace`, `migration_state` required in response schemas.
  - Swagger renders with examples and OAuth scopes.
- Dependencies: None.
- Risk: MEDIUM.

### API-002 — RBAC Scope Enforcement
- Description: Enforce endpoint-level scopes aligned to execution sensitivity.
- Acceptance Criteria:
  - Approve/execute/rollback endpoints reject tokens without matching scope.
  - Scope failures produce deterministic `403` error contract.
- Dependencies: API-001.
- Risk: HIGH.

### API-003 — Idempotent Optimization Request Handling
- Description: Add idempotency keys for optimization requests to prevent duplicate execution intents.
- Acceptance Criteria:
  - Repeat key returns same optimization ID.
  - Race conditions do not create duplicate migration plans.
- Dependencies: API-001.
- Risk: MEDIUM.

## E. UI / Payload Integrity

### UIP-001 — Prediction vs Exploration vs Final Separation
- Description: Render distinct sections in UI payload for ML prediction, pricing exploration, and final decision.
- Acceptance Criteria:
  - UI model carries separate blocks.
  - Non-predicted decisions suppress exploration cost details.
- Dependencies: API-001.
- Risk: MEDIUM.

### UIP-002 — Safety-Fallback Messaging Standardization
- Description: Standardize user-facing fallback/block/no-op messages.
- Acceptance Criteria:
  - Fallback string exactly: `Safety fallback due to confidence decay`.
  - Blocked decisions display explicit blocking rationale.
  - No-op decisions explain insufficient evidence.
- Dependencies: MLD-005.
- Risk: LOW.

### UIP-003 — Negative-Savings Display Guard
- Description: UI-level guard to reject rendering of negative savings or percentages.
- Acceptance Criteria:
  - Frontend validation drops/flags invalid payloads.
  - Telemetry captures payload-contract violations.
- Dependencies: API-001.
- Risk: LOW.

## F. Observability

### OBS-001 — Decision and Safety Metrics Instrumentation
- Description: Emit Prometheus metrics for decisions, blocks, fallbacks, drift, and realized/estimated savings.
- Acceptance Criteria:
  - Required metrics published: `optimization_decisions_total`, `optimization_blocked_total`, `confidence_decay_factor`, `pricing_version_drift_detected`, `migration_state_transitions_total`, `savings_realized_usd`, `savings_estimated_usd`, `fallback_actions_total`.
  - Metrics include tenant/provider/decision labels where safe.
- Dependencies: MLD-001, ORC-001.
- Risk: MEDIUM.

### OBS-002 — Alerting for Unsafe Conditions
- Description: Create alert rules for drift, fallback spikes, blocked execution spikes, and confidence degradation.
- Acceptance Criteria:
  - Alerts defined in Terraform and deployable.
  - Runbook links attached to alert annotations.
- Dependencies: OBS-001.
- Risk: MEDIUM.

### OBS-003 — Confidence Decay Trend Dashboard
- Description: Dashboard panels for confidence factors and decay trends.
- Acceptance Criteria:
  - End-user and admin dashboards include decay trend panels.
  - Filters support tenant/provider/decision-state dimensions.
- Dependencies: OBS-001.
- Risk: LOW.

## G. Compliance & Governance

### GOV-001 — Immutable Decision Audit Ledger
- Description: Persist immutable audit records for prediction, guardrails, pricing, state transitions, and operator actions.
- Acceptance Criteria:
  - Append-only storage with tamper-evidence hash chain.
  - Every execution and rollback event has actor, timestamp, reason.
- Dependencies: ORC-001, API-002.
- Risk: HIGH.

### GOV-002 — Change Management Controls for Models and Pricing Policies
- Description: Require approvals and evidence for model/policy/version changes.
- Acceptance Criteria:
  - Change records include approver, test evidence, rollout timestamp.
  - Canary and rollback hooks documented and verified.
- Dependencies: GOV-001.
- Risk: MEDIUM.

### GOV-003 — Data Accuracy and Non-Execution Disclosures
- Description: Enforce customer-visible disclosure when decisions are blocked/no-op/fallback.
- Acceptance Criteria:
  - API + UI include standardized reasons.
  - Compliance review confirms language alignment with SOC2/ISO evidence needs.
- Dependencies: UIP-002.
- Risk: LOW.

---

# 2. OpenAPI Spec (YAML)

- File: `docs/openapi/finops_optimization_contract.yaml`
- OpenAPI version: `3.1.0`
- Required endpoints included:
  - `POST /optimize/storage`
  - `GET /optimizations/{id}`
  - `POST /migrations/{id}/approve`
  - `POST /migrations/{id}/execute`
  - `POST /migrations/{id}/rollback`
  - `GET /pricing/versions`
  - `GET /confidence/explain/{id}`
- Mandatory fields included in schemas:
  - `decision_state`
  - `confidence_final`
  - `confidence_trace`
  - `pricing_version`
  - `pricing_source`
  - `pricing_confidence`
  - `guardrail_trace`
  - `migration_state`

---

# 3. Swagger UI Example Payloads

## 3.1 POST /optimize/storage (Response)

```json
{
  "optimization_id": "opt_9f55",
  "resource_id": "bucket-finance-prod",
  "optimization_unit": "BUCKET",
  "ml_prediction": {
    "predicted_provider": "AWS",
    "predicted_tier": "STANDARD_IA",
    "confidence_base": 0.99
  },
  "pricing_exploration": {
    "candidate_count": 7,
    "strategy": "deterministic_min_cost",
    "suppressed": true
  },
  "final_decision": {
    "recommended_provider": "AWS",
    "recommended_tier": "STANDARD",
    "before_cost_usd": 1842.23,
    "after_cost_usd": 1842.23,
    "savings_usd": 0.0,
    "percent_change": null,
    "rationale": "Pricing drift detected. Execution blocked."
  },
  "decision_state": "BLOCKED",
  "confidence_final": 0.59,
  "confidence_trace": {
    "formula": "confidence_final = confidence_base * data_window_factor * billing_realism_factor * aggregation_factor * migration_risk_factor",
    "confidence_base": 0.99,
    "data_window_factor": 0.8,
    "billing_realism_factor": 0.75,
    "aggregation_factor": 1.0,
    "migration_risk_factor": 1.0,
    "confidence_final": 0.594,
    "downgrade_reasons": [
      "Limited observation window (47 days).",
      "Pricing realism 'ESTIMATE' reduced confidence."
    ]
  },
  "guardrail_trace": [
    "Pricing drift detected (2026-02-10 vs latest 2026-02-18); execution blocked."
  ],
  "pricing_version": "2026-02-10",
  "pricing_source": "AWS",
  "pricing_confidence": "ESTIMATE",
  "pricing_trace": {
    "pricing_version_used": "2026-02-10",
    "latest_pricing_version": "2026-02-18",
    "pricing_drift_detected": true,
    "pricing_confidence": "ESTIMATE",
    "exploration_suppressed": true
  },
  "migration_state": "BLOCKED"
}
```

## 3.2 POST /migrations/{id}/execute (Blocked example)

```json
{
  "migration_id": "mig_44e1",
  "previous_state": "APPROVED",
  "migration_state": "BLOCKED",
  "allowed_next_states": ["ROLLED_BACK"],
  "decision_state": "BLOCKED",
  "guardrail_trace": [
    "Execution policy blocked predicted action (confidence/billing realism)."
  ],
  "confidence_final": 0.72,
  "pricing_confidence": "EXPORT"
}
```

---

# 4. Grafana Dashboard Designs

## 4.1 End-User Dashboard (FinOps / Cloud Teams)

Layout:
1. **Header Row**
   - `Estimated Savings (30d)`
   - `Realized Savings (30d)`
   - `Blocked Optimizations (30d)`
   - `Fallback Actions (30d)`
2. **Decision Quality Row**
   - `Decision State Distribution` (stacked bar by `decision_state`)
   - `Confidence Decay Factor Trend` (time series)
3. **Pricing Integrity Row**
   - `Pricing Drift Incidents` (time series)
   - `Version Sync Status` (table: version used vs latest)
4. **Migration Safety Row**
   - `Migration State Transitions` (heatmap)
   - `Rollback Rate` (gauge)

## 4.2 Admin / Platform Operator Dashboard

Layout:
1. **Control Plane Health**
   - `Optimization Throughput` (RPS)
   - `Blocked Rate` (percentage)
   - `Policy Violations` (counter)
2. **Model Governance**
   - `Confidence Factor Distribution` (histogram)
   - `Confidence Floor Breaches` (counter)
3. **Pricing Governance**
   - `Drift Detection Events` (time series)
   - `Pricing Confidence Mix (REAL/EXPORT/ESTIMATE)` (pie)
4. **Migration Orchestration**
   - `State Transition Matrix` (table)
   - `Mid-flight Blocks` (time series)

Alerts:
- `HighBlockedRate`: blocked decisions > 25% over 15m.
- `PricingDriftSpike`: drift events >= 10 over 10m.
- `ConfidenceDecayRegression`: average `confidence_decay_factor` drops below 0.65 for 30m.
- `FallbackBurst`: fallback actions > 20 over 10m.

---

# 5. Prometheus Metric Definitions

- `optimization_decisions_total{decision_state,provider,optimization_unit}`
  - Counter for all emitted decisions.
- `optimization_blocked_total{reason,provider}`
  - Counter for blocked terminal states.
- `confidence_decay_factor{factor_name,provider}`
  - Gauge for each confidence factor value (`data_window_factor`, `billing_realism_factor`, `aggregation_factor`, `migration_risk_factor`).
- `pricing_version_drift_detected{provider,version_used,latest_version}`
  - Counter incremented on drift detection.
- `migration_state_transitions_total{from_state,to_state}`
  - Counter for migration lifecycle transitions.
- `savings_realized_usd{provider}`
  - Counter for measured post-migration savings.
- `savings_estimated_usd{provider}`
  - Counter for predicted (not realized) savings.
- `fallback_actions_total{fallback_type,provider}`
  - Counter for safety fallback decisions.

---

# 6. Terraform Code Snippets

- Files:
  - `infra/terraform/observability/grafana_finops_dashboards.tf`
  - `infra/terraform/observability/grafana_finops_alerts.tf`

These snippets provision:
- End-user and admin Grafana dashboards.
- Prometheus alert rules for drift, blocked rate, fallback burst, and confidence regressions.

---

# 7. SOC2 / ISO 27001 Control Mapping

| Framework | Control ID | Control Description | Platform Feature | Evidence Produced | Audit Frequency |
|---|---|---|---|---|---|
| SOC2 CC | CC6.1 | Logical access controls | RBAC scopes per endpoint (`migration:execute`, etc.) | Access logs + denied scope events | Quarterly |
| SOC2 CC | CC7.2 | Change management | Versioned pricing/model policy gates | Change tickets, approval records, rollout logs | Quarterly |
| SOC2 CC | CC7.3 | Monitoring and anomalies | Drift, fallback, blocked alerts | Alert history, incident timelines | Monthly |
| SOC2 CC | CC8.1 | Risk mitigation controls | Decision-state blocking + guardrails | Guardrail trace + blocked decision audit events | Monthly |
| SOC2 CC | CC9.2 | Data integrity | Pricing clamp, non-negative savings enforcement | Contract test reports + payload integrity checks | Monthly |
| ISO 27001 | A.8.15 | Logging | Immutable decision and migration logs | Signed audit ledger extracts | Monthly |
| ISO 27001 | A.8.16 | Monitoring activities | Prometheus + Grafana alerting | Dashboard exports + alert evidence | Monthly |
| ISO 27001 | A.8.20 | Network/service security | Cross-cloud guardrails for latency/egress risk | Guardrail policy evaluations | Quarterly |
| ISO 27001 | A.5.15 | Access control policy | API scope-policy mapping | RBAC policy docs + enforcement test output | Semi-annual |
| ISO 27001 | A.5.17 | Authentication information | OAuth2 client credential scope enforcement | Token validation logs | Quarterly |
| ISO 27001 | A.5.36 | Compliance with policies | Execution gate requires high confidence + REAL billing | Blocked execution records with rationale | Quarterly |

Why unsafe optimizations are BLOCKED:
- Blocking protects customers from irreversible or misleading actions when confidence, billing realism, or pricing freshness is insufficient.
- The system makes non-execution explicit and auditable, preventing hidden aggressive recommendations from propagating into execution workflows.
