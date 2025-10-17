#!/usr/bin/env bash
# Enhanced live dashboard with colors and real-time updates
set -euo pipefail

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
RED='\033[0;31m'
BOLD='\033[1m'
NC='\033[0m' # No Color

LOG_FILE=$(ls -t logs/overnight_15min_*.log 2>/dev/null | head -1 || echo "")

while true; do
    clear
    
    echo -e "${BOLD}${CYAN}╔════════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${BOLD}${CYAN}║           🚀 OVERNIGHT 15-MIN TEST - LIVE DASHBOARD           ║${NC}"
    echo -e "${BOLD}${CYAN}╚════════════════════════════════════════════════════════════════╝${NC}"
    echo ""
    
    # Current time
    echo -e "${BOLD}🕐 Current Time:${NC} $(date '+%Y-%m-%d %H:%M:%S')"
    echo ""
    
    # Process status
    PID=$(pgrep -f "bulletproof_test.py.*900" || echo "")
    if [ -n "$PID" ]; then
        RUNTIME=$(ps -p "$PID" -o etime --no-headers | xargs)
        echo -e "${GREEN}✅ Test Process:${NC} RUNNING (PID: $PID)"
        echo -e "   ${BLUE}Runtime:${NC} $RUNTIME"
    else
        echo -e "${RED}❌ Test Process:${NC} NOT RUNNING"
    fi
    
    # WARP status
    WARP_STATUS=$(warp-cli status 2>&1 | grep -i "Connected" && echo -e "${GREEN}✅ Connected${NC}" || echo -e "${RED}❌ Disconnected${NC}")
    echo -e "${BLUE}🌐 WARP:${NC} $WARP_STATUS"
    
    # Labeler status
    LABELER_PID=$(pgrep -f "live_labeler.py" || echo "")
    if [ -n "$LABELER_PID" ]; then
        echo -e "${GREEN}✅ Labeler:${NC} RUNNING (PID: $LABELER_PID)"
    else
        echo -e "${YELLOW}⚠️  Labeler:${NC} NOT RUNNING"
    fi
    
    echo ""
    echo -e "${BOLD}${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    
    if [ -z "$LOG_FILE" ]; then
        echo -e "${RED}❌ No log file found${NC}"
    else
        # Progress
        DECISIONS=$(grep -c "DECISION COMPLETE" "$LOG_FILE" 2>/dev/null || echo "0")
        TOTAL=24
        PERCENT=$((DECISIONS * 100 / TOTAL))
        
        echo ""
        echo -e "${BOLD}📊 Progress: ${DECISIONS}/${TOTAL} decisions${NC} (${PERCENT}%)"
        
        # Progress bar
        FILLED=$((DECISIONS * 50 / TOTAL))
        BAR=$(printf "█%.0s" $(seq 1 $FILLED))
        EMPTY=$(printf "░%.0s" $(seq 1 $((50 - FILLED))))
        echo -e "   ${GREEN}${BAR}${NC}${EMPTY}"
        
        # Estimated time
        if [ "$DECISIONS" -gt 0 ]; then
            START_TIME=$(stat -c %Y "$LOG_FILE")
            CURRENT_TIME=$(date +%s)
            ELAPSED=$((CURRENT_TIME - START_TIME))
            AVG_TIME=$((ELAPSED / DECISIONS))
            REMAINING=$((AVG_TIME * (TOTAL - DECISIONS)))
            ETA=$(date -d "@$((CURRENT_TIME + REMAINING))" '+%H:%M')
            
            echo -e "   ${BLUE}Elapsed:${NC} $((ELAPSED / 3600))h $((ELAPSED % 3600 / 60))m"
            echo -e "   ${BLUE}ETA Complete:${NC} ~${ETA}"
        fi
        
        echo ""
        echo -e "${BOLD}${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
        echo ""
        
        # Latest decision
        echo -e "${BOLD}🎯 Latest Decision:${NC}"
        LAST_DECISION=$(grep -B 2 "DECISION COMPLETE" "$LOG_FILE" 2>/dev/null | tail -7 || echo "   No decisions yet")
        
        # Parse and colorize
        ACTION=$(echo "$LAST_DECISION" | grep "Action:" | awk '{print $3}' || echo "")
        CONF=$(echo "$LAST_DECISION" | grep "Confidence:" | awk '{print $3}' || echo "")
        REASON=$(echo "$LAST_DECISION" | grep "Reasoning:" | cut -d: -f2- | cut -c1-60 || echo "")
        TIME=$(echo "$LAST_DECISION" | grep "Decision Time:" | awk '{print $4}' || echo "")
        
        if [ -n "$ACTION" ]; then
            if [ "$ACTION" = "SKIP" ]; then
                echo -e "   ${YELLOW}Action:${NC} $ACTION"
            elif [ "$ACTION" = "BUY" ]; then
                echo -e "   ${GREEN}Action:${NC} $ACTION"
            else
                echo -e "   ${BLUE}Action:${NC} $ACTION"
            fi
            
            [ -n "$CONF" ] && echo -e "   ${BLUE}Confidence:${NC} $CONF"
            [ -n "$TIME" ] && echo -e "   ${BLUE}Time:${NC} ${TIME}"
            [ -n "$REASON" ] && echo -e "   ${BLUE}Reason:${NC}${REASON}..."
        else
            echo "   Waiting for first decision..."
        fi
        
        echo ""
        echo -e "${BOLD}${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
        echo ""
        
        # Recent activity (last 5 lines)
        echo -e "${BOLD}📝 Recent Activity:${NC}"
        tail -5 "$LOG_FILE" 2>/dev/null | sed 's/^/   /' || echo "   No activity"
        
        echo ""
        echo -e "${BOLD}${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
        
        # Log file info
        echo ""
        echo -e "${BOLD}📂 Files:${NC}"
        echo -e "   Log: ${LOG_FILE}"
        echo -e "   Size: $(du -h "$LOG_FILE" | awk '{print $1}')"
        echo -e "   Updated: $(stat -c %y "$LOG_FILE" | cut -d. -f1)"
    fi
    
    echo ""
    echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${BOLD}Commands:${NC} tail -f $LOG_FILE | stop: kill $PID | refresh: 30s"
    echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    
    sleep 30
done
