# Time Filter A/B Test - Complete Package

## 📦 What's Been Created

### Core Framework (3 files)
1. **`scripts/test_time_filter.py`** (289 lines)
   - A/B testing framework for time-of-day filters
   - Statistical significance testing
   - Progress tracking and reporting
   - Command: `./venv/bin/python scripts/test_time_filter.py --status`

2. **`time_filter_wrapper.py`** (152 lines)
   - Integration wrapper for main bot
   - Random test group assignment (50/50 split)
   - Signal filtering based on UTC hour
   - Trade tagging for analysis

3. **`INTEGRATION_STEPS.md`** (300+ lines)
   - Step-by-step integration guide
   - Complete with code examples
   - Troubleshooting section
   - Verification commands

### Documentation (3 files)
4. **`TIME_FILTER_INTEGRATION.md`** (280+ lines)
   - Comprehensive overview
   - Configuration options
   - Usage examples
   - Timeline estimates

5. **`INTEGRATION_STEPS.md`** (see above)

6. **`quick_integrate.sh`** (helper script)
   - Quick reference for changes needed
   - Auto-creates backup
   - Shows integration summary

### Backup Created
- **`main.py.backup`** - Your original main.py saved safely

## 🎯 The Test Strategy

### Hypothesis
**"Does avoiding low-volatility hours (22:00-02:00 UTC) improve trading performance?"**

### Method
- **Control Group (50%)**: Trade 24/7 as normal
- **Test Group (50%)**: Skip signals during 22:00-02:00 UTC
- **Goal**: Collect 50 trades per group
- **Timeline**: 5-7 days at current velocity

### Success Criteria
**Winner if:** Win rate improves >2% OR Avg P&L improves >R5  
**Loser if:** Win rate drops >2% OR Avg P&L drops >R5  
**No change if:** Within ±2% win rate AND ±R5 avg P&L

## 🚀 Quick Start (3 Steps)

### 1. Review Changes Needed
```bash
cd ~/ozzy-simple
./quick_integrate.sh
```

### 2. Follow Integration Guide
```bash
# Open the detailed guide
cat INTEGRATION_STEPS.md

# OR view in browser
code INTEGRATION_STEPS.md
```

### 3. Make 4 Code Changes to main.py
1. Add import: `from time_filter_wrapper import TimeFilterWrapper`
2. Initialize wrapper in `__init__`
3. Apply filter in `check_signal()`
4. Tag trades in `execute_trade()`

See **INTEGRATION_STEPS.md** for exact code snippets.

## 📊 Monitoring Commands

### Check Test Status
```bash
cd ~/ozzy-simple
./venv/bin/python scripts/test_time_filter.py --status
```

### Watch Bot Logs
```bash
tail -f ~/ozzy-simple/bot.log | grep -E "Test group|Control group|avoid window"
```

### Daily Summary
```bash
cd ~/ozzy-simple
./venv/bin/python scripts/quick_status.py
./venv/bin/python scripts/test_time_filter.py --status
```

### Final Report (When Complete)
```bash
cd ~/ozzy-simple
./venv/bin/python scripts/test_time_filter.py --report
```

## 📁 File Locations

```
~/ozzy-simple/
├── main.py                          ← EDIT THIS (4 changes needed)
├── main.py.backup                   ← Backup created automatically
├── time_filter_wrapper.py           ← Integration wrapper (NEW)
├── scripts/
│   ├── test_time_filter.py          ← A/B test analyzer (NEW)
│   ├── verify_baseline.py           ← Verify baseline performance
│   └── quick_status.py              ← Daily progress check
├── INTEGRATION_STEPS.md             ← Step-by-step guide (NEW)
├── TIME_FILTER_INTEGRATION.md       ← Comprehensive docs (NEW)
├── STRATEGY_EVOLUTION_PLAN.md       ← 6-month evolution roadmap
└── quick_integrate.sh               ← Quick reference (NEW)
```

## ⚙️ Configuration Options

### Default Configuration
```python
TimeFilterWrapper(
    test_name="time_filter_night",
    avoid_hours=[(22, 2)],  # Avoid 22:00-02:00 UTC
    enabled=True
)
```

### Alternative Configurations

**Test Early Morning:**
```python
avoid_hours=[(0, 4)]  # Avoid 00:00-04:00 UTC
```

**Test Multiple Windows:**
```python
avoid_hours=[(22, 2), (12, 14)]  # Avoid night AND lunch
```

**Test Entire Asian Session:**
```python
avoid_hours=[(2, 8)]  # Avoid 02:00-08:00 UTC
```

## 🔧 Integration Details

### Changes to main.py (4 locations)

#### 1. Import (Line ~20)
```python
from time_filter_wrapper import TimeFilterWrapper
```

#### 2. Initialize (Line ~63)
```python
self.time_filter = TimeFilterWrapper(
    test_name="time_filter_night",
    avoid_hours=[(22, 2)],
    enabled=True
)
```

#### 3. Apply Filter (Line ~217)
```python
signal, test_group = self.time_filter.apply_filter(signal, symbol)
```

#### 4. Tag Trades (Line ~335)
```python
'entry_reason': self.time_filter.format_entry_reason(
    signal.get('reason', ''),
    test_group
)
```

## 📈 Expected Results

### After 5-7 Days

You'll have data showing:
- Control group win rate (24/7 trading)
- Test group win rate (filtered trading)
- Statistical significance (p-value)
- Average P&L comparison
- Trade count per symbol
- Hourly distribution

### Decision Tree

```
                    Generate Report
                          |
                /---------+---------\
               /                     \
        Win rate +2%            Win rate -2%
        OR P&L +R5              OR P&L -R5
             |                       |
      Apply Filter             Keep 24/7
             |                       |
      Update Config            Stay Baseline
```

## 🎓 Learning from This Test

### Win Scenario
- **Insight**: Low-volatility hours hurt performance
- **Action**: Add time filter to config permanently
- **Next**: Test other variables (confidence, RSI, etc.)

### Loss Scenario
- **Insight**: All hours are valuable for trading
- **Action**: Keep 24/7 trading
- **Next**: Test other variables (confidence, RSI, etc.)

### No Difference Scenario
- **Insight**: Time of day doesn't matter significantly
- **Action**: Keep 24/7 trading (simpler)
- **Next**: Focus on more impactful variables

## 🔒 Safety Features

### Built-in Safeguards
- ✅ Backup created automatically
- ✅ Test can be disabled instantly
- ✅ Control group always trades normally
- ✅ No impact on existing positions
- ✅ All changes isolated to test framework

### Rollback Plan
```bash
# If anything goes wrong:
cd ~/ozzy-simple
pkill -f "python main.py"
cp main.py.backup main.py
nohup python main.py > bot.log 2>&1 &
```

## 📚 Related Documentation

- **STRATEGY_EVOLUTION_PLAN.md** - 6-month improvement roadmap
- **VERIFY_BASELINE_README.md** - Baseline verification guide
- **HOW_TO_GO_LIVE.md** - Real money transition guide
- **TRADING_HOURS_REMOVED.md** - 24/7 enablement details

## 🎯 Next Steps After Integration

1. ✅ Make 4 code changes to main.py
2. ✅ Restart bot
3. ⏳ Monitor daily with --status
4. ⏳ Wait 5-7 days for data collection
5. ✅ Generate final report
6. ✅ Make go/no-go decision
7. ✅ Move to next evolution test

## 💡 Pro Tips

### Tip 1: Monitor Daily
Don't wait until day 7. Check progress daily to catch issues early.

### Tip 2: Check Both Groups
Verify BOTH control and test groups are collecting data. If only one is active, there might be an integration issue.

### Tip 3: Note Current Hour
The test group will have fewer signals during 22:00-02:00 UTC. This is expected and correct.

### Tip 4: Document Results
When test completes, save the report output. You'll want to reference it later.

### Tip 5: One Test at a Time
Don't start other evolution tests while this one is running. Keep variables isolated.

## 🆘 Support

### If Integration Fails
1. Check syntax: `python main.py`
2. Review INTEGRATION_STEPS.md carefully
3. Restore backup: `cp main.py.backup main.py`
4. Try again with exact code from guide

### If Test Not Collecting Data
1. Verify bot is running: `ps aux | grep main.py`
2. Check logs: `tail -100 bot.log`
3. Look for "Test group" or "Control group" in logs
4. Verify time filter initialized: `grep "Time filter" bot.log`

### If Results Unclear
1. Collect more data (100 trades per group instead of 50)
2. Check for statistical significance (p-value < 0.05)
3. Look at median P&L, not just average
4. Compare win rate AND average P&L together

## 📊 Baseline Context

**Current Performance (444 trades):**
- Win Rate: 58.1%
- Avg P&L: R29.65
- Total P&L: R13,167.25
- Profit Factor: 1.69x

**Goal:** Find improvements that compound to 67.5% win rate, R60/trade

**Timeline:** 6 months of systematic testing

---

**Package Created:** October 11, 2025  
**Status:** ✅ Ready for Integration  
**Integration Time:** 15-20 minutes  
**Data Collection Time:** 5-7 days  
**Total Package:** 6 files, 1,000+ lines of framework code  
