import { NeonBadge } from "@/components/ui/NeonBadge";
import type { Recommendation } from "@/lib/types";

export type MigrationFeedbackState = {
  kind: "COMPLETED" | "ROLLED_BACK" | "BLOCKED" | "SIMULATED_RESULTS";
  message: string;
} | null;

interface RecommendationCardProps {
  item: Recommendation;
  executionLabel: string;
  buttonLabel: string;
  buttonReason: string;
  mlPredictedTier: string;
  riskLevel: string;
  savingsLine: string;
  executionForbidden: boolean;
  needsRiskGate: boolean;
  executing: boolean;
  onMigrate: (item: Recommendation) => void | Promise<void>;
  migrationFeedback?: MigrationFeedbackState;
}

export function RecommendationCard({
  item,
  executionLabel,
  buttonLabel,
  buttonReason,
  mlPredictedTier,
  riskLevel,
  savingsLine,
  executionForbidden,
  needsRiskGate,
  executing,
  onMigrate,
  migrationFeedback,
}: RecommendationCardProps) {
  const feedbackTone =
    migrationFeedback?.kind === "COMPLETED"
      ? "text-teal-700"
      : migrationFeedback?.kind === "SIMULATED_RESULTS"
        ? "text-blue-700"
        : migrationFeedback?.kind === "ROLLED_BACK"
          ? "text-amber-700"
          : "text-rose-700";

  return (
    <article className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 className="text-sm font-semibold text-slate-900">{item.resource_name}</h3>
          <p className="mt-1 text-xs text-slate-600">
            {item.current_provider} · {item.current_tier} → {item.recommended_tier}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2 text-xs">
          <NeonBadge tone="indigo">{item.current_provider}</NeonBadge>
          <NeonBadge tone={executionForbidden ? "rose" : needsRiskGate ? "indigo" : "emerald"}>
            {executionLabel}
          </NeonBadge>
        </div>
      </div>

      <div className="mt-4 grid gap-3 md:grid-cols-3">
        <div className="rounded-xl border border-blue-200 bg-blue-50 p-3">
          <p className="text-[11px] uppercase tracking-wide text-blue-700">Model Confidence</p>
          <p className="mt-1 text-lg font-semibold text-blue-700">
            {(item.model_confidence * 100).toFixed(1)}%
          </p>
          <p className="mt-1 text-[11px] text-slate-600">Classifier certainty only</p>
        </div>
        <div className="rounded-xl border border-amber-200 bg-amber-50 p-3">
          <p className="text-[11px] uppercase tracking-wide text-amber-700">Operational Readiness</p>
          <p className="mt-1 text-lg font-semibold text-amber-700">
            {(item.operational_readiness * 100).toFixed(1)}%
          </p>
          <p className="mt-1 text-[11px] text-slate-600">{item.operational_readiness_band}</p>
        </div>
        <div className="rounded-xl border border-blue-200 bg-blue-50 p-3">
          <p className="text-[11px] uppercase tracking-wide text-blue-700">Execution Eligibility</p>
          <p className="mt-1 text-sm font-semibold text-blue-700">{executionLabel}</p>
          <p className="mt-1 text-[11px] text-slate-600">{item.execution_eligibility}</p>
        </div>
      </div>

      <div className="mt-3 grid gap-2 text-xs text-slate-600 md:grid-cols-2">
        <p>
          <span className="font-semibold text-slate-900">Data Maturity:</span> {item.data_maturity}
        </p>
        <p>
          <span className="font-semibold text-slate-900">Billing Realism:</span> {item.billing_realism}
        </p>
        <p>
          <span className="font-semibold text-slate-900">Execution Authority:</span> {item.execution_authority}
        </p>
        <p>
          <span className="font-semibold text-slate-900">Recommendation State:</span> {item.recommendation_state}
        </p>
      </div>

      <div className="mt-3 rounded-xl border border-slate-200 bg-white p-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="text-xs text-slate-600">
            <span className="font-semibold text-slate-900">Action:</span> {item.recommendation_action}
            {" · "}
            <span className="font-semibold text-slate-900">Decision:</span> {item.decision_state}
            {" · "}
            <span className="font-semibold text-slate-900">Risk:</span> {riskLevel}
            {" · "}
            <span className="font-semibold text-slate-900">ML Tier:</span> {mlPredictedTier}
          </div>
          <button
            type="button"
            disabled={executionForbidden || executing}
            title={buttonReason}
            onClick={() => void onMigrate(item)}
            className="rounded-full border border-blue-200 px-4 py-1.5 text-xs font-semibold text-blue-700 shadow-[0_12px_26px_rgba(37,99,235,0.18)] transition hover:border-blue-300 hover:bg-blue-50 disabled:cursor-not-allowed disabled:border-slate-200 disabled:text-slate-500 disabled:shadow-none"
          >
            {buttonLabel}
          </button>
        </div>
        <p className="mt-2 text-xs text-slate-600">{savingsLine}</p>
        <p className="mt-1 text-xs text-slate-500">{buttonReason}</p>
        <p className="mt-1 text-xs text-slate-500">Unlock path: {item.execution_unlock_hint}</p>
        <p className="mt-1 text-xs text-slate-500">
          Source: {item.ingestion_mode} · Permission: {item.integration_permission}
        </p>
        {item.guardrail_trace.length > 0 ? (
          <p className="mt-1 text-xs text-amber-700">Guardrails: {item.guardrail_trace.join(" | ")}</p>
        ) : null}
        {item.operational_readiness_reasons.length > 0 ? (
          <p className="mt-1 text-xs text-slate-500">
            Readiness factors: {item.operational_readiness_reasons.join(" ")}
          </p>
        ) : null}
        {migrationFeedback ? (
          <p className={`mt-2 text-xs font-semibold ${feedbackTone}`}>
            {migrationFeedback.kind === "COMPLETED"
              ? "Completed Successfully"
              : migrationFeedback.kind === "SIMULATED_RESULTS"
                ? `Dry-Run Completed: ${migrationFeedback.message}`
                : migrationFeedback.kind === "ROLLED_BACK"
                  ? `Rolled Back: ${migrationFeedback.message}`
                  : `Blocked: ${migrationFeedback.message}`}
          </p>
        ) : null}
      </div>

      <details className="mt-3 rounded-xl border border-slate-200 bg-white p-3">
        <summary className="cursor-pointer text-xs font-semibold uppercase tracking-wide text-slate-600">
          Technical Trace
        </summary>
        <div className="mt-3 grid gap-4 lg:grid-cols-2">
          <div>
            <p className="text-xs uppercase tracking-wide text-slate-500">Feature Snapshot</p>
            <ul className="mt-2 space-y-1 text-xs text-slate-600">
              {Object.entries(item.feature_snapshot).map(([key, value]) => (
                <li key={key} className="flex justify-between gap-3">
                  <span className="text-slate-500">{key}</span>
                  <span>{String(value)}</span>
                </li>
              ))}
            </ul>
          </div>
          <div>
            <p className="text-xs uppercase tracking-wide text-slate-500">Rule Trace</p>
            <ul className="mt-2 space-y-1 text-xs text-slate-600">
              {item.rule_override_trace.map((trace, index) => (
                <li key={`${item.id}-${index}`}>{trace}</li>
              ))}
            </ul>
          </div>
        </div>
      </details>
    </article>
  );
}
