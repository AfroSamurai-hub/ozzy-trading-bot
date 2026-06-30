#!/bin/bash
# Local backup for OzzyBot
# Creates timestamped tar.gz, keeps last 10

set -e

OZ_DIR="/home/rick/ozzy-bot"
BACKUP_DIR="$OZ_DIR/backups"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_NAME="ozzybot_backup_${TIMESTAMP}.tar.gz"

mkdir -p "$BACKUP_DIR"

echo "[$(date)] Creating local backup: $BACKUP_NAME"

tar -czf "$BACKUP_DIR/$BACKUP_NAME" \
    -C "$OZ_DIR" \
    trades.db *.log *.py *.json .env scripts/ docs/ tests/ \
    .config/systemd/user/ozzybot-*.service 2>/dev/null || true

# Keep only last 10 local backups
ls -t "$BACKUP_DIR"/ozzybot_backup_*.tar.gz 2>/dev/null | tail -n +11 | xargs rm -f 2>/dev/null || true

echo "[$(date)] Local backup complete: $BACKUP_DIR/$BACKUP_NAME"
