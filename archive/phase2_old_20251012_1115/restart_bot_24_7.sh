#!/bin/bash
# Restart Bot with 24/7 Trading Enabled
# Usage: bash restart_bot_24_7.sh

set -e  # Exit on error

echo "=============================================="
echo "  🔄 RESTARTING BOT WITH 24/7 TRADING"
echo "=============================================="
echo ""

# Step 1: Find and stop current bot
echo "Step 1: Stopping current bot..."
if pgrep -f "python main.py" > /dev/null; then
    BOT_PID=$(pgrep -f "python main.py")
    echo "  Found bot running (PID: $BOT_PID)"
    echo "  Killing process..."
    kill $BOT_PID
    sleep 2
    
    # Check if still running
    if pgrep -f "python main.py" > /dev/null; then
        echo "  ⚠️  Bot still running, force killing..."
        kill -9 $BOT_PID
        sleep 1
    fi
    echo "  ✅ Bot stopped"
else
    echo "  ℹ️  No bot currently running"
fi
echo ""

# Step 2: Verify config
echo "Step 2: Verifying 24/7 config..."
cd ~/ozzy-simple
source venv/bin/activate

HOURS_ENABLED=$(python -c "import config; print(config.TRADING_HOURS['enabled'])")
if [ "$HOURS_ENABLED" = "False" ]; then
    echo "  ✅ Trading hours disabled (24/7 mode)"
else
    echo "  ❌ Trading hours still enabled!"
    echo "  Please check config.py TRADING_HOURS setting"
    exit 1
fi
echo ""

# Step 3: Start bot in background
echo "Step 3: Starting bot with 24/7 trading..."
nohup python main.py > bot.log 2>&1 &
BOT_PID=$!
sleep 3
echo "  ✅ Bot started (PID: $BOT_PID)"
echo ""

# Step 4: Verify startup
echo "Step 4: Verifying 24/7 mode active..."
if pgrep -f "python main.py" > /dev/null; then
    echo "  ✅ Bot process running"
    
    # Check logs for 24/7 message
    sleep 2
    if grep -q "24/7 (unrestricted)" bot.log; then
        echo "  ✅ 24/7 mode confirmed in logs"
    else
        echo "  ⚠️  Could not confirm 24/7 mode in logs yet"
        echo "  Check logs manually: tail -f bot.log"
    fi
else
    echo "  ❌ Bot not running!"
    echo "  Check logs: cat bot.log"
    exit 1
fi
echo ""

# Step 5: Display status
echo "Step 5: Bot status..."
ps aux | grep "python main.py" | grep -v grep
echo ""

echo "=============================================="
echo "  ✅ BOT RESTARTED WITH 24/7 TRADING"
echo "=============================================="
echo ""
echo "📋 Next steps:"
echo "  1. Monitor logs: tail -f bot.log"
echo "  2. Check for '24/7 (unrestricted)' message"
echo "  3. Verify signals being checked immediately"
echo "  4. Run: python scripts/quick_status.py"
echo ""
echo "🎯 Expected: First trades within 15-30 minutes!"
echo ""
