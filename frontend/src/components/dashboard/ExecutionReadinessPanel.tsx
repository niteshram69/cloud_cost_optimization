import { useMemo } from "react";

import { GlowCard } from "@/components/ui/GlowCard";
import { NeonBadge } from "@/components/ui/NeonBadge";
import type { Recommendation } from "@/lib/types";

interface ExecutionReadinessPanelProps {
  recommendations: Recommendation[];
}

type ReadinessBand = "LOW" | "CONDITIONAL" | "READY";

const maturityScore: Record<Recommendation["data_maturity"], number> = {
  SYNTHETIC_MATURE: 0.45,
  EXPORT_MATURE: 0.7,
  LIVE_MATURE: 1,
};

const billingScore: Record<Recommendation["billing_realism"], number> = {
  ESTIMATE: 0.4,
  EXPORT: 0.7,
  LIVE: 1,
};

const authorityScore: Record<Recommendation["execution_authority"], number> = {
  NONE: 0.25,
  DRY_RUN_ONLY: 0.6,
  WRITE_ENABLED: 1,
};

const dominantValue = <T extends string>(values: T[], fallback: T): T => {
  if (values.length === 0) return fallback;
  const counts = new Map<T, number>();
  values.forEach((value) => counts.set(value, (counts.get(value) ?? 0) + 1));
  return Array.from(counts.entries()).sort((a, b) => b[1] - a[1])[0][0];
};

export function ExecutionReadinessPanel({ recommendations }: ExecutionReadinessPanelProps) {
  const readiness = useMemo(() => {
    if (recommendations.length === 0) {
      return {
        score: 0,
        band: "LOW" as ReadinessBand,
        dataMaturity: "SYNTHETIC_MATURE" as Recommendation["data_maturity"],
        billingRealism: "ESTIMATE" as Recommendation["billing_realism"],
        authority: "NONE" as Recommendation["execution_authority"],
      };
    }

    const dataMaturity = dominantValue(
      recommendations.map((item) => item.data_maturity),
      "SYNTHETIC_MATURE",
    );
    const billingRealism = dominantValue(
      recommendations.map((item) => item.billing_realism),
      "ESTIMATE",
    );
    const authority = dominantValue(
      recommendations.map((item) => item.execution_authority),
      "NONE",
    );

    const score =
      (maturityScore[dataMaturity] + billingScore[billingRealism] + authorityScore[authority]) / 3;

    const band: ReadinessBand = score >= 0.8 ? "READY" : score >= 0.55 ? "CONDITIONAL" : "LOW";

    return { score, band, dataMaturity, billingRealism, authority };
  }, [recommendations]);

  const tone = readiness.band === "READY" ? "emerald" : readiness.band === "CONDITIONAL" ? "indigo" : "rose";

  return (
    <GlowCard className="p-5">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-slate-900">Execution Readiness</h3>
        <NeonBadge tone={tone}>{readiness.band}</NeonBadge>
      </div>

      <div className="mt-4">
        <div className="flex items-center justify-between text-xs text-slate-600">
          <span>Readiness score</span>
          <span className="font-semibold text-slate-900">{Math.round(readiness.score * 100)}%</span>
        </div>
        <div className="mt-2 h-2 w-full overflow-hidden rounded-full bg-slate-100">
          <div
            className="h-full rounded-full bg-blue-600"
            style={{ width: `${Math.round(readiness.score * 100)}%` }}
          />
        </div>
      </div>

      <div className="mt-4 grid gap-2 text-xs text-slate-600">
        <div className="flex items-center justify-between rounded-lg border border-slate-200 bg-white px-3 py-2">
          <span>Data maturity</span>
          <span className="font-semibold text-slate-900">{readiness.dataMaturity}</span>
        </div>
        <div className="flex items-center justify-between rounded-lg border border-slate-200 bg-white px-3 py-2">
          <span>Billing realism</span>
          <span className="font-semibold text-slate-900">{readiness.billingRealism}</span>
        </div>
        <div className="flex items-center justify-between rounded-lg border border-slate-200 bg-white px-3 py-2">
          <span>Execution authority</span>
          <span className="font-semibold text-slate-900">{readiness.authority}</span>
        </div>
      </div>

      <p className="mt-3 text-xs text-slate-500">
        Readiness aggregates data maturity, billing realism, and authority. Execution requires explicit approvals even
        when readiness is high.
      </p>
    </GlowCard>
  );
}
