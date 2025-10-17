# 🔧 COMPREHENSIVE FIX GUIDE - APPLY BEFORE NEXT TEST

## Critical Bugs Found in 7.5 Hour Test

### Test Results Summary:
- ✅ 328 positions opened in 7.5 hours
- ❌ 16.4x over-leveraged ($82,000 on $5,000 capital)
- ❌ 44 positions per hour (way too aggressive)
- ❌ 0 positions closed (TP/SL never triggered)
- ❌ P&L display bug ($0.00 shown per position)

---

## Fix #1: Add Capital Check (CRITICAL) 🚨

**File:** `scripts/test_live_stream.py`
**Location:** Line ~120 (in decision loop, before opening position)

**Find this code:**
```python
# Execute trade if action is BUY
if action == "BUY" and current_price > 0:
    print(f"   → Attempting to open position...")
    position_size = min(250.0, _safe_float(decision.get("position_size", 250.0), 250.0))
    
    # Open the position with current price (not null entry price)
    try:
        position = portfolio.open_position(
```

**Replace with:**
```python
# Execute trade if action is BUY
if action == "BUY" and current_price > 0:
    print(f"   → Attempting to open position...")
    position_size = min(250.0, _safe_float(decision.get("position_size", 250.0), 250.0))
    
    # 🔧 FIX #1: Check capital before opening position
    if portfolio.capital < position_size:
        print(f"   ⚠️ INSUFFICIENT CAPITAL: Need ${position_size:.2f}, have ${portfolio.capital:.2f}")
        print(f"   → Skipping trade (no capital available)")
    else:
        # Open the position with current price (not null entry price)
        try:
            position = portfolio.open_position(
```

**Impact:** Prevents over-leverage, respects capital limits

---

## Fix #2: Add Max Position Limit (CRITICAL) 🚨

**File:** `scripts/test_live_stream.py`
**Location:** Same place as Fix #1 (after capital check)

**Add this check:**
```python
# Execute trade if action is BUY
if action == "BUY" and current_price > 0:
    print(f"   → Attempting to open position...")
    position_size = min(250.0, _safe_float(decision.get("position_size", 250.0), 250.0))
    
    # 🔧 FIX #1: Check capital
    if portfolio.capital < position_size:
        print(f"   ⚠️ INSUFFICIENT CAPITAL")
        print(f"   → Skipping trade")
    # 🔧 FIX #2: Check max positions
    elif len([p for p in portfolio.positions if p.get("status") == "OPEN"]) >= 20:
        print(f"   ⚠️ MAX POSITIONS REACHED: 20/20")
        print(f"   → Skipping trade (wait for positions to close)")
    else:
        # Open the position
        try:
            position = portfolio.open_position(
```

**Impact:** Limits to 20 concurrent positions max (20 × $250 = $5,000)

---

## Fix #3: Add Trading Cooldown (RECOMMENDED) ⏰

**File:** `scripts/test_live_stream.py`
**Location:** Top of decision loop function (around line 71)

**Find this:**
```python
async def _decision_loop(
    agent: TradingAgent,
    mcp_server: TradingMCPServer,
    portfolio: PaperTradingPortfolio,
    symbol: str,
    interval_seconds: int,
    stop_event: asyncio.Event,
    results: List[DecisionRecord],
    slack_notifier: Optional['SlackNotifier'] = None,
) -> None:
    counter = 0
    last_summary_time = time.time()
    SUMMARY_INTERVAL = 300  # Send positions summary every 5 minutes
```

**Replace with:**
```python
async def _decision_loop(
    agent: TradingAgent,
    mcp_server: TradingMCPServer,
    portfolio: PaperTradingPortfolio,
    symbol: str,
    interval_seconds: int,
    stop_event: asyncio.Event,
    results: List[DecisionRecord],
    slack_notifier: Optional['SlackNotifier'] = None,
) -> None:
    counter = 0
    last_summary_time = time.time()
    last_trade_time = 0  # 🔧 FIX #3: Track last trade time
    SUMMARY_INTERVAL = 300  # Send positions summary every 5 minutes
    COOLDOWN_SECONDS = 120  # 🔧 FIX #3: 2 minute cooldown between trades
```

**Then add cooldown check before opening position:**
```python
# Execute trade if action is BUY
if action == "BUY" and current_price > 0:
    print(f"   → Attempting to open position...")
    position_size = min(250.0, _safe_float(decision.get("position_size", 250.0), 250.0))
    
    # 🔧 FIX #3: Check cooldown
    time_since_last_trade = time.time() - last_trade_time
    if time_since_last_trade < COOLDOWN_SECONDS:
        remaining = COOLDOWN_SECONDS - time_since_last_trade
        print(f"   ⏱️ COOLDOWN: {remaining:.0f}s remaining until next trade")
        print(f"   → Skipping trade (preventing spam)")
    # 🔧 FIX #1: Check capital
    elif portfolio.capital < position_size:
        print(f"   ⚠️ INSUFFICIENT CAPITAL")
    # 🔧 FIX #2: Check max positions
    elif len([p for p in portfolio.positions if p.get("status") == "OPEN"]) >= 20:
        print(f"   ⚠️ MAX POSITIONS REACHED")
    else:
        # Open the position
        try:
            position = portfolio.open_position(
                symbol=symbol,
                side="LONG",
                entry_price=current_price,
                size=position_size,
                confidence=confidence,
                reason=reason
            )
            
            last_trade_time = time.time()  # 🔧 Update last trade time
            
            print(f"   → Position opened: {symbol} @ ${current_price:.2f}")
```

**Impact:** Reduces from 44 positions/hour to max 30 positions/hour

---

## Fix #4: Verify TP/SL Logic (CHECK) ✅

The TP/SL logic looks correct, but 0 closures is suspicious. Let's verify it's running:

**File:** `scripts/test_live_stream.py`
**Location:** Around line 220 (TP/SL checking code)

**Add debug output:**
```python
# Check for take profit / stop loss on existing positions
else:
    checked_positions = 0  # 🔧 Debug counter
    for pos in portfolio.positions[:]:
        if pos["symbol"] == symbol and current_price > 0:
            checked_positions += 1
            pnl_pct = pos["pnl_pct"]
            # Take profit at +3.0%
            if pnl_pct >= 3.0:
                print(f"   🎯 TAKE PROFIT TRIGGERED: {pnl_pct:.2f}%")
                closed_trade = portfolio.close_position(...)
```

**Impact:** Confirms TP/SL checking is running

---

## Combined Fix - All in One Place

**File:** `scripts/test_live_stream.py`

**Complete fixed BUY logic:**
```python
# Execute trade if action is "BUY"
if action == "BUY" and current_price > 0:
    print(f"   → BUY signal received")
    position_size = min(250.0, _safe_float(decision.get("position_size", 250.0), 250.0))
    
    # Check all conditions before opening
    time_since_last_trade = time.time() - last_trade_time
    open_positions = [p for p in portfolio.positions if p.get("status") == "OPEN"]
    
    # List of blocking conditions
    if time_since_last_trade < COOLDOWN_SECONDS:
        remaining = COOLDOWN_SECONDS - time_since_last_trade
        print(f"   ⏱️ COOLDOWN: {remaining:.0f}s remaining")
        print(f"   → Skipping trade")
    elif portfolio.capital < position_size:
        print(f"   ⚠️ INSUFFICIENT CAPITAL: Need ${position_size:.2f}, have ${portfolio.capital:.2f}")
        print(f"   → Skipping trade")
    elif len(open_positions) >= 20:
        print(f"   ⚠️ MAX POSITIONS: {len(open_positions)}/20")
        print(f"   → Skipping trade")
    else:
        # All checks passed - open position
        try:
            position = portfolio.open_position(
                symbol=symbol,
                side="LONG",
                entry_price=current_price,
                size=position_size,
                confidence=confidence,
                reason=reason
            )
            
            # Update last trade time
            last_trade_time = time.time()
            
            print(f"   ✅ Position opened: #{position['id']} @ ${current_price:.2f}")
            
            # Send Slack notification
            if slack_notifier:
                slack_notifier.notify_position_opened(...)
                
        except Exception as e:
            print(f"   ❌ Error opening position: {e}")
```

---

## Testing the Fixes

### Step 1: Apply All Fixes
Edit `scripts/test_live_stream.py` with all changes above

### Step 2: Clean Old Data
```bash
rm ~/ozzy-simple/logs/portfolio_state.json
rm ~/ozzy-simple/logs/decisions.json
```

### Step 3: Run New Test
```bash
cd ~/ozzy-simple
source venv/bin/activate

nohup python scripts/test_live_stream.py \
    --symbol BTCUSDT \
    --duration 43200 \
    --decision-interval 60 \
    > logs/test_output.log 2>&1 &

# Get PID
echo $! > logs/bot.pid
```

### Step 4: Monitor
```bash
# Watch logs
tail -f logs/test_output.log

# Check process
ps aux | grep test_live_stream

# Check Slack notifications
```

### Step 5: Verify Fixes Working
After 30 minutes, check:
```bash
cat ~/ozzy-simple/logs/portfolio_state.json | python3 -c "
import json, sys
data = json.load(sys.stdin)
print(f'Positions: {len(data.get(\"positions\", []))}')
print(f'Capital: \${data.get(\"capital\", 0):.2f}')
print(f'Should be ≤20 positions and capital ≥\$0')
"
```

**Expected Results:**
- ✅ Max 20 positions open at any time
- ✅ Capital stays ≥ $0 (no over-leverage)
- ✅ ~15-30 positions opened per hour (with 2min cooldown)
- ✅ Slack updates showing progress
- ✅ Positions close when hitting TP/SL

---

## Success Criteria for Next Test

After 12 hours:
- ✅ 0-20 positions open (never exceeded)
- ✅ Capital between $0-$5,000 (no over-leverage)
- ✅ Some positions closed (TP or SL triggered)
- ✅ Can calculate win rate (closed trades exist)
- ✅ Reasonable position count (~200-360 total, not 528)

Then we can honestly assess if the strategy is profitable!

---

## Priority Order

1. **MUST FIX (Before any test):**
   - Capital check
   - Max position limit

2. **SHOULD FIX (Recommended):**
   - Trading cooldown

3. **NICE TO HAVE:**
   - Debug logging for TP/SL
   - Visual Slack updates (already done!)

Apply fixes in order, test after each if unsure!

---

*Remember: Better to find bugs in paper trading than lose real money!* 💰✨
