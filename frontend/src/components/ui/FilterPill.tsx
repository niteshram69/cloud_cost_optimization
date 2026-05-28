interface FilterPillProps {
  label: string;
  active?: boolean;
  count?: number;
  onClick: () => void;
}

export function FilterPill({ label, active = false, count, onClick }: FilterPillProps) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`inline-flex items-center gap-2 rounded-full border px-4 py-1.5 text-xs font-semibold tracking-[0.08em] uppercase transition ${
        active
          ? "border-blue-200 bg-blue-50 text-blue-700 shadow-[0_10px_24px_rgba(37,99,235,0.14)]"
          : "border-slate-200 bg-white text-slate-600 hover:border-blue-200 hover:text-slate-900"
      }`}
    >
      <span>{label}</span>
      {typeof count === "number" ? (
        <span className="rounded-full border border-current/40 px-1.5 py-0.5 text-[10px]">{count}</span>
      ) : null}
    </button>
  );
}
