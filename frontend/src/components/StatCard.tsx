import type { ReactNode } from "react";

interface StatCardProps {
  title: string;
  value: string;
  subtitle?: string;
  accent?: ReactNode;
}

export function StatCard({ title, value, subtitle, accent }: StatCardProps) {
  return (
    <article className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
      <p className="text-xs uppercase tracking-[0.18em] text-slate-500">{title}</p>
      <div className="mt-3 flex items-end justify-between gap-2">
        <p className="text-2xl font-semibold text-slate-900">{value}</p>
        {accent}
      </div>
      {subtitle ? <p className="mt-2 text-sm text-slate-600">{subtitle}</p> : null}
    </article>
  );
}
