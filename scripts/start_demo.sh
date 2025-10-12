#!/bin/bash
# Start Demo Trading Bot

cd ~/ozzy-simple

# Kill any existing demo bot processes
pkill -f "demo_main.py"

# Wait a moment for processes to stop
sleep 2

# Start the demo bot in the background
nohup python demo_main.py > demo_bot.log 2>&1 &

echo "🚀 Demo bot started!"
echo "💰 Starting with R10,000 virtual capital"
echo ""
echo "📊 Monitor with:"
echo "   tail -f demo_bot.log              # Watch logs"
echo "   python scripts/demo_dashboard.py  # Live dashboard"
echo "   python scripts/fresh_demo_test.py --status  # Quick status"
echo ""
echo "📈 View reports:"
echo "   python scripts/demo_report.py --full  # Comprehensive report"