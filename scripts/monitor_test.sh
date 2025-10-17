#!/bin/bash

# Monitoring Dashboard for Overnight Test
# Usage: ./scripts/monitor_test.sh

LOG_FILE="logs/overnight_ai_warp_20251016_215946.log"
PROGRESS_FILE="logs/test_progress.txt"
PID=27047

clear

echo "════════════════════════════════════════════════════════════════"
echo "🔥 OVERNIGHT TEST MONITORING DASHBOARD"
echo "════════════════════════════════════════════════════════════════"
echo ""
echo "📅 Date: $(date '+%Y-%m-%d %H:%M:%S')"
echo ""

# Check if process is running
echo "════════════════════════════════════════════════════════════════"
echo "🔍 PROCESS STATUS"
echo "════════════════════════════════════════════════════════════════"
if ps -p $PID > /dev/null 2>&1; then
    echo "✅ Test is RUNNING"
    echo "   PID: $PID"
    CPU_MEM=$(ps aux | grep $PID | grep -v grep | awk '{print "   CPU: "$3"%  MEM: "$4"%  Runtime: "$10}')
    echo "$CPU_MEM"
else
    echo "❌ Test is NOT RUNNING"
    echo "   Process may have completed or crashed"
fi
echo ""

# Check WARP status
echo "════════════════════════════════════════════════════════════════"
echo "🌐 CLOUDFLARE WARP STATUS"
echo "════════════════════════════════════════════════════════════════"
WARP_STATUS=$(warp-cli status 2>&1 | grep -i "Status update" || echo "Unknown")
echo "$WARP_STATUS"
echo ""

# Check log file
echo "════════════════════════════════════════════════════════════════"
echo "📊 TEST PROGRESS"
echo "════════════════════════════════════════════════════════════════"
if [ -f "$LOG_FILE" ]; then
    LOG_SIZE=$(ls -lh "$LOG_FILE" | awk '{print $5}')
    LOG_LINES=$(wc -l < "$LOG_FILE")
    echo "📁 Log File: $LOG_FILE"
    echo "   Size: $LOG_SIZE"
    echo "   Lines: $LOG_LINES"
    echo ""
    
    # Count decisions
    DECISIONS_MADE=$(grep -c "🎯 DECISION #" "$LOG_FILE" 2>/dev/null || echo "0")
    echo "✅ Decisions Completed: $DECISIONS_MADE / 72"
    
    # Calculate progress percentage
    PROGRESS=$((DECISIONS_MADE * 100 / 72))
    echo "📈 Progress: $PROGRESS%"
    
    # Progress bar
    FILLED=$((PROGRESS / 2))
    printf "   ["
    for i in $(seq 1 50); do
        if [ $i -le $FILLED ]; then
            printf "█"
        else
            printf "░"
        fi
    done
    printf "] $PROGRESS%%\n"
    echo ""
    
    # Time estimate
    if [ "$DECISIONS_MADE" -gt 0 ]; then
        START_TIME=$(grep "🔥 BULLETPROOF TEST STARTING" -A 2 "$LOG_FILE" | grep "Start Time:" | cut -d' ' -f5-)
        if [ -n "$START_TIME" ]; then
            echo "⏰ Started: $START_TIME"
        fi
        
        REMAINING=$((72 - DECISIONS_MADE))
        MINUTES_LEFT=$((REMAINING * 5))
        HOURS_LEFT=$((MINUTES_LEFT / 60))
        MINS_LEFT=$((MINUTES_LEFT % 60))
        echo "⏳ Estimated Time Remaining: ${HOURS_LEFT}h ${MINS_LEFT}m"
    fi
else
    echo "❌ Log file not found!"
fi
echo ""

# Check for errors
echo "════════════════════════════════════════════════════════════════"
echo "⚠️  ERROR CHECK"
echo "════════════════════════════════════════════════════════════════"
if [ -f "$LOG_FILE" ]; then
    ERROR_COUNT=$(grep -i -c "error\|exception\|timeout\|failed" "$LOG_FILE" 2>/dev/null || echo "0")
    if [ "$ERROR_COUNT" -gt 0 ]; then
        echo "⚠️  Found $ERROR_COUNT potential errors/warnings"
        echo "   Last 5 error-related lines:"
        grep -i "error\|exception\|timeout\|failed" "$LOG_FILE" | tail -5 | sed 's/^/   /'
    else
        echo "✅ No errors detected"
    fi
else
    echo "❌ Log file not found!"
fi
echo ""

# Latest activity
echo "════════════════════════════════════════════════════════════════"
echo "📝 LATEST ACTIVITY (Last 15 lines)"
echo "════════════════════════════════════════════════════════════════"
if [ -f "$LOG_FILE" ]; then
    tail -15 "$LOG_FILE" | sed 's/^/   /'
else
    echo "❌ Log file not found!"
fi
echo ""

echo "════════════════════════════════════════════════════════════════"
echo "💡 QUICK COMMANDS"
echo "════════════════════════════════════════════════════════════════"
echo "   Watch live: tail -f $LOG_FILE"
echo "   Kill test:  kill -9 $PID"
echo "   WARP off:   warp-cli disconnect"
echo "   WARP on:    warp-cli connect"
echo "   Refresh:    ./scripts/monitor_test.sh"
echo "════════════════════════════════════════════════════════════════"
