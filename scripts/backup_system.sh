#!/usr/bin/env bash
# OzzyBot Full System Backup
# Backs up: code, config, DB, schemas, pine scripts, systemd, logs, .env
# Run manually or via cron: 0 2 * * * /home/rick/ozzy-bot/scripts/backup_system.sh

set -e

BOT_DIR="/home/rick/ozzy-bot"
BACKUP_DIR="$BOT_DIR/backups/system"
TIMESTAMP=$(date '+%Y-%m-%d_%H%M%S')
BACKUP_NAME="ozzybot_backup_${TIMESTAMP}"
BACKUP_PATH="$BACKUP_DIR/$BACKUP_NAME"
RETENTION_DAYS=30

echo "[$TIMESTAMP] Starting OzzyBot backup..."

mkdir -p "$BACKUP_PATH"

# 1. SQLite databases
cp "$BOT_DIR/trades.db" "$BACKUP_PATH/"

# 2. Config & secrets
cp "$BOT_DIR/config.py" "$BACKUP_PATH/"
cp "$BOT_DIR/.env" "$BACKUP_PATH/env.backup"

# 3. Core code
cp "$BOT_DIR/webhook.py" "$BACKUP_PATH/"
cp "$BOT_DIR/binance_monitor.py" "$BACKUP_PATH/"
cp "$BOT_DIR/binance_connector.py" "$BACKUP_PATH/"
cp "$BOT_DIR/trade_db.py" "$BACKUP_PATH/"
cp "$BOT_DIR/telegram_command_bot.py" "$BACKUP_PATH/"
cp "$BOT_DIR/telegram_client.py" "$BACKUP_PATH/"
cp "$BOT_DIR/command_center.py" "$BACKUP_PATH/"
cp "$BOT_DIR/signal_generator.py" "$BACKUP_PATH/"

# 4. Policy & indicator modules
for f in "$BOT_DIR"/crypto_entry_policy.py "$BOT_DIR"/filter_policy.py "$BOT_DIR"/movement_policy.py "$BOT_DIR"/sentiment_filter.py "$BOT_DIR"/context_engine.py "$BOT_DIR"/binance_indicators.py "$BOT_DIR"/taapi_client.py "$BOT_DIR"/twelvedata_client.py; do
    [ -f "$f" ] && cp "$f" "$BACKUP_PATH/"
done

# 5. Pine Script strategies
cp -r "$BOT_DIR/pinescript" "$BACKUP_PATH/"

# 6. JSON schemas
cp -r "$BOT_DIR/schemas" "$BACKUP_PATH/"

# 7. Systemd services
cp -r "$BOT_DIR/systemd" "$BACKUP_PATH/"
mkdir -p "$BACKUP_PATH/user-systemd"
cp /home/rick/.config/systemd/user/ozzybot-*.service "$BACKUP_PATH/user-systemd/" 2>/dev/null || true

# 8. Cron jobs
crontab -l > "$BACKUP_PATH/crontab.txt" 2>/dev/null || echo "# no crontab" > "$BACKUP_PATH/crontab.txt"

# 9. Logs (last 7 days)
mkdir -p "$BACKUP_PATH/logs"
for f in trades.log webhook.log health_check.log; do
    [ -f "$BOT_DIR/$f" ] && cp "$BOT_DIR/$f" "$BACKUP_PATH/logs/"
done

# 10. Docs
cp -r "$BOT_DIR/docs" "$BACKUP_PATH/"

# Package it
tar -czf "${BACKUP_PATH}.tar.gz" -C "$BACKUP_DIR" "$BACKUP_NAME"
rm -rf "$BACKUP_PATH"

# Cleanup old backups
find "$BACKUP_DIR" -name "ozzybot_backup_*.tar.gz" -mtime +$RETENTION_DAYS -delete

echo "[$TIMESTAMP] Backup complete: ${BACKUP_NAME}.tar.gz"
echo "[$TIMESTAMP] Size: $(du -h "${BACKUP_PATH}.tar.gz" | cut -f1)"
echo "[$TIMESTAMP] Backups retained: $(find "$BACKUP_DIR" -name '*.tar.gz' | wc -l)"
