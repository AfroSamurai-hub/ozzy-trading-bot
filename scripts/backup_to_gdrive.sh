#!/bin/bash
# OzzyBot backup to Google Drive
# Run manually or via cron

set -e

RCLONE="$HOME/.local/bin/rclone"
OZ_DIR="/home/rick/ozzy-bot"
BACKUP_NAME="ozzybot_backup_$(date +%Y%m%d_%H%M%S).tar.gz"
LOCAL_BACKUP="$OZ_DIR/backups/$BACKUP_NAME"
GDRIVE_REMOTE="ozzybot-gdrive:OzzyBot-Backups"

mkdir -p "$OZ_DIR/backups"

echo "[$(date)] Starting backup to Google Drive..."

# Create local tar.gz
tar -czf "$LOCAL_BACKUP" \
    -C "$OZ_DIR" \
    trades.db ozzy_memory.db *.log *.py *.json .env scripts/ \
    .config/systemd/user/ozzybot-*.service 2>/dev/null || true

# Also backup the docs directory
tar -czf "$OZ_DIR/backups/ozzybot_docs_$(date +%Y%m%d).tar.gz" \
    -C "$OZ_DIR" docs/ 2>/dev/null || true

# Sync to Google Drive
$RCLONE copy "$LOCAL_BACKUP" "$GDRIVE_REMOTE/"
$RCLONE copy "$OZ_DIR/backups/ozzybot_docs_$(date +%Y%m%d).tar.gz" "$GDRIVE_REMOTE/" 2>/dev/null || true

# Clean old local backups (keep last 10)
ls -t "$OZ_DIR"/backups/ozzybot_backup_*.tar.gz 2>/dev/null | tail -n +11 | xargs rm -f 2>/dev/null || true

# Clean old Google Drive backups (keep last 30)
$RCLONE delete --min-age 30d "$GDRIVE_REMOTE/" 2>/dev/null || true

echo "[$(date)] Backup complete: $BACKUP_NAME"
echo "[$(date)] Google Drive folder: OzzyBot-Backups"
