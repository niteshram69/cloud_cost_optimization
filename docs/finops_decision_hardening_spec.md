# FinOps Decision Hardening Specification

## 1. Architecture Diagram (Text)

```text
Ingestion Layer
  -> Object normalization + idempotency
  -> Bucket aggregation (primary optimization unit)
  -> Billing overlay (real/export/estimate confidence tagging)

Decision Layer
  -> ML prediction (tier/provider)
  -> Guardrail evaluation (latency, egress, hot-data archive safety)
  -> Confidence derivation
       confidence_final = confidence_base
                          * data_window_factor
                          * billing_realism_factor
                          * aggregation_factor
                          * migration_risk_factor
  -> Pricing exploration
  -> Decision state machine
       EXPLORATORY -> PREDICTED | FALLBACK | NO_OP | BLOCKED
  -> Pricing clamp gate (state-aware)

Execution Layer
  -> Migration lifecycle state machine
     PLANNED -> APPROVED -> DRY_RUN -> EXECUTING -> COMPLETED
                                  \-> ROLLED_BACK
                                  \-> BLOCKED

Experience Layer
  -> UI payload separates prediction/exploration/final decision
  -> Audit traces: decision, confidence, pricing, guardrails, lifecycle
```

## 2. Decision-State Table

| decision_state | Meaning | Execution allowed | Savings shown | Percent change shown | Notes |
|---|---|---:|---:|---:|---|
| EXPLORATORY | Raw pricing exploration only | No | No | No | Internal stage only, not an optimization outcome |
| PREDICTED | ML prediction passed confidence + safety policy | Yes (if REAL billing and confidence > 80%) | Yes | Yes | Only state that can claim optimization |
| FALLBACK | Safety fallback selected (e.g., Standard-IA) | No | $0.00 | No | Cost-neutral safety move |
| NO_OP | Keep current tier due low confidence/insufficient evidence | No | $0.00 | No | Explicitly explain why no optimization |
| BLOCKED | Policy or guardrail blocked recommendation | No | $0.00 | No | Pricing drift, unsafe migration profile, or policy violation |

## 3. Pricing Clamp Pseudocode

```python
def apply_pricing_clamp(state, before_cost_usd, after_cost_usd):
    before = round(max(before_cost_usd or 0.0, 0.0), 4)

    if state != "PREDICTED":
        # exploratory math must not leak into fallback/no-op/blocked payloads
        return {
            "before_cost_usd": before,
            "after_cost_usd": before,
            "savings_usd": 0.0,
            "percent_change": None,
            "exploration_suppressed": True,
        }

    after = round(max(after_cost_usd if after_cost_usd is not None else before, 0.0), 4)
    if after > before:
        after = before

    savings = round(max(before - after, 0.0), 4)
    percent_change = round((savings / before) * 100, 2) if before > 0 else None

    return {
        "before_cost_usd": before,
        "after_cost_usd": after,
        "savings_usd": savings,
        "percent_change": percent_change,
        "exploration_suppressed": False,
    }
```

## 4. Confidence Math Derivation

### 4.1 Formula

```text
confidence_final =
  confidence_base
  * data_window_factor
  * billing_realism_factor
  * aggregation_factor
  * migration_risk_factor
```

### 4.2 Factors

- `data_window_factor`
  - `>90d` = `1.00`
  - `30-90d` = `0.80`
  - `<30d` = `0.60`

- `billing_realism_factor`
  - `REAL` = `1.00`
  - `EXPORT` = `0.90`
  - `ESTIMATE` = `0.75`

- `aggregation_factor`
  - `BUCKET` = `1.00`
  - `OBJECT` (>=1000 samples) = `0.90`
  - `OBJECT` (<1000 samples) = `0.85`

- `migration_risk_factor`
  - same-cloud + normal access = `1.00`
  - same-cloud + very high access = `0.90`
  - cross-cloud + low access = `0.82`
  - cross-cloud + access >10/30d = `0.72`

### 4.3 Worked Example (required)

```text
base = 0.99
data_window_factor = 0.80
billing_realism_factor = 0.75
aggregation_factor = 1.00
migration_risk_factor = 1.00

confidence_final = 0.99 * 0.80 * 0.75 * 1.00 * 1.00 = 0.594 (~0.59)
```

## 5. Example Corrected Payloads by State

### 5.1 PREDICTED

```json
{
  "decision_state": "PREDICTED",
  "pricing": {
    "before_cost_usd": 1520.12,
    "after_cost_usd": 1130.22,
    "savings_usd": 389.90,
    "percent_change": 25.65
  },
  "confidence_final": 0.84,
  "pricing_confidence": "REAL"
}
```

### 5.2 FALLBACK

```json
{
  "decision_state": "FALLBACK",
  "label": "Safety fallback due to confidence decay",
  "pricing": {
    "before_cost_usd": 840.10,
    "after_cost_usd": 840.10,
    "savings_usd": 0.0,
    "percent_change": null
  },
  "priority": "HIGH"
}
```

### 5.3 NO_OP

```json
{
  "decision_state": "NO_OP",
  "reason": "Insufficient confidence after decay",
  "pricing": {
    "before_cost_usd": 445.30,
    "after_cost_usd": 445.30,
    "savings_usd": 0.0,
    "percent_change": null
  }
}
```

### 5.4 BLOCKED

```json
{
  "decision_state": "BLOCKED",
  "reason": "Pricing version drift detected",
  "pricing": {
    "before_cost_usd": 2210.00,
    "after_cost_usd": 2210.00,
    "savings_usd": 0.0,
    "percent_change": null
  },
  "pricing_trace": {
    "pricing_version_used": "2026-02-10",
    "latest_pricing_version": "2026-02-18",
    "pricing_drift_detected": true
  }
}
```

## 6. UI Wording Guidelines

- Fallback state banner:
  - `Safety fallback due to confidence decay. No optimization executed.`
- Blocked state banner:
  - `Optimization blocked by policy/guardrail. Review pricing drift and confidence inputs.`
- No-op explanation:
  - `No optimization recommended: available evidence is insufficient for safe execution.`
- Predicted action disclaimer:
  - `Execution allowed only with high confidence and REAL billing-backed pricing.`
- Never display:
  - negative savings percentages
  - exploratory before/after values when state is `FALLBACK`, `NO_OP`, or `BLOCKED`

## 7. CloudHealth/Cloudability-Parity Behavior

- Conservative default:
  - Non-PREDICTED outcomes are explicitly cost-neutral and non-executable.
- Safety-first execution:
  - Execution gate requires `decision_state=PREDICTED`, `confidence_final>0.80`, and `pricing_confidence=REAL`.
- Explainability-first:
  - Payload always includes `decision_state`, `confidence_trace`, `guardrail_trace`, `pricing_trace`, and migration lifecycle state.
- Explicit non-optimization reasons:
  - System explains **why** optimization did not happen (drift, low confidence, billing realism, guardrail block) instead of hiding outcome.

## 8. Migration State Machine Table

| Current State | Event | Next State | Rule |
|---|---|---|---|
| PLANNED | approve | APPROVED | Requires `migration:approve` scope |
| APPROVED | dry_run | DRY_RUN | Must pass static guardrail checks |
| APPROVED | execute | EXECUTING | Allowed only from APPROVED |
| EXECUTING | complete | COMPLETED | Requires integrity validation success |
| EXECUTING | rollback | ROLLED_BACK | Rollback is first-class transition |
| COMPLETED | rollback | ROLLED_BACK | Allowed for post-cutover failures |
| PLANNED/APPROVED/DRY_RUN/EXECUTING | block | BLOCKED | Triggered by drift, confidence drop, or guardrail breach |

Failure modes:
- Pricing drift detected after approval -> transition to `BLOCKED`.
- Confidence drops below execution floor mid-flight -> transition to `BLOCKED` and abort.
- Cross-cloud egress/latency risk exceeds threshold -> execution blocked.
- Integrity verification failure during execute -> rollback transition.

Example migration payload:

```json
{
  "migration_id": "mig_7b2f",
  "previous_state": "APPROVED",
  "migration_state": "BLOCKED",
  "allowed_next_states": ["ROLLED_BACK"],
  "decision_state": "BLOCKED",
  "confidence_final": 0.74,
  "pricing_confidence": "EXPORT",
  "guardrail_trace": [
    "Pricing drift detected (2026-02-10 vs latest 2026-02-18).",
    "Execution policy blocked predicted action (confidence/billing realism)."
  ]
}
```
