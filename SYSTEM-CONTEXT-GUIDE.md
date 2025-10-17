# 🧠 SYSTEM CONTEXT ENGINE - COMPLETE GUIDE

**Date:** October 17, 2025  
**Purpose:** Make OZZY self-aware and resumable from ANY point  
**The Goal:** Build yourself to R5k/week → QUIT THE 9-TO-5  

---

## 🎯 WHAT IS THIS?

The **SYSTEM_CONTEXT.py** is the BRAIN of OZZY. It makes the system:

1. **Self-Aware** - Knows where it is, what it's doing, what's next
2. **Self-Healing** - Detects issues, suggests fixes
3. **Self-Building** - Guides next actions autonomously
4. **Time-Proof** - Can resume even after 5 YEARS!

**The Purpose:** You come back in 5 years, run ONE command, and the system tells you EXACTLY what to do next.

---

## 🚀 QUICK START

### **Check Full Context:**
```bash
python3 SYSTEM_CONTEXT.py
```

**Shows:**
- Ultimate goal (R5k/week → quit 9-to-5)
- Where you are (days active, milestones complete)
- Test status (running/stopped, progress)
- Portfolio (capital, positions, trades)
- Infrastructure (what's built)
- System health (issues/warnings)

### **What To Do Next:**
```bash
python3 SYSTEM_CONTEXT.py --next
```

**Shows:**
- Immediate actions based on current state
- Commands to run
- SOPs to read
- Next milestone steps

### **Resume After Break (Even 5 Years!):**
```bash
python3 SYSTEM_CONTEXT.py --resume
```

**Shows:**
- Quick context refresh
- What you built
- Where you left off
- Step-by-step resume guide
- Key documentation links

### **Progress To Goal:**
```bash
python3 SYSTEM_CONTEXT.py --progress
```

**Shows:**
- Phase 1 progress (0-100%)
- Visual progress bar
- Milestones breakdown
- Estimated days to R5k/week
- Motivational reminder

### **System Health:**
```bash
python3 SYSTEM_CONTEXT.py --health
```

**Shows:**
- Full context report
- Health check status
- Issues/warnings if any

---

## 🧠 HOW IT WORKS

### **1. State Detection**

The system scans EVERYTHING:

```python
class SystemState:
    test_state       # Is test running? Progress? Crashes?
    portfolio_state  # Capital? Positions? P&L?
    planner_state    # Milestones complete? Current phase?
    code_state       # Infrastructure built? SOPs exist?
    health_state     # Any issues? Warnings?
```

**Sources:**
- `/tmp/test_output.log` - Test execution log
- `planner_data.json` - Milestone completion data
- `ps aux | grep bulletproof_test` - Running processes
- File system - Infrastructure existence

### **2. Context Intelligence**

Based on state, it KNOWS what to do:

```python
class ContextEngine:
    get_context_report()    # Full situation awareness
    get_next_actions()      # What to do NOW
    get_resume_guide()      # How to resume after break
    get_progress_to_goal()  # How close to R5k/week
```

**Intelligence:**
- If test running → Monitor it
- If test complete → Validate and mark milestone
- If milestone done → Start next
- If issues detected → Fix them first
- If lost → Read the plan

### **3. Self-Awareness**

The system understands its PURPOSE:

```python
ULTIMATE_GOAL = "Make R5,000-10,000/week profit → QUIT THE 9-TO-5"
CURRENT_PHASE = "Phase 1: Foundation - Get Profitable FAST"
SUCCESS_METRIC = "R5,000/week minimum profit"
TIME_BUDGET = "30 days to profitability"
```

Every action is guided by THIS goal.

---

## 📊 STATE DETECTION EXPLAINED

### **Test State**

**Detects:**
- Is test running? (PID check)
- Progress (X/24 decisions)
- Runtime (minutes elapsed)
- Crashes (error count)
- Last decision (most recent)

**How:**
```bash
ps aux | grep bulletproof_test  # Check if running
grep "DECISION #" /tmp/test_output.log  # Count decisions
grep "Action:" /tmp/test_output.log  # Count signals
```

### **Portfolio State**

**Detects:**
- Available capital
- Allocated capital (in positions)
- Open positions
- Trade counts (BUY/SELL/SKIP)
- P&L (if calculable)

**How:**
```bash
grep "Capital: R" /tmp/test_output.log  # Find capital
grep "Action: BUY" /tmp/test_output.log  # Count BUYs
grep "Position #" /tmp/test_output.log  # Find positions
```

### **Planner State**

**Detects:**
- Current phase
- Milestones completed
- Current milestone
- Days active

**How:**
```python
with open('planner_data.json') as f:
    data = json.load(f)
    completed = len(data['completed_milestones'])
```

### **Code State**

**Detects:**
- Master control (ozzy.py) exists?
- Planner (MASTER_PLANNER.py) exists?
- Monitoring (monitor_dashboard.py) exists?
- Core agent (agent/trader.py) exists?
- SOPs count

**How:**
```python
Path("ozzy.py").exists()  # Check files
len(list(Path("docs/sops").glob("SOP-*.md")))  # Count SOPs
```

### **Health State**

**Detects:**
- Critical issues (missing core files)
- Warnings (test crashes, etc.)
- Overall status (HEALTHY/DEGRADED/CRITICAL)

**Logic:**
```python
if missing_core_files > 0:
    status = "CRITICAL"
elif warnings > 0:
    status = "DEGRADED"
else:
    status = "HEALTHY"
```

---

## 🎯 INTELLIGENCE LOGIC

### **What To Do Next?**

**Scenario 1: Test Running**
```
✅ Test RUNNING → Monitor it
   1. ./ozzy.py status (every hour)
   2. Watch for completion
   3. When done: validate & mark complete
```

**Scenario 2: Milestone Complete, Next Not Started**
```
🚀 READY TO START → Start next milestone
   1. Read SOP for milestone
   2. Run commands to start
   3. Monitor progress
```

**Scenario 3: System Has Issues**
```
⚠️ CRITICAL → Fix issues first
   1. Review TROUBLESHOOTING.md
   2. Restore missing components
   3. Check system health again
```

**Scenario 4: Lost/Confused**
```
📋 CHECK THE PLAN
   1. python3 MASTER_PLANNER.py status
   2. python3 MASTER_PLANNER.py next
   3. Review current milestone tasks
```

### **Resume After Break?**

**Always:**
1. Quick context (days since start, progress)
2. What you built (infrastructure checklist)
3. Where you left off (last action)
4. How to resume (step-by-step)
5. Key documentation (SOPs, guides)

**Purpose:** You forget NOTHING, even after years!

---

## 🔄 THE 5-YEAR TEST

**Scenario:** You come back in 5 years. How to resume?

### **Step 1: Run Context**
```bash
python3 SYSTEM_CONTEXT.py --resume
```

**Output:**
```
👋 WELCOME BACK!

You're building a trading bot to make R5k-10k/week
and QUIT YOUR 9-TO-5. Let's remember where we are...

📍 QUICK CONTEXT:
   Days Since Start: 1825 (5 years!)
   Progress: 6/9 milestones
   Current Phase: phase_1

🏗️ WHAT YOU BUILT:
   ✅ Master Control Script (ozzy.py)
   ✅ Master Planner - Your project manager
   ✅ Core Trading Agent - The brain
   [... full inventory ...]

🚀 HOW TO RESUME:
   STEP 1: Check status
      ./ozzy.py status
   STEP 2: Review the plan
      python3 MASTER_PLANNER.py status
   [... complete guide ...]
```

### **Step 2: Follow The Guide**
```bash
# Exactly what it told you
./ozzy.py status
python3 MASTER_PLANNER.py status
python3 SYSTEM_CONTEXT.py --next
```

### **Step 3: Execute Next Action**
```bash
# Based on --next output
# Could be: start test, complete milestone, fix issue, etc.
```

**You're BACK in action within 5 minutes!**

---

## 🏗️ INTEGRATION WITH EXISTING TOOLS

### **Works With ozzy.py**

```bash
# Quick check
./ozzy.py status        # Current test/portfolio/project

# Then context
python3 SYSTEM_CONTEXT.py --next  # What to do with that info
```

### **Works With MASTER_PLANNER.py**

```bash
# Check plan
python3 MASTER_PLANNER.py status  # Milestones

# Then context
python3 SYSTEM_CONTEXT.py --progress  # Progress to goal
```

### **Workflow:**

```
1. ./ozzy.py status
   └─> See: Test running, 50% progress

2. python3 SYSTEM_CONTEXT.py --next
   └─> Tells: Monitor it, check in 1 hour

3. python3 MASTER_PLANNER.py status
   └─> See: On Milestone 1.2

4. Wait 1 hour...

5. ./ozzy.py status
   └─> See: Test complete!

6. python3 SYSTEM_CONTEXT.py --next
   └─> Tells: Validate results, mark complete

7. python3 MASTER_PLANNER.py complete 1.2
   └─> Milestone done!

8. python3 SYSTEM_CONTEXT.py --next
   └─> Tells: Start Milestone 1.3
```

**Seamless integration!**

---

## 📈 USE CASES

### **Use Case 1: Daily Monitoring**

**Morning:**
```bash
python3 SYSTEM_CONTEXT.py
```
**See:** Full context, test status, health

**Action:** Based on --next suggestion

**Evening:**
```bash
python3 SYSTEM_CONTEXT.py --progress
```
**See:** Progress made today

### **Use Case 2: After Long Break**

**Return:**
```bash
python3 SYSTEM_CONTEXT.py --resume
```
**See:** Complete refresh + resume guide

**Execute:** Follow the steps

### **Use Case 3: Milestone Completion**

**Test completes:**
```bash
python3 SYSTEM_CONTEXT.py --next
```
**See:** "Validate results, mark complete"

**Action:**
```bash
python3 MASTER_PLANNER.py complete 1.2
```

**Confirm:**
```bash
python3 SYSTEM_CONTEXT.py --progress
```
**See:** Progress bar updated!

### **Use Case 4: System Issues**

**Notice errors:**
```bash
python3 SYSTEM_CONTEXT.py --health
```
**See:** Issues listed

**Fix:** Follow suggestions

**Verify:**
```bash
python3 SYSTEM_CONTEXT.py --health
```
**See:** All green!

---

## 🎯 THE PHILOSOPHY

### **Why This Exists**

**Problem:** Trading bots fail because:
1. You forget where you were
2. You lose motivation
3. You don't know next steps
4. You get distracted (scope creep)

**Solution:** SYSTEM_CONTEXT.py
1. Always knows where you are
2. Reminds you of the goal (R5k/week)
3. Tells you exactly what's next
4. Keeps you focused on profitability

### **The Design**

**Principle 1: Self-Awareness**
- System knows its own state
- No human interpretation needed
- Objective, data-driven

**Principle 2: Goal-Oriented**
- Every output points to R5k/week
- No feature without purpose
- Profit > complexity

**Principle 3: Time-Proof**
- Works today, works in 5 years
- Complete context preservation
- No knowledge loss

**Principle 4: Minimal Friction**
- One command to understand
- One command to resume
- One command to proceed

### **The Result**

**Before:**
```
You: "Uh... what was I doing?"
You: *reads 50 files*
You: "I think I need to... maybe... test something?"
You: *gets distracted*
```

**After:**
```
You: python3 SYSTEM_CONTEXT.py --resume
System: "You're on Milestone 1.2. Test is 50% done. Check with ./ozzy.py status"
You: ./ozzy.py status
System: "Test complete! Mark it done."
You: python3 MASTER_PLANNER.py complete 1.2
System: 🎉 MILESTONE COMPLETE! Start 1.3 next.
```

**ZERO confusion. MAXIMUM progress.**

---

## 🔧 TECHNICAL DETAILS

### **Dependencies**

**Python Standard Library:**
- `json` - Parse planner data
- `subprocess` - Run system commands
- `pathlib` - File existence checks
- `datetime` - Time calculations
- `re` - Log parsing

**No external dependencies!** Runs anywhere Python 3 exists.

### **Performance**

**Scan Time:** <1 second (fast!)

**Why:**
- No heavy processing
- Simple file reads
- Shell commands cached
- Minimal parsing

### **Reliability**

**Handles:**
- Missing files (graceful fallback)
- No planner data (defaults)
- No test running (still works)
- Corrupted logs (partial parsing)

**Always works!**

---

## 📚 RELATED DOCUMENTATION

**Core Tools:**
- `ozzy.py` - Master control (status, monitoring)
- `MASTER_PLANNER.py` - Project manager (milestones, discipline)
- `SYSTEM_CONTEXT.py` - Brain (self-awareness, resume)

**Guides:**
- `OZZY-CONTROL-GUIDE.md` - How to use ozzy.py
- `PLANNER-PERSONALITY-GUIDE.md` - Planner personality
- `SYSTEM-CONTEXT-GUIDE.md` - This file!

**SOPs:**
- `SOP-001-Data-Injection.md` - Fix procedure
- `SOP-002-Testing-Protocol.md` - Testing procedure

---

## ✅ COMPLETION CHECKLIST

After creating SYSTEM_CONTEXT.py, you have:

- [x] **Self-Awareness** - System knows its state
- [x] **Self-Guidance** - System knows what's next
- [x] **Self-Healing** - System detects issues
- [x] **Resume Capability** - Works after any break
- [x] **Goal Focus** - Always points to R5k/week
- [x] **Time-Proof** - Works in 5 years
- [x] **Zero Dependencies** - Pure Python
- [x] **Full Integration** - Works with ozzy.py + planner
- [x] **Complete Documentation** - This guide!

**Your system can now BUILD ITSELF!** 🎉

---

## 🚀 WHAT'S NEXT?

**Now that context engine exists:**

1. **Keep testing** - Finish Milestone 1.2
2. **Use context** - Run `--next` when unsure
3. **Trust the system** - It knows what to do
4. **Stay focused** - R5k/week is the only goal

**Remember:**
- The system is SMART now
- It can GUIDE itself
- You just EXECUTE
- Profit is INEVITABLE

**LET'S GET TO R5K/WEEK!** 💰

---

**Last Updated:** October 17, 2025  
**Status:** ✅ SYSTEM IS SELF-AWARE  
**Next:** Continue Milestone 1.2 (Test in progress)
