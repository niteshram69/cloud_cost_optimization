import { GlowCard } from "@/components/ui/GlowCard";
import { NeonBadge } from "@/components/ui/NeonBadge";
import type { DashboardSummary } from "@/lib/types";

interface DatasetBannerProps {
  summary: DashboardSummary;
}

const formatTimestamp = (raw?: string | null): string => {
  if (!raw) return "Unavailable";
  const parsed = new Date(raw);
  if (Number.isNaN(parsed.getTime())) return "Unavailable";
  return parsed.toLocaleString(undefined, {
    year: "numeric",
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
};

export function DatasetBanner({ summary }: DatasetBannerProps) {
  const datasetLabel = summary.dataset_label ?? "No dataset loaded";
  const sourceLabel = summary.dataset_source_label ?? summary.dataset_source ?? "Unknown";
  const recordCount = summary.dataset_record_count ?? 0;

  return (
    <GlowCard className="p-5">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="text-xs uppercase tracking-[0.24em] text-slate-500">Dataset Context</p>
          <h2 className="mt-2 text-2xl font-semibold text-slate-900">{datasetLabel}</h2>
          <p className="mt-1 text-sm text-slate-600">Dataset scoping is enforced for recommendations.</p>
        </div>
        <NeonBadge tone="indigo">{sourceLabel}</NeonBadge>
      </div>

      <div className="mt-4 grid gap-3 md:grid-cols-3">
        <div className="rounded-xl border border-slate-200 bg-white px-4 py-3">
          <p className="text-xs uppercase tracking-wide text-slate-500">Source</p>
          <p className="mt-1 text-sm font-semibold text-slate-900">{sourceLabel}</p>
        </div>
        <div className="rounded-xl border border-slate-200 bg-white px-4 py-3">
          <p className="text-xs uppercase tracking-wide text-slate-500">Records</p>
          <p className="mt-1 text-sm font-semibold text-slate-900">{recordCount.toLocaleString()}</p>
        </div>
        <div className="rounded-xl border border-slate-200 bg-white px-4 py-3">
          <p className="text-xs uppercase tracking-wide text-slate-500">Timestamp</p>
          <p className="mt-1 text-sm font-semibold text-slate-900">{formatTimestamp(summary.dataset_created_at)}</p>
        </div>
      </div>
    </GlowCard>
  );
}
