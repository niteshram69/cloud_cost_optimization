import Link from "next/link";

import { GlowCard } from "@/components/ui/GlowCard";
import { NeonBadge } from "@/components/ui/NeonBadge";
import type { ProviderAuthority } from "@/lib/types";

interface IntegrationPanelProps {
  providers: ProviderAuthority[];
}

const formatModeLabel = (mode: "ANALYSIS_MODE" | "EXECUTION_MODE") =>
  mode === "EXECUTION_MODE" ? "Execution Mode" : "Analysis Mode";

export function IntegrationPanel({ providers }: IntegrationPanelProps) {
  return (
    <GlowCard className="p-5">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-slate-900">Integrations</h3>
        <span className="text-xs text-slate-500">{providers.length} providers</span>
      </div>

      <div className="mt-4 space-y-3">
        {providers.length === 0 ? (
          <div className="rounded-xl border border-dashed border-slate-200 bg-white p-3 text-xs text-slate-500">
            No integrations connected.
          </div>
        ) : (
          providers.map((provider) => (
            <div key={provider.provider} className="rounded-xl border border-slate-200 bg-white p-3">
              <div className="flex items-center justify-between gap-2">
                <span className="text-sm font-semibold text-slate-900">{provider.provider}</span>
                <NeonBadge tone={provider.execution_authorized ? "emerald" : "indigo"}>
                  {formatModeLabel(provider.mode)}
                </NeonBadge>
              </div>
              <p className="mt-2 text-xs text-slate-600">
                {provider.ingestion_mode} · {provider.integration_permission}
              </p>
              <p className="mt-1 text-xs text-slate-500">{provider.reason}</p>
              {!provider.execution_authorized ? (
                <Link
                  href="/dashboard/integrations"
                  className="mt-3 inline-flex rounded-full border border-blue-200 px-3 py-1 text-xs font-semibold text-blue-700 hover:border-blue-300 hover:bg-blue-50"
                >
                  Connect for execution
                </Link>
              ) : null}
            </div>
          ))
        )}
      </div>
    </GlowCard>
  );
}
