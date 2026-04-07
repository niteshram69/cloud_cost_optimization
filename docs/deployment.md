# Production Deployment Guide

This guide covers deploying CostIntel Pipeline to a VPS (DigitalOcean, Linode, AWS EC2, etc.) using Docker Compose.

## Prerequisites

- VPS with Ubuntu 22.04 LTS (2GB RAM minimum, 4GB recommended)
- Domain name pointing to your VPS IP
- Docker and Docker Compose installed

## Quick Start

1. **SSH into your VPS:**
```bash
ssh user@your-vps-ip
```

2. **Install Docker:**
```bash
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
sudo usermod -aG docker $USER
newgrp docker
```

3. **Clone the repository:**
```bash
git clone https://github.com/your-org/costintel-pipeline.git
cd costintel-pipeline
```

4. **Create production environment file:**
```bash
cp .env.example .env
# Edit with production values
nano .env
```

Required production variables:
```
APP_ENVIRONMENT=production
DEBUG=false
SECRET_KEY=your-secure-random-key-at-least-32-chars
DATABASE_URL=mysql+aiomysql://costintel:secure-password@mysql:3306/costintel
REDIS_URL=redis://redis:6379/0
CELERY_BROKER_URL=redis://redis:6379/0
CELERY_RESULT_BACKEND=redis://redis:6379/0
```

5. **Start the application:**
```bash
docker-compose -f docker-compose.prod.yml up -d
```

6. **Run database migrations:**
```bash
docker-compose -f docker-compose.prod.yml exec api poetry run alembic upgrade head
```

7. **Create first admin user:**
```bash
docker-compose -f docker-compose.prod.yml exec api python -c "
from backend.app.services.auth_service import AuthService
from backend.app.schemas.auth import RegisterRequest
from backend.app.database import SessionLocal
from backend.app.models import UserRole

def create_admin():
    with SessionLocal() as db:
        service = AuthService(db)
        user = service.register_user(RegisterRequest(
            name='Admin User',
            email='admin@yourcompany.com',
            password='SecurePassword123!',
            company_name='YourCompany',
            cloud_provider='AWS',
            otp_code=None
        ))
        user.role = UserRole.ADMIN
        user.is_active = True
        db.commit()
        print(f'Admin created: {user.id}')

create_admin()
"
```

## SSL/TLS with Let's Encrypt

1. **Install certbot:**
```bash
sudo apt update
sudo apt install -y certbot
```

2. **Obtain certificate:**
```bash
sudo certbot certonly --standalone -d api.yourdomain.com
```

3. **Update nginx configuration** to use SSL certificates (see `docker/nginx.conf`)

4. **Auto-renewal:**
```bash
sudo crontab -e
# Add:
0 12 * * * /usr/bin/certbot renew --quiet
```

## Monitoring & Logging

### View logs:
```bash
# All services
docker-compose -f docker-compose.prod.yml logs -f

# Specific service
docker-compose -f docker-compose.prod.yml logs -f api
docker-compose -f docker-compose.prod.yml logs -f worker
```

### Health checks:
```bash
curl https://api.yourdomain.com/health
```

### Prometheus metrics:
```bash
curl https://api.yourdomain.com/metrics
```

## Scaling

### Horizontal scaling (multiple API containers):
```bash
docker-compose -f docker-compose.prod.yml up -d --scale api=3
```

### Scale workers:
```bash
docker-compose -f docker-compose.prod.yml up -d --scale worker=4
```

## Backup & Recovery

### Database backup:
```bash
# Automated daily backup
docker-compose -f docker-compose.prod.yml exec mysql mysqldump -u root -p costintel > backup_$(date +%Y%m%d).sql

# Or use the automated backup script
./scripts/backup.sh
```

### Restore from backup:
```bash
docker-compose -f docker-compose.prod.yml exec -T mysql mysql -u root -p costintel < backup_20240216.sql
```

## Security Hardening

1. **Use strong passwords** in `.env`
2. **Enable UFW firewall:**
```bash
sudo ufw allow 22
sudo ufw allow 80
sudo ufw allow 443
sudo ufw enable
```
3. **Fail2ban for SSH protection:**
```bash
sudo apt install fail2ban
```
4. **Regular updates:**
```bash
sudo apt update && sudo apt upgrade -y
```

## Troubleshooting

### Container won't start:
```bash
docker-compose -f docker-compose.prod.yml logs api
```

### Database connection issues:
```bash
docker-compose -f docker-compose.prod.yml exec mysql mysql -u costintel -p
```

### Celery worker not processing:
```bash
docker-compose -f docker-compose.prod.yml logs worker
docker-compose -f docker-compose.prod.yml exec redis redis-cli ping
```

## Updating the Application

1. **Pull latest changes:**
```bash
git pull origin main
```

2. **Rebuild and restart:**
```bash
docker-compose -f docker-compose.prod.yml build
docker-compose -f docker-compose.prod.yml up -d
```

3. **Run migrations:**
```bash
docker-compose -f docker-compose.prod.yml exec api poetry run alembic upgrade head
```

## Support

For issues or questions:
- GitHub Issues: https://github.com/costintel/pipeline/issues
- Email: support@costintel.io
