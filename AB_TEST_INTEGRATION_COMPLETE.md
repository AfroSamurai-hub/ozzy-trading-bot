# ✅ A/B Test Integration COMPLETE!

**Date:** October 11, 2025  
**Status:** Ready to start collecting data  
**Integration Time:** ~5 minutes  

---

## 🎯 What Was Changed

### 4 Surgical Modifications to `main.py`

#### ✅ Change 1: Import Added (Line ~20)
```python
from time_filter_wrapper import TimeFilterWrapper
```

#### ✅ Change 2: Test Initialized (Line ~63-72)
```python
# Time filter A/B test
self.time_filter = TimeFilterWrapper(
    test_name="time_filter_night",
    avoid_hours=[(22, 2)],  # Avoid 22:00-02:00 UTC (low volatility)
    enabled=True  # Set to False to disable test
)
logger.info(f"🧪 A/B Test initialized: time_filter_night")
logger.info(f"   Avoid hours (Test group): {self.time_filter.avoid_hours}")
logger.info(f"   Target: 50 trades per variant")
```

#### ✅ Change 3: Filter Applied in check_signal() (Line ~218-221)
```python
# Apply time filter for A/B test
signal, test_group = self.time_filter.apply_filter(signal, symbol)

# Store test group for later use in trade execution
signal['test_group'] = test_group
```

#### ✅ Change 4: Trades Tagged in execute_trade() (Line ~330-348)
```python
# Get test group from signal and format entry reason with A/B test tag
test_group = signal.get('test_group', 'unknown')
entry_reason = self.time_filter.format_entry_reason(
    signal.get('reason', ''),
    test_group
)

db_id = db.log_trade_open({
    # ... other fields ...
    'entry_reason': entry_reason  # Tagged with test group
})

# Log test group assignment
logger.info(f"📊 A/B Test: Assigned to {test_group.upper()} group")
```

---

## 🔍 How It Works Now

### For Every Signal Generated:

1. **Signal Generation** (Normal)
   - Bot checks BTCUSDT, gets candles
   - Generates signal: LONG/SHORT/HOLD

2. **Random Assignment** (NEW - 50/50 split)
   - Randomly assigns to Control or Test group
   - Control: No filtering (trades 24/7)
   - Test: Applies time filter

3. **Time Filter Check** (NEW - Only Test Group)
   - If Control group: Signal passes through unchanged
   - If Test group:
     - Check current UTC hour
     - If 22:00-02:00 UTC: Convert signal to HOLD (skip)
     - Otherwise: Signal passes through unchanged

4. **Trade Execution** (Normal + Tagging)
   - Execute trade if signal is LONG/SHORT
   - Tag trade in database with test group
   - Example: `TEST_time_filter_night_control_rsi_oversold`
   - Or: `TEST_time_filter_night_test_ema_crossover`

5. **Logging** (Enhanced)
   - Logs which group trade was assigned to
   - Logs if test group signal was filtered
   - All visible in bot.log

---

## 📊 What You'll See in Logs

### Startup:
```
🤖 OZZY SIMPLE - AUTOMATED TRADING BOT
======================================================================
Initializing components...
✅ Bot initialized successfully!
🧪 A/B Test initialized: time_filter_night
   Avoid hours (Test group): [(22, 2)]
   Target: 50 trades per variant
======================================================================
```

### Control Group Trade (09:30 UTC):
```
[09:30 UTC] Checking signal for BTCUSDT...
🟢 LONG | STRONG | 68% confidence
Reason: rsi_oversold
💼 Attempting to execute LONG trade on BTCUSDT...
📊 A/B Test: Assigned to CONTROL group
✅ Trade executed successfully!
Order ID: 1234567890
Position: 0.05 BTCUSDT @ $67,234.00
```

### Test Group Trade - ALLOWED (10:45 UTC):
```
[10:45 UTC] Checking signal for ETHUSDT...
🔴 SHORT | GOOD | 54% confidence
Reason: rsi_overbought
💼 Attempting to execute SHORT trade on ETHUSDT...
📊 A/B Test: Assigned to TEST group
✅ Trade executed successfully!
Order ID: 1234567891
Position: 0.8 ETHUSDT @ $3,456.00
```

### Test Group Trade - FILTERED (22:15 UTC):
```
[22:15 UTC] Checking signal for BTCUSDT...
🟢 LONG | STRONG | 72% confidence
Reason: ema_crossover
⚪ HOLD | STRONG | 72% confidence
Reason: ema_crossover
⏭️ No tradable signal - skipping
```

### Test Group Trade - ALLOWED AGAIN (02:30 UTC):
```
[02:30 UTC] Checking signal for SOLUSDT...
🔴 SHORT | EXCELLENT | 85% confidence
Reason: strong_momentum_short
💼 Attempting to execute SHORT trade on SOLUSDT...
📊 A/B Test: Assigned to TEST group
✅ Trade executed successfully!
Order ID: 1234567892
Position: 15 SOLUSDT @ $145.00
```

---

## 🚀 NEXT STEPS - START COLLECTING DATA!

### Step 1: Stop Current Bot
```bash
cd ~/ozzy-simple
pkill -f "python main.py"

# Wait 3 seconds
sleep 3

# Verify stopped
ps aux | grep "python main.py"
# Should show NO results (only the grep command itself)
```

### Step 2: Start Bot with A/B Test Active
```bash
cd ~/ozzy-simple
nohup ./venv/bin/python main.py > bot.log 2>&1 &

# Save PID
echo $! > bot.pid

# Wait 5 seconds for startup
sleep 5
```

### Step 3: Verify A/B Test Started
```bash
# Check last 100 lines of log
tail -100 bot.log

# Should see:
# ✅ Bot initialized successfully!
# 🧪 A/B Test initialized: time_filter_night
#    Avoid hours (Test group): [(22, 2)]
#    Target: 50 trades per variant
```

### Step 4: Watch Real-Time Logs (Optional)
```bash
tail -f bot.log

# Press Ctrl+C to stop watching
```

---

## 📈 MONITORING YOUR TEST

### Daily Status Check (Run Once Per Day)
```bash
cd ~/ozzy-simple
./venv/bin/python scripts/test_time_filter.py --status
```

**Expected Output (Day 1):**
```
╔══════════════════════════════════════════════════════════════════╗
║  TIME-OF-DAY FILTER A/B TEST RESULTS                             ║
╚══════════════════════════════════════════════════════════════════╝

📋 TEST CONFIGURATION
Test Name:           time_filter_night
Avoid Hours (Test):  22:00-02:00 UTC
Target Trades:       50 per group
Status:              In Progress (16%)

📊 PROGRESS
Control Group:       8/50 trades (16%)
Test Group:          8/50 trades (16%)

📈 RESULTS COMPARISON
Metric                    Control (24/7)       Test (Filtered)     
──────────────────────────────────────────────────────────────────────
Trades                    8                    8                   
Win Rate                  62.5%                75.0%               
Wins / Losses             5/3                  6/2                 
Total P&L                 R237.50              R356.00             
Avg P&L per Trade         R29.69               R44.50              

🎯 VERDICT
⏳ INCOMPLETE - Need more trades
   Control needs: 42 more trades
   Test needs: 42 more trades

Early indication: Test leading by R118.50! 🔥
(Too early to draw conclusions - need 50 trades per group)
```

### Continuous Monitoring (Optional)
```bash
# Update every 5 minutes
watch -n 300 './venv/bin/python scripts/test_time_filter.py --status'
```

### Check Bot is Running
```bash
ps aux | grep "python main.py"

# Should show:
# rick     12345  0.2  1.5 123456 78910 ?  S   10:30  0:05 python main.py
```

### Check Recent Activity
```bash
tail -50 bot.log | grep -E "Test|CONTROL|filtered"
```

---

## 📅 TIMELINE EXPECTATIONS

### Day 1 (Today - Oct 11):
- **Expected:** 8-10 trades per group
- **Control:** ~8/50 trades (16%)
- **Test:** ~8/50 trades (16%)
- **Status:** Too early to judge
- **Action:** Verify both groups collecting data

### Day 2 (Oct 12):
- **Expected:** 18-22 trades per group (cumulative)
- **Control:** ~20/50 trades (40%)
- **Test:** ~20/50 trades (40%)
- **Status:** Early patterns emerging
- **Action:** Check progress, verify no errors

### Day 3 (Oct 13):
- **Expected:** 32-38 trades per group (cumulative)
- **Control:** ~35/50 trades (70%)
- **Test:** ~35/50 trades (70%)
- **Status:** Strong indication visible
- **Action:** Review preliminary results

### Day 4-5 (Oct 14-15):
- **Expected:** 50+ trades per group ✅
- **Control:** 50/50 trades (100%) ✅
- **Test:** 50/50 trades (100%) ✅
- **Status:** COMPLETE!
- **Action:** Generate final report, make decision

---

## 🎯 WHAT SUCCESS LOOKS LIKE

### Final Report (Example - Day 5)
```bash
cd ~/ozzy-simple
./venv/bin/python scripts/test_time_filter.py --report
```

**Possible Outcome 1: Test WINS**
```
╔══════════════════════════════════════════════════════════════════╗
║  🏆 FINAL RESULTS - TEST WINS!                                   ║
╚══════════════════════════════════════════════════════════════════╝

CONTROL (24/7 Trading):
  ├─ 50 trades completed
  ├─ Win Rate: 58.0%
  ├─ Total Profit: R1,475
  └─ Avg P&L: R29.50

TEST (Avoid 22:00-02:00):
  ├─ 50 trades completed
  ├─ Win Rate: 63.0% (+5.0% 🔥)
  ├─ Total Profit: R1,880 (+R405! 💰)
  └─ Avg P&L: R37.60 (+R8.10)

🎯 VERDICT: TEST WINS!
   Win rate improved by +5.0%
   Extra profit: R405 on same 50 trades (27% more money!)
   Statistical significance: p < 0.05 ✅

📝 RECOMMENDATION:
   ✅ Apply time filter to baseline config
   ✅ Update config to avoid 22:00-02:00 UTC
   ✅ Expected annual impact: ~R21,000 extra profit!
```

**Possible Outcome 2: Test LOSES**
```
╔══════════════════════════════════════════════════════════════════╗
║  ❌ FINAL RESULTS - TEST LOSES                                   ║
╚══════════════════════════════════════════════════════════════════╝

CONTROL (24/7 Trading):
  ├─ 50 trades completed
  ├─ Win Rate: 58.0%
  ├─ Total Profit: R1,475
  └─ Avg P&L: R29.50

TEST (Avoid 22:00-02:00):
  ├─ 50 trades completed
  ├─ Win Rate: 54.0% (-4.0% ❌)
  ├─ Total Profit: R1,180 (-R295 💸)
  └─ Avg P&L: R23.60 (-R5.90)

🎯 VERDICT: TEST LOSES
   Win rate decreased by -4.0%
   Lost profit: R295 compared to control
   Statistical significance: p < 0.05

📝 RECOMMENDATION:
   ❌ Do NOT apply time filter
   ✅ Keep 24/7 trading
   ✅ Those late night hours ARE valuable!
   ✅ Move to next test: confidence threshold optimization
```

**Possible Outcome 3: No Significant Difference**
```
╔══════════════════════════════════════════════════════════════════╗
║  ⚖️  FINAL RESULTS - NO SIGNIFICANT DIFFERENCE                   ║
╚══════════════════════════════════════════════════════════════════╝

CONTROL (24/7 Trading):
  ├─ 50 trades completed
  ├─ Win Rate: 58.0%
  ├─ Total Profit: R1,475
  └─ Avg P&L: R29.50

TEST (Avoid 22:00-02:00):
  ├─ 50 trades completed
  ├─ Win Rate: 57.0% (-1.0%)
  ├─ Total Profit: R1,425 (-R50)
  └─ Avg P&L: R28.50 (-R1.00)

🎯 VERDICT: NO SIGNIFICANT DIFFERENCE
   Win rate difference: -1.0% (within noise)
   Profit difference: -R50 (minimal)
   Statistical significance: p = 0.42 (not significant)

📝 RECOMMENDATION:
   ⚖️ Time of day doesn't matter significantly
   ✅ Keep 24/7 trading (simpler is better)
   ✅ Focus on other variables (confidence, RSI, etc.)
   ✅ Move to next test
```

---

## 🔧 TROUBLESHOOTING

### Problem: Bot Won't Start
```bash
# Check for syntax errors
cd ~/ozzy-simple
./venv/bin/python main.py

# If errors, check last 50 lines
tail -50 bot.log

# Common fix: restart
pkill -f "python main.py"
sleep 3
nohup ./venv/bin/python main.py > bot.log 2>&1 &
```

### Problem: No Trades Collecting
```bash
# Check bot is running
ps aux | grep "python main.py"

# Check recent logs
tail -100 bot.log

# Look for errors
grep -i "error" bot.log | tail -20
```

### Problem: Only Control Group Has Trades
**This is NORMAL if:**
- Current time is 22:00-02:00 UTC (test group being filtered)
- Check current time: `date -u`

**This is a PROBLEM if:**
- Current time is outside 22:00-02:00 UTC
- AND control has 20+ trades
- BUT test has 0 trades

**Fix:** Check logs for errors, restart bot

### Problem: Test Not Showing in Database
```bash
# Check database for test tags
cd ~/ozzy-simple
sqlite3 ozzy_simple.db "SELECT entry_reason FROM trades WHERE entry_reason LIKE '%TEST_%' ORDER BY id DESC LIMIT 10;"

# Should see entries like:
# TEST_time_filter_night_control_rsi_oversold
# TEST_time_filter_night_test_ema_crossover
```

---

## 🛑 HOW TO DISABLE TEST (If Needed)

### Temporary Disable (Keep Code, Stop Test)
Edit `main.py` line ~68:
```python
self.time_filter = TimeFilterWrapper(
    test_name="time_filter_night",
    avoid_hours=[(22, 2)],
    enabled=False  # ← Change to False
)
```

Then restart:
```bash
pkill -f "python main.py"
nohup ./venv/bin/python main.py > bot.log 2>&1 &
```

### Permanent Disable (Remove Code)
Restore from backup:
```bash
cd ~/ozzy-simple
cp main.py.backup main.py
pkill -f "python main.py"
nohup ./venv/bin/python main.py > bot.log 2>&1 &
```

---

## 📚 FILES INVOLVED

### Core Files:
- ✅ `main.py` - Modified (4 changes)
- ✅ `main.py.backup` - Original backup
- ✅ `time_filter_wrapper.py` - Integration wrapper
- ✅ `scripts/test_time_filter.py` - Analysis tool

### Documentation:
- ✅ `AB_TEST_INTEGRATION_COMPLETE.md` - This file
- ✅ `INTEGRATION_STEPS.md` - Detailed guide
- ✅ `TIME_FILTER_COMPLETE.md` - Package overview
- ✅ `STRATEGY_EVOLUTION_PLAN.md` - 6-month roadmap

### Database:
- ✅ `ozzy_simple.db` - All trade data stored here

---

## 🎓 KEY UNDERSTANDING

### This Test Will:
- ✅ Run automatically in background
- ✅ Split signals 50/50 between control and test
- ✅ Filter test group signals during 22:00-02:00 UTC
- ✅ Tag all trades with test group
- ✅ Continue until 50 trades per group
- ✅ Take 4-5 days to complete

### This Test Will NOT:
- ❌ Break your existing bot functionality
- ❌ Reduce total number of trades significantly
- ❌ Require manual intervention
- ❌ Complete in 1 day (needs time for data)
- ❌ Affect control group trading at all

### What Makes This Scientific:
- ✅ Random 50/50 assignment (no bias)
- ✅ Control group for comparison
- ✅ Same market conditions for both groups
- ✅ Statistical significance testing
- ✅ Sufficient sample size (50 trades per group)
- ✅ One variable tested (time of day)

---

## 🎯 YOUR ACTION ITEMS

### RIGHT NOW (Next 10 minutes):
- [ ] Stop current bot
- [ ] Start bot with A/B test integrated
- [ ] Verify logs show "A/B Test initialized"
- [ ] Watch first few signals to see test working

### DAILY (Next 5 days):
- [ ] Check test progress with `--status`
- [ ] Verify bot still running
- [ ] Check for errors in logs
- [ ] Document any observations

### WHEN COMPLETE (Day 5):
- [ ] Generate final report with `--report`
- [ ] Review results carefully
- [ ] Make decision: apply filter or keep 24/7
- [ ] Document outcome
- [ ] Plan next test (Week 2)

---

## 🏆 SUCCESS METRICS

### Baseline to Beat:
- **Win Rate:** 58.1%
- **Avg P&L:** R29.65

### Test Success = Either:
- Win rate improves by +2% or more
- OR avg P&L improves by R5+ per trade

### Ultimate Goal (6 months):
- **Win Rate:** 67.5%
- **Avg P&L:** R60

**This is Test 1 of ~26 planned evolution tests!**

---

**Integration Complete:** ✅  
**Syntax Verified:** ✅  
**Ready to Start:** ✅  
**Backup Created:** ✅  

🚀 **LET'S START COLLECTING DATA!**

---

*For detailed technical documentation, see:*
- `INTEGRATION_STEPS.md`
- `TIME_FILTER_INTEGRATION.md`
- `STRATEGY_EVOLUTION_PLAN.md`
