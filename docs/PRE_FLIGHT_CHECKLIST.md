# ✈️ OZZY TRADING BOT - PRE-FLIGHT CHECKLIST

**Version:** 1.0  
**Last Updated:** October 17, 2025  
**Purpose:** Ensure safe operation before starting trading bot

> **CRITICAL:** Complete ALL sections before starting live trading.  
> **Time Required:** 10-15 minutes  
> **Frequency:** Every single time before starting the bot

---

## 🎯 GO/NO-GO DECISION CRITERIA

**❌ NO-GO if ANY item in Section A, B, or C fails**  
**⚠️ FIX REQUIRED if items in Section D or E fail**  
**✅ CLEAR FOR TAKEOFF when all checks pass**

---

## SECTION A: ENVIRONMENT VALIDATION ⚙️

```bash
# A1. Python Version Check
python --version
# ✅ Expected: Python 3.10+ or Python 3.11+

# A2. Virtual Environment Active
echo $VIRTUAL_ENV
# ✅ Expected: /home/rick/ozzy-simple/venv

# A3. Test imports
python -c "import agent.trader; import mcp.trading_server; import intelligence.rolling_window_db"
# ✅ Expected: No output (success)
# ❌ If ModuleNotFoundError or SyntaxError → STOP!
```

**Checklist:**
- [ ] Python 3.10+ installed
- [ ] Virtual environment activated
- [ ] All imports succeed without errors

**If ANY fails:** ❌ STOP - Fix environment first!

---

## SECTION B: CONFIGURATION VERIFICATION 📝

```bash
# B1. Check OpenAI API Key
echo $OPENAI_API_KEY | head -c 20
# ✅ Expected: "sk-proj-..." or "sk-..."

# B2. Test OpenAI API
python -c "from openai import OpenAI; client = OpenAI(); print('API Valid')"
# ✅ Expected: "API Valid"
```

**Checklist:**
- [ ] OpenAI API key set and valid
- [ ] Can call OpenAI API successfully

**If ANY fails:** ❌ STOP - Fix configuration!

---

## SECTION C: PATTERN DATABASE VALIDATION 💾

```bash
# C1. Check database exists
ls -lh data/vector_db/chroma.sqlite3
# ✅ Expected: File exists (>100KB)

# C2. Query pattern count
python -c "from intelligence.rolling_window_db import RollingWindowPatternDB; db = RollingWindowPatternDB(); result = db.query_patterns({'rsi': 50}, limit=1); print(f'Patterns: {result[\"count\"]}')"
# ✅ Expected: "Patterns: 2494" (or >1000)
```

**Checklist:**
- [ ] Database file exists
- [ ] Pattern count >1,000

**If fails:** Run `python intelligence/process_historical.py`

---

## SECTION D: PORTFOLIO & EXECUTION CHECKS 💰

```bash
# D1. Test portfolio initialization
python -c "from agent.portfolio import PaperTradingPortfolio; p = PaperTradingPortfolio(10000); print(f'Capital: R{p.capital:,.2f}')"
# ✅ Expected: "Capital: R10,000.00"

# D2. Test position management
python scripts/quick_validation.py
# ✅ Expected: Completes without crashing
```

**Checklist:**
- [ ] Portfolio initializes correctly
- [ ] Quick validation passes

---

## SECTION E: AI AGENT VALIDATION 🤖

```bash
# E1. Test agent initialization
python -c "from agent.trader import TradingAgent; from mcp.trading_server import TradingMCPServer; from agent.portfolio import PaperTradingPortfolio; p = PaperTradingPortfolio(10000); mcp = TradingMCPServer(portfolio=p); agent = TradingAgent(mcp); print('Agent OK')"
# ✅ Expected: "Agent OK" (warnings acceptable)
# ❌ If SyntaxError → STOP AND FIX!
```

**Checklist:**
- [ ] Agent initializes without SyntaxError
- [ ] No import errors

**If SyntaxError:** ❌ STOP - Fix code first!

---

## ✅ FINAL GO/NO-GO

**Questions before starting:**

1. [ ] Have ALL sections A-E passed?
2. [ ] Do you understand emergency stop procedure? (Ctrl+C or `pkill -f bulletproof_test`)
3. [ ] Have you tested in paper trading for 7+ days? (If live trading)
4. [ ] Do you have time to monitor the bot today?
5. [ ] Are you prepared for potential losses?

**If all YES → CLEARED FOR TAKEOFF! 🚀**

```bash
# Start test
cd scripts && python bulletproof_test.py --duration 21600 --interval 900 --capital 10000

# Monitor
tail -f /tmp/test_output.log
```

---

**Emergency Stop:** Press `Ctrl+C` or run `pkill -f bulletproof_test.py`

**See docs/TROUBLESHOOTING.md for common issues**
