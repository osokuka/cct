# ARCOM Docker Deployment Guide

## 🐳 Production Deployment

This guide covers deploying the ARCOM Cleaning Management System using Docker in a production environment.

## Prerequisites

- Docker 20.10+
- Docker Compose 2.0+
- 4GB RAM minimum
- 20GB disk space
- Domain name (optional, for SSL)

## Quick Start

### 1. Clone and Setup

```bash
git clone <repository-url>
cd ARCOM
cp env.example .env
```

### 2. Configure Environment

Edit `.env` file with your production settings:

```bash
# Required settings
SECRET_KEY=your-super-secret-key-here
DB_PASSWORD=your-secure-database-password
ALLOWED_HOSTS=yourdomain.com,www.yourdomain.com

# Optional settings
EMAIL_HOST_USER=your-email@domain.com
EMAIL_HOST_PASSWORD=your-email-password
```

### 3. Deploy

```bash
chmod +x scripts/deploy.sh
./scripts/deploy.sh
```

### 4. Configure Nginx Proxy Manager

1. **Install Nginx Proxy Manager** (if not already installed)
2. **Add Proxy Host**:
   - **Domain**: yourdomain.com (or subdomain)
   - **Forward Hostname/IP**: `arcom_web_1` (or your server IP)
   - **Forward Port**: `8000`
   - **Enable SSL**: Yes (recommended)

### 5. Access Application

- **Application**: http://yourdomain.com (or http://localhost:8000 for direct access)
- **Admin Panel**: http://yourdomain.com/admin
- **Default Login**: admin / admin123

## Manual Deployment

### 1. Build Images

```bash
docker-compose build
```

### 2. Start Database

```bash
docker-compose up -d db redis
```

### 3. Run Migrations

```bash
docker-compose exec web python manage.py migrate
```

### 4. Create Superuser

```bash
docker-compose exec web python manage.py createsuperuser
```

### 5. Collect Static Files

```bash
docker-compose exec web python manage.py collectstatic --noinput
```

### 6. Start All Services

```bash
docker-compose up -d
```

## Service Architecture

### Services Overview

| Service | Purpose | Port | Dependencies |
|---------|---------|------|--------------|
| `web` | Django Application | 8000 | db, redis |
| `db` | PostgreSQL Database | 5432 | - |
| `redis` | Cache & Sessions | 6379 | - |
| `cron` | Daily Maintenance | - | db, redis |
| `celery` | Background Tasks | - | db, redis |
| `celery-beat` | Task Scheduler | - | db, redis |

**Note:** This setup uses Nginx Proxy Manager for reverse proxy instead of built-in nginx.

### Data Volumes

- `postgres_data`: Database files
- `static_volume`: Static files (CSS, JS, images)
- `media_volume`: User uploads
- `redis_data`: Redis cache data

## Configuration

### Environment Variables

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| `SECRET_KEY` | Django secret key | - | Yes |
| `DEBUG` | Debug mode | 0 | No |
| `ALLOWED_HOSTS` | Allowed hosts | localhost | Yes |
| `DB_PASSWORD` | Database password | arcom123 | Yes |
| `DATABASE_URL` | Database URL | Auto-generated | No |
| `REDIS_URL` | Redis URL | redis://redis:6379/0 | No |
| `EMAIL_HOST_USER` | Email username | - | No |
| `EMAIL_HOST_PASSWORD` | Email password | - | No |

### SSL Configuration

SSL is handled by Nginx Proxy Manager. Configure SSL certificates in the NPM interface:

1. **Access NPM**: http://your-npm-ip:81
2. **Add SSL Certificate**: Upload your certificate or use Let's Encrypt
3. **Enable SSL**: Check "Force SSL" in the proxy host configuration

## Monitoring

### Health Checks

All services include health checks:

```bash
# Check service status
docker-compose ps

# View logs
docker-compose logs -f web
docker-compose logs -f cron

# Check health
curl http://localhost/health/
```

### Logs

Logs are available in multiple locations:

- **Application logs**: `docker-compose logs web`
- **Cron logs**: `docker-compose logs cron`
- **Database logs**: `docker-compose logs db`
- **Redis logs**: `docker-compose logs redis`

### Backup

#### Automated Backup

```bash
# Run backup script
./scripts/backup.sh

# Schedule daily backups (add to crontab)
0 2 * * * /path/to/ARCOM/scripts/backup.sh
```

#### Manual Backup

```bash
# Database backup
docker-compose exec db pg_dump -U arcom arcom > backup.sql

# Media files backup
docker cp $(docker-compose ps -q web):/app/media ./media_backup/
```

## Maintenance

### Daily Maintenance

The system automatically runs daily maintenance at 11:59 PM:

- Marks past due tasks as "missed"
- Generates reports
- Cleans up old data

### Manual Maintenance

```bash
# Run daily maintenance manually
docker-compose exec web python manage.py daily_task_maintenance

# Check missed tasks
docker-compose exec web python manage.py mark_missed_tasks --dry-run
```

### Updates

```bash
# Pull latest changes
git pull

# Rebuild and restart
docker-compose down
docker-compose build --no-cache
docker-compose up -d

# Run migrations
docker-compose exec web python manage.py migrate
```

## Troubleshooting

### Common Issues

#### 1. Database Connection Error

```bash
# Check database status
docker-compose logs db

# Restart database
docker-compose restart db
```

#### 2. Static Files Not Loading

```bash
# Collect static files
docker-compose exec web python manage.py collectstatic --noinput

# Check if whitenoise is working
curl -I http://localhost:8000/static/admin/css/base.css
```

#### 3. Cron Not Running

```bash
# Check cron logs
docker-compose logs cron

# Test cron manually
docker-compose exec cron /app/run_maintenance.sh
```

#### 4. Memory Issues

```bash
# Check resource usage
docker stats

# Increase memory limits in docker-compose.yml
```

### Performance Optimization

#### 1. Database Optimization

```bash
# Analyze database
docker-compose exec web python manage.py dbshell
```

#### 2. Cache Optimization

```bash
# Clear cache
docker-compose exec web python manage.py clear_cache

# Check Redis
docker-compose exec redis redis-cli info
```

#### 3. Static Files

```bash
# Compress static files
docker-compose exec web python manage.py compress

# Check nginx caching
curl -I http://localhost/static/admin/css/base.css
```

## Security

### Production Security Checklist

- [ ] Change default passwords
- [ ] Configure SSL certificates
- [ ] Set secure environment variables
- [ ] Enable firewall rules
- [ ] Regular security updates
- [ ] Monitor access logs
- [ ] Backup encryption

### Firewall Configuration

```bash
# Allow only necessary ports
ufw allow 80/tcp
ufw allow 443/tcp
ufw allow 22/tcp  # SSH
ufw enable
```

## Scaling

### Horizontal Scaling

```yaml
# Scale web service
docker-compose up -d --scale web=3

# Load balancer configuration needed
```

### Vertical Scaling

```yaml
# Increase resources in docker-compose.yml
services:
  web:
    deploy:
      resources:
        limits:
          memory: 2G
          cpus: '1.0'
```

## Support

### Logs Collection

```bash
# Collect all logs
mkdir -p logs/$(date +%Y%m%d)
docker-compose logs > logs/$(date +%Y%m%d)/all.log
docker-compose logs web > logs/$(date +%Y%m%d)/web.log
docker-compose logs db > logs/$(date +%Y%m%d)/db.log
```

### System Information

```bash
# Docker version
docker --version
docker-compose --version

# System resources
docker system df
docker system info
```

---

**Need Help?** Check the logs first, then refer to the troubleshooting section above.
