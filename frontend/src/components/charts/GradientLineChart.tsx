interface GradientLineChartProps {
  points: number[];
  className?: string;
}

export function GradientLineChart({ points, className = "" }: GradientLineChartProps) {
  if (points.length === 0) {
    return <div className={`rounded-xl border border-slate-200 bg-white p-4 text-sm text-slate-500 ${className}`}>No chart data</div>;
  }

  const max = Math.max(...points);
  const min = Math.min(...points);
  const range = Math.max(max - min, 1);
  const width = 420;
  const height = 140;

  const d = points
    .map((point, index) => {
      const x = (index / Math.max(points.length - 1, 1)) * width;
      const y = height - ((point - min) / range) * height;
      return `${index === 0 ? "M" : "L"}${x.toFixed(2)} ${y.toFixed(2)}`;
    })
    .join(" ");

  return (
    <div className={`rounded-2xl border border-slate-200 bg-white p-4 shadow-sm ${className}`}>
      <svg viewBox={`0 0 ${width} ${height}`} className="h-36 w-full" aria-hidden="true">
        <defs>
          <linearGradient id="line-gradient" x1="0" y1="0" x2="1" y2="0">
            <stop offset="0%" stopColor="#2563eb" />
            <stop offset="100%" stopColor="#0f766e" />
          </linearGradient>
        </defs>
        <path d={d} fill="none" stroke="url(#line-gradient)" strokeWidth="3" strokeLinecap="round" />
      </svg>
    </div>
  );
}
