# Cloudteck Zero-Trust FinOps
## Dry-Run Authority and Enterprise Readiness Technical Specification

## 1. Scope and Intent

This document defines the production behavior that unlocks controlled migration execution without weakening Zero-Trust guarantees.

In scope:

- Explicit separation of analysis readiness vs execution authority.
- Four independent readiness/authority signals in recommendation payloads.
- Dry-run execution path for non-write contexts (`USER_UPLOAD`, read-only integrations).
- Corrected `NO_OP` semantics and user-facing recommendation states.
- Mode banner and three-signal recommendation card UX contract.

Out of scope:

- Changes to ML classifier internals.
- Changes to confidence decay factors/formula weights.
- Bypass of hard guardrails.

## 2. Problem Summary

The previous behavior was technically safe but operationally misleading:

- Low maturity was collapsed into terminal `NO_OP`.
- Users could not distinguish "not recommended for auto-execution" from "not executable at all."
- `USER_UPLOAD` scenarios had no practical execution simulation path.

Result: recommendations existed but enterprise teams could not trial execution flows.

## 3. Zero-Trust Constraints

The following remain enforced:

- ML never auto-executes migrations.
- Hard guardrails are non-bypassable.
- Cross-cloud UI execution is disallowed.
- Every authorized execution passes through `DRY_RUN`.
- Runtime anomalies trigger rollback and circuit-breaker behavior.

## 4. Enterprise Signal Model

Each recommendation now carries four explicit, independent axes.

### 4.1 `ML_CONFIDENCE`

- Field: `ml_confidence`
- Meaning: classifier certainty only.
- Effect: informational; does not directly grant execution.

### 4.2 `DATA_MATURITY`

- Fields: `data_maturity`, `data_maturity_score`
- Values: `SYNTHETIC_MATURE`, `EXPORT_MATURE`, `LIVE_MATURE`
- Meaning: quality and observation maturity of operational data.

### 4.3 `BILLING_REALISM`

- Field: `billing_realism`
- Values: `ESTIMATE`, `EXPORT`, `LIVE`
- Meaning: financial evidence fidelity.
- Effect: reduces precision/readiness when estimate-based; does not hard-block dry-run.

### 4.4 `EXECUTION_AUTHORITY`

- Field: `execution_authority`
- Values: `NONE`, `DRY_RUN_ONLY`, `WRITE_ENABLED`
- Meaning: what the platform is permitted to do for this provider/resource context.

## 5. Decision and Recommendation Semantics

### 5.1 Engine decision state (internal)

`DecisionState`:

- `EXPLORATORY`
- `PREDICTED`
- `FALLBACK`
- `NO_OP`
- `BLOCKED`

### 5.2 Correct `NO_OP` usage

`NO_OP` is valid only when:

- recommended tier == current tier, or
- hard guardrail forces retain behavior.

`LOW_MATURITY` is no longer represented as `NO_OP`.

### 5.3 User-facing action/state

- `recommendation_action`: `PROPOSED` | `NO_OP`
- `recommendation_state`:
  - `BLOCKED_BY_AUTHORITY`
  - `BLOCKED_BY_GUARDRAIL`
  - `READY_FOR_DRY_RUN`
  - `READY_FOR_EXECUTION`

## 6. Decision Logic (Pseudocode)

```text
input: recommendation, pricing decision, confidence decay output, authority context

if pricing_drift_detected:
    decision_state = BLOCKED
    action = RETAIN

else if decay.policy_action == MOVE_TO_PREDICTED_TIER:
    decision_state = PREDICTED
    action = MOVE_TO_PREDICTED_TIER

else if decay.policy_action == MOVE_TO_STANDARD_IA:
    decision_state = FALLBACK
    action = MOVE_TO_STANDARD_IA

else:
    if recommended_tier == current_tier:
        decision_state = NO_OP
        action = RETAIN
    else:
        decision_state = FALLBACK
        action = PROPOSED

if hot_data_and_archive_target:
    decision_state = BLOCKED
    action = RETAIN

same_tier = (recommended_tier == current_tier)
if same_tier and decision_state != BLOCKED:
    decision_state = NO_OP
    action = RETAIN

hard_block = (decision_state == BLOCKED)
execution_authority = derive_authority(ingestion_mode, integration_permission)
execution_eligibility = derive_eligibility(execution_authority, hard_block, is_cross_cloud)

recommendation_action = NO_OP if decision_state == NO_OP else PROPOSED

if hard_block:
    recommendation_state = BLOCKED_BY_GUARDRAIL
else if execution_eligibility == NONE:
    recommendation_state = BLOCKED_BY_AUTHORITY
else if execution_eligibility == DRY_RUN_ELIGIBLE:
    recommendation_state = READY_FOR_DRY_RUN
else:
    recommendation_state = READY_FOR_EXECUTION
```

## 7. Execution Eligibility Matrix

| Ingestion Context | Permission | Guardrail | Execution Authority | Execution Eligibility | User CTA |
|---|---|---|---|---|---|
| `USER_UPLOAD` | `NONE` | pass | `DRY_RUN_ONLY` | `DRY_RUN_ELIGIBLE` | `Run Migration Dry-Run` |
| `API_INGESTION` | no write | pass | `DRY_RUN_ONLY` | `DRY_RUN_ELIGIBLE` | `Run Migration Dry-Run` |
| `CLOUD_INTEGRATION` | `READ_ONLY` | pass | `DRY_RUN_ONLY` | `DRY_RUN_ELIGIBLE` | `Run Migration Dry-Run` |
| `CLOUD_INTEGRATION` | `READ_WRITE` | pass | `WRITE_ENABLED` | `EXECUTABLE` | `Migrate Now` or `Request Approval` |
| any | any | hard block | any | `NONE` | disabled with guardrail reason |
| `READ_WRITE` + cross-cloud | pass | n/a | `WRITE_ENABLED` | `DRY_RUN_ELIGIBLE` | `Run Migration Dry-Run` |

## 8. Pricing Clamp Semantics

Safety states must not expose exploratory negative/unstable pricing.

```text
before = max(before_cost, 0)

if decision_state != PREDICTED:
    after = before
    savings = 0
    percent_change = null
else:
    after = max(after_cost, 0)
    after = min(after, before)
    savings = max(before - after, 0)
    percent_change = savings / before (if before > 0 else null)
```

## 9. Dry-Run Lifecycle Contract

For `execution_eligibility == DRY_RUN_ELIGIBLE`:

- Create migration plan (`PLANNED`).
- Transition to `DRY_RUN`.
- Produce simulated execution report and risk/rollback metadata.
- Return `migration_state = SIMULATED_RESULTS`.
- No cloud-side write APIs are called.

Expected path:

`PLANNED -> DRY_RUN -> SIMULATED_RESULTS`

Direct execution path remains:

`PLANNED -> DRY_RUN -> APPROVED -> EXECUTING -> COMPLETED|ROLLED_BACK|BLOCKED`

## 10. UX Contract (Phase 1 Implemented)

### 10.1 Mode Banner

Dashboard surfaces:

- `system_mode`: `ANALYSIS_MODE` | `EXECUTION_MODE`
- `analysis_ready`: boolean
- `execution_authorized`: boolean
- per-provider authority cards with reason text

### 10.2 Three-signal recommendation card

Each card prominently shows:

- `Model Confidence`
- `Operational Readiness`
- `Execution Eligibility`

Supporting details:

- data maturity
- billing realism
- execution authority
- recommendation state
- unlock hint

### 10.3 CTA and copy behavior

- `NONE`: button disabled, label `Unavailable`
- `DRY_RUN_ELIGIBLE`: button label `Run Migration Dry-Run`
- `EXECUTABLE` + risk gate required: `Request Approval`
- `EXECUTABLE` + no risk gate: `Migrate Now`

Copy contract:

- Blocked: `Execution authority not available.`
- Dry-run: `Dry-run simulation only. No cloud resources will be modified.`
- Executable: `Execution allowed. DRY_RUN will execute first.`
- Savings in non-predicted states: `Savings unavailable (safety or estimated-pricing state).`

## 11. API and Payload Contract

### 11.1 Recommendation payload additions

- `ml_confidence`
- `data_maturity`
- `data_maturity_score`
- `billing_realism`
- `execution_authority`
- `operational_readiness`
- `operational_readiness_band`
- `execution_eligibility`
- `execution_reason`
- `execution_unlock_hint`
- `recommendation_action`
- `recommendation_state`

### 11.2 Migration authorization contract

Request fields support explicit override + risk acknowledgements:

- `recommendation_id` or `resource_id`
- `approved_target_tier`
- `override_type`
- `override_confidence`
- `justification`
- `acknowledged_risks`

Response supports simulation outcomes:

- `execution_result`: includes `SIMULATED_RESULTS`
- `migration_state`
- `execution_eligibility`
- `dry_run_report`
- `monitoring_report`
- `audit_event_id`

## 12. Why Previous Behavior Was Misleading

The prior model mapped maturity uncertainty directly to terminal `NO_OP`, which implied "do nothing" instead of "not ready for direct execution." That hid the valid simulation path and made authority constraints appear like model disagreement. The new model keeps safety intact but makes the unlock path explicit and operationally actionable.

## 13. Acceptance Criteria

For `USER_UPLOAD` with no write integration:

- tier predictions remain unchanged.
- recommendations use `PROPOSED` (not forced `NO_OP` unless same tier).
- `execution_eligibility = DRY_RUN_ELIGIBLE`.
- CTA is `Run Migration Dry-Run`.
- migration response supports `SIMULATED_RESULTS`.

For write-enabled integration:

- `execution_eligibility` transitions to `EXECUTABLE`.
- direct execution remains dry-run gated.

For hard guardrail violations:

- recommendations are non-executable (`NONE`).
- UI shows explicit guardrail reason and unlock constraints.

## 14. Implementation References

- `backend/app/models/enums.py`
- `backend/app/schemas/dashboard.py`
- `backend/app/schemas/migration_authorization.py`
- `backend/app/services/dashboard_service.py`
- `backend/app/services/migration_authorization_service.py`
- `frontend/lib/types.ts`
- `frontend/app/dashboard/page.tsx`
