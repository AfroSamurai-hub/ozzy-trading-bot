# RISK MANAGEMENT RULES

## ⚠️ Iron Laws (NEVER Violate These)

These rules are non-negotiable. Violating them is how accounts blow up.

---

## 1️⃣ POSITION SIZING

### Base Rule: 2% Maximum Risk Per Trade
```python
# Calculate position size
account_balance = 10000
risk_per_trade = account_balance * 0.02  # $200
entry_price = 42000
stop_loss = 41160  # 2% below entry
risk_per_coin = entry_price - stop_loss  # $840

position_size = risk_per_trade / risk_per_coin  # 0.238 BTC
```

**Formula:**
```
Position Size = (Account × Risk %) / (Entry - Stop Loss)
```

**Adjustments:**
- If win rate < 50%: Reduce to 1.5%
- If drawdown > 10%: Reduce to 1%
- If drawdown > 15%: STOP TRADING

**Never:**
- Increase size to "make up" losses
- Trade full account on one position
- Skip stop loss calculation

---

## 2️⃣ PORTFOLIO HEAT (Total Risk Exposure)

### Maximum 10% Total Portfolio Risk

**Rule:** Sum of all open position risks ≤ 10%

**Example:**
```
Position 1 (BTC): 2% risk
Position 2 (ETH): 2% risk
Position 3 (SOL): 2% risk
Total Heat: 6% ✅ (under 10%)

Can add 1 more position at 2% risk (8% total) ✅
Cannot add 3 more positions (would be 12%) ❌
```

**When Portfolio Heat Reaches:**
- 6%: Caution, consider pausing new entries
- 8%: Warning, only add if exceptional setup
- 10%: STOP, no new positions until one closes

---

## 3️⃣ CORRELATION ADJUSTMENT

### BTC/ETH Correlation = 0.90

**Problem:** BTC and ETH move together 90% of the time. If both at full size (2% each), real risk is ~3.8% (not 4%).

**Adjusted Risk Formula:**
```python
def calculate_adjusted_risk(positions):
    """
    Adjust for correlation between positions
    """
    base_risks = [pos['risk'] for pos in positions]
    
    # For BTC + ETH (correlation 0.90)
    if has_both_btc_and_eth(positions):
        correlation = 0.90
        n_positions = len(positions)
        
        # Reduce each position proportionally
        adjustment_factor = 1 / (1 + correlation * (n_positions - 1))
        
        adjusted_risks = [risk * adjustment_factor for risk in base_risks]
        return adjusted_risks
    
    return base_risks

# Example
BTC position: 2% base risk
ETH position: 2% base risk
Both open: Each limited to 1.05% (adjusted)
Total real risk: ~2.1% (safer than 4%)
```

**Correlation Table:**
| Asset Pair | Correlation | Max Combined Risk |
|------------|-------------|-------------------|
| BTC/ETH | 0.90 | 2.1% (1.05% each) |
| BTC/SOL | 0.75 | 2.9% (1.45% each) |
| ETH/SOL | 0.80 | 2.5% (1.25% each) |
| BTC/AAPL | 0.20 | 3.6% (1.8% each) |

---

## 4️⃣ DRAWDOWN PROTECTION

### Three Levels of Defense

**Level 1: 5% Drawdown**
- **Action:** Review all trades, analyze what changed
- **Position Size:** Reduce to 1.5% per trade
- **Strategy:** Review if market regime shifted
- **Frequency:** Check daily P&L

**Level 2: 10% Drawdown**
- **Action:** STOP TRADING immediately
- **Position Size:** Reduce to 1% per trade (if resuming)
- **Analysis Required:**
  - What regime are we in?
  - Is strategy appropriate for regime?
  - Are confirmations being followed?
  - Review last 20 trades for patterns
- **Resume:** Only after identifying and fixing issue

**Level 3: 15% Drawdown**
- **Action:** MANDATORY 2-week trading pause
- **Position Size:** Close ALL positions
- **Deep Analysis:**
  - Full strategy review
  - Backtest recent period
  - Check if market structure changed
  - Psychological reset
- **Resume:** Only after:
  - Issue identified and fixed
  - Strategy re-validated on recent data
  - Mental state reset (no revenge trading)

**Drawdown Calculation:**
```python
def calculate_drawdown(account_balance, peak_balance):
    """
    Calculate current drawdown percentage
    """
    drawdown = (peak_balance - account_balance) / peak_balance
    return drawdown * 100

# Example
Peak: $10,000
Current: $9,000
Drawdown: 10% → STOP TRADING
```

---

## 5️⃣ DAILY & WEEKLY LIMITS

### Daily Limits (Protect From Tilt)

**Max 3 Losing Trades Per Day → STOP**
- After 3rd loss, STOP trading for the day
- Even if losses are small
- Prevents emotional spiral

**Max 5% Daily Loss → STOP**
- If account drops 5% in one day, STOP
- Close all positions (or let run with stops)
- Review what went wrong
- Resume next day (if not deeper issue)

**Max 2 Trades in Same Symbol Per Day**
- Prevents revenge trading same asset
- If stopped out twice, move on

### Weekly Limits

**Max 10% Weekly Loss → STOP Until Monday**
- If week reaches -10%, STOP trading
- Close positions
- Weekend analysis required
- Strategy review before resuming

**Max 5 Consecutive Losses → PAUSE**
- 5 losses in a row = something systemically wrong
- Not bad luck, likely:
  - Wrong regime
  - Strategy broken
  - Execution issue
- Pause, analyze, fix

---

## 6️⃣ EMERGENCY STOP CONDITIONS

### Exit ALL Positions Immediately If:

**Market Conditions:**
- ✅ VIX spikes > 40 (panic mode)
- ✅ BTC drops > 10% in 1 hour (crash)
- ✅ Major exchange outage > 30 minutes (liquidity risk)
- ✅ News of major exchange hack (contagion risk)

**Personal Conditions:**
- ✅ Emotion overriding rational decisions (anger, fear, euphoria)
- ✅ Unable to focus (personal crisis, health issue)
- ✅ Breaking own rules repeatedly (discipline failure)

**Action:**
1. Close all positions immediately (market orders if needed)
2. Step away from computer
3. Wait 24-48 hours
4. Analyze situation calmly
5. Resume only when conditions normalize

---

## 7️⃣ STOP LOSS RULES (Non-Negotiable)

### Every Trade MUST Have a Stop Loss

**Types of Stops:**
1. **Hard Stop (Default):** Set on exchange immediately
2. **Trailing Stop:** After +4% profit, trail at 2%
3. **Time Stop:** Exit after 30 days if no movement

**Stop Placement:**
- **Default:** 2% below entry (momentum trades)
- **Pattern-based:** Below pattern low (e.g., hammer low)
- **Support-based:** Below support level (add buffer)
- **Volatility-adjusted:** 1.5 × ATR below entry

**NEVER:**
- Remove stop loss (hoping for recovery)
- Move stop loss further away (adding to loser)
- Average down on losing position (doubling risk)

**Stop Loss Calculation:**
```python
def calculate_stop_loss(entry_price, method='percentage'):
    """
    Calculate stop loss based on method
    """
    if method == 'percentage':
        return entry_price * 0.98  # 2% below
    
    elif method == 'atr':
        atr = calculate_atr(candles, 14)
        return entry_price - (atr * 1.5)
    
    elif method == 'support':
        support_level = find_support(candles)
        buffer = support_level * 0.005  # 0.5% buffer
        return support_level - buffer
```

---

## 8️⃣ TAKE PROFIT RULES

### Primary Take Profit: 4% (2:1 Risk/Reward)

**Rule:** Always set initial TP at 2:1 R/R minimum.

**Example:**
- Entry: $42,000
- Stop: $41,160 (2% = $840 risk)
- TP: $43,680 (4% = $1,680 profit = 2× risk)

**Partial Profits (Advanced):**
```python
# Take 50% at 1:1 R/R
# Move stop to breakeven
# Let 50% run to 2:1 or trail

Entry: $42,000
Stop: $41,160

At +2% ($42,840):
    Close 50% position (book 1R profit)
    Move stop to $42,000 (breakeven)

Let remaining 50% run to:
    +4% ($43,680) OR
    Trail stop at 2% below peak
```

**Never:**
- Remove TP hoping for bigger move (greed)
- Move TP further out (let trade breathe)
- Hold past time stop (30 days)

---

## 9️⃣ LEVERAGE RULES

### Maximum Leverage: 3x (Conservative)

**Recommended Leverage by Experience:**
- Beginner: 1x (no leverage)
- Intermediate: 2x
- Advanced: 3x maximum

**Leverage Risk Calculation:**
```python
# Without leverage
Entry: $42,000
Stop: 2% ($41,160)
Loss if stopped: 2% of account

# With 3x leverage
Entry: $42,000
Stop: 2% ($41,160)
Loss if stopped: 6% of account (3× faster!)

# Solution: Adjust position size
Normal position: 2% risk
With 3x leverage: 0.67% risk (to maintain 2% total)
```

**Leverage Rules:**
- If using 3x leverage: Reduce position size to 0.67% risk
- If using 5x leverage: Reduce position size to 0.4% risk
- Never exceed 10x leverage (extremely dangerous)
- In high volatility (VIX > 30): Reduce leverage by 50%

---

## 🔟 POSITION MANAGEMENT

### Maximum Open Positions

**Trending Regime:** Max 3 positions
**Ranging Regime:** Max 2 positions
**High Volatility:** Max 1 position (or 0)

**Why Limits:**
- Focus > diversification in short-term trading
- Easier to manage stops/exits
- Reduces correlation risk
- Prevents over-trading

### Time in Trade

**Maximum:** 30 days per position
**Average Target:** 5-10 days

**Time Stop Rule:**
If position open > 30 days with < 1% movement:
- Exit at breakeven or small profit
- Capital has opportunity cost
- Re-evaluate if setup still valid

---

## 📊 Risk Tracking Dashboard

**Daily Check:**
```
Account Balance: $10,000
Peak Balance: $10,500
Current Drawdown: 4.76%

Open Positions:
1. BTC: $200 risk (2%)
2. ETH: $150 risk (1.5%)
Total Heat: 3.5% ✅

Daily P&L: -$180 (-1.8%)
Consecutive Losses: 2
Trades Today: 2

Status: NORMAL ✅
Can add 1 more position (under 10% heat)
```

---

## 🎯 Risk Checklist (Before Every Trade)

- [ ] Position size calculated? (2% max risk)
- [ ] Stop loss set? (2% below entry)
- [ ] Take profit set? (4% above entry, 2:1 R/R)
- [ ] Portfolio heat < 10%? (check total risk)
- [ ] Correlation adjusted? (if BTC+ETH open)
- [ ] Drawdown < 5%? (check account status)
- [ ] Not at daily limit? (<3 losses today)
- [ ] Market regime checked? (trending/ranging/high vol)
- [ ] Not emotionally compromised? (calm, rational)
- [ ] VIX < 30? (not panic mode)

**If ANY checkbox is ❌: DO NOT TAKE THE TRADE**

---

## 🚨 Common Risk Management Mistakes (AVOID)

1. **"Just This Once" Syndrome**
   - Breaking 2% rule "just this once"
   - Removing stop "just for this trade"
   - Result: Account blown up

2. **Revenge Trading**
   - Doubling position after loss
   - Trading same symbol repeatedly
   - Result: Deeper losses

3. **Overtrading**
   - 10+ trades per day
   - Ignoring daily limits
   - Result: Death by a thousand cuts

4. **Ignoring Correlation**
   - BTC + ETH + SOL all at 2%
   - Real risk: 5%+ (not 6%)
   - Result: Correlated wipeout

5. **Moving Stops**
   - "Just needs more room"
   - Turning 2% loss into 5% loss
   - Result: Account death spiral

---

## 📈 Expected Outcomes (With Proper Risk Management)

**60% Win Rate, 2:1 R/R:**
```
100 trades
60 wins × +2R = +120R
40 losses × -1R = -40R
Net: +80R

If R = $200 (2% of $10,000):
Net profit: $16,000 (160% return)
```

**Even 50% Win Rate:**
```
100 trades
50 wins × +2R = +100R
50 losses × -1R = -50R
Net: +50R

If R = $200:
Net profit: $10,000 (100% return)
```

**Key:** Risk management turns breakeven strategy into profitable one!

---

## 🎓 Key Principles

1. **Protect Capital First**
   - Making money is secondary to not losing money
   - Drawdowns exponentially harder to recover from
   - 50% loss = need 100% gain to recover

2. **Size Matters More Than Win Rate**
   - 40% WR with good R/R > 60% WR with bad R/R
   - Our 43.8% WR lost money because R/R was poor
   - 2:1 R/R makes 35% WR profitable

3. **Consistency > Home Runs**
   - Small steady gains compound
   - Big risky bets blow up accounts
   - Turtle beats hare

4. **Rules Exist for Worst Day, Not Best Day**
   - Easy to follow rules when winning
   - Critical to follow when losing
   - Discipline in adversity = survival

---

**Last Updated:** October 17, 2025  
**Version:** 1.0  
**Status:** ACTIVE - Iron Laws  
**Violations Allowed:** ZERO
