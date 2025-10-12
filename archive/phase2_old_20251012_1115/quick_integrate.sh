#!/bin/bash
# Quick Integration Script for Time Filter A/B Test
# Run: bash quick_integrate.sh

echo "🧪 Time Filter A/B Test - Quick Integration"
echo "==========================================="
echo ""

# Check if backup exists
if [ ! -f "main.py.backup" ]; then
    echo "📦 Creating backup..."
    cp main.py main.py.backup
    echo "✅ Backup created: main.py.backup"
else
    echo "✅ Backup already exists: main.py.backup"
fi

echo ""
echo "📝 Required changes to main.py:"
echo ""
echo "1️⃣  Add import (after line 19):"
echo "   from time_filter_wrapper import TimeFilterWrapper"
echo ""
echo "2️⃣  Initialize in __init__ (after line 62):"
echo "   self.time_filter = TimeFilterWrapper("
echo "       test_name='time_filter_night',"
echo "       avoid_hours=[(22, 2)],"
echo "       enabled=True"
echo "   )"
echo ""
echo "3️⃣  Apply filter in check_signal() (after line 216):"
echo "   signal, test_group = self.time_filter.apply_filter(signal, symbol)"
echo ""
echo "4️⃣  Tag trades in execute_trade() (line ~335):"
echo "   'entry_reason': self.time_filter.format_entry_reason("
echo "       signal.get('reason', ''),"
echo "       test_group"
echo "   )"
echo ""
echo "==========================================="
echo ""
echo "📚 Full instructions: INTEGRATION_STEPS.md"
echo "🔍 Monitor progress: ./venv/bin/python scripts/test_time_filter.py --status"
echo ""
echo "⚠️  Remember to restart bot after changes:"
echo "   pkill -f 'python main.py'"
echo "   nohup python main.py > bot.log 2>&1 &"
echo ""
