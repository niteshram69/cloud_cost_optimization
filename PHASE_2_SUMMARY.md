# Phase 2: Integration Testing & Core Business Logic

## 🎯 Status: IN PROGRESS

**Date:** February 16, 2026  
**Version:** 0.1.0  
**Environment:** Development

---

## ✅ What's Working

### Infrastructure
- ✓ **MySQL Container** - Running on `localhost:3306`
  - Database: `costintel`
  - User: `costintel` / `costintel_dev_password`
  - Migration State: `002_core_business_tables` (HEAD)
  
- ✓ **Redis Container** - Running on `localhost:6379`
  - Ready for caching and Celery
  
- ✓ **FastAPI Server** - Running on `http://localhost:8000`
  - Port: 8000
  - Debug: Enabled
  - Auto-reload: Enabled

- ✓ **Celery Worker** - Started for background jobs
  - Broker: Redis (`redis://localhost:6379/1`)
  - Result Backend: Redis (`redis://localhost:6379/2`)

### API Endpoints

#### Public Endpoints (No Auth Required)
- `GET /` - API information ✓ (200)
- `GET /health` - Health check ✓ (200)
- `GET /docs` - Swagger UI ✓ (200)
- `GET /redoc` - ReDoc documentation ✓ (200)

#### Protected Endpoints (Return 401 as Expected)
- `GET /api/v1/cost/records` - List cost records
- `GET /api/v1/ingestion/jobs` - List ingestion jobs
- `GET /api/v1/classification/results` - List classifications
- `GET /api/v1/decisions/recommendations` - List decisions
- `GET /api/v1/dashboard/summary` - Dashboard summary

### Database Schema
All tables created and ready:
1. `users` - User accounts
2. `api_keys` - API authentication keys
3. `data_sources` - Billing data sources
4. `ingestion_jobs` - File processing jobs
5. `metadata_records` - Extracted metadata
6. `classification_results` - Resource classifications
7. `cost_records` - Cost tracking
8. `benchmarks` - Cost benchmarks
9. `decisions` - Optimization recommendations
10. `webhook_logs` - Webhook event tracking

---

## ⚠️ Known Issues

### 1. User Registration (500 Error)
**Status:** Under Investigation  
**Impact:** Cannot register new users via API  
**Workaround:** Insert users directly into database or use JWT token generation

```bash
# To create test user in database:
docker exec costintel-mysql mysql -u costintel -pcostintel_dev_password costintel \
  -e "INSERT INTO users (email, password_hash, full_name, is_active, email_verified, created_at, updated_at) \
  VALUES ('user@example.com', 'hashed_password', 'User Name', 1, 1, NOW(), NOW());"
```

**Likely Causes:**
- Timestamp handling in user model
- Password hashing with bcrypt
- Database session commit issue

---

## 🚀 Next Steps - Phase 2 (Prioritized)

### High Priority
1. **Fix Authentication**
   - [ ] Debug user registration endpoint (500 error)
   - [ ] Test JWT token generation
   - [ ] Verify password hashing
   - [ ] Test login flow

2. **Manual Data Insertion & Testing**
   - [ ] Insert test users into database
   - [ ] Generate JWT tokens
   - [ ] Test protected endpoints with valid tokens

3. **End-to-End Pipeline Test**
   - [ ] Create sample billing CSV file
   - [ ] Test file upload endpoint
   - [ ] Verify metadata extraction
   - [ ] Test classification engine
   - [ ] Test decision generation
   - [ ] Verify webhook callbacks

### Medium Priority
4. **Celery Integration**
   - [ ] Verify Celery tasks are being processed
   - [ ] Test async job status checks
   - [ ] Monitor task queue

5. **Data Validation**
   - [ ] Test with various CSV formats
   - [ ] Verify error handling
   - [ ] Test edge cases

### Low Priority
6. **Performance & Monitoring**
   - [ ] Set up Prometheus metrics
   - [ ] Configure logging
   - [ ] Load testing

---

## 📊 System Architecture (Current State)

```
┌─────────────────────────────────────────────────────┐
│           CostIntel Pipeline                         │
├─────────────────────────────────────────────────────┤
│                    FastAPI                           │
│            (Running on localhost:8000)               │
├─────────────────────────────────────────────────────┤
│                                                       │
│  ┌──────────┐  ┌────────────┐  ┌──────────────┐    │
│  │   Auth   │  │ Ingestion  │  │  Metadata    │    │
│  │          │  │            │  │              │    │
│  └──────────┘  └────────────┘  └──────────────┘    │
│        │             │                │              │
│        └─────────────┴────────────────┘              │
│                     │                                │
│        ┌────────────▼────────────┐                  │
│        │  Classification Engine  │                  │
│        │  (Rules-based ML)       │                  │
│        └───────────┬──────────────┘                  │
│                    │                                │
│        ┌───────────┴───────────┬──────────┐         │
│        ▼                       ▼          ▼         │
│    ┌────────┐  ┌────────────┐  ┌──────────┐        │
│    │ Cost   │  │ Decisions  │  │Dashboard │        │
│    │Engine  │  │  Engine    │  │           │        │
│    └────────┘  └────────────┘  └──────────┘        │
│                     │                               │
│             ┌───────▼────────┐                      │
│             │ Webhooks       │                      │
│             │ (Async)        │                      │
│             └────────────────┘                      │
└─────────────────────────────────────────────────────┘
        │                    │
        ▼                    ▼
    ┌─────────┐         ┌──────────┐
    │ MySQL   │         │  Redis   │
    │ DB      │         │ Cache/   │
    │         │         │ Celery   │
    └─────────┘         └──────────┘
```

---

## 🧪 Testing Checklist

### Unit Tests
- [ ] Auth service
- [ ] Classification engine
- [ ] Decision engine
- [ ] Repository layer

### Integration Tests
- [ ] File upload → Metadata extraction → Classification
- [ ] Classification → Cost comparison → Decision
- [ ] Decision → Webhook notification

### End-to-End Tests
- [ ] Full pipeline with sample CSV
- [ ] Multi-file batch processing
- [ ] Error handling and recovery

---

## 📝 Useful Commands

### Check Database
```bash
# Connect to MySQL
docker exec -it costintel-mysql mysql -u costintel -pcostintel_dev_password costintel

# List tables
SHOW TABLES;

# View users
SELECT id, email, full_name FROM users;

# View ingestion jobs
SELECT id, file_name, status, created_at FROM ingestion_jobs ORDER BY created_at DESC;
```

### Check Redis
```bash
# Connect to Redis
docker exec -it costintel-redis redis-cli

# Check keys
KEYS *

# Check Celery queue
LLEN celery

# Flush Redis (careful!)
FLUSHDB
```

### API Testing
```bash
# Health check
curl http://localhost:8000/health

# List endpoints (requires auth)
curl -H "Authorization: Bearer <TOKEN>" http://localhost:8000/api/v1/cost/records

# View Swagger UI
open http://localhost:8000/docs
```

### Stop/Start Services
```bash
# Stop all
docker-compose down

# Start all
docker-compose up -d

# Start specific services
docker-compose up -d mysql redis
```

---

## 📚 Documentation Links

- API Docs: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc
- OpenAPI JSON: http://localhost:8000/openapi.json
- Project README: [readme.md](readme.md)
- Architecture Decisions: [adr/README.md](adr/README.md)

---

## 🔍 Investigation Notes

### Auth Registration 500 Error
**Observations:**
- All other endpoints respond correctly (401 for protected, appropriate status for public)
- Database is functioning (migrations succeeded)
- API initialization completes without errors
- The error is isolated to POST /api/v1/auth/register

**Possible locations of error:**
1. `app/modules/auth/service.py::register()` - Line 48
2. `app/modules/auth/repository.py::create()` - Line 22
3. `app/core/security.py::hash_password()` - Password hashing
4. Database session handling in dependency injection

**Next debugging steps:**
1. Add detailed logging to auth service
2. Test password hashing in isolation
3. Check user model field defaults
4. Verify datetime handling for created_at/updated_at

---

## 🎓 Learning Resources

For team members:
- SQLAlchemy async docs: https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html
- FastAPI security: https://fastapi.tiangolo.com/tutorial/security/
- Celery tasks: https://docs.celeryproject.io/en/stable/
- Scikit-learn: https://scikit-learn.org/stable/
- MySQL best practices: https://dev.mysql.com/

---

## 📊 Metrics & Monitoring

### Current Resources
- MySQL: 20 connections (pool_size=20, max_overflow=10)
- Redis: Single instance on port 6379
- Celery: 2 worker processes (concurrency=2)
- API: Single Uvicorn instance with auto-reload

### Performance Targets (for Phase 3)
- File upload: < 5s for 100MB
- Metadata extraction: < 10s per 10k records
- Classification: < 5s per 10k records
- Decision generation: < 2s per 10k records

---

**Last Updated:** 2026-02-16 09:15:00 UTC  
**Maintainer:** CostIntel Team  
**Status:** 🔄 In Development
