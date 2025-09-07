#!/bin/bash
# Database backup script for ARCOM Cleaning Management System

set -e

BACKUP_DIR="/app/backups"
DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="arcom_backup_${DATE}.sql"

echo "💾 Starting database backup..."

# Create backup directory
mkdir -p $BACKUP_DIR

# Create database backup
echo "📊 Creating database backup..."
docker-compose exec -T db pg_dump -U arcom arcom > "${BACKUP_DIR}/${BACKUP_FILE}"

# Compress backup
echo "🗜️ Compressing backup..."
gzip "${BACKUP_DIR}/${BACKUP_FILE}"

# Keep only last 7 days of backups
echo "🧹 Cleaning old backups..."
find $BACKUP_DIR -name "arcom_backup_*.sql.gz" -mtime +7 -delete

echo "✅ Backup completed: ${BACKUP_FILE}.gz"
echo "📁 Backup location: ${BACKUP_DIR}/"
