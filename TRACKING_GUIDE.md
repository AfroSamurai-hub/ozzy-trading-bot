# 💰 CAPITAL & TRADE TRACKING GUIDE

**Last Updated:** October 17, 2025 08:30 AM

---

## 📊 **CURRENT STATUS**

### **Starting Capital:** R10,000.00
### **Current Capital:** R9,025.00
### **Open Positions:** 2
### **Allocated:** R975.00 (9.75%)
### **Available:** R9,025.00 (90.25%)

---

## 🎯 **WHERE TRACKING HAPPENS**

### **1. Live Test Output** (`/tmp/test_output.log`)
Real-time tracking of every decision:
```bash
# View latest portfolio status
grep "💼 Portfolio Status:" -A 2 /tmp/test_output.log | tail -6

# See all positions
grep -E "Position #" /tmp/test_output.log

# Track capital changes
grep "Capital:" /tmp/test_output.log
```

**Shows:**
- Current capital after each decision
- Open positions count
- Position P&L updates
- TP/SL execution

### **2. Portfolio State File** (`logs/portfolio_state.json`)
Persistent storage of portfolio state:
```bash
# View current state
cat logs/portfolio_state.json

# Pretty print
cat logs/portfolio_state.json | python3 -m json.tool
```

**Contains:**
- Starting capital
- Current capital
- All open positions with details
- All closed trades with P&L
- Position history
- Performance metrics

### **3. Monitoring Dashboard** (`monitor_dashboard.py`)
Visual real-time display:
```bash
# Run dashboard
python3 monitor_dashboard.py
```

**Shows:**
- Current capital
- Open positions count
- P&L (profit/loss)
- Recent trades
- Signal distribution

### **4. Trades CSV** (`trades.csv`)
Historical trade log (if enabled):
```bash
# View all trades
cat trades.csv
```

**Records:**
- Entry/exit times
- Entry/exit prices
- Position sizes
- P&L per trade
- Win/loss status

---

## 📈 **CURRENT POSITIONS**

Based on latest test output:

### **Position #1:**
- **Entry:** R66,676.94
- **Status:** OPEN (holding)
- **P&L:** -0.26% (unrealized)
- **Allocated:** ~R500

### **Position #2:**
- **Entry:** R66,500.66
- **Status:** OPEN (holding)
- **P&L:** +0.00% (just opened)
- **Allocated:** ~R475

**Total Positions:** 2  
**Total Allocated:** ~R975  
**Available Capital:** R9,025

---

## 💡 **HOW TO TRACK YOUR PERFORMANCE**

### **Quick Capital Check:**
```bash
# Latest capital amount
grep "Capital:" /tmp/test_output.log | tail -1
```

### **See All Positions:**
```bash
# Open positions
grep "Position #" /tmp/test_output.log | grep "opened @"

# Position updates
grep "Position #" /tmp/test_output.log | grep -E "(holding|TP|SL)"
```

### **Calculate Total P&L:**
```bash
# Starting capital
echo "Starting: R10,000.00"

# Current capital
current=$(grep "Capital:" /tmp/test_output.log | tail -1 | grep -oP 'R[\d,]+\.\d+' | tr -d 'R,')
echo "Current: R$current"

# Calculate P&L
python3 -c "print(f'P&L: R{$current - 10000:.2f}')"
```

### **Position Performance:**
```bash
# All position status updates
grep "📊 Position" /tmp/test_output.log
```

---

## 📊 **DETAILED TRACKING COMMANDS**

### **1. Real-Time Capital:**
```bash
# Watch capital changes live
tail -f /tmp/test_output.log | grep --line-buffered "Capital:"
```

### **2. Trade Execution:**
```bash
# See all BUY/SELL executions
grep -E "(EXECUTING BUY|EXECUTING SELL)" /tmp/test_output.log
```

### **3. Position Openings:**
```bash
# All position openings with prices
grep "opened @" /tmp/test_output.log
```

### **4. TP/SL Triggers:**
```bash
# Check if any TP or SL hit
grep -E "(TP HIT|SL HIT)" /tmp/test_output.log
```

### **5. Complete Trade History:**
```bash
# Full trade sequence
grep -B 3 -A 3 "Position #" /tmp/test_output.log
```

---

## 🎯 **PORTFOLIO STATE FILE STRUCTURE**

The `logs/portfolio_state.json` contains:

```json
{
  "starting_capital": 10000.0,
  "capital": 9025.0,
  "positions": [
    {
      "id": 1,
      "symbol": "BTCUSDT",
      "side": "LONG",
      "entry_price": 66676.94,
      "current_price": 66500.0,
      "size": 500.0,
      "qty": 0.0075,
      "status": "OPEN",
      "entry_time": "2025-10-17 07:58:49",
      "confidence": 0.70,
      "reason": "Whale accumulation pattern",
      "unrealized_pnl": -13.0
    },
    {
      "id": 2,
      "symbol": "BTCUSDT",
      "side": "LONG",
      "entry_price": 66500.66,
      "current_price": 66500.0,
      "size": 475.0,
      "qty": 0.0071,
      "status": "OPEN",
      "entry_time": "2025-10-17 08:28:52",
      "confidence": 0.75,
      "reason": "Bullish momentum",
      "unrealized_pnl": 0.0
    }
  ],
  "closed_trades": [],
  "total_trades": 2,
  "win_rate": 0.0,
  "total_pnl": -13.0
}
```

---

## 💰 **CAPITAL FLOW TRACKING**

### **How Capital Changes:**

1. **Starting:** R10,000.00
2. **Position #1 Opens:** R10,000 - R500 = R9,500
3. **Position #2 Opens:** R9,500 - R475 = R9,025
4. **Position Closes:** R9,025 + (size + P&L) = New Capital

### **Capital Allocation Rules:**

- **Max Position Size:** 5% of capital per trade
- **Max Total Exposure:** 80% of capital
- **Max Open Positions:** 20

**Current Allocation:**
- Position #1: R500 (5.0% of R10,000)
- Position #2: R475 (4.75% of R10,000)
- Total: R975 (9.75% - safe!)

---

## 📊 **MONITORING BEST PRACTICES**

### **Every Hour:**
```bash
# Quick status check
python3 MASTER_PLANNER.py status
tail -30 /tmp/test_output.log
```

### **After Each Decision:**
```bash
# Check latest decision result
grep "DECISION COMPLETE" /tmp/test_output.log | tail -1

# Check capital
grep "Capital:" /tmp/test_output.log | tail -1
```

### **End of Test:**
```bash
# Generate complete report
python3 -c "
import json
with open('logs/portfolio_state.json', 'r') as f:
    state = json.load(f)
    
print(f'Starting Capital: R{state[\"starting_capital\"]:,.2f}')
print(f'Current Capital: R{state[\"capital\"]:,.2f}')
print(f'Total P&L: R{state[\"capital\"] - state[\"starting_capital\"]:,.2f}')
print(f'Return: {((state[\"capital\"] / state[\"starting_capital\"]) - 1) * 100:.2f}%')
print(f'Open Positions: {len(state[\"positions\"])}')
print(f'Closed Trades: {len(state[\"closed_trades\"])}')
"
```

---

## 🎯 **QUICK REFERENCE**

### **Current Capital:**
```bash
grep "Capital:" /tmp/test_output.log | tail -1
```

### **Total P&L:**
```bash
# Current - Starting
# R9,025 - R10,000 = -R975 (allocated to positions)
```

### **Unrealized P&L:**
```bash
grep "Position #" /tmp/test_output.log | grep "%" | tail -5
```

### **Win Rate:**
```bash
# After trades close
cat logs/portfolio_state.json | grep -E "(win_rate|total_trades)"
```

---

## 🚀 **AUTOMATED TRACKING**

The dashboard automatically tracks:
- ✅ Real-time capital updates
- ✅ Position changes
- ✅ P&L calculations
- ✅ Trade signals
- ✅ Confidence levels

**Just run:** `python3 monitor_dashboard.py`

---

## 📝 **MANUAL TRACKING SHEET**

For your own records:

| Time | Decision | Action | Price | Capital | Open Pos | P&L | Notes |
|------|----------|--------|-------|---------|----------|-----|-------|
| 07:58 | 1 | BUY | 66,676.94 | 9,500 | 1 | 0 | First position |
| 08:13 | 2 | SKIP | - | 9,500 | 1 | -0.37% | Spacing rule |
| 08:28 | 3 | BUY | 66,500.66 | 9,025 | 2 | -0.26% | Second position |

---

## 🎊 **SUMMARY**

**You Have 4 Tracking Systems:**

1. **Live Output** - Real-time decisions and capital changes
2. **Portfolio State** - Persistent JSON storage
3. **Dashboard** - Visual monitoring
4. **CSV Files** - Historical trade log (optional)

**Current Status:**
- 💰 Capital: R9,025 available, R975 in positions
- 📊 Positions: 2 open (both LONG BTCUSDT)
- 📈 P&L: -R975 allocated (unrealized: -0.26% avg)
- ✅ System: Tracking everything automatically

**No trade is lost - everything is logged!** 🔒📊

---

**Files to Watch:**
- `/tmp/test_output.log` - Live test output
- `logs/portfolio_state.json` - Portfolio state
- `monitor_dashboard.py` - Visual display
- `trades.csv` - Trade history

**Commands to Remember:**
```bash
# Capital
grep "Capital:" /tmp/test_output.log | tail -1

# Positions
grep "Position #" /tmp/test_output.log

# Dashboard
python3 monitor_dashboard.py
```
