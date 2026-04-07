# Cloudteck Backend (FastAPI + MySQL)

## Run

```bash
cd backend
cp .env.example .env
# default DATABASE_URL:
# mysql+pymysql://root@localhost:3306/cloudteck
mysql -uroot -e "CREATE DATABASE IF NOT EXISTS cloudteck CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
# set JWT_SECRET_KEY
../.venv/bin/pip install -r requirements.txt
../.venv/bin/uvicorn backend.app.main:app --host 127.0.0.1 --port 8001
```

## API Endpoints

- `POST /api/auth/register/request-otp`
- `POST /api/auth/register`
- `POST /api/auth/login`
- `POST /api/auth/password-reset/request-otp`
- `POST /api/auth/password-reset/confirm`
- `POST /api/keys`
- `GET /api/keys`
- `POST /api/keys/{api_key_id}/revoke`
- `POST /api/v1/ingestion/upload`
- `GET /api/v1/ingestion/jobs`
- `GET /api/v1/ingestion/jobs/{job_id}`
- `POST /api/v1/ingestion/events`
- `POST /ingest`
- `POST /api/v2/integrations/connect`
- `POST /api/v2/integrations/sync`
- `GET /api/v2/integrations/status`
- `POST /api/ingestion/official/sync`
- `GET /api/admin/public-datasets/sources`
- `POST /api/admin/public-datasets/ingest`
- `GET /api/billing/overview`
- `GET /api/billing/catalog`
- `POST /api/webhooks/{provider}`
- `POST /api/payments/razorpay/order`
- `POST /api/payments/razorpay/webhook`
- `POST /v1/data`
- `GET /v1/data`
- `GET /v1/data/{id}`
- `POST /v1/data/upload`
- `GET /v1/usage`
- `GET /v1/billing`
- `GET /api/dashboard/summary`
- `GET /api/recommendations`
- `GET /api/data-temperature`
- `GET /api/admin/users`
- `GET /api/admin/users/{user_id}/detail`
- `GET /api/admin/metrics`
- `GET /api/admin/migrations`
- `GET /api/admin/records`
- `PATCH /api/admin/records/{record_id}`
- `DELETE /api/admin/records/{record_id}`
- `GET /metrics`

## Bootstrap Admin

Default bootstrap admin credentials are controlled from `.env`:

- `BOOTSTRAP_ADMIN_EMAIL=nitesh.r@mindteck.us`
- `BOOTSTRAP_ADMIN_PASSWORD=mind@123`

The backend enforces this account on startup when `BOOTSTRAP_ADMIN_ENABLED=true`.

Integration credentials encryption key:

- `INTEGRATION_CREDENTIALS_SECRET=<secret>`
- `OTP_ENABLED=false` to bypass OTP for registration/reset in non-production
- `INGESTION_USE_CELERY=false` to process uploads asynchronously without broker dependency
- Metadata ingestion now uses a hybrid ML + rule classifier with engineered numeric
  features (`requests_30d`, `avg_latency_ms`, `monthly_cost_usd`, `log10(object_count+1)`)
  to classify HOT/COLD/ARCHIVE with confidence-based rule fallback.

## Reset Data (Keep Admin)

Clear historical operational data while preserving the bootstrap admin user:

```bash
mysql -uroot -D cloudteck -e "
SET SQL_SAFE_UPDATES=0;
SET FOREIGN_KEY_CHECKS=0;
DELETE FROM api_keys;
DELETE FROM billing_ingestion_runs;
DELETE FROM billing_usage_records;
DELETE FROM bucket_aggregates;
DELETE FROM bucket_object_references;
DELETE FROM data_sources;
DELETE FROM finops_recommendations;
DELETE FROM finops_resources;
DELETE FROM ingested_records;
DELETE FROM ingestion_jobs;
DELETE FROM invoices;
DELETE FROM login_audits;
DELETE FROM migration_jobs;
DELETE FROM otp_codes;
DELETE FROM payments;
DELETE FROM pricing_ingestion_runs;
DELETE FROM recommendations;
DELETE FROM storage_pricing_records;
DELETE FROM storage_records;
DELETE FROM subscriptions;
DELETE FROM usage_aggregates;
DELETE FROM usage_events;
DELETE FROM webhook_events;
DELETE ua FROM user_accounts ua
LEFT JOIN users u ON u.id = ua.user_id
WHERE u.role <> 'ADMIN' OR u.role IS NULL;
DELETE bc FROM billing_cycles bc
LEFT JOIN users u ON u.id = bc.user_id
WHERE u.role <> 'ADMIN' OR u.role IS NULL;
DELETE FROM users WHERE role <> 'ADMIN';
SET FOREIGN_KEY_CHECKS=1;
"
```

## Worker (Celery + Redis)

```bash
cd backend
../.venv/bin/celery -A backend.app.workers.celery_app.celery_app worker -B --loglevel=info
```
