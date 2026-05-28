"use client";

import { motion } from "framer-motion";
import { useEffect, useMemo, useState } from "react";

interface FloatingKpiProps {
  label: string;
  value: number;
  subtitle: string;
  prefix?: string;
  suffix?: string;
  decimals?: number;
  delay?: number;
  tone?: "indigo" | "emerald" | "violet";
}

export function FloatingKpi({
  label,
  value,
  subtitle,
  prefix = "",
  suffix = "",
  decimals = 0,
  delay = 0,
  tone = "indigo",
}: FloatingKpiProps) {
  const [displayValue, setDisplayValue] = useState(0);

  useEffect(() => {
    let frame = 0;
    const durationMs = 1100;
    const start = performance.now();

    const render = (now: number) => {
      const progress = Math.min((now - start) / durationMs, 1);
      const eased = 1 - Math.pow(1 - progress, 3);
      setDisplayValue(value * eased);
      if (progress < 1) {
        frame = window.requestAnimationFrame(render);
      }
    };

    frame = window.requestAnimationFrame(render);
    return () => window.cancelAnimationFrame(frame);
  }, [value]);

  const toneClass = useMemo(() => {
    if (tone === "emerald") {
      return "shadow-[0_12px_26px_rgba(15,118,110,0.18)] border-teal-200/80";
    }
    if (tone === "violet") {
      return "shadow-[0_12px_26px_rgba(217,119,6,0.18)] border-amber-200/80";
    }
    return "shadow-[0_12px_26px_rgba(37,99,235,0.18)] border-blue-200/80";
  }, [tone]);

  return (
    <motion.article
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.42, ease: "easeOut", delay }}
      whileHover={{ y: -4 }}
      className={`rounded-2xl border border-gray-200 bg-white p-5 shadow-sm ${toneClass}`}
    >
      <p className="text-xs uppercase tracking-[0.18em] text-slate-500">{label}</p>
      <p className="mt-3 text-3xl font-semibold text-slate-900 md:text-4xl">
        {prefix}
        {displayValue.toFixed(decimals)}
        {suffix}
      </p>
      <p className="mt-2 text-sm text-slate-600">{subtitle}</p>
    </motion.article>
  );
}
