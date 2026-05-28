"use client";

import { useEffect, useState } from "react";

import { PageState } from "@/components/PageState";
import { ProtectedView } from "@/components/ProtectedView";
import { StatCard } from "@/components/StatCard";
import {
  deleteAdminRecord,
  fetchAdminMetrics,
  fetchAdminMigrations,
  fetchAdminRecords,
  fetchAdminUserDetail,
  fetchAdminUsers,
  fetchPublicDatasetSources,
  getApiErrorMessage,
  ingestPublicDataset,
  updateAdminRecordExternalId,
} from "@/lib/api";
import type {
  AdminIngestedRecord,
  AdminMetrics,
  AdminMigration,
  AdminUser,
  AdminUserDetail,
  PublicDatasetSource,
} from "@/lib/types";

export default function AdminPage() {
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [metrics, setMetrics] = useState<AdminMetrics | null>(null);
  const [migrations, setMigrations] = useState<AdminMigration[]>([]);
  const [sources, setSources] = useState<PublicDatasetSource[]>([]);
  const [records, setRecords] = useState<AdminIngestedRecord[]>([]);
  const [recordsLoading, setRecordsLoading] = useState(false);
  const [ingestingSource, setIngestingSource] = useState<string | null>(null);
  const [datasetStatus, setDatasetStatus] = useState<string | null>(null);
  const [selectedUserId, setSelectedUserId] = useState<number | null>(null);
  const [selectedUserDetail, setSelectedUserDetail] = useState<AdminUserDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const run = async () => {
      setLoading(true);
      setError(null);
      try {
        const [usersData, metricsData, migrationsData, sourceData, recordsData] = await Promise.all([
          fetchAdminUsers(),
          fetchAdminMetrics(),
          fetchAdminMigrations(),
          fetchPublicDatasetSources(),
          fetchAdminRecords(undefined, 100),
        ]);
        setUsers(usersData);
        setMetrics(metricsData);
        setMigrations(migrationsData);
        setSources(sourceData);
        setRecords(recordsData);
      } catch (err: unknown) {
        setError(getApiErrorMessage(err));
      } finally {
        setLoading(false);
      }
    };

    void run();
  }, []);

  const handleSelectUser = async (userId: number) => {
    setSelectedUserId(userId);
    setDetailLoading(true);
    try {
      const detail = await fetchAdminUserDetail(userId);
      setSelectedUserDetail(detail);
    } catch (err: unknown) {
      setError(getApiErrorMessage(err));
    } finally {
      setDetailLoading(false);
    }
  };

  const handleIngestPublicDataset = async (sourceKey: string) => {
    setIngestingSource(sourceKey);
    setDatasetStatus(null);
    try {
      const result = await ingestPublicDataset(sourceKey, 250);
      setDatasetStatus(
        `Public dataset ${result.source_name} ingested: ${result.inserted_records} inserted, ${result.skipped_records} skipped.`,
      );
    } catch (err: unknown) {
      setDatasetStatus(getApiErrorMessage(err));
    } finally {
      setIngestingSource(null);
    }
  };

  const refreshRecords = async () => {
    setRecordsLoading(true);
    try {
      const rows = await fetchAdminRecords(undefined, 100);
      setRecords(rows);
    } catch (err: unknown) {
      setError(getApiErrorMessage(err));
    } finally {
      setRecordsLoading(false);
    }
  };

  const handleEditRecordExternalId = async (record: AdminIngestedRecord) => {
    const nextExternalId = window.prompt("Enter new external_id", record.external_id ?? "");
    if (nextExternalId === null) return;
    try {
      await updateAdminRecordExternalId(record.id, nextExternalId);
      await refreshRecords();
    } catch (err: unknown) {
      setError(getApiErrorMessage(err));
    }
  };

  const handleDeleteRecord = async (recordId: number) => {
    const confirmed = window.confirm(`Delete record #${recordId}? This cannot be undone.`);
    if (!confirmed) return;
    try {
      await deleteAdminRecord(recordId);
      await refreshRecords();
    } catch (err: unknown) {
      setError(getApiErrorMessage(err));
    }
  };

  return (
    <ProtectedView requiredRole="ADMIN">
      <div className="min-h-screen bg-transparent text-slate-900">
        <main className="mx-auto w-full max-w-7xl px-6 py-8">
          {loading ? <PageState title="Loading admin dashboard" message="Fetching enterprise controls..." /> : null}
          {error ? <PageState title="Failed to load admin dashboard" message={error} /> : null}

          {!loading && !error && metrics ? (
            <div className="space-y-6">
              <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
                <StatCard
                  title="Total Cloud Usage"
                  value={`$${metrics.cloud_usage.total_cost.toLocaleString()}`}
                  subtitle="Current tracked storage cost"
                />
                <StatCard
                  title="Classification Accuracy"
                  value={`${(metrics.classification_accuracy.average_confidence * 100).toFixed(1)}%`}
                  subtitle={`${metrics.classification_accuracy.high_confidence_count}/${metrics.classification_accuracy.total_classified} high-confidence`}
                />
                <StatCard
                  title="Active Migrations"
                  value={`${metrics.system_health.running_migrations}`}
                  subtitle="Jobs currently in RUNNING state"
                />
                <StatCard
                  title="System Health"
                  value={`${metrics.system_health.active_users} active users`}
                  subtitle={`Uptime ${Math.round(metrics.system_health.api_uptime_seconds)}s · Pricing ${metrics.system_health.pricing_version ?? "N/A"}`}
                />
              </section>

              <section className="rounded-xl border border-slate-200 bg-white p-5">
                <h2 className="text-lg font-semibold text-slate-900">Public Dataset Ingestion</h2>
                <p className="mt-1 text-sm text-slate-500">
                  Safe ingestion for AWS CUR/FinOps/Kaggle-style public datasets. Always non-billable.
                </p>
                <div className="mt-4 grid gap-3 md:grid-cols-3">
                  {sources.map((source) => (
                    <div key={source.key} className="rounded-lg border border-slate-200 bg-slate-50 p-3">
                      <p className="text-sm font-semibold text-slate-900">{source.source_name}</p>
                      <p className="mt-1 text-xs text-slate-500">{source.description}</p>
                      <button
                        type="button"
                        className="mt-3 w-full rounded-md border border-blue-200 px-3 py-2 text-xs font-semibold text-blue-700 hover:bg-blue-50 disabled:opacity-60"
                        disabled={ingestingSource === source.key}
                        onClick={() => void handleIngestPublicDataset(source.key)}
                      >
                        {ingestingSource === source.key ? "Ingesting..." : "Ingest Public Data"}
                      </button>
                    </div>
                  ))}
                </div>
                {datasetStatus ? <p className="mt-3 text-sm text-blue-700">{datasetStatus}</p> : null}
              </section>

              <section className="rounded-xl border border-slate-200 bg-white p-5">
                <h2 className="text-lg font-semibold text-slate-900">Cloud Usage Overview</h2>
                <div className="mt-4 grid gap-4 lg:grid-cols-2">
                  <div className="rounded-lg border border-slate-200 bg-slate-50 p-4">
                    <p className="text-sm font-medium text-slate-700">By Provider</p>
                    <ul className="mt-3 space-y-2 text-sm text-slate-600">
                      {Object.entries(metrics.cloud_usage.by_provider).map(([provider, value]) => (
                        <li key={provider} className="flex justify-between">
                          <span>{provider}</span>
                          <span>${value.toFixed(2)}</span>
                        </li>
                      ))}
                    </ul>
                  </div>

                  <div className="rounded-lg border border-slate-200 bg-slate-50 p-4">
                    <p className="text-sm font-medium text-slate-700">By Region</p>
                    <ul className="mt-3 max-h-48 space-y-2 overflow-auto text-sm text-slate-600">
                      {metrics.cloud_usage.by_region.map((regionItem) => (
                        <li key={`${regionItem.provider}-${regionItem.region}`} className="flex justify-between">
                          <span>
                            {regionItem.provider} / {regionItem.region}
                          </span>
                          <span>${regionItem.storage_cost.toFixed(2)}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                </div>
              </section>

              <section className="rounded-xl border border-slate-200 bg-white p-5">
                <div className="flex items-center justify-between">
                  <h2 className="text-lg font-semibold text-slate-900">User Management</h2>
                  <span className="text-sm text-slate-500">{users.length} users</span>
                </div>

                <div className="mt-4 overflow-x-auto">
                  <table className="min-w-full text-left text-sm">
                    <thead className="text-xs uppercase tracking-wide text-slate-500">
                      <tr>
                        <th className="px-3 py-2">Name</th>
                        <th className="px-3 py-2">Email</th>
                        <th className="px-3 py-2">Company</th>
                        <th className="px-3 py-2">Cloud</th>
                        <th className="px-3 py-2">Role</th>
                        <th className="px-3 py-2">Active</th>
                        <th className="px-3 py-2">Account</th>
                        <th className="px-3 py-2">Plan</th>
                        <th className="px-3 py-2">Usage</th>
                        <th className="px-3 py-2">Overage</th>
                        <th className="px-3 py-2">Est. Bill</th>
                        <th className="px-3 py-2">Subscription</th>
                        <th className="px-3 py-2">Last Payment</th>
                        <th className="px-3 py-2">Actions</th>
                      </tr>
                    </thead>
                    <tbody>
                      {users.map((item) => (
                        <tr key={item.id} className="border-t border-slate-200 text-slate-700">
                          <td className="px-3 py-2">{item.name}</td>
                          <td className="px-3 py-2">{item.email}</td>
                          <td className="px-3 py-2">{item.company_name}</td>
                          <td className="px-3 py-2">{item.cloud_provider}</td>
                          <td className="px-3 py-2">{item.role}</td>
                          <td className="px-3 py-2">{item.is_active ? "Yes" : "No"}</td>
                          <td className="px-3 py-2">{item.account_state}</td>
                          <td className="px-3 py-2">{item.plan_code}</td>
                          <td className="px-3 py-2">
                            {item.current_cycle_usage.toLocaleString()} / {item.included_quota.toLocaleString()}
                          </td>
                          <td className="px-3 py-2">{item.overage_usage.toLocaleString()}</td>
                          <td className="px-3 py-2">
                            {item.currency} {item.estimated_cycle_amount.toFixed(2)}
                          </td>
                          <td className="px-3 py-2">{item.subscription_status ?? "-"}</td>
                          <td className="px-3 py-2">{item.last_payment_status ?? "-"}</td>
                          <td className="px-3 py-2">
                            <button
                              type="button"
                              className="rounded-md border border-blue-200 px-2 py-1 text-xs font-semibold text-blue-700 hover:bg-blue-50"
                              onClick={() => void handleSelectUser(item.id)}
                            >
                              View Detail
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </section>

              <section className="rounded-xl border border-slate-200 bg-white p-5">
                <div className="flex items-center justify-between">
                  <h2 className="text-lg font-semibold text-slate-900">User Drill-down</h2>
                  <span className="text-sm text-slate-500">
                    {selectedUserId ? `Tenant ${selectedUserId}` : "Select a user"}
                  </span>
                </div>
                {detailLoading ? (
                  <p className="mt-3 text-sm text-slate-600">Loading user detail...</p>
                ) : null}
                {!detailLoading && !selectedUserDetail ? (
                  <p className="mt-3 text-sm text-slate-500">
                    Click <span className="font-semibold">View Detail</span> on any user to inspect profile, auth, usage,
                    cost, decisions, webhooks, and billing.
                  </p>
                ) : null}
                {!detailLoading && selectedUserDetail ? (
                  <div className="mt-4 grid gap-4 lg:grid-cols-2">
                    <div className="rounded-lg border border-slate-200 bg-slate-50 p-4 text-sm text-slate-600">
                      <p className="font-semibold text-slate-900">Basic Profile</p>
                      <p className="mt-2">Email: {selectedUserDetail.basic_profile.email}</p>
                      <p>Tenant ID: {selectedUserDetail.basic_profile.tenant_id}</p>
                      <p>Status: {selectedUserDetail.basic_profile.status}</p>
                      <p>Role: {selectedUserDetail.basic_profile.role}</p>
                    </div>
                    <div className="rounded-lg border border-slate-200 bg-slate-50 p-4 text-sm text-slate-600">
                      <p className="font-semibold text-slate-900">Auth Info</p>
                      <p className="mt-2">
                        Last login: {selectedUserDetail.auth_info.last_login_at ?? "No login audit yet"}
                      </p>
                      <p>API keys: {selectedUserDetail.auth_info.api_keys.length}</p>
                    </div>
                    <div className="rounded-lg border border-slate-200 bg-slate-50 p-4 text-sm text-slate-600">
                      <p className="font-semibold text-slate-900">Usage Metrics</p>
                      <p className="mt-2">
                        API calls: {selectedUserDetail.usage_metrics.total_api_calls.toLocaleString()}
                      </p>
                      <p>
                        Data ingested: {selectedUserDetail.usage_metrics.total_data_ingested_records.toLocaleString()}{" "}
                        records
                      </p>
                      <p>
                        Current cycle calls: {selectedUserDetail.usage_metrics.current_cycle_requests.toLocaleString()}
                      </p>
                    </div>
                    <div className="rounded-lg border border-slate-200 bg-slate-50 p-4 text-sm text-slate-600">
                      <p className="font-semibold text-slate-900">Cost Insights</p>
                      <p className="mt-2">
                        Storage cost: ${selectedUserDetail.cost_insights.total_storage_cost.toFixed(2)}
                      </p>
                      <p>
                        Estimated savings: ${selectedUserDetail.cost_insights.estimated_monthly_savings.toFixed(2)}
                      </p>
                      <p>Overage usage: {selectedUserDetail.cost_insights.overage_usage.toLocaleString()}</p>
                    </div>
                    <div className="rounded-lg border border-slate-200 bg-slate-50 p-4 text-sm text-slate-600">
                      <p className="font-semibold text-slate-900">Decisions Triggered</p>
                      <p className="mt-2">
                        Recommendations: {selectedUserDetail.decisions_triggered.recommendations_open} open /{" "}
                        {selectedUserDetail.decisions_triggered.recommendations_total} total
                      </p>
                      <p>
                        Migrations: {selectedUserDetail.decisions_triggered.migrations_failed} failed /{" "}
                        {selectedUserDetail.decisions_triggered.migrations_total} total
                      </p>
                    </div>
                    <div className="rounded-lg border border-slate-200 bg-slate-50 p-4 text-sm text-slate-600">
                      <p className="font-semibold text-slate-900">Webhooks & Billing</p>
                      <p className="mt-2">
                        Webhooks: {selectedUserDetail.webhooks_fired.total_events} events,{" "}
                        {selectedUserDetail.webhooks_fired.failed_events} failed
                      </p>
                      <p>
                        Billing: {selectedUserDetail.billing_status.plan_code} ·{" "}
                        {selectedUserDetail.billing_status.account_state}
                      </p>
                      <p>
                        Billable: {selectedUserDetail.billing_status.is_billable ? "Yes" : "No (public dataset)"}
                      </p>
                    </div>
                  </div>
                ) : null}
              </section>

              <section className="rounded-xl border border-slate-200 bg-white p-5">
                <div className="flex items-center justify-between">
                  <h2 className="text-lg font-semibold text-slate-900">Active Migrations</h2>
                  <span className="text-sm text-slate-500">{migrations.length} records</span>
                </div>

                {migrations.length === 0 ? (
                  <p className="mt-4 text-sm text-slate-500">No migration jobs found.</p>
                ) : (
                  <div className="mt-4 overflow-x-auto">
                    <table className="min-w-full text-left text-sm">
                      <thead className="text-xs uppercase tracking-wide text-slate-500">
                        <tr>
                          <th className="px-3 py-2">Resource</th>
                          <th className="px-3 py-2">Source</th>
                          <th className="px-3 py-2">Target</th>
                          <th className="px-3 py-2">Status</th>
                          <th className="px-3 py-2">Progress</th>
                        </tr>
                      </thead>
                      <tbody>
                        {migrations.map((job) => (
                          <tr key={job.id} className="border-t border-slate-200 text-slate-700">
                            <td className="px-3 py-2">{job.resource_name}</td>
                            <td className="px-3 py-2">{job.source_provider}</td>
                            <td className="px-3 py-2">{job.target_provider}</td>
                            <td className="px-3 py-2">{job.status}</td>
                            <td className="px-3 py-2">{job.progress_percent}%</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </section>

              <section className="rounded-xl border border-slate-200 bg-white p-5">
                <div className="flex items-center justify-between">
                  <h2 className="text-lg font-semibold text-slate-900">Record Management</h2>
                  <button
                    type="button"
                    className="rounded-md border border-blue-200 px-3 py-1.5 text-xs font-semibold text-blue-700 hover:bg-blue-50 disabled:opacity-60"
                    onClick={() => void refreshRecords()}
                    disabled={recordsLoading}
                  >
                    {recordsLoading ? "Refreshing..." : "Refresh"}
                  </button>
                </div>

                {records.length === 0 ? (
                  <p className="mt-3 text-sm text-slate-500">No ingested records available.</p>
                ) : (
                  <div className="mt-4 overflow-x-auto">
                    <table className="min-w-full text-left text-sm">
                      <thead className="text-xs uppercase tracking-wide text-slate-500">
                        <tr>
                          <th className="px-3 py-2">ID</th>
                          <th className="px-3 py-2">User</th>
                          <th className="px-3 py-2">Method</th>
                          <th className="px-3 py-2">External ID</th>
                          <th className="px-3 py-2">Schema</th>
                          <th className="px-3 py-2">Created</th>
                          <th className="px-3 py-2">Actions</th>
                        </tr>
                      </thead>
                      <tbody>
                        {records.map((record) => (
                          <tr key={record.id} className="border-t border-slate-200 text-slate-700">
                            <td className="px-3 py-2">#{record.id}</td>
                            <td className="px-3 py-2">{record.user_id}</td>
                            <td className="px-3 py-2">{record.ingestion_method}</td>
                            <td className="px-3 py-2">{record.external_id ?? "-"}</td>
                            <td className="px-3 py-2">{record.schema_version}</td>
                            <td className="px-3 py-2">{record.created_at}</td>
                            <td className="px-3 py-2">
                              <div className="flex gap-2">
                                <button
                                  type="button"
                                  className="rounded-md border border-blue-200 px-2 py-1 text-xs font-semibold text-blue-700 hover:bg-blue-50"
                                  onClick={() => void handleEditRecordExternalId(record)}
                                >
                                  Edit
                                </button>
                                <button
                                  type="button"
                                  className="rounded-md border border-rose-500/40 px-2 py-1 text-xs font-semibold text-rose-200 hover:border-rose-400"
                                  onClick={() => void handleDeleteRecord(record.id)}
                                >
                                  Delete
                                </button>
                              </div>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </section>
            </div>
          ) : null}
        </main>
      </div>
    </ProtectedView>
  );
}
