import type { Recommendation } from "@/lib/types";

interface RecommendationTableProps {
  items: Recommendation[];
  onDryRun: (item: Recommendation) => void | Promise<void>;
  onViewSummary: (item: Recommendation) => void | Promise<void>;
}

const riskLevelLabel = (confidence: number): string => {
  if (confidence < 0.5) return "HIGH";
  if (confidence < 0.8) return "MEDIUM";
  return "LOW";
};

const riskTone =
  (risk: string) =>
    risk === "HIGH"
      ? "bg-rose-100 text-rose-700 border-rose-200"
      : risk === "MEDIUM"
        ? "bg-amber-100 text-amber-700 border-amber-200"
        : "bg-emerald-100 text-emerald-700 border-emerald-200";

const tierTone = (tier: string) => {
  const upper = tier.toUpperCase();
  if (upper.includes("ARCHIVE") || upper.includes("GLACIER")) {
    return "border-slate-200 bg-slate-100 text-slate-600";
  }
  if (upper.includes("COLD") || upper.includes("COOL")) {
    return "border-blue-200 bg-blue-50 text-blue-700";
  }
  if (upper.includes("WARM") || upper.includes("INFREQUENT")) {
    return "border-amber-200 bg-amber-50 text-amber-700";
  }
  return "border-slate-200 bg-white text-slate-600";
};

export function RecommendationTable({ items, onDryRun, onViewSummary }: RecommendationTableProps) {
  if (items.length === 0) {
    return <p className="mt-4 text-sm text-slate-500">No recommendations available.</p>;
  }

  return (
    <div className="mt-4 overflow-hidden rounded-xl border border-slate-200 bg-white">
      <div className="hidden grid-cols-[2fr_1fr_2fr_1fr_1fr_1fr_1.5fr] gap-4 border-b border-slate-200 bg-slate-50 px-4 py-3 text-xs font-semibold uppercase tracking-[0.2em] text-slate-500 lg:grid">
        <span>Resource</span>
        <span>Provider</span>
        <span>Tier Change</span>
        <span>Savings</span>
        <span>Confidence</span>
        <span>Risk</span>
        <span>Actions</span>
      </div>
      {items.map((item) => {
        const risk = item.migration_advisory?.risk_level
          ? String(item.migration_advisory.risk_level).toUpperCase()
          : riskLevelLabel(item.confidence_final);
        const dryRunDisabled = item.execution_eligibility === "NONE";
        const confidencePercent = Math.round(item.confidence_final * 100);
        const savingsTone = item.estimated_monthly_savings > 0 ? "text-green-600" : "text-slate-400";

        return (
          <div
            key={item.id}
            className="grid grid-cols-1 gap-4 border-b border-slate-100 px-4 py-4 transition hover:bg-gray-50 lg:grid-cols-[2fr_1fr_2fr_1fr_1fr_1fr_1.5fr]"
          >
            <div className="space-y-2">
              <p className="text-sm font-semibold text-slate-900 break-all">{item.resource_name}</p>
              <p className="text-xs text-slate-500">
                {item.current_tier} → {item.recommended_tier}
              </p>
            </div>

            <div className="text-sm text-slate-700">
              <p className="text-xs uppercase tracking-wide text-slate-400 lg:hidden">Provider</p>
              <p className="font-semibold">{item.current_provider}</p>
            </div>

            <div className="text-sm text-slate-700">
              <p className="text-xs uppercase tracking-wide text-slate-400 lg:hidden">Tier Change</p>
              <div className="mt-1 flex flex-wrap items-center gap-2 text-xs">
                <span className={`rounded-full border px-2.5 py-1 font-semibold ${tierTone(item.current_tier)}`}>
                  {item.current_tier}
                </span>
                <span className="text-slate-400">→</span>
                <span className={`rounded-full border px-2.5 py-1 font-semibold ${tierTone(item.recommended_tier)}`}>
                  {item.recommended_tier}
                </span>
              </div>
            </div>

            <div className="text-sm">
              <p className="text-xs uppercase tracking-wide text-slate-400 lg:hidden">Savings</p>
              <p className={`text-lg font-semibold ${savingsTone}`}>
                ${item.estimated_monthly_savings.toFixed(2)}/mo
              </p>
            </div>

            <div className="text-sm text-slate-700">
              <p className="text-xs uppercase tracking-wide text-slate-400 lg:hidden">Confidence</p>
              <div className="mt-2 h-2 w-full rounded-full bg-slate-100">
                <div className="h-2 rounded-full bg-blue-500" style={{ width: `${confidencePercent}%` }} />
              </div>
              <p className="mt-1 text-xs text-slate-500">{confidencePercent}%</p>
            </div>

            <div className="text-sm text-slate-700">
              <p className="text-xs uppercase tracking-wide text-slate-400 lg:hidden">Risk</p>
              <span className={`mt-2 inline-flex rounded-full border px-2.5 py-1 text-xs font-semibold ${riskTone(risk)}`}>
                {risk}
              </span>
            </div>

            <div className="text-sm text-slate-700">
              <p className="text-xs uppercase tracking-wide text-slate-400 lg:hidden">Actions</p>
              <div className="mt-2 flex flex-wrap items-center gap-2">
                <button
                  type="button"
                  disabled={dryRunDisabled}
                  onClick={() => void onDryRun(item)}
                  className="rounded-full border border-blue-500 px-3 py-1 text-xs font-semibold text-blue-600 hover:bg-blue-50 disabled:cursor-not-allowed disabled:border-slate-200 disabled:text-slate-400"
                >
                  Dry Run
                </button>
                <button
                  type="button"
                  onClick={() => void onViewSummary(item)}
                  className="rounded-full border border-slate-300 px-3 py-1 text-xs font-semibold text-slate-700 hover:bg-slate-50"
                >
                  View Summary
                </button>
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}
