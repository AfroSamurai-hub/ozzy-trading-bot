# 📊 MONITORING DASHBOARD GUIDE

**Created:** October 17, 2025  
**Status:** ✅ ACTIVE

---

## 🎯 DASHBOARD IS NOW RUNNING!

Your live monitoring dashboard is displaying:

✅ **Process Status** - Is test running? CPU/Memory usage  
✅ **Project Status** - Current phase and milestone progress  
✅ **Test Progress** - Decisions completed, time elapsed, ETA  
✅ **Portfolio** - Capital, positions, P&L  
✅ **Recent Decisions** - Last 10 signals with confidence  
✅ **Signal Distribution** - BUY/SELL/SKIP breakdown  
✅ **Average Confidence** - Overall confidence levels  

**Refresh Rate:** Every 2 seconds  
**Auto-updates:** Real-time as decisions complete

---

## 🚀 HOW TO USE

### **Currently Running:**
The dashboard is already active in a background terminal!

You can see it shows:
- ✅ Process running (PID 24504)
- ✅ Phase 1 progress (1/8 milestones, 12%)
- ✅ Test progress (1/24 decisions, 4.2%)
- ✅ Portfolio: R9,500 (1 position open)
- ✅ Last decision: BUY @ 70% confidence

### **To Run in New Terminal:**

```bash
# Option 1: Default (watches /tmp/test_output.log)
cd ~/ozzy-simple
python3 monitor_dashboard.py

# Option 2: Custom log file
python3 monitor_dashboard.py --log /path/to/custom.log
```

### **To Stop:**
Press `Ctrl+C` in the dashboard terminal

### **To Run Multiple Monitors:**
Open multiple terminals and run the dashboard in each!

---

## 📊 WHAT THE DASHBOARD SHOWS

### **🖥️ Process Status:**
```
✅ RUNNING - Test is active
❌ NOT RUNNING - Test stopped/crashed
PID: Process ID
CPU: CPU usage %
MEM: Memory usage %
Time: Runtime
```

### **🎯 Project Status:**
```
Phase: Current phase (Foundation/Intelligence/etc)
Progress: X/Y milestones (Z%)
```

### **📊 Test Progress:**
```
Decisions: Completed/Total (%)
Progress Bar: Visual progress
Elapsed: Time since test start
Estimated Remaining: ETA to completion
```

### **💼 Portfolio:**
```
Capital: Current available capital
Open Positions: Number of active trades
P&L: Profit/Loss since start
  - Green: Profit
  - Red: Loss
```

### **📈 Recent Decisions:**
```
Signal Distribution:
  BUY/LONG: Green
  SELL/SHORT: Red
  SKIP: Yellow

Table shows last 10 decisions:
  #: Decision number
  Action: What signal (color-coded)
  Confidence: AI confidence (color-coded)
    - Green: ≥70%
    - Yellow: 50-69%
    - Red: <50%
  Price: Entry price
```

---

## 🎨 COLOR CODING

### **Actions:**
- 🟢 **GREEN** - BUY, LONG (bullish signals)
- 🔴 **RED** - SELL, SHORT (bearish signals)
- 🟡 **YELLOW** - SKIP (no trade)

### **Confidence:**
- 🟢 **GREEN** - High confidence (≥70%)
- 🟡 **YELLOW** - Medium confidence (50-69%)
- 🔴 **RED** - Low confidence (<50%)

### **Status:**
- 🟢 **GREEN** - Running, success, profit
- 🔴 **RED** - Stopped, error, loss
- 🟦 **BLUE** - Headers, info

---

## 📈 WHAT TO WATCH FOR

### **Good Signs:**
✅ Process stays RUNNING  
✅ Decisions progressing steadily  
✅ Mix of signals (not all SKIP)  
✅ Confidence levels >40%  
✅ P&L trending positive  
✅ System stable (no crashes)  

### **Warning Signs:**
⚠️ Process shows NOT RUNNING  
⚠️ Decisions stuck (no progress)  
⚠️ All SKIP signals  
⚠️ All 0% confidence  
⚠️ Large negative P&L  
⚠️ Test hangs/freezes  

---

## 🔧 TROUBLESHOOTING

### **Dashboard Not Updating:**
```bash
# Check if test is running
ps aux | grep bulletproof_test.py

# Check log file exists
ls -lh /tmp/test_output.log

# Restart dashboard
# Press Ctrl+C, then:
python3 monitor_dashboard.py
```

### **Process Shows NOT RUNNING:**
```bash
# Check if test crashed
tail -50 /tmp/test_output.log

# Restart test if needed
cd ~/ozzy-simple
source venv/bin/activate
cd scripts
nohup python bulletproof_test.py --duration 21600 --interval 900 --capital 10000 > /tmp/test_output.log 2>&1 &
```

### **No Recent Decisions Showing:**
```bash
# Verify log file has data
grep "DECISION COMPLETE" /tmp/test_output.log

# Check if decisions are being made
tail -f /tmp/test_output.log
```

---

## 💡 PRO TIPS

### **Multiple Views:**
Open 3 terminals side by side:
1. **Dashboard** - `python3 monitor_dashboard.py`
2. **Raw Log** - `tail -f /tmp/test_output.log`
3. **Commands** - For running planner, git, etc.

### **Quick Checks:**
```bash
# Planner status
python3 MASTER_PLANNER.py status

# Signal summary
grep "Action:" /tmp/test_output.log | tail -20

# Confidence levels
grep "Confidence:" /tmp/test_output.log | tail -20
```

### **Screenshots:**
Take screenshots of the dashboard at key milestones:
- First decision
- Every 6 decisions
- Test completion
- High confidence signals
- Profitable trades

---

## 🎯 CURRENT DASHBOARD STATUS

**As of 08:18 AM:**

```
✅ Process: RUNNING (PID 24504)
✅ Progress: 1/24 decisions (4.2%)
✅ Elapsed: 00:19:49
✅ Remaining: ~07:35:00
✅ Capital: R9,500 (1 position open)
✅ P&L: -R500 (-5%)
✅ Last Signal: BUY @ 70% confidence
```

**Next Decision:** ~08:13 AM (recently passed - check dashboard!)

---

## 📝 INTEGRATION WITH PLANNER

The dashboard automatically shows:
- Current phase from MASTER_PLANNER.py
- Milestone progress
- Auto-updates as you complete milestones

**After marking milestone complete:**
```bash
python3 MASTER_PLANNER.py complete 1.2

# Dashboard will show:
# Progress: 2/8 (25%)
```

---

## 🚀 COMMANDS REFERENCE

```bash
# Start dashboard
python3 monitor_dashboard.py

# Start with custom log
python3 monitor_dashboard.py --log /path/to/log

# Stop dashboard
Ctrl+C

# Check if running
ps aux | grep monitor_dashboard

# View raw log
tail -f /tmp/test_output.log

# Quick signal count
echo "BUY:  $(grep -c 'Action: BUY' /tmp/test_output.log)"
echo "SELL: $(grep -c 'Action: SELL' /tmp/test_output.log)"
echo "SKIP: $(grep -c 'Action: SKIP' /tmp/test_output.log)"
```

---

## 🎊 ENJOY YOUR DASHBOARD!

You now have real-time monitoring of:
- ✅ Test progress and timing
- ✅ Decision signals and confidence
- ✅ Portfolio value and P&L
- ✅ System health and stability
- ✅ Project milestone progress

**The dashboard makes it easy to:**
- See what's happening at a glance
- Catch issues immediately
- Track progress toward goals
- Make informed decisions
- Stay motivated!

---

**Dashboard Location:** `/home/rick/ozzy-simple/monitor_dashboard.py`  
**Status:** ✅ RUNNING  
**Terminal ID:** Available in background  

**Tip:** Leave it running in a dedicated terminal or tmux session! 📊🔥
