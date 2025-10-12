#!/bin/bash
# Quick upgrade from conservative to ambitious AI

set -e

echo "🔥 OZZY AI - UPGRADING TO AMBITIOUS MODE"
echo "========================================"
echo ""

# Move to repo root if not already there
if [ ! -f "main.py" ]; then
  if [ -d "/home/rick/ozzy-simple" ]; then
    cd /home/rick/ozzy-simple
  fi
fi

# Check if in correct directory
if [ ! -f "main.py" ]; then
    echo "❌ Error: main.py not found"
    echo "   Run this from /home/rick/ozzy-simple directory"
    exit 1
fi

# Ensure logs dir exists
mkdir -p logs

# Backup conservative AI
echo "📦 Backing up conservative AI..."
if [ -f "ai_signal_validator.py" ]; then
    cp ai_signal_validator.py ai_signal_validator_conservative.py.bak
    echo "✅ Backup created: ai_signal_validator_conservative.py.bak"
else
    echo "⚠️  Conservative AI not found (might be first install)"
fi

# Copy ambitious AI (from either known path)
echo ""
echo "🚀 Installing ambitious AI..."
SRC1="/mnt/user-data/outputs/ozzy_ai_agent.py"
SRC2="/home/rick/Downloads/files (2)/ozzy_ai_agent.py"
if [ -f "$SRC1" ]; then
    cp "$SRC1" .
    echo "✅ Ambitious AI installed: ozzy_ai_agent.py (from $SRC1)"
elif [ -f "$SRC2" ]; then
    cp "$SRC2" .
    echo "✅ Ambitious AI installed: ozzy_ai_agent.py (from $SRC2)"
else
    echo "❌ Error: ozzy_ai_agent.py not found in known locations"
    echo "   Expected at: $SRC1 or $SRC2"
    exit 1
fi

echo ""
echo "🔍 Checking main.py integration..."
if grep -q "ai_agent_enabled" main.py || grep -q "from ozzy_ai_agent import" main.py; then
    echo "✅ Ambitious AI hooks detected in main.py"
    # Flip config flag on
    if grep -q "AMBITIOUS_AI" config.py; then
        sed -i "s/^AMBITIOUS_AI *= *.*/AMBITIOUS_AI = True/" config.py || true
    else
        echo "AMBITIOUS_AI = True" >> config.py
    fi
    echo "✅ Enabled AMBITIOUS_AI=True in config.py"
else
    echo "⚠️  Ambitious AI not detected in main.py — offering auto-wiring"
    read -p "🤔 Auto-update main.py to wire in OzzyAIAgent (parallel to validator)? (y/n): " auto_update
    if [ "$auto_update" = "y" ]; then
        cp main.py main.py.bak
        echo "✅ Backup created: main.py.bak"
        # Minimal safe insert: import and init flag section. We'll append import near existing validator import.
        awk '
            BEGIN{done=0}
            /from ai_signal_validator import AISignalValidator/ && done==0 {
                print $0; print "try:\n    from ozzy_ai_agent import OzzyAIAgent\nexcept Exception:\n    OzzyAIAgent = None"; done=1; next }
            {print $0}
        ' main.py > main.py.tmp && mv main.py.tmp main.py
        # Enable flag in config
        if grep -q "AMBITIOUS_AI" config.py; then
            sed -i "s/^AMBITIOUS_AI *= *.*/AMBITIOUS_AI = True/" config.py || true
        else
            echo "AMBITIOUS_AI = True" >> config.py
        fi
        echo "✅ Wired import and enabled AMBITIOUS_AI=True"
    else
        echo "ℹ️  Skipping auto-wiring. Follow AMBITIOUS_AI_UPGRADE.md for manual steps."
    fi
fi

echo ""
echo "🎯 Ready to restart bot!"
echo ""
read -p "🤔 Restart bot now with ambitious AI? (y/n): " restart_bot

if [ "$restart_bot" = "y" ]; then
    echo ""
    echo "🛑 Stopping current bot (if running)..."
    pkill -f "python.*main.py" || true
    sleep 2
    
    echo "🚀 Starting bot with ambitious AI..."
    if [ -f "venv/bin/python" ]; then
      PY=venv/bin/python
    else
      PY=python
    fi
    nohup $PY main.py > logs/phase1_ambitious_ai.log 2>&1 &
    
    sleep 2
    
    if pgrep -f "python.*main.py" > /dev/null; then
        echo "✅ Bot started successfully!"
        echo ""
        echo "📊 Monitor logs:"
        echo "   tail -f logs/phase1_ambitious_ai.log"
        echo ""
        echo "🎯 Watch AI decisions:"
        echo "   tail -f logs/phase1_ambitious_ai.log | grep 'OZZY AI AGENT'"
    else
        echo "❌ Bot failed to start"
        echo "   Check logs: tail -50 logs/phase1_ambitious_ai.log"
        exit 1
    fi
else
    echo ""
    echo "⏸️  Bot not restarted"
    echo "   When ready, run:"
    echo "   pkill -f main.py"
    echo "   nohup python main.py > logs/phase1_ambitious_ai.log 2>&1 &"
fi

echo ""
echo "🔥 UPGRADE COMPLETE!"
echo ""
echo "Expected changes:"
echo "  • Approval rate: 0% → 35-40%"
echo "  • AI finds opportunities base system missed"
echo "  • IMPROVE actions optimize R/R"
echo "  • CHALLENGE actions show better plays"
echo "  • COUNTER signals for opposite direction trades"
echo ""
echo "Monitor until Monday, then analyze results!"
echo "Read full guide: cat AMBITIOUS_AI_UPGRADE.md"
