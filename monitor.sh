#!/bin/bash
# Quick monitoring script - fixes the Python path issue

cd /home/rick/ozzy-simple

case "$1" in
    "status")
        /home/rick/ozzy-simple/venv/bin/python monitor_phase1.py
        ;;
    "learning")
        /home/rick/ozzy-simple/venv/bin/python learning_analysis.py
        ;;
    "analysis")
        /home/rick/ozzy-simple/venv/bin/python phase1_analysis.py
        ;;
    "log")
        tail -f logs/phase1_monitor.log
        ;;
    "check")
        ps aux | grep main.py | grep -v grep
        ;;
    "restart")
        pkill -f main.py
        sleep 2
        nohup bash -c 'echo "yes" | /home/rick/ozzy-simple/venv/bin/python main.py' > logs/phase1_monitor.log 2>&1 &
        echo "Bot restarted. Check status in 10 seconds with: ./monitor.sh status"
        ;;
    "signals")
        sqlite3 ozzy_simple.db "SELECT COUNT(*) as today_signals FROM signals WHERE DATE(timestamp) = DATE('now')"
        ;;
    *)
        echo "🤖 Phase 1 Monitor - Usage:"
        echo ""
        echo "  ./monitor.sh status     - Quick status check"
        echo "  ./monitor.sh learning   - Learning analysis"
        echo "  ./monitor.sh log        - Live log feed"
        echo "  ./monitor.sh check      - Check if bot running"
        echo "  ./monitor.sh restart    - Restart bot"
        echo "  ./monitor.sh signals    - Count today's signals"
        echo "  ./monitor.sh analysis   - Full Phase 1 analysis (Monday)"
        echo ""
        echo "Current status:"
        /home/rick/ozzy-simple/venv/bin/python monitor_phase1.py
        ;;
esac