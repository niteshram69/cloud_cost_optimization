export type CloudProvider = "AWS" | "AZURE" | "GCP" | "MULTI";
export type UserRole = "USER" | "ADMIN";

export interface AuthUser {
  id: number;
  name: string;
  email: string;
  company_name: string;
  cloud_provider: CloudProvider;
  role: UserRole;
  created_at: string;
}

export interface LoginPayload {
  email: string;
  password: string;
}

export interface RegisterPayload {
  name: string;
  email: string;
  password: string;
  company_name: string;
  cloud_provider: CloudProvider;
  otp_code?: string;
}

export interface OtpRequestPayload {
  email: string;
}

export interface OtpDispatchResponse {
  message: string;
  expires_in_seconds: number;
  debug_otp?: string | null;
}

export interface PasswordResetConfirmPayload {
  email: string;
  otp_code?: string;
  new_password: string;
}

export interface MessageResponse {
  message: string;
}

export interface LoginResponse {
  access_token: string;
  token_type: string;
  user: AuthUser;
}

export interface DashboardSummary {
  total_storage_cost: number;
  estimated_monthly_savings: number;
  hot_percentage: number;
  cold_percentage: number;
  archive_percentage: number;
  pricing_version?: string | null;
  system_mode: "ANALYSIS_MODE" | "EXECUTION_MODE";
  analysis_ready: boolean;
  execution_authorized: boolean;
  provider_authority: ProviderAuthority[];
  dataset_id?: number | null;
  dataset_label?: string | null;
  dataset_source?: string | null;
  dataset_source_label?: string | null;
  dataset_record_count?: number | null;
  dataset_created_at?: string | null;
}

export interface ProviderAuthority {
  provider: "AWS" | "AZURE" | "GCP";
  ingestion_mode: string;
  integration_permission: string;
  mode: "ANALYSIS_MODE" | "EXECUTION_MODE";
  execution_authorized: boolean;
  reason: string;
}

export interface Recommendation {
  id: number;
  resource_name: string;
  current_tier: string;
  current_provider: string;
  recommended_tier: string;
  recommended_provider: string;
  intent_tier?: string | null;
  observed_tier?: string | null;
  observed_temperature?: string | null;
  access_recency_score?: number | null;
  migration_risk?: number | null;
  temperature_score?: number | null;
  estimated_monthly_savings: number;
  priority: string;
  status: string;
  feature_snapshot: Record<string, string | number>;
  confidence_score: number;
  confidence_final: number;
  model_confidence: number;
  ml_confidence: number;
  data_maturity: "SYNTHETIC_MATURE" | "EXPORT_MATURE" | "LIVE_MATURE";
  data_maturity_score: number;
  billing_realism: "ESTIMATE" | "EXPORT" | "LIVE";
  execution_authority: "NONE" | "DRY_RUN_ONLY" | "WRITE_ENABLED";
  operational_readiness: number;
  operational_readiness_band: "READY" | "CONDITIONAL" | "LOW_MATURITY";
  operational_readiness_reasons: string[];
  decision_state: "EXPLORATORY" | "PREDICTED" | "FALLBACK" | "NO_OP" | "BLOCKED";
  recommendation_action: "PROPOSED" | "NO_OP";
  recommendation_state:
    | "BLOCKED_BY_AUTHORITY"
    | "BLOCKED_BY_GUARDRAIL"
    | "READY_FOR_DRY_RUN"
    | "READY_FOR_EXECUTION";
  migration_state: string;
  rule_override_trace: string[];
  guardrail_trace: string[];
  confidence_trace: Record<string, number>;
  pricing_trace: Record<string, unknown>;
  pricing_source?: string | null;
  pricing_confidence?: string | null;
  ingestion_mode: string;
  integration_permission: string;
  execution_eligibility: "NONE" | "DRY_RUN_ELIGIBLE" | "EXECUTABLE";
  execution_reason: string;
  execution_unlock_hint: string;
  current_monthly_cost?: number | null;
  optimized_monthly_cost?: number | null;
  estimated_savings_percent?: number | null;
  pricing_version?: string | null;
  pricing_candidates?: Array<Record<string, string | number>>;
  cost_assumptions?: Record<string, string>;
  migration_advisory?: {
    strategy: string;
    tool: string;
    downtime_required: boolean;
    estimated_time_hours: number;
    risk_level: string;
    lifecycle_state: string;
    lifecycle_path: string[];
    steps: string[];
  } | null;
  decision_trace_block?: string | null;
  created_at: string;
}

export interface RecommendationSummary {
  resource_id: string;
  provider: string;
  current_tier: string;
  recommended_tier: string;
  classification: string;
  lifecycle_stage: string;
  temperature_score: number;
  recency_score: number;
  momentum: number;
  access_volatility: number;
  access_frequency: number;
  effective_access: number;
  requests_30d: number;
  requests_90d: number;
  last_access_days?: number | null;
  storage_cost_current?: number | null;
  storage_cost_recommended?: number | null;
  estimated_savings: number;
  migration_risk: string;
  migration_risk_score?: number | null;
  confidence: number;
  execution_eligibility: string;
  predicted_archive_in_days?: number | null;
  reasoning: string[];
}

export interface GroupedRecommendation {
  group_key: string;
  data_temperature: string;
  recommended_provider: string;
  recommended_tier: string;
  dataset_count: number;
  avg_monthly_savings: number;
  total_monthly_savings: number;
  avg_confidence_score: number;
  risk_level: string;
  pricing_version?: string | null;
  preview_resource_names: string[];
}

export interface DataTemperature {
  hot_count: number;
  warm_count?: number;
  cold_count: number;
  archive_count: number;
}

export interface UserMigration {
  id: number;
  resource_name: string;
  source_provider: string;
  target_provider: string;
  status: string;
  progress_percent: number;
  before_monthly_cost: number;
  after_monthly_cost: number;
  cost_delta: number;
  risk_score: number;
  rollback_plan: string;
  error_message: string | null;
  started_at: string | null;
  completed_at: string | null;
  created_at: string;
}

export interface AdminUser {
  id: number;
  name: string;
  email: string;
  company_name: string;
  cloud_provider: string;
  role: string;
  is_active: boolean;
  account_state: string;
  plan_code: string;
  subscription_status: string | null;
  current_cycle_usage: number;
  included_quota: number;
  overage_usage: number;
  estimated_cycle_amount: number;
  currency: string;
  last_payment_status: string | null;
  created_at: string;
}

export interface RegionUsage {
  provider: string;
  region: string;
  storage_cost: number;
}

export interface AdminMetrics {
  cloud_usage: {
    total_cost: number;
    by_provider: Record<string, number>;
    by_region: RegionUsage[];
  };
  classification_accuracy: {
    average_confidence: number;
    high_confidence_count: number;
    total_classified: number;
  };
  system_health: {
    active_users: number;
    running_migrations: number;
    failed_migrations: number;
    api_uptime_seconds: number;
    pricing_version?: string | null;
  };
}

export interface AdminMigration {
  id: number;
  user_id: number;
  resource_name: string;
  source_provider: string;
  target_provider: string;
  status: string;
  progress_percent: number;
  error_message: string | null;
  started_at: string | null;
  completed_at: string | null;
  created_at: string;
}

export interface AdminIngestedRecord {
  id: number;
  user_id: number;
  data_source_id: number | null;
  ingestion_method: string;
  schema_version: string;
  external_id: string | null;
  lineage_ref: string;
  raw_payload: Record<string, unknown>;
  normalized_payload: Record<string, unknown>;
  created_at: string;
  processed_at: string | null;
}

export interface BillingPlanCard {
  code: string;
  name: string;
  monthly_price: string;
  included_requests: number;
  overage_price_per_request: string;
  features: string[];
  cta: string;
}

export interface BillingCatalog {
  plans: BillingPlanCard[];
  faq: Array<{ q: string; a: string }>;
  payment_enforcement_enabled: boolean;
}

export interface BillingOverview {
  plan_code: string;
  account_state: string;
  usage_count: number;
  included_quota: number;
  usage_percent: number;
  payment_enforcement_enabled: boolean;
  upgrade_cta: string;
  contact_sales_cta: string;
}

export interface PublicDatasetSource {
  key: string;
  source_name: string;
  description: string;
  provider_hint: string;
  format: string;
  is_billable: boolean;
}

export interface PublicDatasetIngestResponse {
  source_key: string;
  source_name: string;
  tenant_id: number;
  inserted_records: number;
  skipped_records: number;
  is_billable: boolean;
}

export interface IngestionUploadResponse {
  job_id: number;
  status: string;
  file_name: string;
  data_origin: string;
  is_billable: boolean;
  message: string;
}

export interface IngestionJobStatus {
  job_id: number;
  status: string;
  file_name: string | null;
  source_type: string;
  record_count: number;
  error_message: string | null;
  data_origin: string;
  is_billable: boolean;
  created_at: string;
  updated_at: string;
}

export interface IntegrationConnectPayload {
  provider: "AWS" | "GCP" | "AZURE";
  source_name: string;
  endpoint_url: string;
  auth_type: string;
  credentials: Record<string, string>;
  sync_interval_minutes: number;
  is_read_only: boolean;
}

export interface IntegrationConnectResponse {
  integration_id: number;
  provider: string;
  source_name: string;
  status: string;
  sync_interval_minutes: number;
  is_read_only: boolean;
  created_at: string;
}

export interface IntegrationStatus {
  integration_id: number;
  provider: string;
  source_name: string;
  status: string;
  last_synced_at: string | null;
  sync_cursor: string | null;
  sync_interval_minutes: number;
  is_read_only: boolean;
}

export interface IntegrationSyncResponse {
  integration_id: number;
  provider: string;
  source_name: string;
  records_ingested: number;
  next_cursor: string | null;
  total_ingestion_cost: string;
  status: string;
}

export interface AdminUserDetail {
  basic_profile: {
    user_id: number;
    tenant_id: string;
    name: string;
    email: string;
    company_name: string;
    status: string;
    role: string;
    created_at: string;
  };
  auth_info: {
    last_login_at: string | null;
    api_keys: Array<{
      id: number;
      name: string;
      key_prefix: string;
      scopes: string[];
      is_active: boolean;
      last_used_at: string | null;
      created_at: string;
    }>;
  };
  usage_metrics: {
    total_api_calls: number;
    total_data_ingested_records: number;
    total_data_ingested_bytes_estimate: number;
    current_cycle_requests: number;
  };
  cost_insights: {
    total_storage_cost: number;
    estimated_monthly_savings: number;
    latest_cycle_total_amount: string;
    overage_usage: number;
    overage_amount: string;
  };
  decisions_triggered: {
    recommendations_total: number;
    recommendations_open: number;
    migrations_total: number;
    migrations_failed: number;
  };
  webhooks_fired: {
    total_events: number;
    failed_events: number;
    latest_event_at: string | null;
  };
  billing_status: {
    plan_code: string;
    account_state: string;
    subscription_status: string | null;
    latest_invoice_status: string | null;
    latest_payment_status: string | null;
    payment_enforced: boolean;
    is_billable: boolean;
  };
}

export interface PricingCandidate {
  cloud: string;
  native_tier: string;
  canonical_tier: string;
  region: string;
  storage_price_per_gb: number;
  retrieval_price_per_gb: number;
  monthly_cost: number;
  currency: string;
}

export interface PricingDecisionRequest {
  resource_id: string;
  data_temperature: "HOT" | "COLD" | "ARCHIVE";
  storage_gb: number;
  monthly_retrieval_gb: number;
  region_preference?: string | null;
  current_cloud?: string | null;
  current_tier?: string | null;
  current_monthly_cost?: number | null;
  currency?: string;
}

export interface PricingDecisionResponse {
  resource_id: string;
  data_temperature: string;
  current_cloud: string | null;
  current_tier: string | null;
  recommended_cloud: string;
  recommended_tier: string;
  current_monthly_cost: number;
  optimized_monthly_cost: number;
  estimated_savings_percent: number;
  pricing_version: string;
  currency: string;
  region_preference: string | null;
  candidates: PricingCandidate[];
  cost_assumptions: Record<string, string>;
  explanation: string;
}

export interface PricingVersionResponse {
  cloud: string;
  pricing_version: string;
  effective_date: string;
  currency: string;
  records_count: number;
  last_updated_at: string;
}

export interface AzurePricingSyncResponse {
  cloud: string;
  pricing_version: string;
  records_inserted: number;
  records_existing: number;
  source_url: string;
  sync_started_at: string;
  sync_completed_at: string;
  status: string;
}

export interface CloudPricingSyncResponse {
  cloud: string;
  pricing_version: string;
  records_inserted: number;
  records_existing: number;
  source_url: string;
  sync_started_at: string;
  sync_completed_at: string;
  status: string;
}

export interface TopSavingsOpportunity {
  resource_id: string;
  data_temperature: string;
  current_cloud: string;
  current_tier: string;
  recommended_cloud: string;
  recommended_tier: string;
  region: string;
  current_monthly_cost: number;
  optimized_monthly_cost: number;
  monthly_savings: number;
  estimated_savings_percent: number;
  pricing_version: string;
  currency: string;
}

export interface TopSavingsResponse {
  total_considered: number;
  total_monthly_savings: number;
  opportunities: TopSavingsOpportunity[];
  export: {
    generated_at: string;
    pricing_version: string;
    csv_headers: string[];
    csv_rows: string[][];
    pdf_payload: Record<string, unknown>;
  };
}

export interface MigrationAuthorizeRequest {
  recommendation_id?: number;
  resource_id?: string;
  approved_target_tier?: string;
  override_type?: "USER_CONFIRMED";
  justification?: string;
  override_confidence?: boolean;
  acknowledged_risks: Array<"LATENCY" | "RETRIEVAL_COST" | "MANUAL_OVERRIDE">;
}

export interface MigrationAuthorizeResponse {
  migration_plan_id: number;
  recommendation_id: number;
  resource_id: string;
  migration_state: string;
  execution_result: "COMPLETED" | "ROLLED_BACK" | "BLOCKED" | "SIMULATED_RESULTS";
  execution_eligibility: "NONE" | "DRY_RUN_ELIGIBLE" | "EXECUTABLE";
  message: string;
  confidence_final: number;
  guardrail_trace: string[];
  dry_run_report: Record<string, unknown>;
  monitoring_report?: Record<string, unknown> | null;
  audit_event_id?: number | null;
  authorized_at: string;
}
