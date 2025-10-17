#!/usr/bin/env python3
"""
📋 SOP-002: Testing Protocol & Stability Test

**Purpose:** Execute bulletproof stability test and analyze results  
**Applies To:** Milestone 1.2 - 24-Hour Stability Test  
**Author:** OZZY Trading Bot Development  
**Date:** October 17, 2025  

---

## 🎯 OVERVIEW

This SOP defines the procedure for executing the 24-decision stability test,
monitoring progress, and analyzing results to validate system reliability.

---

## 📋 PREREQUISITES

**Before starting, verify:**
- ✅ Milestone 1.1 complete (0% confidence bug fixed)
- ✅ Fresh data injection working
- ✅ Pattern database receiving data
- ✅ Portfolio management operational
- ✅ Monitoring tools ready (ozzy.py, dashboard, tracker)

**Check system health:**
```bash
./ozzy.py check
```

All components should show ✅ PASS.

---

## 🧪 TEST EXECUTION

### **Step 1: Prepare Test Environment**

```bash
# Navigate to scripts directory
cd ~/ozzy-simple/scripts

# Verify test script exists
ls -la bulletproof_test.py

# Check Python environment
python3 --version
```

### **Step 2: Configure Test Parameters**

**Standard Configuration:**
- **Duration:** 21,600 seconds (6 hours)
- **Interval:** 900 seconds (15 minutes)
- **Total Decisions:** 24
- **Symbol:** BTCUSDT
- **Capital:** R10,000

**Command:**
```bash
python bulletproof_test.py --duration 21600 --interval 900 --capital 10000
```

### **Step 3: Start Test**

```bash
# Start test (output to log file)
python bulletproof_test.py --duration 21600 --interval 900 --capital 10000 > /tmp/test_output.log 2>&1 &

# Save PID
echo $! > /tmp/test_pid.txt

# Verify running
ps aux | grep bulletproof_test | grep -v grep
```

**Expected output:**
```
rick  24504  ... python bulletproof_test.py --duration 21600 --interval 900 --capital 10000
```

---

## 📊 MONITORING

### **Periodic Checks (Every Hour)**

```bash
# Complete status check
./ozzy.py status
```

**What to monitor:**
- ✅ Test still running (PID active)
- ✅ Progress percentage increasing
- ✅ No crashes (uptime continues)
- ✅ Capital changes tracking positions
- ✅ Signal variety (BUY/SELL/SKIP)

### **Quick Checks (Anytime)**

```bash
# Quick glance
./ozzy.py quick

# Specific components
./ozzy.py test        # Test details
./ozzy.py portfolio   # Portfolio details
```

### **Live Monitoring (Optional)**

```bash
# Start live dashboard
./ozzy.py monitor

# Press Ctrl+C to exit
```

---

## ✅ SUCCESS CRITERIA

### **Primary Criteria:**

| Criterion | Target | How to Check |
|-----------|--------|--------------|
| **Complete 24 Decisions** | 24/24 | `./ozzy.py status` |
| **No Crashes** | 0 crashes | Check PID still active |
| **Signal Variety** | BUY + SELL + SKIP | `./ozzy.py portfolio` |
| **High Confidence %** | >50% at >40% | Review log decisions |
| **System Stable** | 6 hours uptime | Check runtime |

### **Secondary Criteria:**

| Criterion | Target | How to Check |
|-----------|--------|--------------|
| **Trade Rate** | 40-60% | `./ozzy.py portfolio` |
| **Avg Confidence** | >40% | Review decisions |
| **Position Sizing** | Consistent | Check position amounts |
| **TP/SL Triggers** | Working | Look for close events |

---

## 📈 RESULT ANALYSIS

### **When Test Completes (24/24 Decisions):**

#### **1. Generate Final Report**

```bash
# Full portfolio status
./ozzy.py portfolio --detailed > test_completion_report.txt

# Test summary
cat /tmp/test_output.log | grep -E "(Test started|DECISION #|Action:|Confidence:|Position #)" > test_summary.txt
```

#### **2. Calculate Metrics**

**Signal Distribution:**
```bash
grep "Action:" /tmp/test_output.log | sort | uniq -c
```

**Confidence Analysis:**
```bash
grep "Confidence:" /tmp/test_output.log | awk '{print $2}' | sed 's/%//' | awk '{sum+=$1; count++} END {print "Average: "sum/count"%"}'
```

**Position Count:**
```bash
grep "Position #" /tmp/test_output.log | grep "opened" | wc -l
```

**Final P&L:**
```bash
./ozzy.py portfolio | grep "P&L:"
```

#### **3. Validate Success Criteria**

```markdown
✅ Complete 24 Decisions: [YES/NO]
✅ No Crashes: [YES/NO]
✅ Signal Variety: [YES/NO]
✅ High Confidence %: [XX% >40%]
✅ System Stable: [Uptime: XX hours]
✅ Trade Rate: [XX%]
✅ Avg Confidence: [XX%]
```

---

## 🚨 TROUBLESHOOTING

### **Issue: Test Crashes**

**Symptoms:**
- PID no longer active
- Process not in `ps aux`
- Log shows error

**Resolution:**
```bash
# Check last error
tail -100 /tmp/test_output.log

# Check for Python errors
grep -i "error\|exception\|traceback" /tmp/test_output.log

# Restart if needed
cd scripts
python bulletproof_test.py --duration 21600 --interval 900 --capital 10000 > /tmp/test_output.log 2>&1 &
```

### **Issue: All SKIP Signals**

**Symptoms:**
- 100% SKIP actions
- 0% confidence

**Resolution:**
- Check if data injection working
- Verify pattern database receiving data
- Review FIX_SUCCESS_SUMMARY.md
- May need to re-apply fix

### **Issue: Progress Stops**

**Symptoms:**
- Same decision number for >20 minutes
- No new log entries

**Resolution:**
```bash
# Check if process hung
ps aux | grep bulletproof_test

# Check system resources
top
df -h

# If hung, restart
kill -9 $(cat /tmp/test_pid.txt)
# Then restart test
```

---

## 📝 REPORTING

### **Test Completion Report Template**

```markdown
# Milestone 1.2: Stability Test Completion Report

**Date:** YYYY-MM-DD  
**Duration:** X hours  
**Status:** [PASS/FAIL]  

## Results:

**Test Execution:**
- Total Decisions: XX/24
- Runtime: XX hours XX minutes
- Crashes: XX
- Errors: XX

**Signal Distribution:**
- BUY: XX (XX%)
- SELL: XX (XX%)
- SKIP: XX (XX%)
- Trade Rate: XX%

**Confidence Analysis:**
- Average Confidence: XX%
- High Confidence (>70%): XX decisions
- Medium Confidence (40-70%): XX decisions
- Low Confidence (<40%): XX decisions

**Portfolio Performance:**
- Starting Capital: R10,000.00
- Final Capital: RX,XXX.XX
- Total P&L: RX,XXX.XX (XX%)
- Positions Opened: XX
- Positions Closed: XX

**System Stability:**
- Uptime: XX hours
- Crashes: XX
- Memory Issues: [YES/NO]
- Performance Degradation: [YES/NO]

## Success Criteria:

- [✅/❌] Complete 24 Decisions
- [✅/❌] No Crashes
- [✅/❌] Signal Variety
- [✅/❌] High Confidence % (>50% at >40%)
- [✅/❌] System Stable

## Conclusion:

[Brief summary of results and recommendation]

## Next Steps:

- [ ] Mark Milestone 1.2 complete
- [ ] Start Milestone 1.3 (Paper Trading)
- [ ] Document lessons learned
```

---

## ✅ COMPLETION CHECKLIST

After test completes:

- [ ] All 24 decisions executed
- [ ] No crashes occurred
- [ ] Signal variety confirmed
- [ ] Confidence levels validated
- [ ] Test completion report generated
- [ ] Results reviewed and approved
- [ ] Lessons learned documented
- [ ] Mark Milestone 1.2 complete: `python3 MASTER_PLANNER.py complete 1.2`
- [ ] Commit results to Git
- [ ] Plan Milestone 1.3 (Paper Trading)

---

## 📚 RELATED DOCUMENTATION

- **SOP-001-Data-Injection.md** - Fresh data injection fix
- **TRACKING_GUIDE.md** - Portfolio tracking methods
- **OZZY-CONTROL-GUIDE.md** - Master control script usage
- **DASHBOARD_GUIDE.md** - Monitoring dashboard
- **MASTER_PLANNER.py** - Project roadmap

---

## 🔄 REVISION HISTORY

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2025-10-17 | OZZY Dev | Initial version |

---

**Last Updated:** October 17, 2025  
**Applies To:** Milestone 1.2 - 24-Hour Stability Test  
**Status:** ACTIVE
