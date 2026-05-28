import { GlowCard } from "@/components/ui/GlowCard";
import { NeonBadge } from "@/components/ui/NeonBadge";
import type { DashboardSummary } from "@/lib/types";

interface ModeBannerProps {
  summary: DashboardSummary;
  recommendationCount: number;
  riskyCount: number;
}

const formatModeLabel = (mode: "ANALYSIS_MODE" | "EXECUTION_MODE") =>
  mode === "EXECUTION_MODE" ? "Execution Mode" : "Analysis Mode";

export function ModeBanner({ summary, recommendationCount, riskyCount }: ModeBannerProps) {
  const analysisActive = summary.system_mode === "ANALYSIS_MODE" || !summary.execution_authorized;
  const executionActive = summary.execution_authorized && summary.system_mode === "EXECUTION_MODE";

  return (
    <GlowCard className="p-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <p className="text-xs uppercase tracking-[0.24em] text-blue-700">Cloudteck Operating Modes</p>
          <h2 className="mt-2 text-2xl font-semibold text-slate-900">{formatModeLabel(summary.system_mode)}</h2>
          <p className="mt-1 text-sm text-slate-600">
            Analysis Ready: {summary.analysis_ready ? "Yes" : "No"} · Execution Authorized:{" "}
            {summary.execution_authorized ? "Yes" : "No"}
          </p>
        </div>
        <div className="rounded-xl border border-slate-200 bg-white px-4 py-2 text-xs text-slate-600">
          ML never auto-executes. Guardrails and dry-run remain mandatory.
        </div>
      </div>

      <div className="mt-4 grid gap-3 md:grid-cols-2">
        <div
          className={`rounded-xl border px-4 py-3 ${analysisActive ? "border-blue-200 bg-blue-50" : "border-slate-200 bg-white"}`}
        >
          <p className="text-xs uppercase tracking-wide text-slate-500">Analysis Mode</p>
          <p className="mt-1 text-sm font-semibold text-slate-900">Read-only access</p>
          <p className="mt-1 text-xs text-slate-600">Dry run allowed for all recommendations.</p>
        </div>
        <div
          className={`rounded-xl border px-4 py-3 ${executionActive ? "border-emerald-200 bg-emerald-50" : "border-slate-200 bg-white"}`}
        >
          <p className="text-xs uppercase tracking-wide text-slate-500">Execution Mode</p>
          <p className="mt-1 text-sm font-semibold text-slate-900">Read-write enabled</p>
          <p className="mt-1 text-xs text-slate-600">Cloud integration connected with write permissions.</p>
        </div>
      </div>

      <div className="mt-4 flex flex-wrap gap-2">
        <NeonBadge tone="indigo">Pricing {summary.pricing_version ?? "unsynced"}</NeonBadge>
        <NeonBadge tone="emerald">{recommendationCount} Open Recommendations</NeonBadge>
        <NeonBadge tone="rose">{riskyCount} Guardrail-Sensitive</NeonBadge>
      </div>
    </GlowCard>
  );
}
