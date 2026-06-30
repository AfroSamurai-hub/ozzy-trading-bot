#!/bin/bash
# ==============================================================================
# Hermes Daily Report Pipeline
# Runs hermes_ai_brief.py, parses the Gemini summary, and sends it to Telegram.
# ==============================================================================

set -o pipefail

# Repo root directory
REPO_ROOT="/home/rick/ozzy-bot"
cd "$REPO_ROOT"

# Load environment variables
if [ -f ".env" ]; then
    # Filter and export only valid variable assignments to avoid subshell evaluation issues
    eval "$(grep -v '^#' .env | grep -v '^\s*$' | sed 's/^/export /')"
fi

# Fallback compatibility check for token naming differences
BOT_TOKEN="${TELEGRAM_BOT_TOKEN:-$TELEGRAM_TOKEN}"
CHAT_ID="$TELEGRAM_CHAT_ID"

if [ -z "$BOT_TOKEN" ] || [ -z "$CHAT_ID" ]; then
    echo "❌ Error: TELEGRAM_TOKEN or TELEGRAM_CHAT_ID is missing from .env!" >&2
    exit 1
fi

echo "🚀 Running Hermes AI Brief Generator..."
# Run the AI generator and capture both stdout and stderr
RAW_OUTPUT=$("$REPO_ROOT/venv/bin/python3" "$REPO_ROOT/scripts/hermes_ai_brief.py" 2>err.log)
EXIT_CODE=$?

if [ $EXIT_CODE -ne 0 ]; then
    ERR_MSG=$(cat err.log)
    echo "❌ AI Brief Generation Failed (Exit Code: $EXIT_CODE): $ERR_MSG" >&2
    
    # Notify operator of the generation failure
    ERROR_TEXT="⚠️ <b>Hermes Report Generation Failed</b>
Error Code: <code>$EXIT_CODE</code>
Details: <code>$ERR_MSG</code>"

    curl -s -X POST "https://api.telegram.org/bot${BOT_TOKEN}/sendMessage" \
        -d "chat_id=${CHAT_ID}" \
        -d "parse_mode=HTML" \
        --data-urlencode "text=${ERROR_TEXT}"
    
    rm -f err.log
    exit $EXIT_CODE
fi

# Clean up err.log if it succeeded
rm -f err.log

# Parse the 'summary' from the JSON output using jq
SUMMARY=$(echo "$RAW_OUTPUT" | jq -r '.summary' 2>/dev/null)

if [ -z "$SUMMARY" ] || [ "$SUMMARY" == "null" ]; then
    echo "❌ Error: Could not parse 'summary' from generator output!" >&2
    
    ERROR_TEXT="⚠️ <b>Hermes Report Parser Failed</b>
Reason: The Gemini advisor brief did not contain a valid '.summary' text block."

    curl -s -X POST "https://api.telegram.org/bot${BOT_TOKEN}/sendMessage" \
        -d "chat_id=${CHAT_ID}" \
        -d "parse_mode=HTML" \
        --data-urlencode "text=${ERROR_TEXT}"
    exit 1
fi

echo "📤 Dispatching parsed brief to Telegram..."

TELEGRAM_TEXT="🤖 <b>Hermes AI Daily Diagnostics Brief</b>

${SUMMARY}"

# Send curl request to Telegram API
RESPONSE=$(curl -s -w "\n%{http_code}" -X POST "https://api.telegram.org/bot${BOT_TOKEN}/sendMessage" \
    -d "chat_id=${CHAT_ID}" \
    -d "parse_mode=HTML" \
    --data-urlencode "text=${TELEGRAM_TEXT}")

HTTP_STATUS=$(echo "$RESPONSE" | tail -n1)
BODY=$(echo "$RESPONSE" | sed '$d')

if [ "$HTTP_STATUS" -ne 200 ]; then
    echo "❌ Failed to send Telegram message. HTTP Status: $HTTP_STATUS" >&2
    echo "Response: $BODY" >&2
    exit 1
fi

echo "✅ Hermes Daily Report completed and delivered successfully!"
exit 0
