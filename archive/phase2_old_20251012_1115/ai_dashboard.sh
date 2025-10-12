#!/bin/bash
# Live AI Trading Dashboard - Updates every 5 seconds
# Real-time monitoring in one terminal

cd /home/rick/ozzy-simple

# Colors for better visibility
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
CYAN='\033[0;36m'
WHITE='\033[1;37m'
NC='\033[0m' # No Color

# Extract a numeric value from config for STARTING_CAPITAL (best-effort)
get_starting_capital() {
    if [ -f "config.py" ]; then
        awk -F'=' '/STARTING_CAPITAL/ { gsub(/[^0-9.]/, "", $2); if($2!="") print $2 }' config.py | head -1
    fi
}

# Function to check if bot is running
check_bot_status() {
    if ps aux | grep -q "[m]ain.py"; then
        echo -e "${GREEN}✅ RUNNING${NC}"
    else
        echo -e "${RED}❌ STOPPED${NC}"
    fi
}

# Function to get last AI analysis
get_last_ai_analysis() {
    if [ -f "ozzy_simple.db" ]; then
        sqlite3 ozzy_simple.db "
        SELECT 
            substr(timestamp, 12, 8) || ' ' ||
            symbol || ' ' ||
            base_signal || ' ' ||
            ROUND(base_confidence, 1) || '% → ' ||
            ai_recommendation || ' ' ||
            ROUND(ai_confidence, 1) || '% ' ||
            CASE WHEN agreement = 1 THEN '🤝' ELSE '🔀' END
        FROM ai_analysis 
        ORDER BY timestamp DESC 
        LIMIT 1
        " 2>/dev/null
    fi
}

# Function to get recent activity
get_recent_activity() {
    BOT_LOG=$(ls -1t logs/bot_*.log 2>/dev/null | head -1)
    if [ -n "$BOT_LOG" ] && [ -f "$BOT_LOG" ]; then
        tail -50 "$BOT_LOG" | grep -E "(📊 MONITOR:|🤖 Requesting|✅ APPROVE|❌ REJECT|⚠️  MODIFY|Checking signal for|🟢|🔴|PAPER TRADE EXECUTED)" | tail -5
    elif [ -f "logs/phase2_launch.log" ]; then
        tail -50 logs/phase2_launch.log | grep -E "(PAPER TRADE EXECUTED|📊 MONITOR:|🤖 Requesting|✅ APPROVE|❌ REJECT|⚠️  MODIFY|Checking signal for)" | tail -5
    elif [ -f "logs/phase1_ai.log" ]; then
        tail -5 logs/phase1_ai.log | grep -E "(📊 MONITOR:|🤖 Requesting|✅ APPROVE|❌ REJECT|⚠️  MODIFY)" | tail -3
    fi
}

# Function to get stats
get_today_stats() {
    if [ -f "ozzy_simple.db" ]; then
        sqlite3 ozzy_simple.db "
        SELECT 
            (SELECT COUNT(*) FROM signals WHERE DATE(timestamp) = DATE('now')) as signals,
            (SELECT COUNT(*) FROM ai_analysis WHERE DATE(timestamp) = DATE('now')) as ai_validations,
            (SELECT COUNT(*) FROM ai_analysis WHERE DATE(timestamp) = DATE('now') AND ai_recommendation = 'APPROVE') as approvals,
            (SELECT COUNT(*) FROM ai_analysis WHERE DATE(timestamp) = DATE('now') AND ai_recommendation = 'REJECT') as rejections,
            (SELECT COUNT(*) FROM ai_analysis WHERE DATE(timestamp) = DATE('now') AND ai_recommendation = 'MODIFY') as modifications,
            (SELECT ROUND(AVG(agreement) * 100, 1) FROM ai_analysis WHERE DATE(timestamp) = DATE('now')) as agreement_rate
        " 2>/dev/null
    fi
}

# Main dashboard loop
echo -e "${WHITE}🤖 OZZY AI LIVE DASHBOARD - Starting...${NC}"
sleep 2

while true; do
    # Clear screen and position cursor
    clear
    
    # Determine Mode once per loop so we can show it in the header and below
    MODE=$(python3 - <<'PY'
import config
pt = getattr(config,'PAPER_TRADING',False)
mon = getattr(config,'MONITOR_ONLY_MODE',True)
pp = getattr(config,'PHASE_2_MODE',False)
if pt and not mon:
    print('Phase 2 (Paper Trading)')
elif mon:
    print('Phase 1.5 (AI Monitor)')
else:
    print('Live/Custom')
PY
    )
    
    # Header
    echo -e "${CYAN}╔══════════════════════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${CYAN}║${WHITE}                    🤖 OZZY AI TRADING DASHBOARD - LIVE                      ${CYAN}║${NC}"
    echo -e "${CYAN}║${WHITE}                            Mode: ${BLUE}${MODE}${WHITE}                                   ${CYAN}║${NC}"
    echo -e "${CYAN}╚══════════════════════════════════════════════════════════════════════════════╝${NC}"
    
    echo ""
    echo -e "${YELLOW}📊 REAL-TIME STATUS${NC} $(date '+%H:%M:%S')"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    # Phase 2 start timestamp (for filtering views)
    PHASE2_TS=""
    if [ -f "ozzy_simple.db" ]; then
        PHASE2_TS=$(sqlite3 ozzy_simple.db "SELECT value FROM meta WHERE key='phase2_start_ts' ORDER BY id DESC LIMIT 1" 2>/dev/null)
    fi
    
    # Phase 2 summary: capital and today's paper PnL
    if [ -f "ozzy_simple.db" ]; then
        has_paper=$(sqlite3 ozzy_simple.db "SELECT name FROM sqlite_master WHERE type='table' AND name='paper_trades'" 2>/dev/null)
        if [ ! -z "$has_paper" ]; then
            cap=$(python3 - <<'PY'
import config
print(getattr(config,'STARTING_CAPITAL',10000.0))
PY
            )
            today_pnl=$(sqlite3 ozzy_simple.db "SELECT COALESCE(SUM(pnl),0) FROM paper_trades WHERE date(timestamp)=date('now')" 2>/dev/null)
            [ -z "$today_pnl" ] && today_pnl=0
            total_pnl=$(sqlite3 ozzy_simple.db "SELECT COALESCE(SUM(pnl),0) FROM paper_trades" 2>/dev/null)
            [ -z "$total_pnl" ] && total_pnl=0
            current=$(python3 - <<PY
cap=float("$cap" or 10000)
tp=float("$total_pnl" or 0)
print(f"{cap+tp:.2f}")
PY
            )
            echo -e "Capital: ${WHITE}R${cap}${NC} → Current: ${WHITE}R${current}${NC}   |   Phase 2 PnL (Today): ${WHITE}R$(printf '%.2f' "$today_pnl")${NC}"
        fi
    fi

    echo -e "Bot Status: $(check_bot_status)   |   Mode: ${BLUE}${MODE}${NC}"
    
    # Portfolio exposure line (Phase 2 only)
    if [ -f "ozzy_simple.db" ]; then
        has_paper=$(sqlite3 ozzy_simple.db "SELECT name FROM sqlite_master WHERE type='table' AND name='paper_trades'" 2>/dev/null)
        if [ ! -z "$has_paper" ]; then
            cap=$(python3 - <<'PY'
import config
print(getattr(config,'STARTING_CAPITAL',10000.0))
PY
            )
            exp=$(sqlite3 ozzy_simple.db "SELECT COALESCE(SUM(value),0) FROM paper_trades WHERE status='OPEN' AND phase='PHASE_2'" 2>/dev/null)
            [ -z "$exp" ] && exp=0
            exp_pct=$(python3 - <<PY
cap=float("$cap" or 10000)
exp=float("$exp" or 0)
print(f"{(exp/cap*100 if cap else 0):.2f}")
PY
            )
            cap_pct=$(python3 - <<'PY'
import config
print(getattr(config,'PORTFOLIO_EXPOSURE_CAP_PCT',0.10))
PY
            )
            avail_pct=$(python3 - <<PY
cap_pct=float("$cap_pct" or 0)
exp_pct=float("$exp_pct" or 0)
print(f"{max(cap_pct*100 - exp_pct, 0):.2f}")
PY
            )
            open_cnt=$(sqlite3 ozzy_simple.db "SELECT COUNT(*) FROM paper_trades WHERE status='OPEN' AND phase='PHASE_2'" 2>/dev/null)
            sides=$(sqlite3 ozzy_simple.db "SELECT symbol || ' ' || side || ' x' || COUNT(*) FROM paper_trades WHERE status='OPEN' AND phase='PHASE_2' GROUP BY symbol, side ORDER BY symbol, side" 2>/dev/null | tr '\n' ',' | sed 's/,$//')
            echo -e "Exposure Used: ${WHITE}${exp_pct}%${NC} (R${exp} / R${cap})   |   Available: ${WHITE}${avail_pct}%${NC}   |   Open: ${WHITE}${open_cnt}${NC} (${sides})"
        fi
    fi
    
    # Phase 2 paper-trade counts (today)
    if [ -f "ozzy_simple.db" ]; then
        p2_counts=$(sqlite3 ozzy_simple.db "SELECT 
           (SELECT COUNT(*) FROM paper_trades WHERE date(timestamp)=date('now') AND phase='PHASE_2') as p2_trades,
           (SELECT COUNT(*) FROM paper_trades WHERE status='OPEN' AND phase='PHASE_2') as p2_open,
           (SELECT COALESCE(SUM(pnl),0) FROM paper_trades WHERE date(timestamp)=date('now') AND phase='PHASE_2') as p2_pnl
        " 2>/dev/null)
        if [ ! -z "$p2_counts" ]; then
            p2_trades=$(echo "$p2_counts" | cut -d'|' -f1)
            p2_open=$(echo "$p2_counts" | cut -d'|' -f2)
            p2_pnl=$(echo "$p2_counts" | cut -d'|' -f3)
            echo -e "Phase 2 Trades: ${WHITE}${p2_trades}${NC}   |   Open: ${WHITE}${p2_open}${NC}   |   Today PnL: ${WHITE}R${p2_pnl}${NC}"
        fi
    fi
    
    echo ""
    echo -e "${PURPLE}🤖 LATEST AI ANALYSIS${NC}"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    # Last AI decision (filtered to Phase 2 window when available)
    last_ai=""
    if [ -f "ozzy_simple.db" ] && [ ! -z "$PHASE2_TS" ]; then
        last_ai=$(sqlite3 ozzy_simple.db "
        SELECT 
            substr(timestamp, 12, 8) || ' ' ||
            symbol || ' ' ||
            base_signal || ' ' ||
            ROUND(base_confidence, 1) || '% → ' ||
            ai_recommendation || ' ' ||
            ROUND(ai_confidence, 1) || '% ' ||
            CASE WHEN agreement = 1 THEN '🤝' ELSE '🔀' END
        FROM ai_analysis 
        WHERE timestamp >= '$PHASE2_TS'
        ORDER BY timestamp DESC 
        LIMIT 1
        " 2>/dev/null)
    fi
    if [ -z "$last_ai" ]; then
        last_ai=$(get_last_ai_analysis)
    fi
    if [ ! -z "$last_ai" ]; then
        echo -e "${WHITE}$last_ai${NC}"
    else
        echo "No AI analysis yet..."
    fi
    
    echo ""
    echo -e "${GREEN}📡 LIVE ACTIVITY STREAM${NC}"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    
    # Recent activity
    recent=$(get_recent_activity)
    if [ ! -z "$recent" ]; then
        echo "$recent" | while read line; do
            # Color code different types of activity
            if echo "$line" | grep -q "📊 MONITOR:"; then
                echo -e "${BLUE}$line${NC}"
            elif echo "$line" | grep -q "🤖 Requesting"; then
                echo -e "${PURPLE}$line${NC}"
            elif echo "$line" | grep -q "✅ APPROVE"; then
                echo -e "${GREEN}$line${NC}"
            elif echo "$line" | grep -q "❌ REJECT"; then
                echo -e "${RED}$line${NC}"
            elif echo "$line" | grep -q "⚠️  MODIFY"; then
                echo -e "${YELLOW}$line${NC}"
            elif echo "$line" | grep -q "PAPER TRADE EXECUTED"; then
                echo -e "${GREEN}$line${NC}"
            else
                echo "$line"
            fi
        done
    else
        echo "Waiting for activity..."
    fi
    
    echo ""
    echo -e "${WHITE}🧪 PAPER TRADES SNAPSHOT${NC}"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    if [ -f "ozzy_simple.db" ]; then
        paper_overview=$(sqlite3 ozzy_simple.db "SELECT \n            (SELECT COUNT(*) FROM paper_trades WHERE status='OPEN') as open_positions,\n            (SELECT COUNT(*) FROM paper_trades) as total_trades,\n            COALESCE((SELECT ROUND(SUM(pnl),2) FROM paper_trades WHERE status='CLOSED'),0) as closed_pnl\n        " 2>/dev/null)
        if [ ! -z "$paper_overview" ]; then
            open_positions=$(echo "$paper_overview" | cut -d'|' -f1)
            total_trades=$(echo "$paper_overview" | cut -d'|' -f2)
            closed_pnl=$(echo "$paper_overview" | cut -d'|' -f3)
            echo -e "Open Positions: ${WHITE}${open_positions}${NC}   |   Total Trades: ${WHITE}${total_trades}${NC}   |   Realized P&L: ${WHITE}R${closed_pnl}${NC}"
        else
            echo "No paper trades yet."
        fi

        echo ""
        echo -e "${WHITE}Recent Paper Trades (Last 5)${NC}"
        echo "TIME   SYMBOL   SIDE   ENTRY    STATUS   REASON"
        sqlite3 ozzy_simple.db "\n            SELECT substr(timestamp,12,5) || '  ' ||\n                   printf('%-7s', symbol) || '  ' ||\n                   printf('%-5s', side) || '  ' ||\n                   printf('R%-7.2f', entry) || '  ' ||\n                   printf('%-7s', status) || '  ' ||\n                   substr(COALESCE(reason,''),1,28)\n            FROM paper_trades\n            ORDER BY timestamp DESC\n            LIMIT 5\n        " 2>/dev/null
    else
        echo "Database not found."
    fi

        # Phase 2 executed tiers (today)
        echo ""
        echo -e "${YELLOW}🧠 PHASE 2 EXECUTIONS BY TIER (Today)${NC}"
        echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        if [ -f "ozzy_simple.db" ]; then
            tier_stats=$(sqlite3 ozzy_simple.db "
                SELECT 
                    SUM(CASE WHEN base_confidence >= 45 THEN 1 ELSE 0 END) as t1,
                    SUM(CASE WHEN base_confidence >= 35 AND base_confidence < 45 THEN 1 ELSE 0 END) as t2,
                    SUM(CASE WHEN base_confidence >= 30 AND base_confidence < 35 THEN 1 ELSE 0 END) as t3,
                    SUM(CASE WHEN base_confidence < 30 THEN 1 ELSE 0 END) as rej,
                    COALESCE(SUM(pnl),0)
                FROM paper_trades
                WHERE phase='PHASE_2' AND date(timestamp,'localtime')=date('now','localtime')
            " 2>/dev/null)
            if [ ! -z "$tier_stats" ]; then
                t1=$(echo "$tier_stats" | cut -d'|' -f1)
                t2=$(echo "$tier_stats" | cut -d'|' -f2)
                t3=$(echo "$tier_stats" | cut -d'|' -f3)
                trj=$(echo "$tier_stats" | cut -d'|' -f4)
                tpnl=$(echo "$tier_stats" | cut -d'|' -f5)
                echo -e "🟢 Tier 1 (≥45%): ${WHITE}${t1}${NC}   |   🟡 Tier 2 (35-44%): ${WHITE}${t2}${NC}   |   🟠 Tier 3 (30-34%): ${WHITE}${t3}${NC}   |   🔴 <30%: ${WHITE}${trj}${NC}"
                echo -e "Phase 2 Realized P&L (Today): ${WHITE}R${tpnl}${NC}"
            else
                echo "No Phase 2 executions yet today."
            fi
        else
            echo "Database not found."
        fi

    echo ""
    echo -e "${CYAN}📈 RECENT AI DECISIONS (Last 5)${NC}"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "TIME     SYMBOL   BASE  BASE%  AI_REC    AI%   MATCH"
    
    if [ -f "ozzy_simple.db" ]; then
        if [ ! -z "$PHASE2_TS" ]; then
            sqlite3 ozzy_simple.db "
            SELECT 
                substr(timestamp, 12, 5) || '  ' ||
                printf('%-7s', symbol) || '  ' ||
                printf('%-4s', base_signal) || '  ' ||
                printf('%4.1f', base_confidence) || '   ' ||
                printf('%-7s', ai_recommendation) || '  ' ||
                printf('%4.1f', ai_confidence) || '   ' ||
                CASE WHEN agreement = 1 THEN '🤝' ELSE '🔀' END
            FROM ai_analysis 
            WHERE timestamp >= '$PHASE2_TS'
            ORDER BY timestamp DESC 
            LIMIT 5
            " 2>/dev/null
        else
            sqlite3 ozzy_simple.db "
            SELECT 
                substr(timestamp, 12, 5) || '  ' ||
                printf('%-7s', symbol) || '  ' ||
                printf('%-4s', base_signal) || '  ' ||
                printf('%4.1f', base_confidence) || '   ' ||
                printf('%-7s', ai_recommendation) || '  ' ||
                printf('%4.1f', ai_confidence) || '   ' ||
                CASE WHEN agreement = 1 THEN '🤝' ELSE '🔀' END
            FROM ai_analysis 
            ORDER BY timestamp DESC 
            LIMIT 5
            " 2>/dev/null
        fi
    fi

    # Phase 2 paper trades snapshot (if table exists)
    if [ -f "ozzy_simple.db" ]; then
        has_paper=$(sqlite3 ozzy_simple.db "SELECT name FROM sqlite_master WHERE type='table' AND name='paper_trades'" 2>/dev/null)
        if [ ! -z "$has_paper" ]; then
            echo ""
            echo -e "${GREEN}💸 PHASE 2 PAPER TRADES (Today)${NC}"
            echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
            sqlite3 ozzy_simple.db "
         SELECT 'Open: ' || (SELECT COUNT(*) FROM paper_trades WHERE status='OPEN' AND phase='PHASE_2') ||
             ' | Closed: ' || (SELECT COUNT(*) FROM paper_trades WHERE status='CLOSED' AND date(timestamp)=date('now') AND phase='PHASE_2') ||
             ' | PnL: R' || printf('%.2f', COALESCE((SELECT SUM(pnl) FROM paper_trades WHERE date(timestamp)=date('now') AND phase='PHASE_2'),0))
            " 2>/dev/null
            echo ""
            echo -e "${WHITE}Latest Executions${NC}"
            sqlite3 ozzy_simple.db "
         SELECT substr(timestamp,12,5) || '  ' || printf('%-7s', symbol) || '  ' || printf('%-5s', side) || '  R' || printf('%.2f', entry) ||
                   '  → TP R' || printf('%.2f', COALESCE(target,0)) || ' / SL R' || printf('%.2f', COALESCE(stop,0)) ||
                   '  size ' || printf('%.4f', size) || '  ' || status
         FROM paper_trades WHERE phase='PHASE_2' ORDER BY timestamp DESC LIMIT 5
            " 2>/dev/null
        fi
    fi

    # Ambitious agent quick stats (if table exists)
    if [ -f "ozzy_simple.db" ]; then
        has_agent=$(sqlite3 ozzy_simple.db "SELECT name FROM sqlite_master WHERE type='table' AND name='ai_agent_analysis'" 2>/dev/null)
        if [ ! -z "$has_agent" ]; then
            echo ""
            echo -e "${PURPLE}🔥 AMBITIOUS AI (Today)${NC}"
            echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
            sqlite3 ozzy_simple.db "
            SELECT 'Analyzed: ' || COUNT(*) ||
                   ' | Approve: ' || SUM(CASE WHEN ai_action='APPROVE' THEN 1 ELSE 0 END) ||
                   ' | Improve: ' || SUM(CASE WHEN ai_action='IMPROVE' THEN 1 ELSE 0 END) ||
                   ' | Challenge: ' || SUM(CASE WHEN ai_action='CHALLENGE' THEN 1 ELSE 0 END) ||
                   ' | Reject: ' || SUM(CASE WHEN ai_action='REJECT' THEN 1 ELSE 0 END) ||
                   ' | Counter: ' || SUM(CASE WHEN ai_action='COUNTER' THEN 1 ELSE 0 END)
            FROM ai_agent_analysis WHERE DATE(timestamp)=DATE('now')
            " 2>/dev/null
        fi
    fi

    # Multi-asset performance breakdown (lightweight)
    if grep -q "^\s*MULTI_ASSET_ENABLED\s*=\s*True" config.py 2>/dev/null; then
        echo ""
        echo -e "${CYAN}🌍 MULTI-ASSET SNAPSHOT${NC}"
        echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        if [ -f "ozzy_simple.db" ]; then
            MONITOR_ONLY=$(python3 - <<'PY' 2>/dev/null
import config
print('1' if getattr(config,'MONITOR_ONLY_MODE',False) else '0')
PY
            )
            if [ "$MONITOR_ONLY" = "1" ]; then
                echo "GOLD         |  0 trades | R   0.00 (monitor-only)"
                echo "FOREX        |  0 trades | R   0.00 (monitor-only)"
                echo "MAJOR CRYPTO |  0 trades | R   0.00 (monitor-only)"
                ALT_ENABLED=$(python3 - <<'PY' 2>/dev/null
import config
alts = any(s in getattr(config,'TRADING_SYMBOLS',[]) for s in ('SOLUSDT','BNBUSDT'))
print('1' if alts else '0')
PY
                )
                if [ "$ALT_ENABLED" = "1" ]; then
                    echo "ALTCOINS     |  0 trades | R   0.00 (monitor-only)"
                else
                    echo "ALTCOINS    | disabled"
                fi
            else
            ALT_ENABLED=$(python3 - <<'PY' 2>/dev/null
import config
alts = any(s in getattr(config,'TRADING_SYMBOLS',[]) for s in ('SOLUSDT','BNBUSDT'))
print('1' if alts else '0')
PY
            )

            if [ "$ALT_ENABLED" = "1" ]; then
                python3 - <<'PY' 2>/dev/null
import sqlite3
DB='ozzy_simple.db'
conn=sqlite3.connect(DB)
cur=conn.cursor()
def row(q):
    cur.execute(q)
    r=cur.fetchone(); return (r[0] or 0, r[1] or 0.0) if r else (0,0.0)
def out(name, where):
    cur.execute(f"SELECT COUNT(*), ROUND(SUM(pnl),2) FROM trades WHERE {where} AND date(entry_timestamp)=date('now','localtime')")
    r=cur.fetchone() or (0,0.0)
    trades=int(r[0] or 0); pnl=float(r[1] or 0.0)
    print(f"{name:12s} | {trades:2d} trades | R{pnl:7.2f}")
out('GOLD','symbol="XAUUSDT"')
out('FOREX','symbol IN ("EURUSD","GBPUSD","USDJPY")')
out('MAJOR CRYPTO','symbol IN ("BTCUSDT","ETHUSDT")')
out('ALTCOINS','symbol IN ("SOLUSDT","BNBUSDT")')
conn.close()
PY
            else
                python3 - <<'PY' 2>/dev/null
import sqlite3
DB='ozzy_simple.db'
conn=sqlite3.connect(DB)
cur=conn.cursor()
def out(name, where):
    cur.execute(f"SELECT COUNT(*), ROUND(SUM(pnl),2) FROM trades WHERE {where} AND date(entry_timestamp)=date('now','localtime')")
    r=cur.fetchone() or (0,0.0)
    trades=int(r[0] or 0); pnl=float(r[1] or 0.0)
    print(f"{name:12s} | {trades:2d} trades | R{pnl:7.2f}")
out('GOLD','symbol="XAUUSDT"')
out('FOREX','symbol IN ("EURUSD","GBPUSD","USDJPY")')
out('MAJOR CRYPTO','symbol IN ("BTCUSDT","ETHUSDT")')
conn.close()
PY
                echo "ALTCOINS    | disabled"
            fi
            fi
        fi
    fi
    
    echo ""
    echo -e "${WHITE}🎮 LIVE CONTROLS${NC}"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo -e "CTRL+C: Exit  |  ./monitor.sh restart: Restart bot  |  tail -f logs/phase1_ai.log: Full log"
    
    # Live update indicator
    echo ""
    echo -e "${GREEN}●${NC} Live updating every 5 seconds... ${BLUE}[$(date '+%H:%M:%S')]${NC}"
    
    # Check if bot crashed
    if ! ps aux | grep -q "[m]ain.py"; then
        echo ""
        echo -e "${RED}⚠️  BOT NOT RUNNING! Restart with: ./monitor.sh restart${NC}"
    fi
    
    # Show current log activity
    BOT_LOG=$(ls -1t logs/bot_*.log 2>/dev/null | head -1)
    if [ -n "$BOT_LOG" ] && [ -f "$BOT_LOG" ]; then
        last_log_line=$(tail -1 "$BOT_LOG")
        echo -e "${CYAN}Last log: ${NC}$(echo "$last_log_line" | cut -c1-80)..."
    elif [ -f "logs/phase2_launch.log" ]; then
        last_log_line=$(tail -1 logs/phase2_launch.log)
        echo -e "${CYAN}Last log: ${NC}$(echo "$last_log_line" | cut -c1-80)..."
    elif [ -f "logs/phase1_ai.log" ]; then
        last_log_line=$(tail -1 logs/phase1_ai.log)
        echo -e "${CYAN}Last log: ${NC}$(echo "$last_log_line" | cut -c1-80)..."
    fi
    
    # Wait 5 seconds before refresh
    sleep 5
done