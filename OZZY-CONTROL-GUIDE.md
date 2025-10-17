# 🎯 OZZY.PY - Master Control Guide

**ONE COMMAND TO RULE THEM ALL** 🚀

No more:
- ❌ "Which file do I run?"
- ❌ "Let me check if test is running..."
- ❌ "Where's the portfolio command?"
- ❌ Opening 5 different terminals

**Now:** Just `./ozzy.py status` → See EVERYTHING! ✨

---

## 🚀 QUICK START

### **The ONE Command You Need:**

```bash
./ozzy.py status
```

**Shows everything in one view:**
- ✅ Test status (running/stopped, progress)
- ✅ Latest decisions (BUY/SELL/SKIP)
- ✅ Portfolio summary (capital, positions)
- ✅ Project status (milestones completed)
- ✅ Quick action commands

**Run this every hour!** Perfect for periodic monitoring (Option 2).

---

## 📋 ALL COMMANDS

### **1. `./ozzy.py status` - Complete Status** 🎯

**The main command.** Everything you need in one screen.

```bash
./ozzy.py status
```

**Output:**
```
======================================================================
🎯 OZZY COMPLETE STATUS
======================================================================

🧪 TEST STATUS
----------------------------------------------------------------------
Status: ✅ RUNNING (PID: 24504)
Progress: 5/24 decisions (20.8%)
████████░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░ 20.8%
Runtime: 67 minutes
Estimated completion: 256 minutes

🎯 LATEST DECISIONS
----------------------------------------------------------------------
Decision #1: BUY @ 70.0%
Decision #2: SKIP @ 0.0%
Decision #3: BUY @ 70.0%
Decision #4: SKIP @ 50.0%
Decision #5: SKIP @ 50.0%

💰 PORTFOLIO SUMMARY
----------------------------------------------------------------------
Capital: R9,025.00
Open Positions: 2
Signals: 2 BUY, 0 SELL, 3 SKIP
Trade Rate: 40.0%

📋 PROJECT STATUS
----------------------------------------------------------------------
Current Phase: phase_1
Milestones Completed: 1
Latest: ✅ phase_1.1.1

⚡ QUICK ACTIONS
----------------------------------------------------------------------
Full portfolio:  ./ozzy.py portfolio
Project details: ./ozzy.py plan
Live monitor:    ./ozzy.py monitor
Quick check:     ./ozzy.py quick

======================================================================
```

**When to use:** Every hour, when checking progress, before meetings, whenever!

---

### **2. `./ozzy.py quick` - Quick Glance** ⚡

Super fast, minimal output. Just the essentials.

```bash
./ozzy.py quick
```

**Output:**
```
⚡ QUICK STATUS

✅ Test: Running
   5/24 decisions (20.8%)
💰 Capital: R9,025.00
   Positions: 2 | Decisions: 5
🎯 Milestones: 1 completed
```

**When to use:** 
- Quick checks between work
- Terminal with limited space
- Just want to know "is it running?"

---

### **3. `./ozzy.py test` - Test Management** 🧪

Deep dive into test progress and management.

```bash
./ozzy.py test
```

**Shows:**
- Test status (running/stopped)
- Progress bar and percentage
- Runtime and estimated completion
- Next decision timing
- Commands to view logs or stop test

**When to use:**
- Want test-specific details
- Need to check ETA
- Planning to stop test

---

### **4. `./ozzy.py portfolio` - Portfolio Deep Dive** 💰

Full portfolio analysis with all details.

```bash
./ozzy.py portfolio
```

**Shows:**
- Starting vs current capital
- Allocated funds
- P&L (realized + unrealized)
- All open positions with details
- All closed trades
- Signal distribution
- Trade rate

**When to use:**
- Want to see full financial picture
- Check individual position P&L
- Analyze trading performance

---

### **5. `./ozzy.py plan` - Project Planning** 📋

Project status and milestone tracking.

```bash
./ozzy.py plan
```

**Shows:**
- Current phase and goal
- All milestones (completed/active/locked)
- Success criteria
- Forbidden features (scope creep prevention)
- Next actions

**When to use:**
- Planning next work
- Checking milestones
- Need motivation/direction

---

### **6. `./ozzy.py monitor` - Live Monitoring** 📊

Starts the live monitoring dashboard (auto-refresh).

```bash
./ozzy.py monitor
```

**Shows:**
- Real-time test progress
- Live portfolio updates
- Recent decisions
- Auto-refreshes every 2 seconds
- Press Ctrl+C to exit

**When to use:**
- Want to watch test live
- Important decision coming up
- Just enjoy watching it work 😎

---

### **7. `./ozzy.py check` - Health Check** 🏥

Verifies all components are in place.

```bash
./ozzy.py check
```

**Checks:**
- ✅ Test process running
- ✅ Log file exists and size
- ✅ Planner data present
- ✅ Portfolio state file
- ✅ Test scripts available
- ✅ Monitor dashboard exists
- ✅ Portfolio tracker exists

**Output:**
```
🏥 HEALTH CHECK

✅ Test Process        PID 24504
✅ Log File           234.5 KB
✅ Planner Data       Present
✅ Portfolio State    Present
✅ Test Script        Present
✅ Monitor Dashboard  Present
✅ Portfolio Tracker  Present

Summary: 7/7 checks passed
🎉 All systems operational!
```

**When to use:**
- Troubleshooting issues
- After setup/restart
- Sanity check

---

### **8. `./ozzy.py help` - Show Help** ❓

Shows all available commands.

```bash
./ozzy.py help
```

---

## 🎯 YOUR WORKFLOW (OPTION 2: PERIODIC CHECKS)

### **Perfect Periodic Monitoring:**

```bash
# Morning - Full status
./ozzy.py status

# Every hour - Quick check
./ozzy.py quick

# Lunch - Full status again
./ozzy.py status

# Afternoon - Portfolio check
./ozzy.py portfolio

# Before end of day - Full status
./ozzy.py status

# When test completes - Detailed portfolio
./ozzy.py portfolio
```

---

## ⏰ RECOMMENDED SCHEDULE

### **Hourly Routine:**

```bash
# On the hour (10:00, 11:00, 12:00, etc.)
./ozzy.py status
```

**Takes 5 seconds. Shows everything.**

### **Deep Dive (Once Daily):**

```bash
# Once a day - full analysis
./ozzy.py portfolio
./ozzy.py plan
```

### **Quick Peeks (Anytime):**

```bash
# Just checking if running
./ozzy.py quick
```

---

## 🔥 POWER USER TIPS

### **1. Alias for Speed:**

Add to `~/.bashrc`:
```bash
alias oz='cd ~/ozzy-simple && ./ozzy.py'
```

Then just:
```bash
oz status
oz quick
oz portfolio
```

### **2. Watch Command:**

Auto-refresh every 60 seconds:
```bash
watch -n 60 './ozzy.py status'
```

### **3. Background Monitoring:**

```bash
# Terminal 1: Work
./ozzy.py quick

# Terminal 2: Live monitor
./ozzy.py monitor
```

### **4. Quick Health Check:**

Before leaving computer:
```bash
./ozzy.py check && ./ozzy.py status
```

Ensures everything running + current status.

---

## 📊 COMPARISON: Before vs After

### **BEFORE ozzy.py:**

```bash
# Check if test running
ps aux | grep bulletproof_test | grep -v grep

# Check portfolio
python3 track_portfolio.py

# Check project
python3 MASTER_PLANNER.py status

# Check progress
grep "DECISION #" /tmp/test_output.log | tail -5

# Start monitor
python3 monitor_dashboard.py

# Health check
ls -la scripts/
cat planner_data.json
tail /tmp/test_output.log
```

**Result:** 6+ commands, multiple files to remember! 😵

### **AFTER ozzy.py:**

```bash
./ozzy.py status
```

**Result:** ONE command. Everything visible. 🎯

---

## 🎯 SEAMLESS INTEGRATION

### **How It Connects Everything:**

```
ozzy.py (Master Control)
   ├── Test Status → Checks running process
   ├── Test Progress → Parses log file
   ├── Portfolio → Calls track_portfolio.py
   ├── Project Status → Reads planner_data.json
   ├── Monitoring → Launches monitor_dashboard.py
   └── Health Check → Verifies all components

NO manual checking if things exist!
NO wondering which file to open!
EVERYTHING connected seamlessly!
```

---

## 💡 WHAT EACH COMMAND CHECKS FOR YOU

### **`./ozzy.py status` Automatically:**

1. ✅ Is test running? (checks process)
2. ✅ How far along? (parses log)
3. ✅ Latest decisions? (extracts from log)
4. ✅ Current capital? (calculates from log)
5. ✅ Positions open? (counts from log)
6. ✅ Milestones complete? (reads planner data)

**You don't check anything manually. It checks FOR you!**

---

## 🚀 EXAMPLE SESSION

### **Morning (9:00 AM):**

```bash
$ ./ozzy.py status

# Output shows:
# - Test running ✅
# - 5/24 decisions (20.8%)
# - R9,025 capital
# - 2 positions open
# - Milestone 1.2 in progress

# Perfect! Everything on track.
```

### **Mid-Day (12:00 PM):**

```bash
$ ./ozzy.py quick

# Output shows:
# ✅ Test: Running
#    12/24 decisions (50%)
# 💰 Capital: R9,500
#    Positions: 1 | Decisions: 12
# 🎯 Milestones: 1 completed

# Great! Halfway done.
```

### **Afternoon (3:00 PM):**

```bash
$ ./ozzy.py status

# Shows:
# - 18/24 decisions (75%)
# - R10,200 capital (profitable!)
# - 0 positions (all closed)
# - High confidence signals

# Excellent progress!
```

### **Test Complete (14:00 PM):**

```bash
$ ./ozzy.py portfolio

# Shows full breakdown:
# - Final capital: R10,500
# - P&L: +R500 (+5%)
# - Closed trades: 4
# - Win rate: 75%

# Mark milestone complete!
$ python3 MASTER_PLANNER.py complete 1.2
```

---

## 🎊 THE MAGIC

### **What Makes It Seamless:**

1. **Auto-Detection:** Checks if test running automatically
2. **Smart Parsing:** Extracts data from log files
3. **No File Hunting:** Knows where everything is
4. **Error Handling:** Graceful if files missing
5. **Color Coding:** Green = good, Red = issues, Yellow = warnings
6. **Progress Bars:** Visual feedback
7. **Quick Actions:** Shows next commands to run
8. **One Entry Point:** Everything accessible from `ozzy.py`

### **You Never Have To:**

- ❌ Remember which script does what
- ❌ Check if file exists before opening
- ❌ Parse log files manually
- ❌ Calculate percentages
- ❌ Count decisions
- ❌ Wonder if test is running

**It does ALL of that FOR you!** ✨

---

## 🔥 BOTTOM LINE

### **The Old Way:**

```bash
# Is test running?
ps aux | grep...

# Hmm, what's the capital?
python3 track...

# Wait, which milestone?
python3 MASTER...

# Where's the monitor?
ls *.py...
```

**5+ commands. Confusion. Frustration.** 😵

### **The New Way:**

```bash
./ozzy.py status
```

**ONE command. Complete visibility. Zero confusion.** 🎯

---

## 📋 COMMAND CHEAT SHEET

```bash
./ozzy.py status      # Everything (USE THIS!)
./ozzy.py quick       # Fast check
./ozzy.py test        # Test details
./ozzy.py portfolio   # Money details
./ozzy.py plan        # Project details
./ozzy.py monitor     # Live view
./ozzy.py check       # Health check
./ozzy.py help        # Show help
```

**Bookmark this page. Print it. Tattoo it.** This is your control center! 🚀

---

## 🎯 RECOMMENDATION FOR YOU

### **Your Hourly Routine:**

```bash
# Every hour
./ozzy.py status
```

**That's it.** 

5 seconds. Complete picture. Make decisions. Move on.

**Perfect for Option 2 (Periodic Checks)!** ✅

---

## 💪 NEXT LEVEL

Want even MORE seamless?

```bash
# Add to crontab (runs every hour automatically)
0 * * * * cd ~/ozzy-simple && ./ozzy.py status > /tmp/ozzy_status.txt

# Then just:
cat /tmp/ozzy_status.txt
```

**Status updates ITSELF every hour.** 🤯

---

**Created:** October 17, 2025  
**Purpose:** Seamless control center for OZZY  
**Status:** ACTIVE and AWESOME! 🔥  

**Welcome to effortless monitoring!** 🎊
