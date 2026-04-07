# CostIntel Pipeline Enterprise Enhancements

## 1. Data Ingestion Architecture (How Users Provide Data)

### Ingestion Channels

#### A. Manual File Upload (Finance / onboarding / demos)
- Endpoint: `POST /api/v1/ingestion/upload`
- Auth: JWT
- Content type: `multipart/form-data` (`.csv` or `.json`)
- Async processing: Celery task `backend.app.workers.tasks.process_ingestion_upload_job`
- Status APIs:
  - `GET /api/v1/ingestion/jobs`
  - `GET /api/v1/ingestion/jobs/{job_id}`

Processing flow:
1. Validate file schema.
2. Persist raw file to upload storage.
3. Create ingestion job (`PENDING`).
4. Celery worker parses + normalizes rows.
5. Attach records to tenant/user.
6. Mark job `READY` or `FAILED`.

Mandatory metadata embedded per ingested row:
```json
{
  "tenant_id": "tenant-<user_id>",
  "uploaded_by": "<user_email>",
  "data_origin": "USER_UPLOAD",
  "is_billable": true
}
```

#### B. API-Based Programmatic Ingestion (engineering / CI)
- Endpoint: `POST /api/v1/ingestion/events`
- Auth: API key (`X-API-Key`)
- Idempotency required: payload `idempotency_key` or `X-Idempotency-Key`
- Required fields:
  - `source_type`
  - `resource_id`
  - `timestamp`
  - `usage_metrics` / `cost_metrics`

Processing flow:
1. Authenticate API key.
2. Enforce idempotency.
3. Validate schema.
4. Persist raw + normalized event.
5. Update usage counters for analytics/billing preview.

#### C. Official Cloud Integrations (continuous enterprise mode)
- Endpoints:
  - `POST /api/v2/integrations/connect`
  - `POST /api/v2/integrations/sync`
  - `GET /api/v2/integrations/status`
- Auth: JWT
- Credential handling: encrypted at rest (`auth_config.encrypted_credentials`)
- Scope: read-only integration model

Supported providers in this phase:
- AWS
- GCP
- Azure

### Public Dataset Testing Mode

Admin-only APIs:
- `GET /api/admin/public-datasets/sources`
- `POST /api/admin/public-datasets/ingest`

Every public-dataset record is tagged:
```json
{
  "data_origin": "PUBLIC_DATASET",
  "source_name": "<DATASET_NAME>",
  "is_billable": false
}
```

Controls:
- never billable
- never payment-enforced
- isolated synthetic tenants
- visible in dashboards for realistic testing

## 2. OTP Reset Implementation (DB + Security)

- OTP is persisted in DB table (`otp_codes`) with:
  - hashed code only
  - TTL (`expires_at`)
  - retry counter (`attempt_count`)
  - one-time consume marker (`consumed_at`)
- OTP is never stored in memory-only state.
- OTP delivery is async (`BackgroundTasks`) to keep API latency stable.

Password reset flow:
1. `POST /api/auth/password-reset/request-otp`
2. OTP generated and hash stored.
3. OTP sent via async email sender.
4. `POST /api/auth/password-reset/confirm`
5. OTP is verified, consumed, password rotated.

Security hardening:
- request endpoint returns generic message (anti-enumeration)
- confirm endpoint returns generic invalid/expired message
- max retry attempts enforced

## 3. Billing & Payment UI API Contracts (Non-Enforcing)

Billing visibility APIs:
- `GET /api/billing/overview`
- `GET /api/billing/catalog`

Contract goals:
- show current plan and usage %
- show pricing cards + FAQ
- expose `payment_enforcement_enabled` flag
- expose upgrade/contact CTA text

Current runtime policy:
- `PAYMENT_ENFORCEMENT_ENABLED=false`
- no user blocking
- no quota hard-enforcement

## 4. Admin User-Detail Aggregated API

- Endpoint: `GET /api/admin/users/{user_id}/detail`
- Single response includes:
  - `basic_profile` (email, tenant, status, role)
  - `auth_info` (API keys, last login)
  - `usage_metrics` (API calls + ingested volume)
  - `cost_insights` (cost + savings + overage)
  - `decisions_triggered` (recommendations/migrations)
  - `webhooks_fired` (volume/failures/latest)
  - `billing_status` (read-only, includes `is_billable`)

## 5. Enterprise UI/UX Structure (Frontend-Ready Wireframe)

### Visual Direction
- neutral/clean enterprise surfaces
- high information density with clear hierarchy
- minimal motion, focus on status and decisions

### Landing Page
1. Hero value proposition
2. Cloud waste problem framing
3. Pipeline explanation (collect -> classify -> optimize -> migrate)
4. Capability grid
5. Audience segmentation (FinOps/Admin/Platform)
6. Security and trust
7. Pricing preview (non-enforcing)
8. CTA (Start Free / Contact Sales)

### Global Nav
Logo | Features | Pricing | Docs | About Us | Contact Us | Login | Register

### User App IA
- Dashboard
- Data Sources
- Billing
- Profile/Auth

### Data Sources Page
- Manual Upload card + status table
- Programmatic ingestion contract section
- Integration connect/sync/status panel

### Admin IA
- Tenant/User list
- User drill-down
- Public dataset controls
- System health
- Migration and decision logs

## 6. Edge Cases & Failure Handling

- file upload schema mismatch -> `400` with non-sensitive reason
- duplicate idempotency key -> `409`
- Celery dispatch unavailable -> fallback inline background processing
- integration sync credential/endpoint failure -> source status `FAILED`
- Redis outage -> usage aggregation falls back to DB
- public dataset source unavailable -> fallback sample rows
- OTP brute-force -> retry cap + generic response

## 7. Future Payment Enforcement Notes

- keep feature-flagged enforcement (`PAYMENT_ENFORCEMENT_ENABLED`)
- add tenant-level controlled rollout
- phase strategy:
  1. warnings
  2. soft throttling
  3. restricted writes
  4. suspension
- maintain immutable audit trail for all account-state transitions
