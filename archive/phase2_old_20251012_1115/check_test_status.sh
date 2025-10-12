#!/bin/bash
# A/B Test Status Check Script
# Quick command to check test progress

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  🧪 TIME FILTER A/B TEST - QUICK STATUS"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Check bot is running
if ps aux | grep -v grep | grep "python.*main.py" > /dev/null; then
    BOT_PID=$(ps aux | grep -v grep | grep "python.*main.py" | awk '{print $2}')
    echo "✅ Bot Status: RUNNING (PID: $BOT_PID)"
else
    echo "❌ Bot Status: NOT RUNNING"
    echo "   Start with: cd ~/ozzy-simple && nohup ./venv/bin/python main.py > bot.log 2>&1 &"
fi

echo ""

# Check current UTC time
echo "🕐 Current Time: $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
CURRENT_HOUR=$(date -u '+%H')
if [ $CURRENT_HOUR -ge 22 ] || [ $CURRENT_HOUR -lt 2 ]; then
    echo "   ⏰ IN AVOID WINDOW (22:00-02:00 UTC) - Test group filtered"
else
    echo "   ✅ Outside avoid window - Both groups active"
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Run detailed status
cd ~/ozzy-simple
./venv/bin/python scripts/test_time_filter.py --status

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "📚 Commands:"
echo "   Watch logs:    tail -f ~/ozzy-simple/bot.log"
echo "   Full report:   cd ~/ozzy-simple && ./venv/bin/python scripts/test_time_filter.py --report"
echo "   Bot status:    ps aux | grep main.py"
echo ""
