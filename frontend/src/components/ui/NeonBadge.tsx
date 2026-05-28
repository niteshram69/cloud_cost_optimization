import type { ReactNode } from "react";

type BadgeTone = "indigo" | "emerald" | "violet" | "rose";

interface NeonBadgeProps {
  children: ReactNode;
  tone?: BadgeTone;
}

const toneClass: Record<BadgeTone, string> = {
  indigo: "border-blue-200 bg-blue-50 text-blue-700 shadow-[0_8px_18px_rgba(37,99,235,0.16)]",
  emerald: "border-teal-200 bg-teal-50 text-teal-700 shadow-[0_8px_18px_rgba(15,118,110,0.16)]",
  violet: "border-amber-200 bg-amber-50 text-amber-700 shadow-[0_8px_18px_rgba(217,119,6,0.16)]",
  rose: "border-rose-200 bg-rose-50 text-rose-700 shadow-[0_8px_18px_rgba(225,29,72,0.16)]",
};

export function NeonBadge({ children, tone = "indigo" }: NeonBadgeProps) {
  return (
    <span
      className={`inline-flex items-center gap-2 rounded-full border px-3 py-1 text-xs font-semibold tracking-[0.08em] uppercase ${toneClass[tone]}`}
    >
      {children}
    </span>
  );
}
