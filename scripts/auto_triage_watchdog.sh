#!/bin/bash
# ==============================================================================
# OzzyBot Auto-Triage Watchdog
# Checks the unified webhook and monitor services every 5 minutes.
# Auto-heals by restarting affected services and logs every action taken.
# ==============================================================================

set -o pipefail

REPO_ROOT="/home/rick/ozzy-bot"
LOG_FILE="$REPO_ROOT/logs/watchdog.log"
CURL_TIMEOUT=8           # Seconds before curl gives up on a status endpoint
MAX_CONSECUTIVE_FAILS=2  # Restart after this many sequential failures

# State file to track consecutive failures (survives across cron runs)
STATE_DIR="$REPO_ROOT/cache"
FAIL_FILE="$STATE_DIR/.watchdog_fails"

ENV_FILE="$REPO_ROOT/.env"

mkdir -p "$STATE_DIR"
export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id - u)}"

# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────
ts() { date '+%Y-%m-%d %H:%M:%S'; }

log() {
    echo "[$(ts)] $*" | tee -a "$LOG_FILE"
}

# Send a Telegram message. Called ONLY when a restart is actually triggered.
# Credentials are loaded fresh from .env each time — never cached in memory.
send_telegram() {
    local message="$1"

    # Source credentials from .env (ignore errors if key missing)
    local token chat_id
    token=$(grep -E '^TELEGRAM_TOKEN=' "$ENV_FILE" 2>/dev/null | cut -d'=' -f2- | tr -d '\r')
    chat_id=$(grep -E '^TELEGRAM_CHAT_ID=' "$ENV_FILE" 2>/dev/null | cut -d'=' -f2- | tr -d '\r')

    if [ -z "$token" ] || [ -z "$chat_id" ]; then
        log "⚠️  TELEGRAM: Credentials missing from .env — alert not sent."
        return 1
    fi

    local api_url="https://api.telegram.org/bot${token}/sendMessage"
    local http_code
    http_code=$(curl -s -o /dev/null -w "%{http_code}" \
        --max-time 10 \
        -X POST "$api_url" \
        -d "chat_id=${chat_id}" \
        --data-urlencode "text=${message}" \
        --data-urlencode "parse_mode=HTML" 2>/dev/null)

    if [ "$http_code" = "200" ]; then
        log "📲  TELEGRAM: Alert sent successfully (HTTP $http_code)."
    else
        log "❌  TELEGRAM: Alert failed (HTTP $http_code). Check token/chat_id in .env."
    fi
}

read_fails() {
    local file="$1"
    if [ -f "$file" ]; then cat "$file"; else echo 0; fi
}

write_fails() {
    local file="$1" count="$2"
    echo "$count" > "$file"
}

reset_fails() {
    write_fails "$1" 0
}

# ──────────────────────────────────────────────────────────────────────────────
# Service health check
# Returns 0 (healthy) or 1 (unhealthy)
# ──────────────────────────────────────────────────────────────────────────────
check_endpoint() {
    local url="$1"
    local response http_status bot_status

    # Capture response body + HTTP status code
    response=$(curl -s -o /tmp/watchdog_resp.json -w "%{http_code}" \
        --max-time "$CURL_TIMEOUT" "$url" 2>/dev/null)
    http_status="$response"

    # Fail if curl timed out or non-200 HTTP
    if [ -z "$http_status" ] || [ "$http_status" != "200" ]; then
        return 1
    fi

    # Fail if the JSON body says anything other than "running"
    bot_status=$(jq -r '.status // "unknown"' /tmp/watchdog_resp.json 2>/dev/null)
    if [ "$bot_status" != "running" ]; then
        return 1
    fi

    return 0
}

# ──────────────────────────────────────────────────────────────────────────────
# Restart a group of services and log the action
# ──────────────────────────────────────────────────────────────────────────────
restart_services() {
    local label="$1"
    shift
    local services=("$@")
    local restart_time
    restart_time=$(ts)

    log "⚠️  SELF-HEAL: $label unhealthy — restarting services: ${services[*]}"
    if systemctl --user restart "${services[@]}" 2>&1 | tee -a "$LOG_FILE"; then
        log "✅  RESTART OK: ${services[*]} restarted successfully."
        send_telegram "⚠️ <b>OzzyBot Auto-Triage</b>\n\nSelf-heal triggered on <b>$label</b>.\n\n🔁 Restarted: <code>${services[*]}</code>\n🕐 Time: $restart_time\n\nServices are back online. Check /status to confirm."
    else
        log "❌  RESTART FAILED: Could not restart ${services[*]}. Manual intervention required!"
        send_telegram "🔴 <b>OzzyBot Auto-Triage — RESTART FAILED</b>\n\nCould not restart <b>$label</b>.\n\n❌ Services: <code>${services[*]}</code>\n🕐 Time: $restart_time\n\n⚡ Manual intervention required!"
    fi
}

# ──────────────────────────────────────────────────────────────────────────────
# Triage: Unified core (port 5001)
# Covers: ozzybot-webhook.service + ozzybot-monitor.service
# ──────────────────────────────────────────────────────────────────────────────
triage_unified() {
    local fails
    fails=$(read_fails "$FAIL_FILE")

    if check_endpoint "http://127.0.0.1:5001/status"; then
        if [ "$fails" -gt 0 ]; then
            log "✅  UNIFIED: Recovered after $fails failed check(s). Resetting counter."
            reset_fails "$FAIL_FILE"
        fi
        return 0
    fi

    fails=$((fails + 1))
    write_fails "$FAIL_FILE" "$fails"
    log "⚠️  UNIFIED: Health check FAILED ($fails/$MAX_CONSECUTIVE_FAILS) — endpoint http://127.0.0.1:5001/status unresponsive."

    if [ "$fails" -ge "$MAX_CONSECUTIVE_FAILS" ]; then
        restart_services "UNIFIED CORE" "ozzybot-webhook.service" "ozzybot-monitor.service"
        reset_fails "$FAIL_FILE"
    fi
}

# ──────────────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────────────
triage_unified

exit 0
