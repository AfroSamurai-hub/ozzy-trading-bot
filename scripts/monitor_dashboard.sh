#!/bin/bash
# 🔍 Simple System Monitor

clear

echo "╔════════════════════════════════════════════════════════════╗"
echo "║                                                            ║"
echo "║           🔍 SYSTEM STATUS DASHBOARD 🔍                   ║"
echo "║                                                            ║"
echo "╚════════════════════════════════════════════════════════════╝"
echo ""
echo "⏰ Current Time: $(date '+%Y-%m-%d %H:%M:%S %Z')"
echo ""

echo "═══════════════════════════════════════════════════════════"
echo "📊 OVERNIGHT TEST STATUS (PID 6683)"
echo "═══════════════════════════════════════════════════════════"

if ps -p 6683 > /dev/null 2>&1; then
    echo "✅ Status: RUNNING"
    echo ""
    ps -p 6683 -o pid,etime,%cpu,%mem,cmd --no-headers | while read line; do
        echo "📈 Process Info:"
        echo "   $line"
    done
    echo ""
    
    # Get start time
    START_TIME=$(ps -p 6683 -o lstart --no-headers)
    echo "🕐 Started: $START_TIME"
    
    # Get elapsed time
    ELAPSED=$(ps -p 6683 -o etime --no-headers | tr -d ' ')
    echo "⏱️  Runtime: $ELAPSED"
    
else
    echo "❌ Status: NOT RUNNING"
    echo ""
    echo "💡 Process may have completed or crashed."
    echo "   Check logs/overnight_FIXED_20251016_1637.log for results"
fi

echo ""
echo "═══════════════════════════════════════════════════════════"
echo "📝 LOG FILES STATUS"
echo "═══════════════════════════════════════════════════════════"

if [ -f "logs/overnight_FIXED_20251016_1637.log" ]; then
    SIZE=$(stat -f%z "logs/overnight_FIXED_20251016_1637.log" 2>/dev/null || stat -c%s "logs/overnight_FIXED_20251016_1637.log" 2>/dev/null)
    LINES=$(wc -l < "logs/overnight_FIXED_20251016_1637.log")
    
    echo "📄 Overnight Log:"
    echo "   Size: $SIZE bytes"
    echo "   Lines: $LINES"
    
    if [ "$SIZE" -le 100 ]; then
        echo "   ⚠️  Very small - output likely buffered"
    else
        echo "   ✅ Log file has content!"
        echo ""
        echo "📋 Last 10 lines:"
        tail -10 "logs/overnight_FIXED_20251016_1637.log" | sed 's/^/   /'
    fi
else
    echo "❌ Log file not found"
fi

echo ""
echo "═══════════════════════════════════════════════════════════"
echo "🗄️  PATTERN DATABASE"
echo "═══════════════════════════════════════════════════════════"

if [ -d "data/vector_db" ]; then
    DB_SIZE=$(du -sh data/vector_db 2>/dev/null | cut -f1)
    echo "📊 ChromaDB Size: $DB_SIZE"
    
    FILE_COUNT=$(find data/vector_db -type f 2>/dev/null | wc -l)
    echo "📁 Files: $FILE_COUNT"
else
    echo "❌ Database directory not found"
fi

echo ""
echo "═══════════════════════════════════════════════════════════"
echo "💾 PATTERN INTELLIGENCE DATA"
echo "═══════════════════════════════════════════════════════════"

if [ -f "data/pattern_stats.json" ]; then
    STATS_SIZE=$(stat -f%z "data/pattern_stats.json" 2>/dev/null || stat -c%s "data/pattern_stats.json" 2>/dev/null)
    echo "📊 Pattern Stats File: $STATS_SIZE bytes"
    
    # Try to count patterns
    PATTERN_COUNT=$(grep -o '"pattern_id"' data/pattern_stats.json 2>/dev/null | wc -l)
    echo "🎯 Patterns Tracked: ~$PATTERN_COUNT"
else
    echo "⚠️  Pattern stats file not found (will be created on first trade)"
fi

echo ""
echo "═══════════════════════════════════════════════════════════"
echo "💼 PORTFOLIO STATE"
echo "═══════════════════════════════════════════════════════════"

if [ -f "data/portfolio_state.json" ]; then
    echo "📊 Portfolio state file exists"
    
    # Try to extract balance
    if command -v jq &> /dev/null; then
        BALANCE=$(jq -r '.balance // "N/A"' data/portfolio_state.json 2>/dev/null)
        POSITIONS=$(jq -r '.positions | length // 0' data/portfolio_state.json 2>/dev/null)
        CLOSED=$(jq -r '.closed_positions | length // 0' data/portfolio_state.json 2>/dev/null)
        
        echo "💰 Balance: R$BALANCE"
        echo "📊 Open Positions: $POSITIONS"
        echo "✅ Closed Positions: $CLOSED"
    else
        echo "   (Install 'jq' for detailed stats)"
    fi
else
    echo "⚠️  Portfolio state file not found"
fi

echo ""
echo "═══════════════════════════════════════════════════════════"
echo "🌍 CURRENT MARKET SESSION"
echo "═══════════════════════════════════════════════════════════"

HOUR=$(date -u +%H)

if [ $HOUR -ge 0 ] && [ $HOUR -lt 7 ]; then
    echo "🌏 Asian Early (00-07 UTC) - Low volume"
elif [ $HOUR -ge 7 ] && [ $HOUR -lt 13 ]; then
    echo "🌏 Asian Late / European Start (07-13 UTC) - Building"
elif [ $HOUR -ge 13 ] && [ $HOUR -lt 16 ]; then
    echo "🔥 OVERLAP (13-16 UTC) - HIGHEST VOLUME!"
elif [ $HOUR -ge 16 ] && [ $HOUR -lt 22 ]; then
    echo "🌎 US Session (16-22 UTC) - High volume"
else
    echo "🌏 Asian Session (22-24 UTC) - Low volume"
fi

echo ""
echo "═══════════════════════════════════════════════════════════"
echo "📊 RECENT ACTIVITY"
echo "═══════════════════════════════════════════════════════════"

# Check for recent log files
echo "📝 Recent logs (last 24h):"
find logs -name "*.log" -mtime -1 -type f 2>/dev/null | while read log; do
    SIZE=$(stat -f%z "$log" 2>/dev/null || stat -c%s "$log" 2>/dev/null)
    echo "   • $(basename $log): $SIZE bytes"
done

echo ""
echo "═══════════════════════════════════════════════════════════"
echo "💡 QUICK COMMANDS"
echo "═══════════════════════════════════════════════════════════"
echo ""
echo "  Watch this dashboard:"
echo "    watch -n 10 bash scripts/monitor_dashboard.sh"
echo ""
echo "  Tail overnight log:"
echo "    tail -f logs/overnight_FIXED_20251016_1637.log"
echo ""
echo "  Check process:"
echo "    ps aux | grep 6683"
echo ""
echo "  Force log flush (kills process!):"
echo "    kill -TERM 6683"
echo ""
echo "═══════════════════════════════════════════════════════════"
