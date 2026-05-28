"use client";

import { useEffect, useMemo, useState } from "react";

import { PageState } from "@/components/PageState";
import { ProtectedView } from "@/components/ProtectedView";
import { ModeBanner } from "@/components/dashboard/ModeBanner";
import {
  fetchDashboardSummary,
  fetchDataTemperature,
  fetchRecommendations,
  fetchUserMigrations,
  getApiErrorMessage,
} from "@/lib/api";
import type {
  DashboardSummary,
  DataTemperature,
  Recommendation,
  UserMigration,
} from "@/lib/types";

const hasRiskSignature = (item: Recommendation) =>
  item.operational_readiness < 0.8 ||
  item.execution_eligibility !== "EXECUTABLE" ||
  item.rule_override_trace.some((trace) => {
    const lower = trace.toLowerCase();
    return lower.includes("guardrail") || lower.includes("fallback") || lower.includes("blocked");
  });

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

const formatCompactNumber = (value: number) =>
  value >= 1000 ? value.toLocaleString() : value.toFixed(0);

const formatDate = (raw: string) => {
  const parsed = new Date(raw);
  if (Number.isNaN(parsed.getTime())) return "-";
  return parsed.toLocaleDateString(undefined, {
    month: "short",
    day: "2-digit",
  });
};

export default function DashboardPage() {
  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [temperature, setTemperature] = useState<DataTemperature | null>(null);
  const [recommendations, setRecommendations] = useState<Recommendation[]>([]);
  const [migrations, setMigrations] = useState<UserMigration[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const run = async () => {
      setLoading(true);
      setError(null);
      try {
        const [summaryData, recommendationsData, temperatureData, migrationsData] =
          await Promise.allSettled([
            fetchDashboardSummary(),
            fetchRecommendations(),
            fetchDataTemperature(),
            fetchUserMigrations(),
          ]);
        const warnings: string[] = [];
        if (summaryData.status === "fulfilled") setSummary(summaryData.value);
        else warnings.push("Summary unavailable");
        if (recommendationsData.status === "fulfilled") setRecommendations(recommendationsData.value);
        else warnings.push("Recommendations delayed");
        if (temperatureData.status === "fulfilled") setTemperature(temperatureData.value);
        else warnings.push("Data temperature unavailable");
        if (migrationsData.status === "fulfilled") setMigrations(migrationsData.value);
        else warnings.push("Migration history unavailable");
        if (warnings.length > 0) {
          setError(warnings.join(" • "));
        }
      } catch (err: unknown) {
        setError(getApiErrorMessage(err));
      } finally {
        setLoading(false);
      }
    };

    void run();
  }, []);

  const temperatureCounts = useMemo(() => {
    if (!temperature) {
      return { hot: 0, warm: 0, cold: 0, archive: 0, total: 0 };
    }
    const warm = temperature.warm_count ?? 0;
    const total = temperature.hot_count + warm + temperature.cold_count + temperature.archive_count;
    return {
      hot: temperature.hot_count,
      warm,
      cold: temperature.cold_count,
      archive: temperature.archive_count,
      total,
    };
  }, [temperature]);

  const riskyCount = useMemo(() => recommendations.filter(hasRiskSignature).length, [recommendations]);

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

  const readinessTone =
    readiness.band === "READY" ? "text-emerald-700" : readiness.band === "CONDITIONAL" ? "text-blue-700" : "text-rose-700";

  const providerStats = useMemo(() => {
    const providers: Array<"AWS" | "AZURE" | "GCP"> = ["AWS", "AZURE", "GCP"];
    return providers.map((provider) => {
      const items = recommendations.filter((item) => item.current_provider.toUpperCase() === provider);
      const executionReady = items.filter((item) => item.execution_eligibility === "EXECUTABLE").length;
      const approvalRequired = items.filter((item) => item.execution_eligibility === "DRY_RUN_ELIGIBLE").length;
      const blocked = items.filter((item) => item.execution_eligibility === "NONE").length;
      return { provider, total: items.length, executionReady, approvalRequired, blocked };
    });
  }, [recommendations]);

  const temperaturePercentages = useMemo(() => {
    if (!temperature || temperatureCounts.total === 0) return { hot: 0, warm: 0, cold: 0, archive: 0 };
    return {
      hot: (temperatureCounts.hot / temperatureCounts.total) * 100,
      warm: (temperatureCounts.warm / temperatureCounts.total) * 100,
      cold: (temperatureCounts.cold / temperatureCounts.total) * 100,
      archive: (temperatureCounts.archive / temperatureCounts.total) * 100,
    };
  }, [temperature, temperatureCounts]);

  const topSavings = useMemo(() => {
    if (recommendations.length === 0) return null;
    return recommendations.reduce((best, item) =>
      item.estimated_monthly_savings > (best?.estimated_monthly_savings ?? -Infinity) ? item : best,
    );
  }, [recommendations]);

  const coolingCandidate = useMemo(() => {
    const candidates = recommendations.filter((item) => {
      const tier = item.recommended_tier.toUpperCase();
      return tier.includes("ARCHIVE") || tier.includes("GLACIER") || tier.includes("COLD");
    });
    if (candidates.length === 0) return null;
    return candidates.reduce((best, item) =>
      item.estimated_monthly_savings > (best?.estimated_monthly_savings ?? -Infinity) ? item : best,
    );
  }, [recommendations]);

  const idleDaysEstimate = (value?: number | null) => {
    if (value === null || value === undefined || Number.isNaN(value)) return null;
    const clamped = Math.min(Math.max(value, 0), 1);
    return Math.max(0, Math.round((1 - clamped) * 90));
  };

  const recentRecommendations = useMemo(() => {
    return [...recommendations]
      .sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime())
      .slice(0, 5);
  }, [recommendations]);

  const recentMigrations = useMemo(() => {
    return [...migrations]
      .sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime())
      .slice(0, 5);
  }, [migrations]);

  return (
    <ProtectedView>
      <div className="relative min-h-screen overflow-x-clip bg-slate-50 text-slate-900">
        <div className="pointer-events-none absolute -right-56 top-0 h-72 w-72 rounded-full bg-blue-200/40 blur-[120px]" />
        <div className="pointer-events-none absolute -left-40 top-48 h-72 w-72 rounded-full bg-cyan-200/40 blur-[130px]" />

        <main className="relative mx-auto w-full max-w-7xl px-6 py-8">
          {loading ? <PageState title="Loading dashboard" message="Fetching your cloud cost intelligence..." /> : null}
          {!loading && !summary ? <PageState title="Failed to load dashboard" message={error ?? "Try again."} /> : null}

          {!loading && summary && temperature ? (
            <div className="space-y-8">
              {error ? (
                <section className="rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-700">
                  Partial data loaded: {error}
                </section>
              ) : null}

              <section className="flex flex-wrap items-center justify-between gap-4">
                <div>
                  <p className="text-xs uppercase tracking-[0.25em] text-slate-500">Overview</p>
                  <h1 className="mt-2 text-2xl font-semibold text-slate-900">Cloud Intelligence Dashboard</h1>
                  <p className="mt-1 text-sm text-slate-600">
                    Executive view of spend, optimization opportunity, and operational readiness.
                  </p>
                </div>
              </section>

              <ModeBanner summary={summary} recommendationCount={recommendations.length} riskyCount={riskyCount} />

              <section className="grid gap-6 md:grid-cols-2 xl:grid-cols-4">
                <div className="rounded-xl bg-white p-6 shadow-sm">
                  <p className="text-xs uppercase tracking-[0.2em] text-slate-500">Monthly Spend</p>
                  <p className="mt-4 text-3xl font-semibold text-slate-900">
                    ${summary.total_storage_cost.toLocaleString()}
                  </p>
                  <p className="mt-2 text-sm text-slate-500">Baseline storage outlay.</p>
                </div>
                <div className="rounded-xl bg-white p-6 shadow-sm">
                  <p className="text-xs uppercase tracking-[0.2em] text-emerald-600">Estimated Savings</p>
                  <p className="mt-4 text-3xl font-semibold text-emerald-600">
                    ${summary.estimated_monthly_savings.toLocaleString()}
                  </p>
                  <p className="mt-2 text-sm text-slate-500">Optimization opportunity.</p>
                </div>
                <div className="rounded-xl bg-white p-6 shadow-sm">
                  <p className="text-xs uppercase tracking-[0.2em] text-slate-500">Object Footprint</p>
                  <p className="mt-4 text-3xl font-semibold text-slate-900">
                    {temperatureCounts.total.toLocaleString()}
                  </p>
                  <p className="mt-2 text-sm text-slate-500">Active storage objects.</p>
                </div>
                <div className="rounded-xl bg-white p-6 shadow-sm">
                  <p className="text-xs uppercase tracking-[0.2em] text-blue-600">Open Recommendations</p>
                  <p className="mt-4 text-3xl font-semibold text-blue-600">
                    {recommendations.length.toLocaleString()}
                  </p>
                  <p className="mt-2 text-sm text-slate-500">Actionable opportunities.</p>
                </div>
              </section>

              <section className="grid gap-6 lg:grid-cols-2">
                <div className="rounded-xl bg-white p-6 shadow-sm">
                  <div className="flex items-center justify-between">
                    <h2 className="text-lg font-semibold text-slate-900">Storage Temperature</h2>
                    <span className="text-xs text-slate-500">
                      {formatCompactNumber(temperatureCounts.total)} total objects
                    </span>
                  </div>
                  <div className="mt-6 h-3 w-full overflow-hidden rounded-full bg-slate-100">
                    <div className="flex h-full w-full">
                      <div className="h-full bg-red-500" style={{ width: `${temperaturePercentages.hot}%` }} />
                      <div className="h-full bg-orange-500" style={{ width: `${temperaturePercentages.warm}%` }} />
                      <div className="h-full bg-blue-500" style={{ width: `${temperaturePercentages.cold}%` }} />
                      <div className="h-full bg-slate-400" style={{ width: `${temperaturePercentages.archive}%` }} />
                    </div>
                  </div>
                  <div className="mt-5 grid gap-3 text-sm text-slate-600 md:grid-cols-2">
                    <div className="flex items-center justify-between rounded-lg border border-red-100 bg-red-50 px-3 py-2">
                      <span className="flex items-center gap-2">
                        <span className="h-2 w-2 rounded-full bg-red-500" />
                        HOT
                      </span>
                      <span className="font-semibold text-red-600">{temperatureCounts.hot.toLocaleString()}</span>
                    </div>
                    <div className="flex items-center justify-between rounded-lg border border-orange-100 bg-orange-50 px-3 py-2">
                      <span className="flex items-center gap-2">
                        <span className="h-2 w-2 rounded-full bg-orange-500" />
                        WARM
                      </span>
                      <span className="font-semibold text-orange-600">{temperatureCounts.warm.toLocaleString()}</span>
                    </div>
                    <div className="flex items-center justify-between rounded-lg border border-blue-100 bg-blue-50 px-3 py-2">
                      <span className="flex items-center gap-2">
                        <span className="h-2 w-2 rounded-full bg-blue-500" />
                        COLD
                      </span>
                      <span className="font-semibold text-blue-600">{temperatureCounts.cold.toLocaleString()}</span>
                    </div>
                    <div className="flex items-center justify-between rounded-lg border border-slate-200 bg-slate-50 px-3 py-2">
                      <span className="flex items-center gap-2">
                        <span className="h-2 w-2 rounded-full bg-slate-500" />
                        ARCHIVE
                      </span>
                      <span className="font-semibold text-slate-600">{temperatureCounts.archive.toLocaleString()}</span>
                    </div>
                  </div>
                </div>

                <div className="rounded-xl bg-white p-6 shadow-sm">
                  <div className="flex items-center justify-between">
                    <h2 className="text-lg font-semibold text-slate-900">Execution Readiness</h2>
                    <span className={`text-sm font-semibold ${readinessTone}`}>
                      {Math.round(readiness.score * 100)}% {readiness.band}
                    </span>
                  </div>
                  <p className="mt-2 text-sm text-slate-500">
                    Readiness reflects data maturity, billing realism, and execution authority.
                  </p>
                  <div className="mt-6 space-y-4">
                    <ReadinessRow label="Data maturity" value={maturityScore[readiness.dataMaturity ?? "SYNTHETIC_MATURE"]} tone="bg-blue-500" />
                    <ReadinessRow label="Billing realism" value={billingScore[readiness.billingRealism ?? "ESTIMATE"]} tone="bg-emerald-500" />
                    <ReadinessRow label="Execution authority" value={authorityScore[readiness.authority ?? "NONE"]} tone="bg-indigo-500" />
                  </div>
                </div>
              </section>

              <section className="grid gap-6 md:grid-cols-3">
                <div className="rounded-xl bg-white p-6 shadow-sm">
                  <p className="text-xs uppercase tracking-[0.2em] text-slate-500">Top Savings Opportunity</p>
                  <p className="mt-4 text-lg font-semibold text-slate-900">
                    {topSavings ? topSavings.resource_name : "No opportunities yet"}
                  </p>
                  <p className="mt-2 text-2xl font-semibold text-emerald-600">
                    {topSavings ? `$${topSavings.estimated_monthly_savings.toFixed(2)}/mo` : "--"}
                  </p>
                </div>
                <div className="rounded-xl bg-white p-6 shadow-sm">
                  <p className="text-xs uppercase tracking-[0.2em] text-slate-500">Cooling Dataset</p>
                  <p className="mt-4 text-lg font-semibold text-slate-900">
                    {coolingCandidate ? coolingCandidate.resource_name : "Monitoring cooling signals"}
                  </p>
                  <p className="mt-2 text-sm text-slate-600">
                    {coolingCandidate
                      ? `Recommended: ${coolingCandidate.recommended_tier} • Idle ${idleDaysEstimate(
                          coolingCandidate.access_recency_score,
                        ) ?? "—"} days`
                      : "Awaiting cold storage trajectory."}
                  </p>
                </div>
                <div className="rounded-xl bg-white p-6 shadow-sm">
                  <p className="text-xs uppercase tracking-[0.2em] text-slate-500">Guardrail Pressure</p>
                  <p className="mt-4 text-2xl font-semibold text-rose-600">{riskyCount}</p>
                  <p className="mt-2 text-sm text-slate-500">Recommendations requiring approval.</p>
                </div>
              </section>

              <section className="grid gap-6 lg:grid-cols-3">
                {providerStats.map((provider) => (
                  <div key={provider.provider} className="rounded-xl bg-white p-6 shadow-sm">
                    <div className="flex items-center justify-between">
                      <h3 className="text-sm font-semibold text-slate-900">{provider.provider} Readiness</h3>
                      <span className="text-xs text-slate-500">{provider.total} recs</span>
                    </div>
                    <div className="mt-4 grid grid-cols-3 gap-2 text-xs">
                      <div className="rounded-lg border border-emerald-200 bg-emerald-50 px-2 py-1 text-emerald-700">
                        Ready {provider.executionReady}
                      </div>
                      <div className="rounded-lg border border-blue-200 bg-blue-50 px-2 py-1 text-blue-700">
                        Dry Run {provider.approvalRequired}
                      </div>
                      <div className="rounded-lg border border-rose-200 bg-rose-50 px-2 py-1 text-rose-700">
                        Blocked {provider.blocked}
                      </div>
                    </div>
                  </div>
                ))}
              </section>

              <section className="grid gap-6 lg:grid-cols-2">
                <div className="rounded-xl bg-white p-6 shadow-sm">
                  <div className="flex items-center justify-between">
                    <h3 className="text-lg font-semibold text-slate-900">Recent Activity</h3>
                    <span className="text-xs text-slate-500">Latest recommendations</span>
                  </div>
                  {recentRecommendations.length === 0 ? (
                    <p className="mt-4 text-sm text-slate-500">No recent recommendations yet.</p>
                  ) : (
                    <div className="mt-4 space-y-3">
                      {recentRecommendations.map((item) => (
                        <div key={item.id} className="flex items-center justify-between text-sm">
                          <div>
                            <p className="font-semibold text-slate-900">{item.resource_name}</p>
                            <p className="text-xs text-slate-500">
                              {item.current_provider} · {item.current_tier} → {item.recommended_tier}
                            </p>
                          </div>
                          <div className="text-right">
                            <p className="text-sm font-semibold text-emerald-700">
                              ${item.estimated_monthly_savings.toFixed(2)}/mo
                            </p>
                            <p className="text-xs text-slate-500">{formatDate(item.created_at)}</p>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>

                <div className="rounded-xl bg-white p-6 shadow-sm">
                  <div className="flex items-center justify-between">
                    <h3 className="text-lg font-semibold text-slate-900">Migration History</h3>
                    <span className="text-xs text-slate-500">Last 5 jobs</span>
                  </div>
                  {recentMigrations.length === 0 ? (
                    <p className="mt-4 text-sm text-slate-500">No migration activity yet.</p>
                  ) : (
                    <div className="mt-4 space-y-3">
                      {recentMigrations.map((job) => (
                        <div key={job.id} className="flex items-center justify-between text-sm">
                          <div>
                            <p className="font-semibold text-slate-900">{job.resource_name}</p>
                            <p className="text-xs text-slate-500">
                              {job.source_provider} → {job.target_provider}
                            </p>
                          </div>
                          <div className="text-right">
                            <p className="text-sm font-semibold text-slate-900">{job.status}</p>
                            <p className="text-xs text-slate-500">{formatDate(job.created_at)}</p>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </section>
            </div>
          ) : null}
        </main>
      </div>
    </ProtectedView>
  );
}

function ReadinessRow({ label, value, tone }: { label: string; value: number; tone: string }) {
  const percent = Math.round(Math.min(Math.max(value, 0), 1) * 100);
  return (
    <div>
      <div className="flex items-center justify-between text-sm text-slate-600">
        <span>{label}</span>
        <span className="font-semibold text-slate-900">{percent}%</span>
      </div>
      <div className="mt-2 h-2 w-full rounded-full bg-slate-100">
        <div className={`h-2 rounded-full ${tone}`} style={{ width: `${percent}%` }} />
      </div>
    </div>
  );
}
