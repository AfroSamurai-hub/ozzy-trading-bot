#!/usr/bin/env bash
# Monitor overnight 15-minute test
set -euo pipefail

LOG_FILE=$(ls -t logs/overnight_15min_*.log 2>/dev/null | head -1)

if [ -z "$LOG_FILE" ]; then
    echo "❌ No overnight test log found"
    exit 1
fi

clear
echo "=========================================="
echo "🔍 OVERNIGHT 15-MIN TEST MONITOR"
echo "=========================================="
echo ""

# Process status
PID=$(pgrep -f "bulletproof_test.py.*900" || echo "")
if [ -n "$PID" ]; then
    echo "✅ Test running (PID: $PID)"
    ps -p "$PID" -o pid,etime,cmd --no-headers
else
    echo "⚠️  Test not running"
fi
echo ""

# WARP status
WARP_STATUS=$(warp-cli status 2>&1 | grep -i "status" || echo "Unknown")
echo "🌐 WARP: $WARP_STATUS"
echo ""

# Log file info
echo "📝 Log: $LOG_FILE"
echo "   Size: $(du -h "$LOG_FILE" | awk '{print $1}')"
echo "   Modified: $(stat -c %y "$LOG_FILE" | cut -d. -f1)"
echo ""

# Decision progress
DECISIONS=$(grep -c "DECISION COMPLETE" "$LOG_FILE" || echo "0")
echo "🎯 Progress: $DECISIONS/24 decisions completed"
echo "   Expected: ~$(echo "24 * 900 / 3600" | bc) hours total"
ELAPSED=$(grep -m1 "🔥 BULLETPROOF TEST STARTING" "$LOG_FILE" | awk '{print $3, $4}' || echo "")
if [ -n "$ELAPSED" ]; then
    echo "   Started: $ELAPSED"
fi
echo ""

# Latest decision
echo "📊 Latest Decision:"
grep -A 4 "DECISION COMPLETE" "$LOG_FILE" | tail -5 || echo "   No decisions yet"
echo ""

# Labeler status
LABELER_PID=$(pgrep -f "live_labeler.py" || echo "")
if [ -n "$LABELER_PID" ]; then
    echo "✅ Labeler running (PID: $LABELER_PID)"
else
    echo "⚠️  Labeler not running"
fi
echo ""

echo "=========================================="
echo "Commands:"
echo "  tail -f $LOG_FILE  # Watch live"
echo "  kill $PID          # Stop test"
echo "  ./scripts/start_labeler.sh  # Start labeler"
echo "=========================================="
