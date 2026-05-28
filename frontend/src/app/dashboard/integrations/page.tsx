"use client";

import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { AxiosError } from "axios";

import { PageState } from "@/components/PageState";
import { ProtectedView } from "@/components/ProtectedView";
import { GlowCard } from "@/components/ui/GlowCard";
import { NeonBadge } from "@/components/ui/NeonBadge";
import {
  connectIntegration,
  fetchIngestionJobs,
  fetchIntegrationStatus,
  getApiErrorMessage,
  syncIntegration,
  uploadIngestionFile,
} from "@/lib/api";
import type { IngestionJobStatus, IntegrationConnectPayload, IntegrationStatus } from "@/lib/types";

const DEFAULT_INTEGRATION_FORM: IntegrationConnectPayload & { credential_value: string } = {
  provider: "AWS",
  source_name: "",
  endpoint_url: "",
  auth_type: "api_key",
  credentials: {},
  sync_interval_minutes: 60,
  is_read_only: true,
  credential_value: "",
};

const PROVIDERS = ["AWS", "AZURE", "GCP"] as const;

type Provider = (typeof PROVIDERS)[number];

export default function IntegrationsPage() {
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [jobs, setJobs] = useState<IngestionJobStatus[]>([]);
  const [integrations, setIntegrations] = useState<IntegrationStatus[]>([]);
  const [integrationForm, setIntegrationForm] = useState(DEFAULT_INTEGRATION_FORM);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [savingIntegration, setSavingIntegration] = useState(false);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const loadData = useCallback(async () => {
    const [jobData, integrationData] = await Promise.all([fetchIngestionJobs(), fetchIntegrationStatus()]);
    setJobs(jobData);
    setIntegrations(integrationData);
  }, []);

  const safeLoadData = useCallback(async () => {
    try {
      await loadData();
      setError(null);
    } catch (err: unknown) {
      if (err instanceof AxiosError && err.response?.status === 401) {
        setError("Session expired. Please sign in again.");
      } else {
        setError(getApiErrorMessage(err));
      }
    }
  }, [loadData]);

  useEffect(() => {
    const run = async () => {
      setLoading(true);
      setError(null);
      await safeLoadData();
      setLoading(false);
    };
    void run();
  }, [safeLoadData]);

  const integrationByProvider = useMemo(() => {
    const map = new Map<Provider, IntegrationStatus>();
    integrations.forEach((integration) => {
      const provider = integration.provider.toUpperCase() as Provider;
      if (PROVIDERS.includes(provider)) {
        map.set(provider, integration);
      }
    });
    return map;
  }, [integrations]);

  const handleUpload = async () => {
    if (!selectedFile) return;
    setUploading(true);
    setStatusMessage(null);
    try {
      const result = await uploadIngestionFile(selectedFile);
      setStatusMessage(`${result.message} Job #${result.job_id} created.`);
      setSelectedFile(null);
      await safeLoadData();
      setTimeout(() => {
        void safeLoadData();
      }, 1500);
      setTimeout(() => {
        void safeLoadData();
      }, 5000);
    } catch (err: unknown) {
      setStatusMessage(getApiErrorMessage(err));
    } finally {
      setUploading(false);
    }
  };

  const handleConnectIntegration = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setSavingIntegration(true);
    setStatusMessage(null);
    try {
      const credentialKey = integrationForm.auth_type === "oauth" ? "access_token" : "api_key";
      const credentials: Record<string, string> = {
        [credentialKey]: integrationForm.credential_value,
      };

      await connectIntegration({
        provider: integrationForm.provider,
        source_name: integrationForm.source_name,
        endpoint_url: integrationForm.endpoint_url,
        auth_type: integrationForm.auth_type,
        credentials,
        sync_interval_minutes: integrationForm.sync_interval_minutes,
        is_read_only: integrationForm.is_read_only,
      });
      setIntegrationForm(DEFAULT_INTEGRATION_FORM);
      setStatusMessage("Integration saved successfully.");
      await safeLoadData();
    } catch (err: unknown) {
      setStatusMessage(getApiErrorMessage(err));
    } finally {
      setSavingIntegration(false);
    }
  };

  const handleSync = async (integrationId: number) => {
    setStatusMessage(null);
    try {
      const result = await syncIntegration(integrationId);
      setStatusMessage(
        `Integration sync complete: ${result.records_ingested} records ingested for ${result.source_name}.`,
      );
      await safeLoadData();
    } catch (err: unknown) {
      setStatusMessage(getApiErrorMessage(err));
    }
  };

  const handleProviderConnect = (provider: Provider) => {
    setIntegrationForm((current) => ({
      ...current,
      provider,
      source_name: `${provider.toLowerCase()}-integration`,
    }));
    setStatusMessage(`Configure ${provider} integration below.`);
    document.getElementById("integration-config")?.scrollIntoView({ behavior: "smooth" });
  };

  return (
    <ProtectedView>
      <div className="relative min-h-screen bg-slate-50 text-slate-900">
        <div className="pointer-events-none absolute -right-44 top-0 h-64 w-64 rounded-full bg-blue-200/40 blur-[110px]" />
        <div className="pointer-events-none absolute -left-36 top-64 h-64 w-64 rounded-full bg-cyan-200/40 blur-[120px]" />
        <main className="relative mx-auto w-full max-w-7xl px-6 py-8">
          {loading ? <PageState title="Loading integrations" message="Fetching authority configuration..." /> : null}
          {error ? <PageState title="Failed to load integrations" message={error} /> : null}

          {!loading && !error ? (
            <div className="space-y-8">
              <section>
                <p className="text-xs uppercase tracking-[0.25em] text-slate-500">Integrations</p>
                <h1 className="mt-2 text-2xl font-semibold text-slate-900">Cloud Connectivity</h1>
                <p className="mt-1 text-sm text-slate-600">
                  Manage ingestion sources, sync authority, and execution readiness across providers.
                </p>
              </section>

              <section className="space-y-6">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div>
                    <h2 className="text-lg font-semibold text-slate-900">Cloud Providers</h2>
                    <p className="text-sm text-slate-500">Connect enterprise cloud accounts for execution authority.</p>
                  </div>
                  <NeonBadge tone="emerald">Authority: FULL</NeonBadge>
                </div>

                <div className="grid gap-6 md:grid-cols-3">
                  {PROVIDERS.map((provider) => {
                    const integration = integrationByProvider.get(provider);
                    const connected = Boolean(integration);
                    const statusLabel = connected
                      ? integration?.is_read_only
                        ? "Analysis Mode"
                        : "Execution Mode"
                      : "Not Connected";
                    const sourceLabel = connected ? "Cloud API" : "File Upload";
                    const permissionMode = connected
                      ? integration?.is_read_only
                        ? "Read-only"
                        : "Write-enabled"
                      : "Analysis Only";

                    return (
                      <GlowCard key={provider} className="p-6">
                        <div className="flex items-center justify-between">
                          <div>
                            <h3 className="text-base font-semibold text-slate-900">{provider}</h3>
                            <p className="text-xs text-slate-500">Enterprise cloud provider</p>
                          </div>
                          <NeonBadge tone={connected ? "emerald" : "rose"}>
                            {connected ? "Connected" : "Not Connected"}
                          </NeonBadge>
                        </div>
                        <div className="mt-4 space-y-2 text-sm text-slate-600">
                          <div className="flex items-center justify-between">
                            <span>Status</span>
                            <span className="font-semibold text-slate-900">{statusLabel}</span>
                          </div>
                          <div className="flex items-center justify-between">
                            <span>Source</span>
                            <span className="font-semibold text-slate-900">{sourceLabel}</span>
                          </div>
                          <div className="flex items-center justify-between">
                            <span>Mode</span>
                            <span className="font-semibold text-slate-900">{permissionMode}</span>
                          </div>
                        </div>
                        <div className="mt-5 flex flex-wrap gap-2">
                          {connected ? (
                            <button
                              type="button"
                              onClick={() => void handleSync(integration.integration_id)}
                              className="rounded-full border border-blue-200 px-4 py-2 text-xs font-semibold text-blue-700 hover:border-blue-300 hover:bg-blue-50"
                            >
                              Sync Cloud
                            </button>
                          ) : (
                            <button
                              type="button"
                              onClick={() => handleProviderConnect(provider)}
                              className="rounded-full border border-blue-200 px-4 py-2 text-xs font-semibold text-blue-700 hover:border-blue-300 hover:bg-blue-50"
                            >
                              Connect Cloud
                            </button>
                          )}
                        </div>
                      </GlowCard>
                    );
                  })}
                </div>

                <GlowCard className="p-6" delay={0.05}>
                  <div className="flex items-center justify-between">
                    <h3 className="text-sm font-semibold text-slate-900">Connection Configuration</h3>
                    <NeonBadge tone="indigo">Authority: FULL</NeonBadge>
                  </div>
                  <form id="integration-config" onSubmit={handleConnectIntegration} className="mt-4 grid gap-4">
                    <div className="grid gap-4 md:grid-cols-2">
                      <label className="flex flex-col gap-2 text-sm text-slate-600">
                        Provider
                        <select
                          value={integrationForm.provider}
                          onChange={(event) =>
                            setIntegrationForm((current) => ({
                              ...current,
                              provider: event.target.value as IntegrationConnectPayload["provider"],
                            }))
                          }
                          className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm text-slate-900"
                        >
                          <option value="AWS">AWS</option>
                          <option value="AZURE">Azure</option>
                          <option value="GCP">GCP</option>
                        </select>
                      </label>
                      <label className="flex flex-col gap-2 text-sm text-slate-600">
                        Source Name
                        <input
                          value={integrationForm.source_name}
                          onChange={(event) =>
                            setIntegrationForm((current) => ({ ...current, source_name: event.target.value }))
                          }
                          className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm text-slate-900"
                          placeholder="aws-main"
                        />
                      </label>
                    </div>

                    <div className="grid gap-4 md:grid-cols-2">
                      <label className="flex flex-col gap-2 text-sm text-slate-600">
                        Endpoint URL
                        <input
                          value={integrationForm.endpoint_url}
                          onChange={(event) =>
                            setIntegrationForm((current) => ({ ...current, endpoint_url: event.target.value }))
                          }
                          className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm text-slate-900"
                          placeholder="https://api.your-cloud.com"
                        />
                      </label>
                      <label className="flex flex-col gap-2 text-sm text-slate-600">
                        Auth Type
                        <select
                          value={integrationForm.auth_type}
                          onChange={(event) =>
                            setIntegrationForm((current) => ({
                              ...current,
                              auth_type: event.target.value as IntegrationConnectPayload["auth_type"],
                            }))
                          }
                          className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm text-slate-900"
                        >
                          <option value="api_key">API Key</option>
                          <option value="oauth">OAuth</option>
                        </select>
                      </label>
                    </div>

                    <div className="grid gap-4 md:grid-cols-2">
                      <label className="flex flex-col gap-2 text-sm text-slate-600">
                        Credential
                        <input
                          value={integrationForm.credential_value}
                          onChange={(event) =>
                            setIntegrationForm((current) => ({ ...current, credential_value: event.target.value }))
                          }
                          className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm text-slate-900"
                          placeholder="Enter credential"
                        />
                      </label>
                      <label className="flex flex-col gap-2 text-sm text-slate-600">
                        Sync Interval (minutes)
                        <input
                          type="number"
                          value={integrationForm.sync_interval_minutes}
                          onChange={(event) =>
                            setIntegrationForm((current) => ({
                              ...current,
                              sync_interval_minutes: Number(event.target.value),
                            }))
                          }
                          className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm text-slate-900"
                        />
                      </label>
                    </div>

                    <label className="flex items-center gap-2 text-sm text-slate-600">
                      <input
                        type="checkbox"
                        checked={integrationForm.is_read_only}
                        onChange={(event) =>
                          setIntegrationForm((current) => ({ ...current, is_read_only: event.target.checked }))
                        }
                        className="h-4 w-4 accent-blue-600"
                      />
                      Enable read-only mode (analysis only)
                    </label>

                    <div className="flex items-center gap-3">
                      <button
                        type="submit"
                        disabled={savingIntegration}
                        className="rounded-full border border-blue-200 px-4 py-2 text-sm font-semibold text-blue-700 hover:border-blue-300 hover:bg-blue-50 disabled:cursor-not-allowed disabled:opacity-60"
                      >
                        {savingIntegration ? "Saving..." : "Save Integration"}
                      </button>
                      {statusMessage ? <span className="text-xs text-slate-600">{statusMessage}</span> : null}
                    </div>
                  </form>
                </GlowCard>
              </section>

              <section className="space-y-4">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div>
                    <h2 className="text-lg font-semibold text-slate-900">API Integration</h2>
                    <p className="text-sm text-slate-500">Automation-ready ingestion pipeline.</p>
                  </div>
                  <NeonBadge tone="indigo">Authority: ANALYSIS</NeonBadge>
                </div>

                <GlowCard className="p-6">
                  <div className="grid gap-3 text-sm text-slate-600 md:grid-cols-2">
                    <div>
                      <p className="text-xs uppercase tracking-wide text-slate-500">API Endpoint</p>
                      <p className="mt-1 font-semibold text-slate-900">/api/v1/resources</p>
                    </div>
                    <div>
                      <p className="text-xs uppercase tracking-wide text-slate-500">Authentication</p>
                      <p className="mt-1 font-semibold text-slate-900">API Key</p>
                    </div>
                    <div>
                      <p className="text-xs uppercase tracking-wide text-slate-500">Status</p>
                      <p className="mt-1 font-semibold text-slate-900">Available</p>
                    </div>
                  </div>
                  <div className="mt-4 flex flex-wrap gap-2">
                    <button
                      type="button"
                      onClick={() => setStatusMessage("API key generation is not configured in this preview.")}
                      className="rounded-full border border-blue-200 px-4 py-2 text-xs font-semibold text-blue-700 hover:border-blue-300 hover:bg-blue-50"
                    >
                      Generate API Key
                    </button>
                    <button
                      type="button"
                      onClick={() => setStatusMessage("Documentation portal not configured in this preview.")}
                      className="rounded-full border border-slate-200 px-4 py-2 text-xs font-semibold text-slate-700 hover:border-slate-300 hover:bg-slate-50"
                    >
                      View Documentation
                    </button>
                  </div>
                </GlowCard>
              </section>

              <section className="space-y-4">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div>
                    <h2 className="text-lg font-semibold text-slate-900">File Upload</h2>
                    <p className="text-sm text-slate-500">Lowest authority. Dry-run only.</p>
                  </div>
                  <NeonBadge tone="rose">Authority: DRY RUN ONLY</NeonBadge>
                </div>

                <GlowCard className="p-6">
                  <p className="text-sm text-slate-600">Upload CSV / JSON datasets for analysis.</p>
                  <div className="mt-4 flex flex-wrap items-center gap-3">
                    <input
                      type="file"
                      accept=".csv,.json"
                      onChange={(event) => setSelectedFile(event.target.files?.[0] ?? null)}
                      className="block rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-700"
                    />
                    <button
                      type="button"
                      disabled={!selectedFile || uploading}
                      onClick={() => void handleUpload()}
                      className="rounded-full border border-blue-200 px-4 py-2 text-sm font-semibold text-blue-700 hover:bg-blue-50 disabled:opacity-60"
                    >
                      {uploading ? "Uploading..." : "Upload Dataset"}
                    </button>
                  </div>
                  {statusMessage ? <p className="mt-3 text-xs text-slate-600">{statusMessage}</p> : null}
                </GlowCard>

                <GlowCard className="p-6">
                  <h3 className="text-sm font-semibold text-slate-900">Upload Job Status</h3>
                  {jobs.length === 0 ? (
                    <p className="mt-3 text-sm text-slate-600">No ingestion jobs yet.</p>
                  ) : (
                    <div className="mt-3 overflow-x-auto">
                      <table className="min-w-full text-left text-sm">
                        <thead className="text-xs uppercase tracking-wide text-slate-500">
                          <tr>
                            <th className="px-3 py-2">Job</th>
                            <th className="px-3 py-2">File</th>
                            <th className="px-3 py-2">Status</th>
                            <th className="px-3 py-2">Records</th>
                            <th className="px-3 py-2">Origin</th>
                            <th className="px-3 py-2">Error</th>
                          </tr>
                        </thead>
                        <tbody>
                          {jobs.map((job) => (
                            <tr key={job.job_id} className="border-t border-slate-200 text-slate-700">
                              <td className="px-3 py-2">#{job.job_id}</td>
                              <td className="px-3 py-2">{job.file_name ?? "-"}</td>
                              <td className="px-3 py-2">{job.status}</td>
                              <td className="px-3 py-2">{job.record_count}</td>
                              <td className="px-3 py-2">{job.data_origin}</td>
                              <td className="px-3 py-2">{job.error_message ?? "-"}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </GlowCard>
              </section>
            </div>
          ) : null}
        </main>
      </div>
    </ProtectedView>
  );
}
