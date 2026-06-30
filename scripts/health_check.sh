#!/usr/bin/env bash
# OzzyBot Health Check - Zero token cost
# Checks: active unified webhook, Binance monitor, disk space, stale equity date
# Sends Telegram alert ONLY on failure via existing telegram_client.py

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BOT_DIR="/home/rick/ozzy-bot"
WEBHOOK_URL="${HERMES_HEALTH_WEBHOOK_URL:-http://127.0.0.1:5001/ping}"
LOG_FILE="$BOT_DIR/health_check.log"
ALERT_FLAG="$BOT_DIR/.health_alert_pending"
TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')
ISSUES=""

# Check 1: Webhook responding?
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout 5 --max-time 10 "$WEBHOOK_URL" 2>/dev/null || echo "000")
if [ "$HTTP_CODE" != "200" ]; then
    ISSUES="${ISSUES}❌ Active webhook not responding at $WEBHOOK_URL (HTTP $HTTP_CODE)\n"
fi


# Check 3: Binance position monitor service running?
MONITOR_SERVICE="${HERMES_HEALTH_MONITOR_SERVICE:-ozzybot-monitor.service}"
if ! systemctl --user is-active --quiet "$MONITOR_SERVICE"; then
    ISSUES="${ISSUES}❌ Binance position monitor service not active ($MONITOR_SERVICE)\n"
fi

# Check 4: Disk space
DISK_USAGE=$(df / | tail -1 | awk '{print $5}' | sed 's/%//')
if [ "$DISK_USAGE" -gt 90 ]; then
    ISSUES="${ISSUES}⚠️ Disk usage at ${DISK_USAGE}%\n"
fi

# Check 5: day_equity.json date (stale date blocks all trading)
DAY_EQUITY_FILE="${HERMES_HEALTH_DAY_EQUITY_FILE:-$BOT_DIR/day_equity.json}"
if [ -f "$DAY_EQUITY_FILE" ]; then
    EQUITY_DATE=$(/usr/bin/python3 -c "import json; print(json.load(open('$DAY_EQUITY_FILE'))['date'])" 2>/dev/null || echo "unknown")
    TODAY=$(date '+%Y-%m-%d')
    if [ "$EQUITY_DATE" != "$TODAY" ]; then
        ISSUES="${ISSUES}⚠️ $(basename "$DAY_EQUITY_FILE") stale ($EQUITY_DATE vs $TODAY) — restart active webhook\n"
    fi
fi

# Log result
if [ -n "$ISSUES" ]; then
    echo "[$TIMESTAMP] FAIL: $(echo -e "$ISSUES" | tr '\n' ' ')" >> "$LOG_FILE"
    # Write alert flag for Python to pick up
    echo -e "$ISSUES" > "$ALERT_FLAG"
    echo "FAIL"
    exit 1
else
    # Remove alert flag if it exists (recovery)
    rm -f "$ALERT_FLAG"
    echo "[$TIMESTAMP] OK" >> "$LOG_FILE"
    echo "OK"
    exit 0
fi
