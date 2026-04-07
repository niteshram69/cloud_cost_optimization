# cloudtek by mindteck

A scalable backend service that processes user data through a metadata-driven pipeline for cloud cost optimization, classification, and decision-making.

## Overview

CostIntel Pipeline helps data engineers, FinOps teams, and cloud administrators reduce cloud bills by:
- **Ingesting** billing data, logs, and telemetry from multiple sources
- **Extracting metadata** from ingested data for context
- **Classifying** resources by sensitivity, relevance, and cost categories
- **Comparing costs** against historical data and provider alternatives
- **Recommending actions** like archiving, tier switching, or rightsizing
- **Automating decisions** via webhooks and configurable rules

## Architecture

```
┌──────────────┐    ┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│   Ingestion  │───▶│   Metadata   │───▶│Classification│───▶│    Cost      │
│   Endpoint   │    │  Collector   │    │   Engine     │    │  Comparison  │
└──────────────┘    └──────────────┘    └──────────────┘    └──────────────┘
                                                                   │
                                                                   ▼
                                                            ┌──────────────┐
                                                            │    Decision  │
                                                            │    Engine    │
                                                            │  (Webhooks)  │
                                                            └──────────────┘
```

**Tech Stack:**
- **Backend:** Python 3.12 + FastAPI (async)
- **Database:** MySQL 8.0 + SQLAlchemy 2.0 (async)
- **Cache/Queue:** Redis + Celery
- **Auth:** JWT + API Keys (PyJWT)
- **ML:** scikit-learn (rule-based, extensible to transformers)
- **Monitoring:** Prometheus metrics + structured logging

## V2 Multi-Cloud Storage Optimization

The project now includes an enterprise-focused v2 engine for hybrid rule + ML
storage lifecycle optimization across AWS, GCP, and Azure.

- API prefix: `/api/v2`
- Prometheus endpoint: `/metrics`
- Admin dashboard API: `/api/v2/dashboards/admin`
- Client dashboard API: `/api/v2/dashboards/client/{tenant_id}`

Detailed architecture and design rationale:
- `docs/multi_cloud_storage_optimization.md`
- `dashboards/grafana/storage_optimization_dashboard.json`

## Zero-Trust Manual Migration (UI "Migrate Now")

Cloudteck now supports client-authorized, metadata-only tier migrations with strict
zero-trust controls.

- Endpoint: `POST /migrations/authorize`
- Execution path enforced: `PLANNED -> DRY_RUN -> APPROVED -> EXECUTING -> COMPLETED`
- Failure path enforced: `EXECUTING -> ROLLED_BACK -> BLOCKED`
- Hard blocks are non-bypassable
- Cross-cloud UI execution is rejected
- Every run writes audit + circuit-breaker records

### Authorize Request
```json
{
  "resource_id": "provider::uuid",
  "approved_target_tier": "STANDARD_IA",
  "override_confidence": true,
  "acknowledged_risks": ["LATENCY", "RETRIEVAL_COST", "MANUAL_OVERRIDE"]
}
```

### Active Mode MySQL Schema

Production DDL for memory/policy/feedback loop tables is available in:
- `backend/docs/sql/active_mode_schema.sql`

Core tables:
- `metric_history`
- `governance_policies`
- `circuit_breaker_events`
- `migration_plans`
- `audit_events`

## Quick Start

### Prerequisites
- Python 3.12+
- Poetry
- Docker & Docker Compose
- MySQL 8.0 (or use Docker)
- Redis 7.0+ (or use Docker)

### Installation

1. **Clone and setup environment:**
```bash
git clone <repo-url>
cd costintel-pipeline
cp .env.example .env
# Edit .env with your settings
```

2. **Install dependencies:**
```bash
poetry install
poetry shell
```

Optional migration SDKs (for enforced cross-cloud moves):
```bash
poetry install -E migration-sdks
```

3. **Start infrastructure services:**
```bash
docker-compose up -d mysql redis
```

4. **Run database migrations:**
```bash
poetry run alembic upgrade head
```

5. **Start the application:**
```bash
cd backend
python3.12 -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8001 --reload
```

6. **Start frontend (separate terminal):**
```bash
cd frontend
npm run dev -- --hostname 127.0.0.1 --port 3000
```

### Docker (Full Stack)

Run everything with Docker Compose:
```bash
docker-compose up -d
```

Services:
- API: http://localhost:8000
- API Docs: http://localhost:8000/docs
- Flower (Celery monitor): http://localhost:5555
- MySQL: localhost:3306
- Redis: localhost:6379

## API Documentation

Once running, interactive API documentation is available at:
- **Swagger UI:** http://localhost:8000/docs
- **ReDoc:** http://localhost:8000/redoc
- **OpenAPI Schema:** http://localhost:8000/openapi.json

### Quick API Test

```bash
# Health check
curl http://localhost:8000/health

# Register user
curl -X POST http://localhost:8000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email": "user@example.com", "password": "securepassword123"}'

# Get token
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"user@example.com","password":"securepassword123"}'

# Upload data (with token)
curl -X POST http://localhost:8000/api/v1/ingestion/upload \
  -H "Authorization: Bearer <token>" \
  -F "file=@billing-data.csv"
```

## Development

### Project Structure
```
costintel-pipeline/
├── app/
│   ├── core/           # Config, database, logging, security
│   ├── modules/        # Domain modules (auth, ingestion, etc.)
│   ├── collectors/     # Event-driven + batch metadata ingestion
│   ├── feature_engineering/  # ML/rules feature extraction
│   ├── rules_engine/   # HOT/COLD/ARCHIVE baseline policy engine
│   ├── ml_engine/      # RandomForest model + training pipeline
│   ├── pricing_engine/ # Region-aware multi-cloud cost normalization
│   ├── decision_engine/ # Hybrid ML+rules decisioning
│   ├── migration_engine/ # Safe cross-cloud migration orchestration
│   ├── dashboards/     # Admin/client dashboard aggregation
│   ├── api/            # /api/v2 routes
│   ├── dependencies.py   # FastAPI dependencies
│   └── main.py         # Application factory
├── alembic/            # Database migrations
├── tests/              # Test suite
├── docker/             # Docker configurations
└── adr/                # Architecture Decision Records
```

### Running Tests
```bash
# Run all tests
poetry run pytest

# Run with coverage
poetry run pytest --cov=app --cov-report=html

# Run specific test
poetry run pytest tests/test_auth.py -v
```

### Code Quality
```bash
# Linting
poetry run ruff check .

# Formatting
poetry run ruff format .

# Type checking
poetry run mypy app/

# Run pre-commit hooks
poetry run pre-commit run --all-files
```

### Database Migrations
```bash
# Create migration
poetry run makemigrations -m "add user table"

# Apply migrations
poetry run migrate

# Downgrade
poetry run alembic downgrade -1
```

## Deployment

### VPS Deployment (Production)

See `docs/deployment.md` for detailed instructions.

Quick summary:
1. Provision VPS (Ubuntu 22.04+)
2. Install Docker & Docker Compose
3. Configure environment variables
4. Run: `docker-compose -f docker-compose.prod.yml up -d`
5. Configure Nginx reverse proxy
6. Enable SSL (Let's Encrypt)

### Scaling

**Horizontal Scaling:**
- Run multiple API containers behind Nginx load balancer
- Use Redis for distributed caching and Celery broker
- MySQL read replicas for query scaling

**Background Workers:**
- Scale Celery workers independently: `docker-compose up -d --scale worker=4`
- Use separate queues for priority tasks

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `APP_ENVIRONMENT` | dev/staging/production | `development` |
| `SECRET_KEY` | JWT signing key | (required) |
| `DATABASE_URL` | MySQL connection string | (required) |
| `REDIS_URL` | Redis connection string | (required) |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | JWT expiry | 30 |
| `DATA_RETENTION_DAYS` | Auto-purge old data | 90 |
| `WEBHOOK_MAX_RETRIES` | Retry failed webhooks | 5 |
| `RATE_LIMIT_REQUESTS` | API rate limit | 100/min |
| `PRICING_CATALOG_PATH` | Region-aware storage pricing catalog | `app/pricing_engine/pricing_catalog.json` |
| `ML_MODEL_PATH` | Persisted ML model path | `./artifacts/storage_temperature_model.joblib` |
| `ML_CONFIDENCE_THRESHOLD` | Fallback cutoff for ML classifier | `0.75` |
| `MIGRATION_AUDIT_LOG_PATH` | JSONL audit trail for migrations | `./logs/migration_audit.jsonl` |
| `MIGRATION_MAX_PARALLEL` | Parallel migration limit | `4` |
| `MIGRATION_MAX_OPS_PER_SECOND` | Migration throttle limit | `4.0` |

See `.env.example` for complete list.

## Features Roadmap

**Phase 1 (MVP):**
- [x] User authentication & API keys
- [x] Data ingestion (files/API)
- [x] Metadata extraction
- [x] Rule-based classification
- [x] Cost comparison engine
- [x] Decision engine with webhooks
- [x] Dashboard API

**Phase 2:**
- [x] AWS/GCP/Azure billing API integration
- [ ] Advanced ML classification (anomaly detection)
- [ ] Scheduled reports
- [ ] BI tool exports (Tableau, PowerBI)

**Phase 3:**
- [ ] Multi-region deployment
- [ ] Real-time cost streaming
- [ ] AI-powered recommendations

## License

MIT License - see LICENSE file.

## Support

- **Issues:** [GitHub Issues](https://github.com/costintel/pipeline/issues)
- **Discussions:** [GitHub Discussions](https://github.com/costintel/pipeline/discussions)
- **Email:** support@costintel.io
