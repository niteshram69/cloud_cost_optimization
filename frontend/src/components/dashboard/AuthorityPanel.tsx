import { GlowCard } from "@/components/ui/GlowCard";
import { NeonBadge } from "@/components/ui/NeonBadge";
import type { DashboardSummary } from "@/lib/types";

interface AuthorityPanelProps {
  summary: DashboardSummary;
}

const formatModeLabel = (mode: "ANALYSIS_MODE" | "EXECUTION_MODE") =>
  mode === "EXECUTION_MODE" ? "Execution Mode" : "Analysis Mode";

export function AuthorityPanel({ summary }: AuthorityPanelProps) {
  const authorityTone = summary.execution_authorized ? "emerald" : "rose";

  return (
    <GlowCard className="p-5">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-slate-900">Execution Authority</h3>
        <NeonBadge tone={authorityTone}>
          {summary.execution_authorized ? "Authorized" : "Not Authorized"}
        </NeonBadge>
      </div>

      <div className="mt-4 grid gap-3">
        <div className="rounded-xl border border-slate-200 bg-white p-3">
          <p className="text-[11px] uppercase tracking-wide text-slate-500">System Mode</p>
          <p className="mt-1 text-sm font-semibold text-slate-900">{formatModeLabel(summary.system_mode)}</p>
          <p className="mt-1 text-xs text-slate-500">ML recommendations never auto-execute.</p>
        </div>
        <div className="rounded-xl border border-slate-200 bg-white p-3">
          <p className="text-[11px] uppercase tracking-wide text-slate-500">Analysis Ready</p>
          <p className="mt-1 text-sm font-semibold text-slate-900">{summary.analysis_ready ? "Yes" : "No"}</p>
          <p className="mt-1 text-xs text-slate-500">Observation and pricing context validated.</p>
        </div>
        <div className="rounded-xl border border-slate-200 bg-white p-3">
          <p className="text-[11px] uppercase tracking-wide text-slate-500">Execution Gate</p>
          <p className="mt-1 text-sm font-semibold text-slate-900">
            {summary.execution_authorized ? "Write-enabled" : "Dry-run only"}
          </p>
          <p className="mt-1 text-xs text-slate-500">Explicit approval required for all execution.</p>
        </div>
      </div>

      <div className="mt-4 text-xs text-slate-600">
        Authority is provider-scoped. Connect a cloud integration with READ_WRITE permissions to enable execution.
        Dry-run remains available for analysis-only sources.
      </div>
    </GlowCard>
  );
}
