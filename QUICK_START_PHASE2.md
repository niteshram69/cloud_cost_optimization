# Quick Start - Phase 2 (Post-Feb-16-2026)

## Current Status
✅ Infrastructure Running  
✅ Database Migrations Complete  
✅ API Server Running  
⚠️ Authentication Issue (500 error on registration)  
✅ Protected Endpoints Secured (returning 401)

---

## Start Services (One Command)

```bash
cd "/workspaces/Cloud-Storage-Optimization/Cloud cost optimization"

# Start MySQL and Redis
docker-compose up -d mysql redis

# In separate terminals:

# Terminal 1: Start API Server
/workspaces/Cloud-Storage-Optimization/.venv/bin/python -m uvicorn backend.app.main:app --host 0.0.0.0 --port 8000

# Terminal 2: Start Celery Worker
/workspaces/Cloud-Storage-Optimization/.venv/bin/python -m celery -A backend.app.workers.celery_app.celery_app worker --loglevel=info --concurrency=2

# Terminal 3: (Optional) Celery Flower Monitor
#/workspaces/Cloud-Storage-Optimization/.venv/bin/python -m flower -A celery_worker --port=5555
```

---

## Verify Everything is Running

```bash
# Check API
curl http://localhost:8000/health

# Check MySQL
docker exec costintel-mysql mysql -u costintel -pcostintel_dev_password costintel -e "SELECT 1"

# Check Redis
docker exec costintel-redis redis-cli ping

# View Swagger UI
open http://localhost:8000/docs
```

---

## To Fix Authentication Issue

```bash
# 1. Find the root cause in auth service
vim app/modules/auth/service.py  # Line 48, register() method

# 2. Test password hashing in isolation
/workspaces/Cloud-Storage-Optimization/.venv/bin/python -c "
from passlib.context import CryptContext
pwd_context = CryptContext(schemes=['bcrypt'], deprecated='auto')
hash = pwd_context.hash('TestPass123!')
print('Hash:', hash)
print('Verify:', pwd_context.verify('TestPass123!', hash))
"

# 3. Create test user directly in DB
docker exec costintel-mysql mysql -u costintel -pcostintel_dev_password costintel << EOF
INSERT INTO users (email, password_hash, full_name, is_active, email_verified, created_at, updated_at) 
VALUES ('test@example.com', '\$2b\$12\$abcdefghijklmnopqrstuv.bcrypthash', 'Test User', 1, 1, NOW(), NOW());
EOF

# 4. Generate JWT token manually
/workspaces/Cloud-Storage-Optimization/.venv/bin/python << 'EOF'
from backend.app.core.security import create_access_token
from datetime import datetime, timedelta

# Create token with user_id=1
tokens = {
    "access_token": create_access_token(subject="1", role="ADMIN"),
    "token_type": "bearer"
}

import json
print(json.dumps(tokens, indent=2))
EOF
```

---

## Test With Generated Token

```bash
# Save token to variable
TOKEN="your_token_here"

# Test protected endpoint
curl -H "Authorization: Bearer $TOKEN" \
     http://localhost:8000/api/v1/cost/records

# Test user info
curl -H "Authorization: Bearer $TOKEN" \
     http://localhost:8000/api/v1/auth/me
```

---

## File Upload Test (When Auth is Fixed)

```bash
# Create sample CSV
cat > billing_sample.csv << EOF
resource_id,provider,service_type,cost_amount,usage_quantity,period_start,period_end
i-1234567890,aws,ec2,125.50,730,2026-01-01,2026-02-01
eip-987654321,aws,elastic-ip,3.65,730,2026-01-01,2026-02-01
vol-abcdef123456,aws,ebs,75.00,1,2026-01-01,2026-02-01
EOF

# Upload file (needs valid token)
curl -X POST http://localhost:8000/api/v1/ingestion/upload \
     -H "Authorization: Bearer $TOKEN" \
     -F "file=@billing_sample.csv"
```

---

## Check Database State

```bash
# Current migrations
docker exec costintel-mysql mysql -u costintel -pcostintel_dev_password costintel \
  -e "SELECT * FROM alembic_version;"

# Count records
docker exec costintel-mysql mysql -u costintel -pcostintel_dev_password costintel \
  -e "SELECT 
        (SELECT COUNT(*) FROM users) as users,
        (SELECT COUNT(*) FROM ingestion_jobs) as jobs,
        (SELECT COUNT(*) FROM cost_records) as costs,
        (SELECT COUNT(*) FROM decisions) as decisions;"
```

---

## Docker Cleanup (If Needed)

```bash
# Stop all services
docker-compose down

# Remove volumes (⚠️ DELETES DATA)
docker-compose down -v

# Rebuild images
docker-compose build --no-cache

# Fresh start
docker-compose up -d
```

---

## Common Errors & Solutions

### "Connection refused to localhost:3306"
→ MySQL container not running: `docker-compose up -d mysql`

### "Unknown database 'costintel'"
→ Run migrations: `alembic upgrade head`

### "Address already in use :8000"
→ Kill existing process: `lsof -i :8000 | grep LISTEN | awk '{print $2}' | xargs kill -9`

### "Module not found" errors
→ Install dependencies: `/workspaces/Cloud-Storage-Optimization/.venv/bin/pip install -r requirements.txt`

### Celery not processing tasks
→ Check Redis: `docker exec costintel-redis redis-cli PING`  
→ Check Celery logs: Look for "Started" message in Celery terminal

---

## Useful Environment Variables

```bash
# In .env file (already created):
SECRET_KEY=dev-secret-key-change-in-production-12345678901234567890
DATABASE_URL=mysql+aiomysql://costintel:costintel_dev_password@localhost:3306/costintel
REDIS_URL=redis://localhost:6379/0
CELERY_BROKER_URL=redis://localhost:6379/1
CELERY_RESULT_BACKEND=redis://localhost:6379/2
APP_ENVIRONMENT=development
DEBUG=true
```

---

## Next Phase Goals

1. ✅ Verify all endpoints with authentication
2. ✅ Test file upload & metadata extraction
3. ✅ Validate classification engine
4. ✅ Test decision generation
5. ✅ Verify webhook notifications
6. ✅ Load test the system

---

## Resources

- **API Docs:** http://localhost:8000/docs
- **Phase 2 Details:** See [PHASE_2_SUMMARY.md](PHASE_2_SUMMARY.md)
- **Project README:** [readme.md](readme.md)
- **Architecture Records:** [adr/](adr/)

---

**Created:** 2026-02-16 09:15 UTC  
**Target Audience:** Developers continuing Phase 2 work
