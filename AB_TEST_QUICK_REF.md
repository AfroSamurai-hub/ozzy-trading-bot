# 🎯 A/B TEST QUICK REFERENCE

## ✅ INTEGRATION STATUS: COMPLETE

**Date Started:** October 11, 2025, 09:53 UTC  
**Bot PID:** 6678  
**Test Name:** time_filter_night  
**Status:** LIVE - Collecting Data  

---

## 📊 TEST CONFIGURATION

| Setting | Value |
|---------|-------|
| Control Group | Trades 24/7 (normal) |
| Test Group | Avoids 22:00-02:00 UTC |
| Assignment | Random 50/50 split |
| Target | 50 trades per group |
| Total Needed | 100 trades |
| Expected Time | 4-5 days |

---

## 🚀 DAILY COMMANDS

### Quick Status Check
```bash
./check_test_status.sh
```

### Full Status Report
```bash
cd ~/ozzy-simple
./venv/bin/python scripts/test_time_filter.py --status
```

### Watch Live Activity
```bash
tail -f ~/ozzy-simple/bot.log | grep -E "A/B Test|Test group"
```

### Verify Bot Running
```bash
ps aux | grep main.py
```

---

## 📅 EXPECTED TIMELINE

| Day | Date | Expected Progress |
|-----|------|------------------|
| 1 | Oct 11 | Control: 8/50, Test: 8/50 (16%) |
| 2 | Oct 12 | Control: 20/50, Test: 20/50 (40%) |
| 3 | Oct 13 | Control: 35/50, Test: 35/50 (70%) |
| 4-5 | Oct 14-15 | **COMPLETE!** Both groups 50/50 ✅ |

---

## 🎯 FINAL REPORT (Day 5)

When test completes:
```bash
cd ~/ozzy-simple
./venv/bin/python scripts/test_time_filter.py --report
```

### Decision Criteria

**Apply Filter (Test Wins) if:**
- Win rate improves by +2% or more
- OR Avg P&L improves by +R5 or more

**Keep 24/7 (Test Loses) if:**
- Win rate decreases by -2% or more  
- OR Avg P&L decreases by -R5 or more

**No Change (Inconclusive) if:**
- Changes within ±2% win rate AND ±R5 P&L

---

## 🔧 TROUBLESHOOTING

### Bot Not Running?
```bash
cd ~/ozzy-simple
nohup ./venv/bin/python main.py > bot.log 2>&1 &
echo $! > bot.pid
```

### Check for Errors
```bash
tail -100 ~/ozzy-simple/bot.log | grep -i error
```

### Only One Group Has Trades?
**This is NORMAL if:**
- Current time is 22:00-02:00 UTC (test group filtered)
- Check time: `date -u`

**This is a PROBLEM if:**
- Time is outside 22:00-02:00 UTC
- AND control has 20+ trades but test has 0
- Solution: Check logs, restart bot

---

## 📚 DOCUMENTATION FILES

| File | Purpose |
|------|---------|
| `AB_TEST_INTEGRATION_COMPLETE.md` | Complete guide with examples |
| `TIME_FILTER_COMPLETE.md` | Package overview |
| `INTEGRATION_STEPS.md` | Step-by-step integration |
| `STRATEGY_EVOLUTION_PLAN.md` | 6-month roadmap |
| `check_test_status.sh` | Quick status checker |

---

## 🎓 KEY REMINDERS

- ✅ Bot is running - don't restart unless necessary
- ✅ Test needs 4-5 days - be patient!
- ✅ Check progress once daily
- ✅ Don't change parameters while test runs
- ✅ This is Test 1 of your evolution plan

---

## 🏆 BASELINE TO BEAT

**Current Performance (444 trades):**
- Win Rate: 58.1%
- Avg P&L: R29.65
- Total P&L: R13,167.25

**Goal After Test:**
- If test wins: 60%+ win rate, R35+ avg P&L
- Ultimate goal: 67.5% win rate, R60 avg P&L (6 months)

---

## 💡 WHAT'S HAPPENING

### Every Signal Generated:

1. Bot generates LONG/SHORT/HOLD signal
2. **Randomly assigns** to Control or Test (50/50)
3. **Control group**: Signal passes through unchanged (trades 24/7)
4. **Test group**: 
   - If 22:00-02:00 UTC: Signal converted to HOLD (skipped)
   - Otherwise: Signal passes through unchanged
5. Trade executed and tagged in database
6. Log shows: "📊 A/B Test: Assigned to CONTROL/TEST group"

### In the Database:

All trades tagged with:
- Control: `TEST_time_filter_night_control_rsi_oversold`
- Test: `TEST_time_filter_night_test_ema_crossover`

This allows the analysis script to:
- Count trades per group
- Calculate win rate per group
- Compare performance
- Determine statistical significance

---

## 🎯 NEXT STEPS

### Daily (Next 5 Days):
- [ ] Check progress: `./check_test_status.sh`
- [ ] Verify bot still running
- [ ] Check for errors in logs

### When Complete (Day 5):
- [ ] Generate final report
- [ ] Review results
- [ ] Make decision: apply or skip filter
- [ ] Document outcome
- [ ] Plan Test 2 (confidence threshold)

---

**Test Started:** October 11, 2025, 09:53 UTC  
**Expected Completion:** October 15-16, 2025  
**Status:** 🟢 ACTIVE - Data Collection In Progress  

🚀 **Let the data collection begin!**
