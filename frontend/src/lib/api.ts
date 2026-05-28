import axios, { AxiosError } from "axios";

import type {
  AdminUserDetail,
  AdminMetrics,
  AdminMigration,
  AdminIngestedRecord,
  AzurePricingSyncResponse,
  CloudPricingSyncResponse,
  AdminUser,
  BillingCatalog,
  BillingOverview,
  DashboardSummary,
  DataTemperature,
  GroupedRecommendation,
  IngestionJobStatus,
  IngestionUploadResponse,
  IntegrationConnectPayload,
  IntegrationConnectResponse,
  IntegrationStatus,
  IntegrationSyncResponse,
  LoginPayload,
  LoginResponse,
  MessageResponse,
  OtpDispatchResponse,
  OtpRequestPayload,
  PasswordResetConfirmPayload,
  PublicDatasetIngestResponse,
  PublicDatasetSource,
  PricingDecisionRequest,
  PricingDecisionResponse,
  PricingVersionResponse,
  TopSavingsResponse,
  Recommendation,
  RecommendationSummary,
  RegisterPayload,
  UserMigration,
  MigrationAuthorizeRequest,
  MigrationAuthorizeResponse,
} from "@/lib/types";

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8001";

const AUTH_STORAGE_KEY = "cloudteck_auth";

export const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    "Content-Type": "application/json",
  },
  timeout: 30000,
});

api.interceptors.request.use((config) => {
  if (typeof window === "undefined") return config;
  const raw = localStorage.getItem(AUTH_STORAGE_KEY);
  if (!raw) return config;

  try {
    const parsed = JSON.parse(raw) as { token?: string };
    if (parsed.token) {
      config.headers.Authorization = `Bearer ${parsed.token}`;
    }
  } catch {
    localStorage.removeItem(AUTH_STORAGE_KEY);
  }

  return config;
});

api.interceptors.response.use(
  (response) => response,
  (error: unknown) => {
    if (typeof window !== "undefined" && error instanceof AxiosError) {
      const status = error.response?.status;
      const requestUrl = String(error.config?.url ?? "");
      const isAuthEndpoint =
        requestUrl.includes("/api/auth/login") ||
        requestUrl.includes("/api/auth/register") ||
        requestUrl.includes("/api/auth/password-reset") ||
        requestUrl.includes("/api/auth/register/request-otp");

      // Session expired/invalid: clear stale local session and notify app.
      if (status === 401 && !isAuthEndpoint) {
        localStorage.removeItem(AUTH_STORAGE_KEY);
        window.dispatchEvent(new Event("cloudteck:unauthorized"));
      }
    }
    return Promise.reject(error);
  },
);

export function getApiErrorMessage(error: unknown): string {
  const fallback = "Something went wrong. Please try again.";
  if (!(error instanceof AxiosError)) return fallback;
  const detail = error.response?.data?.detail;
  const nestedDetails = error.response?.data?.error?.details;
  if (Array.isArray(detail) && detail.length > 0) {
    const first = detail[0] as { loc?: unknown[]; msg?: string };
    const path = Array.isArray(first?.loc)
      ? first.loc
          .filter((item) => typeof item === "string" || typeof item === "number")
          .join(".")
      : "";
    const msg = typeof first?.msg === "string" ? first.msg : "Validation failed";
    return path ? `${path}: ${msg}` : msg;
  }
  if (Array.isArray(nestedDetails) && nestedDetails.length > 0) {
    const first = nestedDetails[0] as { loc?: unknown[]; msg?: string };
    const path = Array.isArray(first?.loc)
      ? first.loc
          .filter((item) => typeof item === "string" || typeof item === "number")
          .join(".")
      : "";
    const msg = typeof first?.msg === "string" ? first.msg : "Validation failed";
    return path ? `${path}: ${msg}` : msg;
  }
  if (typeof detail === "string" && detail !== "Validation failed") return detail;
  if (typeof error.response?.data?.error?.message === "string") {
    return error.response.data.error.message;
  }
  if (typeof detail === "string") return detail;
  return error.message || fallback;
}

export async function registerUser(payload: RegisterPayload) {
  const { data } = await api.post("/api/auth/register", payload);
  return data;
}

export async function requestRegistrationOtp(
  payload: OtpRequestPayload,
): Promise<OtpDispatchResponse> {
  const { data } = await api.post<OtpDispatchResponse>("/api/auth/register/request-otp", payload);
  return data;
}

export async function loginUser(payload: LoginPayload): Promise<LoginResponse> {
  const { data } = await api.post<LoginResponse>("/api/auth/login", payload);
  return data;
}

export async function requestPasswordResetOtp(
  payload: OtpRequestPayload,
): Promise<OtpDispatchResponse> {
  const { data } = await api.post<OtpDispatchResponse>("/api/auth/password-reset/request-otp", payload);
  return data;
}

export async function confirmPasswordReset(
  payload: PasswordResetConfirmPayload,
): Promise<MessageResponse> {
  const { data } = await api.post<MessageResponse>("/api/auth/password-reset/confirm", payload);
  return data;
}

export async function fetchDashboardSummary(): Promise<DashboardSummary> {
  const { data } = await api.get<DashboardSummary>("/api/dashboard/summary");
  return data;
}

export async function fetchRecommendations(): Promise<Recommendation[]> {
  const { data } = await api.get<Recommendation[]>("/api/recommendations");
  return data;
}

export async function fetchRecommendationSummary(resourceId: string): Promise<RecommendationSummary> {
  const encoded = encodeURIComponent(resourceId);
  const { data } = await api.get<RecommendationSummary>(`/api/recommendations/${encoded}/summary`);
  return data;
}

export async function fetchGroupedRecommendations(): Promise<GroupedRecommendation[]> {
  const { data } = await api.get<GroupedRecommendation[]>("/api/recommendations/grouped");
  return data;
}

export async function fetchDataTemperature(): Promise<DataTemperature> {
  const { data } = await api.get<DataTemperature>("/api/data-temperature");
  return data;
}

export async function fetchUserMigrations(): Promise<UserMigration[]> {
  const { data } = await api.get<UserMigration[]>("/api/migrations");
  return data;
}

export async function authorizeMigration(
  payload: MigrationAuthorizeRequest,
): Promise<MigrationAuthorizeResponse> {
  const { data } = await api.post<MigrationAuthorizeResponse>("/migrations/authorize", payload);
  return data;
}

export async function fetchAdminUsers(): Promise<AdminUser[]> {
  const { data } = await api.get<AdminUser[]>("/api/admin/users");
  return data;
}

export async function fetchAdminUserDetail(userId: number): Promise<AdminUserDetail> {
  const { data } = await api.get<AdminUserDetail>(`/api/admin/users/${userId}/detail`);
  return data;
}

export async function fetchAdminMetrics(): Promise<AdminMetrics> {
  const { data } = await api.get<AdminMetrics>("/api/admin/metrics");
  return data;
}

export async function fetchAdminMigrations(): Promise<AdminMigration[]> {
  const { data } = await api.get<AdminMigration[]>("/api/admin/migrations");
  return data;
}

export async function fetchBillingOverview(): Promise<BillingOverview> {
  const { data } = await api.get<BillingOverview>("/api/billing/overview");
  return data;
}

export async function fetchBillingCatalog(): Promise<BillingCatalog> {
  const { data } = await api.get<BillingCatalog>("/api/billing/catalog");
  return data;
}

export async function fetchPublicDatasetSources(): Promise<PublicDatasetSource[]> {
  const { data } = await api.get<PublicDatasetSource[]>("/api/admin/public-datasets/sources");
  return data;
}

export async function ingestPublicDataset(sourceKey: string, limit = 500): Promise<PublicDatasetIngestResponse> {
  const { data } = await api.post<PublicDatasetIngestResponse>("/api/admin/public-datasets/ingest", {
    source_key: sourceKey,
    limit,
  });
  return data;
}

export async function uploadIngestionFile(file: File): Promise<IngestionUploadResponse> {
  const formData = new FormData();
  formData.append("file", file);
  const { data } = await api.post<IngestionUploadResponse>("/api/v1/ingestion/upload", formData, {
    headers: { "Content-Type": "multipart/form-data" },
    timeout: 60000,
  });
  return data;
}

export async function fetchIngestionJobs(limit = 50): Promise<IngestionJobStatus[]> {
  const { data } = await api.get<IngestionJobStatus[]>("/api/v1/ingestion/jobs", {
    params: { limit },
  });
  return data;
}

export async function connectIntegration(
  payload: IntegrationConnectPayload,
): Promise<IntegrationConnectResponse> {
  const { data } = await api.post<IntegrationConnectResponse>("/api/v2/integrations/connect", payload);
  return data;
}

export async function fetchIntegrationStatus(): Promise<IntegrationStatus[]> {
  const { data } = await api.get<IntegrationStatus[]>("/api/v2/integrations/status");
  return data;
}

export async function syncIntegration(integrationId: number): Promise<IntegrationSyncResponse> {
  const { data } = await api.post<IntegrationSyncResponse>("/api/v2/integrations/sync", {
    integration_id: integrationId,
  });
  return data;
}

export async function fetchAdminRecords(userId?: number, limit = 100): Promise<AdminIngestedRecord[]> {
  const { data } = await api.get<AdminIngestedRecord[]>("/api/admin/records", {
    params: {
      ...(userId ? { user_id: userId } : {}),
      limit,
    },
  });
  return data;
}

export async function updateAdminRecordExternalId(
  recordId: number,
  externalId: string,
): Promise<AdminIngestedRecord> {
  const { data } = await api.patch<AdminIngestedRecord>(`/api/admin/records/${recordId}`, {
    external_id: externalId,
  });
  return data;
}

export async function deleteAdminRecord(recordId: number): Promise<MessageResponse> {
  const { data } = await api.delete<MessageResponse>(`/api/admin/records/${recordId}`);
  return data;
}

export async function fetchLatestPricingVersion(): Promise<PricingVersionResponse> {
  const { data } = await api.get<PricingVersionResponse>("/api/pricing/version/latest");
  return data;
}

export async function runAzurePricingSync(): Promise<AzurePricingSyncResponse> {
  const { data } = await api.post<AzurePricingSyncResponse>("/api/pricing/admin/azure/sync");
  return data;
}

export async function runAwsPricingSync(maxRecords = 1000): Promise<CloudPricingSyncResponse> {
  const { data } = await api.post<CloudPricingSyncResponse>("/api/pricing/admin/aws/sync", null, {
    params: { max_records: maxRecords },
  });
  return data;
}

export async function runGcpPricingSync(maxPages = 8, maxRecords = 1000): Promise<CloudPricingSyncResponse> {
  const { data } = await api.post<CloudPricingSyncResponse>("/api/pricing/admin/gcp/sync", null, {
    params: { max_pages: maxPages, max_records: maxRecords },
  });
  return data;
}

export async function fetchPricingDecision(payload: PricingDecisionRequest): Promise<PricingDecisionResponse> {
  const { data } = await api.post<PricingDecisionResponse>("/api/pricing/decision", payload);
  return data;
}

export async function fetchTopSavingsOpportunities(limit = 10): Promise<TopSavingsResponse> {
  const { data } = await api.get<TopSavingsResponse>("/api/pricing/opportunities/top", {
    params: { limit },
  });
  return data;
}

export const authStorageKey = AUTH_STORAGE_KEY;
