# Cloudteck Revenue API Platform (Production Blueprint)

## 1. High-Level System Architecture Diagram (ASCII)

```text
┌──────────────────────────────────────────────────────────────────────────┐
│                               Clients                                    │
│  SDKs / B2B Apps / Frontend / Batch Uploaders / Partner Webhooks        │
└───────────────┬───────────────────────────────┬──────────────────────────┘
                │                               │
                ▼                               ▼
      ┌───────────────────┐             ┌──────────────────────┐
      │ API Gateway/LB    │             │ Webhook Endpoints    │
      │ (TLS, WAF, rate)  │             │ (signature + idempot)│
      └─────────┬─────────┘             └──────────┬───────────┘
                │                                   │
                ▼                                   ▼
         ┌────────────────────────────────────────────────────┐
         │ FastAPI Control Plane                              │
         │ - Auth (JWT + API Key)                             │
         │ - Plan enforcement                                  │
         │ - /v1 data APIs                                     │
         │ - Billing/Usage APIs                                │
         │ - Admin APIs                                         │
         └───────┬──────────────────────┬──────────────────────┘
                 │                      │
                 ▼                      ▼
      ┌─────────────────────┐   ┌─────────────────────────────┐
      │ Redis               │   │ Celery Workers / Schedulers │
      │ - usage counters    │   │ - official sync jobs        │
      │ - idempotency keys  │   │ - usage flush               │
      │ - queue broker      │   │ - billing close/invoicing   │
      └─────────┬───────────┘   └─────────────┬───────────────┘
                │                             │
                └──────────────┬──────────────┘
                               ▼
                    ┌─────────────────────────┐
                    │ PostgreSQL              │
                    │ - users/plans/accounts  │
                    │ - raw + normalized data │
                    │ - usage raw + aggregate │
                    │ - billing/invoices/paym │
                    │ - webhook audit trail   │
                    └──────────┬──────────────┘
                               ▼
                      ┌───────────────────┐
                      │ Grafana/Prometheus│
                      │ metrics + alerts  │
                      └───────────────────┘
```

## 2. Data Ingestion Flows

### Official API Ingestion
1. Admin/user configures source via `/api/ingestion/official/sync`.
2. Worker/API client fetches upstream API with auth headers.
3. Retry/backoff handles transient failures and 429.
4. Raw payload stored in `ingested_records.raw_payload`.
5. Normalized object stored in `ingested_records.normalized_payload`.
6. Incremental cursor updated in `data_sources.sync_cursor`.
7. Source-level ingestion cost tracked in `data_sources.ingestion_cost`.

### Webhook-Based Real-Time Ingestion
1. External provider POSTs to `/api/webhooks/{provider}`.
2. Signature validated (Razorpay/webhook secret).
3. Idempotency key (`provider + event_id`) enforced in `webhook_events`.
4. Raw event persisted immediately (`webhook_events.payload`).
5. Background processing normalizes and upserts into `ingested_records`.
6. Status updates: `RECEIVED -> PROCESSED/FAILED/DUPLICATE`.

### User-Submitted Data
1. API key users submit JSON via `POST /v1/data`.
2. File uploads via `POST /v1/data/upload` (CSV/JSON).
3. SDK events can call same endpoint with `ingestion_method=SDK_EVENT`.
4. Validation + normalization performed server-side.
5. Data linked to `user_id`, `api_key_id`, ingestion method, timestamp.
6. Volume counted for usage and billing.

## 3. REST API Design Examples

### Auth & API keys
- `POST /api/auth/login` (JWT)
- `POST /api/keys` (create hashed API key)
- `GET /api/keys`
- `POST /api/keys/{id}/revoke`

### Versioned Data APIs (`X-API-Key` required)
- `POST /v1/data`
- `GET /v1/data?page=1&page_size=50&sort_by=created_at&sort_order=desc`
- `GET /v1/data?ingestion_method=WEBHOOK&fields=id,name,status`
- `GET /v1/data/{id}`
- `POST /v1/data/upload`
- `GET /v1/usage`
- `GET /v1/billing`

### Billing & payments
- `POST /api/payments/razorpay/order`
- `POST /api/payments/razorpay/webhook`
- `POST /api/admin/billing/close-cycles`

### Admin observability
- `GET /api/admin/users`
- `GET /api/admin/metrics`
- `POST /api/admin/usage/flush`
- `GET /metrics`

## 4. Database Schema (SQL)

```sql
-- users (existing)
CREATE TABLE users (
  id SERIAL PRIMARY KEY,
  name VARCHAR(120) NOT NULL,
  email VARCHAR(255) UNIQUE NOT NULL,
  hashed_password VARCHAR(255) NOT NULL,
  company_name VARCHAR(255) NOT NULL,
  cloud_provider VARCHAR(16) NOT NULL,
  role VARCHAR(16) NOT NULL,
  is_active BOOLEAN NOT NULL DEFAULT TRUE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX ix_users_email ON users(email);

CREATE TABLE plans (
  id SERIAL PRIMARY KEY,
  code VARCHAR(32) UNIQUE NOT NULL,
  name VARCHAR(80) NOT NULL,
  description VARCHAR(255) NOT NULL,
  base_monthly_price NUMERIC(10,2) NOT NULL,
  included_requests INTEGER NOT NULL,
  overage_price_per_request NUMERIC(10,6) NOT NULL,
  currency VARCHAR(8) NOT NULL,
  is_active BOOLEAN NOT NULL DEFAULT TRUE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX ix_plans_code ON plans(code);

CREATE TABLE user_accounts (
  id SERIAL PRIMARY KEY,
  user_id INTEGER UNIQUE NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  plan_id INTEGER NOT NULL REFERENCES plans(id),
  account_state VARCHAR(32) NOT NULL,
  billing_currency VARCHAR(8) NOT NULL DEFAULT 'USD',
  billing_region VARCHAR(32) NOT NULL DEFAULT 'IN',
  trial_ends_at TIMESTAMPTZ NULL,
  grace_period_ends_at TIMESTAMPTZ NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX ix_user_accounts_state ON user_accounts(account_state);

CREATE TABLE api_keys (
  id SERIAL PRIMARY KEY,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  name VARCHAR(120) NOT NULL,
  key_prefix VARCHAR(24) UNIQUE NOT NULL,
  key_hash VARCHAR(255) UNIQUE NOT NULL,
  scopes VARCHAR(255) NOT NULL,
  is_active BOOLEAN NOT NULL DEFAULT TRUE,
  last_used_at TIMESTAMPTZ NULL,
  revoked_at TIMESTAMPTZ NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX ix_api_keys_user ON api_keys(user_id);
CREATE INDEX ix_api_keys_prefix ON api_keys(key_prefix);

CREATE TABLE data_sources (
  id SERIAL PRIMARY KEY,
  user_id INTEGER NULL REFERENCES users(id) ON DELETE SET NULL,
  source_type VARCHAR(32) NOT NULL,
  provider VARCHAR(64) NOT NULL,
  name VARCHAR(120) NOT NULL,
  auth_config JSONB NULL,
  sync_cursor VARCHAR(255) NULL,
  last_synced_at TIMESTAMPTZ NULL,
  ingestion_cost NUMERIC(12,6) NOT NULL DEFAULT 0,
  status VARCHAR(32) NOT NULL DEFAULT 'ACTIVE',
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX ix_data_sources_user ON data_sources(user_id);
CREATE INDEX ix_data_sources_provider ON data_sources(provider);

CREATE TABLE ingested_records (
  id SERIAL PRIMARY KEY,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  api_key_id INTEGER NULL REFERENCES api_keys(id) ON DELETE SET NULL,
  data_source_id INTEGER NULL REFERENCES data_sources(id) ON DELETE SET NULL,
  ingestion_method VARCHAR(32) NOT NULL,
  schema_version VARCHAR(32) NOT NULL,
  external_id VARCHAR(255) NULL,
  idempotency_key VARCHAR(128) NULL,
  lineage_ref VARCHAR(255) NOT NULL,
  content_hash VARCHAR(128) NOT NULL,
  raw_payload JSONB NOT NULL,
  normalized_payload JSONB NOT NULL,
  is_processed BOOLEAN NOT NULL DEFAULT TRUE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  processed_at TIMESTAMPTZ NULL,
  CONSTRAINT uq_ingested_user_method_idempotency
    UNIQUE (user_id, ingestion_method, idempotency_key)
);
CREATE INDEX ix_ingested_user_created ON ingested_records(user_id, created_at DESC);
CREATE INDEX ix_ingested_external ON ingested_records(external_id);
CREATE INDEX ix_ingested_hash ON ingested_records(content_hash);

CREATE TABLE usage_events (
  id SERIAL PRIMARY KEY,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  api_key_id INTEGER NULL REFERENCES api_keys(id) ON DELETE SET NULL,
  endpoint VARCHAR(255) NOT NULL,
  method VARCHAR(16) NOT NULL,
  request_count INTEGER NOT NULL DEFAULT 1,
  data_volume_bytes INTEGER NOT NULL DEFAULT 0,
  compute_units INTEGER NOT NULL DEFAULT 0,
  idempotency_key VARCHAR(128) NULL,
  request_hash VARCHAR(128) NOT NULL,
  occurred_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX ix_usage_events_user_time ON usage_events(user_id, occurred_at DESC);
CREATE INDEX ix_usage_events_api ON usage_events(api_key_id);
CREATE INDEX ix_usage_events_endpoint ON usage_events(endpoint);

CREATE TABLE usage_aggregates (
  id SERIAL PRIMARY KEY,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  api_key_id INTEGER NULL REFERENCES api_keys(id) ON DELETE SET NULL,
  endpoint VARCHAR(255) NOT NULL,
  bucket VARCHAR(8) NOT NULL,
  bucket_start TIMESTAMPTZ NOT NULL,
  request_count INTEGER NOT NULL DEFAULT 0,
  data_volume_bytes INTEGER NOT NULL DEFAULT 0,
  compute_units INTEGER NOT NULL DEFAULT 0,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT uq_usage_aggregate_bucket
    UNIQUE (user_id, api_key_id, endpoint, bucket_start, bucket)
);
CREATE INDEX ix_usage_agg_user_bucket ON usage_aggregates(user_id, bucket_start DESC);

CREATE TABLE billing_cycles (
  id SERIAL PRIMARY KEY,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  plan_id INTEGER NOT NULL REFERENCES plans(id),
  starts_at TIMESTAMPTZ NOT NULL,
  ends_at TIMESTAMPTZ NOT NULL,
  status VARCHAR(16) NOT NULL,
  included_quota INTEGER NOT NULL,
  request_count INTEGER NOT NULL DEFAULT 0,
  overage_count INTEGER NOT NULL DEFAULT 0,
  base_amount NUMERIC(12,2) NOT NULL DEFAULT 0,
  overage_amount NUMERIC(12,2) NOT NULL DEFAULT 0,
  total_amount NUMERIC(12,2) NOT NULL DEFAULT 0,
  currency VARCHAR(8) NOT NULL DEFAULT 'USD',
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX ix_billing_cycles_user_period ON billing_cycles(user_id, starts_at DESC);
CREATE INDEX ix_billing_cycles_status ON billing_cycles(status);

CREATE TABLE invoices (
  id SERIAL PRIMARY KEY,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  billing_cycle_id INTEGER UNIQUE NOT NULL REFERENCES billing_cycles(id) ON DELETE CASCADE,
  invoice_number VARCHAR(64) UNIQUE NOT NULL,
  status VARCHAR(16) NOT NULL,
  amount NUMERIC(12,2) NOT NULL,
  currency VARCHAR(8) NOT NULL,
  issued_at TIMESTAMPTZ NULL,
  due_at TIMESTAMPTZ NULL,
  paid_at TIMESTAMPTZ NULL,
  metadata_json JSONB NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX ix_invoices_user_status ON invoices(user_id, status);

CREATE TABLE payments (
  id SERIAL PRIMARY KEY,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  invoice_id INTEGER NULL REFERENCES invoices(id) ON DELETE SET NULL,
  provider VARCHAR(32) NOT NULL,
  provider_order_id VARCHAR(128) NULL,
  provider_payment_id VARCHAR(128) NULL,
  event_type VARCHAR(128) NOT NULL,
  status VARCHAR(16) NOT NULL,
  amount NUMERIC(12,2) NOT NULL,
  currency VARCHAR(8) NOT NULL,
  raw_event JSONB NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX ix_payments_user ON payments(user_id, created_at DESC);
CREATE INDEX ix_payments_provider_ref ON payments(provider, provider_payment_id);

CREATE TABLE subscriptions (
  id SERIAL PRIMARY KEY,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  plan_id INTEGER NOT NULL REFERENCES plans(id),
  provider VARCHAR(32) NOT NULL,
  provider_subscription_id VARCHAR(128) UNIQUE NOT NULL,
  status VARCHAR(16) NOT NULL,
  current_period_start TIMESTAMPTZ NULL,
  current_period_end TIMESTAMPTZ NULL,
  cancel_at_period_end BOOLEAN NOT NULL DEFAULT FALSE,
  metadata_json JSONB NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX ix_subscriptions_user ON subscriptions(user_id, created_at DESC);

CREATE TABLE webhook_events (
  id SERIAL PRIMARY KEY,
  provider VARCHAR(64) NOT NULL,
  event_id VARCHAR(255) NOT NULL,
  user_id INTEGER NULL REFERENCES users(id) ON DELETE SET NULL,
  signature VARCHAR(255) NULL,
  payload JSONB NOT NULL,
  status VARCHAR(16) NOT NULL,
  error_message VARCHAR(500) NULL,
  received_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  processed_at TIMESTAMPTZ NULL,
  CONSTRAINT uq_webhook_provider_event UNIQUE (provider, event_id)
);
CREATE INDEX ix_webhook_received ON webhook_events(received_at DESC);
```

## 5. Usage Tracking Logic (Pseudo-code)

```python
def handle_v1_request(user, api_key, endpoint, method, idempotency_key):
    validate_account_state(user)
    enforce_plan_access(user, endpoint)

    if idempotency_key and already_seen(idempotency_key, user, endpoint):
        return previous_response_or_ack()

    redis_key = build_usage_key(user.id, api_key.id, endpoint, hour_bucket(now))
    redis.hincrby(redis_key, "request_count", 1)
    redis.hincrby(redis_key, "data_volume_bytes", payload_size)
    redis.sadd("usage:pending_keys", redis_key)
    redis.expire(redis_key, TTL)

    db.insert_usage_event(
      user_id=user.id, api_key_id=api_key.id,
      endpoint=endpoint, method=method,
      request_count=1, occurred_at=now
    )
    db.increment_open_cycle_request_count(user.id, +1)
```

## 6. Billing Calculation Logic

```python
def compute_cycle_bill(plan, usage_count):
    included = plan.included_requests
    base = plan.base_monthly_price
    overage_count = max(usage_count - included, 0)
    overage_amount = overage_count * plan.overage_price_per_request
    total = base + overage_amount
    return {
      "included_quota": included,
      "usage_count": usage_count,
      "overage_count": overage_count,
      "base_amount": base,
      "overage_amount": overage_amount,
      "total_amount": total
    }
```

Determinism rules:
- No frontend-calculated billing.
- Inputs are immutable usage and plan snapshots.
- Invoices are linked to billing cycle IDs.
- Re-calculation against same cycle data must produce same totals.

## 7. Razorpay Integration Flow

1. Backend receives invoice/checkout request.
2. Backend creates Razorpay order using secret key (never from frontend).
3. Frontend uses returned order ID only for checkout UI.
4. Razorpay sends webhook to backend.
5. Backend verifies `X-Razorpay-Signature` using HMAC SHA-256.
6. Backend persists payment event + updates invoice/subscription/account state.
7. Access changes only after backend payment confirmation.

## 8. Webhook Handler Example

```python
@app.post("/api/webhooks/{provider}")
async def webhook(provider: str, request: Request):
    raw = await request.body()
    payload = json.loads(raw)
    event_id = request.headers["X-Webhook-Id"] or payload["id"]
    signature = request.headers.get("X-Webhook-Signature")

    if provider == "razorpay":
        verify_signature(raw, signature)

    event = save_if_new(provider, event_id, payload, signature)
    if event.is_duplicate:
        return {"status": "DUPLICATE"}

    queue_background_processing(event.id)
    return {"status": "RECEIVED"}
```

## 9. Failure & Edge-Case Handling

- Upstream API rate limit: retry with exponential backoff; store sync cursor and continue.
- Webhook duplicates: unique `(provider, event_id)`; mark `DUPLICATE`.
- Replay attacks: signature + timestamp/idempotency windows.
- Redis outage: fallback to DB-only usage inserts.
- Payment webhook out-of-order: idempotent status transitions by provider IDs.
- Billing disputes: raw usage events + cycle snapshots + invoices are audit trail.
- Over-quota users: transition to `PAYMENT_DUE`, then `SUSPENDED` after grace period.

## 10. Scalability & Cost Optimization Tips

- Partition `usage_events` and `ingested_records` by time for large tenants.
- Keep hot counters in Redis, flush in batches.
- Materialize daily aggregates for analytics dashboards.
- Use read replicas for `/v1/data` and `/v1/usage` read paths.
- Compress large raw payloads (JSONB + TOAST, or object storage pointers).
- Cache expensive `GET /v1/data` queries with short TTL and `Vary: X-API-Key`.
- Introduce async bulk ingestion and dead-letter queue for failed webhook processing.
