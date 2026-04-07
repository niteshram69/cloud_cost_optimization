#!/bin/bash
# Automated backup script for CostIntel Pipeline

set -e

# Configuration
BACKUP_DIR="/backups"
RETENTION_DAYS=30
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
CONTAINER_NAME="costintel-mysql-prod"
DB_NAME="costintel"
DB_USER="root"

# Ensure backup directory exists
mkdir -p $BACKUP_DIR

# Function to send notification (optional)
send_notification() {
    local message=$1
    # Add your notification method here (Slack, email, etc.)
    echo "$message"
}

# Backup database
echo "Starting database backup..."
docker exec $CONTAINER_NAME mysqldump \
    -u $DB_USER \
    -p$(cat /run/secrets/mysql_root_password) \
    --single-transaction \
    --routines \
    --triggers \
    $DB_NAME > $BACKUP_DIR/costintel_backup_$TIMESTAMP.sql

if [ $? -eq 0 ]; then
    # Compress backup
gzip $BACKUP_DIR/costintel_backup_$TIMESTAMP.sql
    BACKUP_SIZE=$(du -h $BACKUP_DIR/costintel_backup_$TIMESTAMP.sql.gz | cut -f1)
    echo "Backup completed: costintel_backup_$TIMESTAMP.sql.gz ($BACKUP_SIZE)"
    send_notification "Backup successful: costintel_backup_$TIMESTAMP.sql.gz ($BACKUP_SIZE)"
else
    echo "Backup failed!"
    send_notification "Backup failed for $TIMESTAMP"
    exit 1
fi

# Cleanup old backups
echo "Cleaning up backups older than $RETENTION_DAYS days..."
find $BACKUP_DIR -name "costintel_backup_*.sql.gz" -mtime +$RETENTION_DAYS -delete

# List remaining backups
echo "Current backups:"
ls -lh $BACKUP_DIR/costintel_backup_*.sql.gz 2>/dev/null || echo "No backups found"

echo "Backup process completed."
