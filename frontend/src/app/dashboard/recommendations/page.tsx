"use client";

import { useEffect, useMemo, useState } from "react";

import { PageState } from "@/components/PageState";
import { ProtectedView } from "@/components/ProtectedView";
import { DatasetBanner } from "@/components/dashboard/DatasetBanner";
import { RecommendationTable } from "@/components/dashboard/RecommendationTable";
import { FilterPill } from "@/components/ui/FilterPill";
import { GlowCard } from "@/components/ui/GlowCard";
import { NeonBadge } from "@/components/ui/NeonBadge";
import {
  authorizeMigration,
  fetchDashboardSummary,
  fetchGroupedRecommendations,
  fetchRecommendations,
  fetchRecommendationSummary,
  fetchUserMigrations,
  getApiErrorMessage,
} from "@/lib/api";
import type {
  DashboardSummary,
  GroupedRecommendation,
  Recommendation,
  RecommendationSummary,
  UserMigration,
} from "@/lib/types";

type FocusFilter = "ALL" | "SAVINGS" | "RISK";

type RiskAcknowledgement = "LATENCY" | "RETRIEVAL_COST" | "MANUAL_OVERRIDE";

const REQUIRED_RISKS: RiskAcknowledgement[] = ["LATENCY", "RETRIEVAL_COST"];

const hasRiskSignature = (item: Recommendation) =>
  item.operational_readiness < 0.8 ||
  item.execution_eligibility !== "EXECUTABLE" ||
  item.rule_override_trace.some((trace) => {
    const lower = trace.toLowerCase();
    return lower.includes("guardrail") || lower.includes("fallback") || lower.includes("blocked");
  });

const requiresRiskAuthorization = (item: Recommendation): boolean =>
  item.execution_eligibility === "EXECUTABLE" &&
  (item.confidence_final < 0.8 || item.decision_state !== "PREDICTED" || item.operational_readiness_band !== "READY");

const isExecutionForbidden = (item: Recommendation): boolean =>
  item.execution_eligibility === "NONE";

const riskLevelLabel = (confidence: number): string => {
  if (confidence < 0.5) return "HIGH";
  if (confidence < 0.8) return "MEDIUM";
  return "LOW";
};

const temperatureTone = (tier: string): string => {
  switch (tier.toUpperCase()) {
    case "HOT":
      return "border-rose-200 bg-rose-50 text-rose-700";
    case "WARM":
      return "border-amber-200 bg-amber-50 text-amber-700";
    case "COLD":
      return "border-blue-200 bg-blue-50 text-blue-700";
    case "ARCHIVE":
      return "border-slate-200 bg-slate-100 text-slate-600";
    default:
      return "border-slate-200 bg-slate-50 text-slate-500";
  }
};

const riskBand = (risk: number): "LOW" | "MEDIUM" | "HIGH" => {
  if (risk >= 0.6) return "HIGH";
  if (risk >= 0.3) return "MEDIUM";
  return "LOW";
};

const riskTone = (risk: number | string): string => {
  if (typeof risk === "string") {
    const band = risk.toUpperCase();
    if (band === "HIGH") return "border-rose-200 bg-rose-50 text-rose-700";
    if (band === "MEDIUM") return "border-amber-200 bg-amber-50 text-amber-700";
    return "border-emerald-200 bg-emerald-50 text-emerald-700";
  }
  const band = riskBand(risk);
  if (band === "HIGH") return "border-rose-200 bg-rose-50 text-rose-700";
  if (band === "MEDIUM") return "border-amber-200 bg-amber-50 text-amber-700";
  return "border-emerald-200 bg-emerald-50 text-emerald-700";
};

const extractMlPredictionTier = (item: Recommendation): string => {
  const line = item.rule_override_trace.find((trace) => trace.toLowerCase().startsWith("ml prediction:"));
  if (!line) return item.recommended_tier;
  const raw = line.split(":", 2)[1]?.trim() ?? item.recommended_tier;
  const parts = raw.split(/\s+/).filter(Boolean);
  return parts.length > 1 ? parts.slice(1).join(" ") : raw;
};

const isCompletedStatus = (status: string) =>
  ["COMPLETED", "ROLLED_BACK", "FAILED", "CANCELLED"].includes(status.toUpperCase());

const clamp = (value: number, min = 0, max = 1) => Math.min(Math.max(value, min), max);

const formatMoney = (value?: number | null) => {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return `$${value.toFixed(2)}/mo`;
};

export default function RecommendationsPage() {
  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [recommendations, setRecommendations] = useState<Recommendation[]>([]);
  const [groupedRecommendations, setGroupedRecommendations] = useState<GroupedRecommendation[]>([]);
  const [migrations, setMigrations] = useState<UserMigration[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [focusFilter, setFocusFilter] = useState<FocusFilter>("ALL");
  const [activeGroup, setActiveGroup] = useState<GroupedRecommendation | null>(null);
  const [executingResourceId, setExecutingResourceId] = useState<string | null>(null);
  const [actionMessage, setActionMessage] = useState<string | null>(null);
  const [modalRecommendation, setModalRecommendation] = useState<Recommendation | null>(null);
  const [modalError, setModalError] = useState<string | null>(null);
  const [summaryItem, setSummaryItem] = useState<RecommendationSummary | null>(null);
  const [summaryLoading, setSummaryLoading] = useState(false);
  const [summaryError, setSummaryError] = useState<string | null>(null);
  const [overrideJustification, setOverrideJustification] = useState("");
  const [riskChecks, setRiskChecks] = useState<Record<RiskAcknowledgement, boolean>>({
    LATENCY: false,
    RETRIEVAL_COST: false,
    MANUAL_OVERRIDE: false,
  });
  const [traceItem, setTraceItem] = useState<Recommendation | null>(null);
  const [bulkStatus, setBulkStatus] = useState<string | null>(null);

  useEffect(() => {
    const run = async () => {
      setLoading(true);
      setError(null);
      try {
        const [summaryData, recsData, groupedData, migrationsData] = await Promise.allSettled([
          fetchDashboardSummary(),
          fetchRecommendations(),
          fetchGroupedRecommendations(),
          fetchUserMigrations(),
        ]);
        const warnings: string[] = [];
        if (summaryData.status === "fulfilled") setSummary(summaryData.value);
        else warnings.push("Summary unavailable");
        if (recsData.status === "fulfilled") setRecommendations(recsData.value);
        else warnings.push("Recommendations unavailable");
        if (groupedData.status === "fulfilled") setGroupedRecommendations(groupedData.value);
        else warnings.push("Grouped recommendations unavailable");
        if (migrationsData.status === "fulfilled") setMigrations(migrationsData.value);
        else warnings.push("Execution jobs unavailable");

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

  const filteredRecommendations = useMemo(() => {
    let items = recommendations;
    if (activeGroup) {
      items = items.filter(
        (item) =>
          item.recommended_provider === activeGroup.recommended_provider &&
          item.recommended_tier === activeGroup.recommended_tier,
      );
    }
    if (focusFilter === "SAVINGS") {
      return items.filter((item) => item.estimated_monthly_savings >= 100);
    }
    if (focusFilter === "RISK") {
      return items.filter(hasRiskSignature);
    }
    return items;
  }, [activeGroup, focusFilter, recommendations]);

  const activeJobs = useMemo(
    () => migrations.filter((job) => !isCompletedStatus(job.status)),
    [migrations],
  );
  const historyJobs = useMemo(
    () => migrations.filter((job) => isCompletedStatus(job.status)),
    [migrations],
  );
  const summaryOpen = summaryLoading || summaryItem !== null || summaryError !== null;

  const closeRiskModal = () => {
    setModalRecommendation(null);
    setModalError(null);
    setOverrideJustification("");
    setRiskChecks({
      LATENCY: false,
      RETRIEVAL_COST: false,
      MANUAL_OVERRIDE: false,
    });
  };

  const executeMigration = async (
    item: Recommendation,
    options: { overrideConfidence: boolean; acknowledgedRisks: RiskAcknowledgement[]; justification?: string },
  ) => {
    setExecutingResourceId(item.resource_name);
    setActionMessage(null);
    try {
      const result = await authorizeMigration({
        recommendation_id: item.id,
        resource_id: item.resource_name,
        approved_target_tier: item.recommended_tier,
        override_confidence: options.overrideConfidence,
        override_type: options.overrideConfidence ? "USER_CONFIRMED" : undefined,
        justification: options.justification,
        acknowledged_risks: options.acknowledgedRisks,
      });

      setActionMessage(`${result.execution_result}: ${result.message}`);
    } catch (err: unknown) {
      setActionMessage(getApiErrorMessage(err));
      throw err;
    } finally {
      setExecutingResourceId(null);
    }
  };

  const handleDryRun = async (item: Recommendation) => {
    if (isExecutionForbidden(item)) return;
    await executeMigration(item, {
      overrideConfidence: false,
      acknowledgedRisks: [],
    });
  };

  const handleViewSummary = async (item: Recommendation) => {
    setSummaryLoading(true);
    setSummaryError(null);
    setSummaryItem(null);
    try {
      const data = await fetchRecommendationSummary(item.resource_name);
      setSummaryItem(data);
    } catch (err: unknown) {
      setSummaryError(getApiErrorMessage(err));
    } finally {
      setSummaryLoading(false);
    }
  };

  const closeSummaryModal = () => {
    setSummaryItem(null);
    setSummaryError(null);
    setSummaryLoading(false);
  };

  const handleApprove = async (item: Recommendation) => {
    if (item.execution_eligibility !== "EXECUTABLE") return;
    if (requiresRiskAuthorization(item)) {
      setModalRecommendation(item);
      setModalError(null);
      setOverrideJustification("");
      setRiskChecks({
        LATENCY: false,
        RETRIEVAL_COST: false,
        MANUAL_OVERRIDE: false,
      });
      return;
    }

    await executeMigration(item, {
      overrideConfidence: false,
      acknowledgedRisks: [],
    });
  };

  const handleAuthorizeFromModal = async () => {
    if (!modalRecommendation) return;
    const acknowledgedRisks = REQUIRED_RISKS.filter((risk) => riskChecks[risk]);
    if (acknowledgedRisks.length !== REQUIRED_RISKS.length) {
      setModalError("All risk acknowledgements are required before approval.");
      return;
    }
    if (!overrideJustification.trim()) {
      setModalError("Business justification is required for manual override.");
      return;
    }

    setModalError(null);
    await executeMigration(modalRecommendation, {
      overrideConfidence: true,
      acknowledgedRisks,
      justification: overrideJustification.trim(),
    });
    closeRiskModal();
  };

  const handleGroupReview = (group: GroupedRecommendation) => {
    setActiveGroup(group);
  };

  const handleGroupDryRun = async (group: GroupedRecommendation) => {
    const candidates = recommendations.filter(
      (item) =>
        item.recommended_provider === group.recommended_provider &&
        item.recommended_tier === group.recommended_tier &&
        item.execution_eligibility !== "NONE",
    );

    if (candidates.length === 0) {
      setBulkStatus("No eligible recommendations found for this group.");
      return;
    }

    setBulkStatus(`Running dry-run for ${candidates.length} recommendations...`);
    const results = await Promise.allSettled(
      candidates.map((item) =>
        authorizeMigration({
          recommendation_id: item.id,
          resource_id: item.resource_name,
          approved_target_tier: item.recommended_tier,
          override_confidence: false,
          acknowledged_risks: [],
        }),
      ),
    );
    const success = results.filter((result) => result.status === "fulfilled").length;
    const failed = results.length - success;
    setBulkStatus(`Dry-run submitted: ${success} succeeded, ${failed} failed.`);
  };

  return (
    <ProtectedView>
      <div className="relative min-h-screen bg-slate-50 text-slate-900">
        <div className="pointer-events-none absolute -right-40 top-0 h-64 w-64 rounded-full bg-blue-200/40 blur-[110px]" />
        <div className="pointer-events-none absolute -left-32 top-72 h-64 w-64 rounded-full bg-cyan-200/40 blur-[120px]" />
        <main className="relative mx-auto w-full max-w-7xl px-6 py-8">
          {loading ? <PageState title="Loading recommendations" message="Preparing operational data..." /> : null}
          {!loading && !summary ? <PageState title="Unable to load" message={error ?? "Try again."} /> : null}

          {!loading && summary ? (
            <div className="space-y-8">
              {error ? (
                <section className="rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-700">
                  Partial data loaded: {error}
                </section>
              ) : null}

              <section>
                <p className="text-xs uppercase tracking-[0.25em] text-slate-500">Recommendations</p>
                <h1 className="mt-2 text-2xl font-semibold text-slate-900">Optimization Command Center</h1>
                <p className="mt-1 text-sm text-slate-600">
                  Review, simulate, and approve storage tier changes with full operational context.
                </p>
              </section>

              <DatasetBanner summary={summary} />

              <section className="grid gap-6 md:grid-cols-3">
                <GlowCard className="p-6">
                  <p className="text-xs uppercase tracking-[0.2em] text-blue-600">Open Recommendations</p>
                  <p className="mt-4 text-3xl font-semibold text-slate-900">{recommendations.length}</p>
                  <p className="mt-2 text-sm text-slate-500">Operational decisions ready for review.</p>
                </GlowCard>
                <GlowCard className="p-6">
                  <p className="text-xs uppercase tracking-[0.2em] text-green-600">Estimated Savings</p>
                  <p className="mt-4 text-3xl font-semibold text-green-600">
                    ${summary.estimated_monthly_savings.toLocaleString()}
                  </p>
                  <p className="mt-2 text-sm text-slate-500">Potential monthly impact.</p>
                </GlowCard>
                <GlowCard className="p-6">
                  <p className="text-xs uppercase tracking-[0.2em] text-rose-600">Guardrail-Sensitive</p>
                  <p className="mt-4 text-3xl font-semibold text-rose-600">
                    {recommendations.filter(hasRiskSignature).length}
                  </p>
                  <p className="mt-2 text-sm text-slate-500">Require explicit approval.</p>
                </GlowCard>
              </section>

              <GlowCard className="p-6">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div>
                    <h2 className="text-lg font-semibold text-slate-900">Recommendation Groups</h2>
                    <p className="text-sm text-slate-500">Clustered opportunities for portfolio actions.</p>
                  </div>
                  <NeonBadge tone="indigo">{groupedRecommendations.length} groups</NeonBadge>
                </div>

                {groupedRecommendations.length === 0 ? (
                  <p className="mt-4 text-sm text-slate-500">No groups available yet.</p>
                ) : (
                  <div className="mt-4 grid gap-3">
                    {groupedRecommendations.map((group) => (
                      <div key={group.group_key} className="rounded-xl border border-slate-200 bg-white p-4">
                        <div className="flex flex-wrap items-center justify-between gap-3">
                          <div>
                            <p className="text-sm font-semibold text-slate-900">
                              {group.dataset_count} {group.data_temperature} datasets → {group.recommended_tier}
                            </p>
                            <p className="mt-1 text-xs text-slate-500">
                              Estimated Savings: ${group.total_monthly_savings.toFixed(2)}/month
                            </p>
                          </div>
                          <div className="flex flex-wrap gap-2">
                            <button
                              type="button"
                              onClick={() => handleGroupReview(group)}
                              className="rounded-full border border-slate-200 px-3 py-1 text-xs font-semibold text-slate-700 hover:border-slate-300 hover:bg-slate-50"
                            >
                              Review Group
                            </button>
                            <button
                              type="button"
                              onClick={() => void handleGroupDryRun(group)}
                              className="rounded-full border border-blue-200 px-3 py-1 text-xs font-semibold text-blue-700 hover:border-blue-300 hover:bg-blue-50"
                            >
                              Run Dry Run
                            </button>
                          </div>
                        </div>
                        <div className="mt-2 text-xs text-slate-500">
                          Avg ${group.avg_monthly_savings.toFixed(2)} / dataset · Risk {group.risk_level}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
                {bulkStatus ? <p className="mt-3 text-xs text-slate-600">{bulkStatus}</p> : null}
              </GlowCard>

              <GlowCard className="p-6">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div>
                    <h2 className="text-lg font-semibold text-slate-900">All Recommendations</h2>
                    <p className="text-sm text-slate-500">Operational decision table.</p>
                  </div>
                  <div className="flex flex-wrap items-center gap-2">
                    {activeGroup ? (
                      <button
                        type="button"
                        onClick={() => setActiveGroup(null)}
                        className="rounded-full border border-slate-200 px-3 py-1 text-xs font-semibold text-slate-700 hover:border-slate-300 hover:bg-slate-50"
                      >
                        Clear Group Filter
                      </button>
                    ) : null}
                    <FilterPill
                      label="All"
                      count={recommendations.length}
                      active={focusFilter === "ALL"}
                      onClick={() => setFocusFilter("ALL")}
                    />
                    <FilterPill
                      label="Savings"
                      count={recommendations.filter((item) => item.estimated_monthly_savings >= 100).length}
                      active={focusFilter === "SAVINGS"}
                      onClick={() => setFocusFilter("SAVINGS")}
                    />
                    <FilterPill
                      label="Risk"
                      count={recommendations.filter(hasRiskSignature).length}
                      active={focusFilter === "RISK"}
                      onClick={() => setFocusFilter("RISK")}
                    />
                  </div>
                </div>
                {actionMessage ? (
                  <p className="mt-3 rounded-lg border border-blue-100 bg-blue-50 px-3 py-2 text-xs text-blue-700">
                    {actionMessage}
                  </p>
                ) : null}
                <RecommendationTable
                  items={filteredRecommendations}
                  onDryRun={handleDryRun}
                  onViewSummary={handleViewSummary}
                />
              </GlowCard>

              <GlowCard className="p-6">
                <div className="flex items-center justify-between">
                  <h2 className="text-lg font-semibold text-slate-900">Execution Jobs</h2>
                  <span className="text-sm text-slate-500">{activeJobs.length} running</span>
                </div>
                {activeJobs.length === 0 ? (
                  <p className="mt-4 text-sm text-slate-500">No active execution jobs.</p>
                ) : (
                  <div className="mt-4 overflow-x-auto rounded-xl border border-slate-200 bg-slate-50">
                    <table className="min-w-full text-left text-sm">
                      <thead className="text-xs uppercase tracking-wide text-slate-500">
                        <tr>
                          <th className="px-3 py-2">Resource</th>
                          <th className="px-3 py-2">Route</th>
                          <th className="px-3 py-2">Status</th>
                          <th className="px-3 py-2">Progress</th>
                          <th className="px-3 py-2">Risk</th>
                        </tr>
                      </thead>
                      <tbody>
                        {activeJobs.map((job) => (
                          <tr key={job.id} className="border-t border-slate-200 text-slate-700">
                            <td className="px-3 py-2">{job.resource_name}</td>
                            <td className="px-3 py-2">
                              {job.source_provider} → {job.target_provider}
                            </td>
                            <td className="px-3 py-2">{job.status}</td>
                            <td className="px-3 py-2">{job.progress_percent}%</td>
                            <td className="px-3 py-2">{(job.risk_score * 100).toFixed(1)}%</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </GlowCard>

              <GlowCard className="p-6">
                <div className="flex items-center justify-between">
                  <h2 className="text-lg font-semibold text-slate-900">Migration History</h2>
                  <span className="text-sm text-slate-500">{historyJobs.length} records</span>
                </div>
                {historyJobs.length === 0 ? (
                  <p className="mt-4 text-sm text-slate-500">No completed migrations yet.</p>
                ) : (
                  <div className="mt-4 overflow-x-auto rounded-xl border border-slate-200 bg-slate-50">
                    <table className="min-w-full text-left text-sm">
                      <thead className="text-xs uppercase tracking-wide text-slate-500">
                        <tr>
                          <th className="px-3 py-2">Resource</th>
                          <th className="px-3 py-2">Route</th>
                          <th className="px-3 py-2">Before</th>
                          <th className="px-3 py-2">After</th>
                          <th className="px-3 py-2">Result</th>
                        </tr>
                      </thead>
                      <tbody>
                        {historyJobs.map((job) => (
                          <tr key={job.id} className="border-t border-slate-200 text-slate-700">
                            <td className="px-3 py-2">{job.resource_name}</td>
                            <td className="px-3 py-2">
                              {job.source_provider} → {job.target_provider}
                            </td>
                            <td className="px-3 py-2">${job.before_monthly_cost.toFixed(2)}</td>
                            <td className="px-3 py-2">${job.after_monthly_cost.toFixed(2)}</td>
                            <td className="px-3 py-2">{job.status}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </GlowCard>
            </div>
          ) : null}

          {summaryOpen ? (
            <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 px-4">
              <div className="w-full max-w-3xl rounded-2xl border border-slate-200 bg-white p-6 shadow-[0_18px_50px_rgba(15,23,42,0.2)]">
                <div className="flex items-center justify-between gap-3">
                  <div>
                    <h3 className="text-lg font-semibold text-slate-900">Recommendation Summary</h3>
                    <p className="text-xs text-slate-500">
                      {summaryItem ? summaryItem.resource_id : "Loading resource details..."}
                    </p>
                  </div>
                  <button
                    type="button"
                    onClick={closeSummaryModal}
                    className="text-sm text-slate-500 hover:text-slate-700"
                  >
                    Close
                  </button>
                </div>

                {summaryLoading ? (
                  <p className="mt-4 text-sm text-slate-600">Loading summary...</p>
                ) : summaryError ? (
                  <p className="mt-4 text-sm text-rose-700">{summaryError}</p>
                ) : summaryItem ? (
                  <div className="mt-6 space-y-6">
                    <section className="rounded-xl border border-slate-200 bg-slate-50 p-4">
                      <div className="flex flex-wrap items-center justify-between gap-3">
                        <div>
                          <p className="text-xs uppercase tracking-[0.2em] text-slate-500">Resource Overview</p>
                          <h4 className="mt-2 text-lg font-semibold text-slate-900">{summaryItem.resource_id}</h4>
                        </div>
                        <span
                          className={`inline-flex items-center rounded-full border px-3 py-1 text-xs font-semibold ${temperatureTone(
                            summaryItem.classification,
                          )}`}
                        >
                          {summaryItem.classification}
                        </span>
                      </div>
                      <div className="mt-4 grid gap-3 text-sm text-slate-600 md:grid-cols-3">
                        <div>
                          <p className="text-xs uppercase tracking-wide text-slate-400">Provider</p>
                          <p className="mt-1 font-semibold text-slate-900">{summaryItem.provider}</p>
                        </div>
                        <div>
                          <p className="text-xs uppercase tracking-wide text-slate-400">Execution</p>
                          <p className="mt-1 font-semibold text-slate-900">{summaryItem.execution_eligibility}</p>
                        </div>
                        <div>
                          <p className="text-xs uppercase tracking-wide text-slate-400">Tier Change</p>
                          <div className="mt-2 flex flex-wrap items-center gap-2 text-xs">
                            <span className="rounded-full border border-slate-200 bg-white px-3 py-1 font-semibold text-slate-600">
                              {summaryItem.current_tier}
                            </span>
                            <span className="text-slate-400">→</span>
                            <span className="rounded-full border border-blue-200 bg-blue-50 px-3 py-1 font-semibold text-blue-700">
                              {summaryItem.recommended_tier}
                            </span>
                          </div>
                        </div>
                      </div>
                      <div className="mt-4 flex flex-wrap items-center gap-3 text-xs text-slate-500">
                        <span>
                          Lifecycle: <span className="font-semibold text-slate-700">{summaryItem.lifecycle_stage}</span>
                        </span>
                        {summaryItem.last_access_days !== null && summaryItem.last_access_days !== undefined ? (
                          <span>
                            Last access:{" "}
                            <span className="font-semibold text-slate-700">{summaryItem.last_access_days} days</span>
                          </span>
                        ) : null}
                      </div>
                    </section>

                    <section className="grid gap-4 md:grid-cols-2">
                      <div className="rounded-xl border border-slate-200 bg-white p-4">
                        <p className="text-xs uppercase tracking-[0.2em] text-slate-500">Temperature Analysis</p>
                        <div className="mt-4 space-y-2 text-sm text-slate-600">
                          <p>
                            Temperature score: <span className="font-semibold text-slate-900">{summaryItem.temperature_score.toFixed(2)}</span>
                          </p>
                          <p>
                            Effective access: <span className="font-semibold text-slate-900">{summaryItem.effective_access.toFixed(2)}</span>
                          </p>
                          <p>
                            Access recency: <span className="font-semibold text-slate-900">{summaryItem.recency_score.toFixed(2)}</span>
                          </p>
                          <p>
                            Momentum: <span className="font-semibold text-slate-900">{summaryItem.momentum.toFixed(2)}</span>
                          </p>
                        </div>
                      </div>

                      <div className="rounded-xl border border-slate-200 bg-white p-4">
                        <p className="text-xs uppercase tracking-[0.2em] text-slate-500">Access Behavior</p>
                        {(() => {
                          const requests30 = Math.round(summaryItem.requests_30d);
                          const requests90 = Math.round(summaryItem.requests_90d);
                          const base = Math.max(requests90, 1);
                          const lastAccessDays = summaryItem.last_access_days ?? null;
                          const momentum = Math.round(clamp(summaryItem.momentum / 2) * 100);
                          const volatility = Math.round(clamp(summaryItem.access_volatility) * 100);

                          return (
                            <div className="mt-4 space-y-3 text-sm text-slate-600">
                              <AccessMetric
                                label="Requests (30 days)"
                                value={`${requests30.toLocaleString()}`}
                                percent={Math.min(100, Math.round((requests30 / base) * 100))}
                              />
                              <AccessMetric label="Requests (90 days)" value={`${requests90.toLocaleString()}`} percent={100} />
                              <AccessMetric
                                label="Last Access"
                                value={lastAccessDays === null ? "—" : `${lastAccessDays} days`}
                                percent={
                                  lastAccessDays === null ? 0 : Math.max(0, 100 - Math.min(100, lastAccessDays))
                                }
                              />
                              <AccessMetric label="Momentum" value={`${momentum}%`} percent={momentum} />
                              <AccessMetric label="Volatility" value={`${volatility}%`} percent={volatility} />
                            </div>
                          );
                        })()}
                      </div>
                    </section>

                    <section className="grid gap-4 md:grid-cols-2">
                      <div className="rounded-xl border border-slate-200 bg-white p-4">
                        <p className="text-xs uppercase tracking-[0.2em] text-slate-500">Lifecycle Cooling</p>
                        <p className="mt-3 text-sm text-slate-600">
                          Idle Days:{" "}
                          <span className="font-semibold text-slate-900">
                            {summaryItem.last_access_days ?? Math.round((1 - clamp(summaryItem.recency_score)) * 90)}
                          </span>
                        </p>
                        {summaryItem.predicted_archive_in_days !== null &&
                        summaryItem.predicted_archive_in_days !== undefined ? (
                          <p className="mt-1 text-xs text-slate-500">
                            Predicted archive transition in {summaryItem.predicted_archive_in_days} days.
                          </p>
                        ) : null}
                        <div className="mt-4 flex flex-wrap items-center gap-2 text-xs font-semibold text-slate-500">
                          {["HOT", "WARM", "COLD", "ARCHIVE"].map((stage, index) => (
                            <span key={stage} className="flex items-center gap-2">
                              <span
                                className={`rounded-full px-3 py-1 ${
                                  stage === summaryItem.lifecycle_stage.toUpperCase()
                                    ? "bg-blue-600 text-white"
                                    : "bg-slate-100 text-slate-600"
                                }`}
                              >
                                {stage}
                              </span>
                              {index < 3 ? <span className="text-slate-300">→</span> : null}
                            </span>
                          ))}
                        </div>
                      </div>

                      <div className="rounded-xl border border-slate-200 bg-white p-4">
                        <p className="text-xs uppercase tracking-[0.2em] text-slate-500">Cost Comparison</p>
                        <div className="mt-4 space-y-2 text-sm text-slate-600">
                          <div className="flex items-center justify-between">
                            <span>{summaryItem.current_tier}</span>
                            <span className="font-semibold text-slate-900">
                              {formatMoney(summaryItem.storage_cost_current)}
                            </span>
                          </div>
                          <div className="flex items-center justify-between">
                            <span>{summaryItem.recommended_tier}</span>
                            <span className="font-semibold text-slate-900">
                              {formatMoney(summaryItem.storage_cost_recommended)}
                            </span>
                          </div>
                          <div className="mt-3 rounded-lg border border-emerald-100 bg-emerald-50 px-3 py-2">
                            <p className="text-xs uppercase tracking-wide text-emerald-700">Estimated Savings</p>
                            <p className="mt-1 text-lg font-semibold text-emerald-700">
                              ${summaryItem.estimated_savings.toFixed(2)}/mo
                            </p>
                          </div>
                        </div>
                      </div>
                    </section>

                    <section className="grid gap-4 md:grid-cols-2">
                      <div className="rounded-xl border border-slate-200 bg-white p-4">
                        <p className="text-xs uppercase tracking-[0.2em] text-slate-500">Migration Risk</p>
                        <div className="mt-4 flex items-center gap-3">
                          <span
                            className={`inline-flex items-center rounded-full border px-3 py-1 text-xs font-semibold ${riskTone(
                              summaryItem.migration_risk,
                            )}`}
                          >
                            {summaryItem.migration_risk}
                          </span>
                          {summaryItem.migration_risk_score !== null &&
                          summaryItem.migration_risk_score !== undefined ? (
                            <span className="text-sm text-slate-600">
                              Score {summaryItem.migration_risk_score.toFixed(2)}
                            </span>
                          ) : null}
                        </div>
                      </div>

                      <div className="rounded-xl border border-slate-200 bg-white p-4">
                        <p className="text-xs uppercase tracking-[0.2em] text-slate-500">Confidence</p>
                        <div className="mt-4 h-2 w-full rounded-full bg-slate-100">
                          <div
                            className="h-2 rounded-full bg-emerald-500"
                            style={{ width: `${Math.round(summaryItem.confidence * 100)}%` }}
                          />
                        </div>
                        <p className="mt-2 text-sm text-slate-600">
                          {Math.round(summaryItem.confidence * 100)}% confidence score
                        </p>
                      </div>
                    </section>

                    <section className="rounded-xl border border-slate-200 bg-white p-4">
                      <p className="text-xs uppercase tracking-[0.2em] text-slate-500">Recommendation Reasoning</p>
                      {summaryItem.reasoning.length > 0 ? (
                        <ul className="mt-3 list-disc space-y-1 pl-5 text-sm text-slate-600">
                          {summaryItem.reasoning.map((line, index) => (
                            <li key={`${summaryItem.resource_id}-${index}`}>{line}</li>
                          ))}
                        </ul>
                      ) : (
                        <p className="mt-3 text-sm text-slate-500">No reasoning details available.</p>
                      )}
                    </section>
                  </div>
                ) : null}
              </div>
            </div>
          ) : null}

          {modalRecommendation ? (
            <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 px-4">
              <div className="w-full max-w-2xl rounded-2xl border border-blue-200 bg-white p-5 shadow-[0_16px_40px_rgba(37,99,235,0.18)]">
                <h3 className="text-lg font-semibold text-slate-900">Risk Confirmation Required</h3>
                <p className="mt-1 text-sm text-slate-600">
                  This approval requires explicit risk acknowledgement. Review and authorize to proceed.
                </p>

                <div className="mt-4 grid gap-2 text-sm text-slate-700 md:grid-cols-2">
                  <p>Resource: {modalRecommendation.resource_name}</p>
                  <p>Recommended tier: {modalRecommendation.recommended_tier}</p>
                  <p>ML-predicted tier: {extractMlPredictionTier(modalRecommendation)}</p>
                  <p>Model confidence: {(modalRecommendation.model_confidence * 100).toFixed(2)}%</p>
                  <p>
                    Operational readiness: {(modalRecommendation.operational_readiness * 100).toFixed(2)}% (
                    {modalRecommendation.operational_readiness_band})
                  </p>
                  <p>Estimated savings: ${modalRecommendation.estimated_monthly_savings.toFixed(2)}/mo</p>
                  <p>Risk level: {riskLevelLabel(modalRecommendation.confidence_final)}</p>
                </div>

                <div className="mt-3 rounded-xl border border-slate-200 bg-slate-50 p-3 text-xs text-amber-700">
                  Guardrail triggers:{" "}
                  {modalRecommendation.guardrail_trace.length > 0
                    ? modalRecommendation.guardrail_trace.join(" | ")
                    : "No explicit guardrail message; confidence-based override still required."}
                </div>
                <p className="mt-2 text-xs text-slate-500">{modalRecommendation.execution_reason}</p>

                <div className="mt-4 space-y-2 text-sm text-slate-700">
                  <label className="flex items-start gap-2">
                    <input
                      type="checkbox"
                      checked={riskChecks.RETRIEVAL_COST}
                      onChange={(event) =>
                        setRiskChecks((current) => ({ ...current, RETRIEVAL_COST: event.target.checked }))
                      }
                      className="mt-0.5 h-4 w-4 accent-blue-600"
                    />
                    <span>I acknowledge retrieval cost risk.</span>
                  </label>
                  <label className="flex items-start gap-2">
                    <input
                      type="checkbox"
                      checked={riskChecks.LATENCY}
                      onChange={(event) => setRiskChecks((current) => ({ ...current, LATENCY: event.target.checked }))}
                      className="mt-0.5 h-4 w-4 accent-blue-600"
                    />
                    <span>I acknowledge latency risk.</span>
                  </label>
                </div>

                <div className="mt-3">
                  <label className="mb-1 block text-xs uppercase tracking-wide text-slate-500">
                    Business Justification
                  </label>
                  <textarea
                    value={overrideJustification}
                    onChange={(event) => setOverrideJustification(event.target.value)}
                    placeholder="Business approved migration..."
                    className="min-h-20 w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm text-slate-900 outline-none focus:border-blue-400 focus:ring-2 focus:ring-blue-100"
                  />
                </div>

                {modalError ? <p className="mt-3 text-sm text-rose-700">{modalError}</p> : null}

                <div className="mt-5 flex flex-wrap items-center justify-end gap-2">
                  <button
                    type="button"
                    onClick={closeRiskModal}
                    className="rounded-full border border-slate-200 px-4 py-2 text-sm text-slate-600 hover:border-slate-400 hover:bg-slate-50"
                  >
                    Cancel
                  </button>
                  <button
                    type="button"
                    onClick={() => void handleAuthorizeFromModal()}
                    disabled={
                      executingResourceId === modalRecommendation.resource_name ||
                      REQUIRED_RISKS.some((risk) => !riskChecks[risk]) ||
                      !overrideJustification.trim()
                    }
                    className="rounded-full border border-blue-200 px-4 py-2 text-sm font-semibold text-blue-700 shadow-[0_12px_26px_rgba(37,99,235,0.2)] hover:border-blue-300 hover:bg-blue-50 disabled:cursor-not-allowed disabled:border-slate-200 disabled:text-slate-500 disabled:shadow-none"
                  >
                    {executingResourceId === modalRecommendation.resource_name ? "Authorizing..." : "Approve"}
                  </button>
                </div>
              </div>
            </div>
          ) : null}

          {traceItem ? (
            <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 px-4">
              <div className="w-full max-w-3xl rounded-2xl border border-slate-200 bg-white p-6 shadow-[0_18px_50px_rgba(15,23,42,0.2)]">
                <div className="flex items-center justify-between">
                  <h3 className="text-lg font-semibold text-slate-900">Decision Trace</h3>
                  <button
                    type="button"
                    onClick={() => setTraceItem(null)}
                    className="text-sm text-slate-500 hover:text-slate-700"
                  >
                    Close
                  </button>
                </div>

                <div className="mt-4 grid gap-4 lg:grid-cols-2">
                  <div>
                    <p className="text-xs uppercase tracking-wide text-slate-500">Feature Snapshot</p>
                    <ul className="mt-2 space-y-1 text-xs text-slate-600">
                      {Object.entries(traceItem.feature_snapshot).map(([key, value]) => (
                        <li key={key} className="flex justify-between gap-3">
                          <span className="text-slate-500">{key}</span>
                          <span>{String(value)}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                  <div>
                    <p className="text-xs uppercase tracking-wide text-slate-500">Rule Trace</p>
                    <ul className="mt-2 space-y-1 text-xs text-slate-600">
                      {traceItem.rule_override_trace.map((trace, index) => (
                        <li key={`${traceItem.id}-${index}`}>{trace}</li>
                      ))}
                    </ul>
                    {traceItem.guardrail_trace.length > 0 ? (
                      <div className="mt-3 rounded-lg border border-amber-200 bg-amber-50 p-2 text-xs text-amber-700">
                        Guardrails: {traceItem.guardrail_trace.join(" | ")}
                      </div>
                    ) : null}
                  </div>
                </div>
              </div>
            </div>
          ) : null}
        </main>
      </div>
    </ProtectedView>
  );
}

function AccessMetric({ label, value, percent }: { label: string; value: string; percent: number }) {
  return (
    <div>
      <div className="flex items-center justify-between text-xs text-slate-500">
        <span>{label}</span>
        <span className="font-semibold text-slate-700">{value}</span>
      </div>
      <div className="mt-2 h-2 w-full rounded-full bg-slate-100">
        <div className="h-2 rounded-full bg-blue-500" style={{ width: `${Math.min(percent, 100)}%` }} />
      </div>
    </div>
  );
}
