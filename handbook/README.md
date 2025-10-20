# Trading Handbook

## 🎯 Overview

This is Ozzy's **institutional knowledge base** - a comprehensive trading handbook that documents strategies, patterns, risk management rules, and market regimes. Modeled after Renaissance Technologies and Two Sigma's approach to systematic trading.

## 📚 Documents

### 1. [MOMENTUM_STRATEGY.md](./MOMENTUM_STRATEGY.md)
**Evidence-based momentum trading strategy**
- Peer-reviewed foundation (Jegadeesh & Titman 1993)
- Realistic expectations: 55-60% WR (NOT 84% marketing BS)
- Entry/exit criteria (6 confirmations required)
- Historical failure modes documented
- Backtest learnings integrated (43.8% WR without confirmations → 60-65% expected with confirmations)

### 2. [PATTERN_LIBRARY.md](./PATTERN_LIBRARY.md)
**Validated candlestick patterns with real performance data**
- 🟢 High-confidence patterns (60%+ WR)
- 🟡 Medium-confidence patterns (50-60% WR, conditional)
- 🔴 Retired patterns (don't trade)
- Actual backtest results: hammer (40% WR), morning_star (40% WR), doji (46% WR)
- Key lesson: "Pattern ≠ Signal. Pattern + Confirmations = Signal"

### 3. [MARKET_REGIMES.md](./MARKET_REGIMES.md)
**Market regime classification and strategy selection**
- 🟢 Trending: Momentum works (65-70% WR expected)
- 🟡 Ranging: Mean reversion works (60-65% WR), momentum fails (40-45% WR)
- 🔴 High Volatility: Cash is king (all strategies <35% WR)
- Detection algorithms (ADX, VIX, EMA)
- Position sizing adjustments per regime

### 4. [RISK_RULES.md](./RISK_RULES.md)
**Iron laws (non-negotiable)**
- 2% max risk per trade
- 10% max portfolio heat
- Drawdown protection (5%/10%/15% triggers)
- BTC/ETH correlation adjustment (0.90)
- Daily limits (3 losses → stop)
- Emergency stops (VIX > 40)

## 🔧 Integration

### Quick Start
```python
from scripts.handbook_loader import TradingHandbook

# Initialize handbook
handbook = TradingHandbook()

# Build trade signal
trade_signal = {
    'symbol': 'BTCUSDT',
    'action': 'LONG',
    'strategy': 'momentum',
    'pattern': 'hammer',
    'confidence': 0.75,
    'risk_amount': 200,
    'account_balance': 10000,
    'entry_price': 42000,
    'stop_loss': 41160,  # 2% stop
    'take_profit': 43680,  # 4% TP (2:1 R/R)
    'volume_confirmed': True,
    'trend_confirmed': True,
    'at_key_level': True,
    'rsi_confirmed': True,
    'market_regime': 'TRENDING',
    'vix': 18
}

# Validate against handbook
approved, violations = handbook.check_trade_against_rules(trade_signal)

if approved:
    print("✅ TRADE APPROVED - Handbook compliant")
else:
    print(f"❌ TRADE REJECTED - Violations: {violations}")

# Get detailed analysis
result = handbook.get_trade_recommendation(trade_signal)
print(f"Confirmations: {result['confirmations_met']}/{result['confirmations_total']}")
print(f"Adjusted Confidence: {result['adjusted_confidence']:.1%}")
```

### Full Analysis
```python
# Print comprehensive trade analysis
handbook.print_trade_analysis(trade_signal)

# Output:
# ======================================================================
# 📚 TRADING HANDBOOK ANALYSIS
# ======================================================================
# 
# 🎯 SYMBOL: BTCUSDT
# 📊 STRATEGY: momentum
# 📈 PATTERN: hammer
# 🌍 REGIME: TRENDING
# 
# ✅ CONFIRMATIONS: 8/8
#    ✅ Volume
#    ✅ Trend
#    ✅ Support Resistance
#    ✅ Rsi Momentum
#    ✅ Regime Appropriate
#    ✅ Stop Loss Set
#    ✅ Take Profit Set
#    ✅ Position Sized
# 
# 📊 CONFIDENCE:
#    Base: 75.0%
#    Adjustment: 1.20x
#    Final: 90.0%
# 
# 🎯 RECOMMENDATION: APPROVED - Strong setup (8/8 confirmations)
# ✅ TRADE APPROVED BY HANDBOOK
# ======================================================================
```

## ✅ Validation Rules

The handbook validates:

1. **Position Sizing** - Max 2% risk per trade
2. **Stop Loss** - 2% default, max 5% distance
3. **Risk/Reward** - Minimum 2:1 R/R
4. **Pattern Confirmations** - Volume + trend required
5. **Market Regime** - Strategy appropriate for regime
6. **VIX Level** - Emergency stop if VIX > 40
7. **Pattern Status** - Not retired/probationary

### Confirmation Checklist
Before ANY trade, verify:
- [ ] Volume >1.5x average
- [ ] Trend aligned (price vs 200 EMA)
- [ ] At key support/resistance
- [ ] RSI momentum confirmed
- [ ] Regime appropriate for strategy
- [ ] Stop loss set (2%)
- [ ] Take profit set (4%, 2:1 R/R)
- [ ] Position sized (2% risk)

**Rule:** If <5/8 confirmations met, SKIP THE TRADE

## 📊 Expected Performance

**With Full Confirmations (Target):**
- Win Rate: 60-65%
- Avg R: +1.5R
- Profit Factor: 2.0-2.5
- Monthly Return: 5-10%

**Our 60-Day Backtest (Without Confirmations):**
- Win Rate: 43.8% ❌
- Avg R: -0.04R
- Profit Factor: 0.95
- Total Return: -0.18%

**Lesson:** Confirmations are CRITICAL!

## 🔬 Backtest Results (Oct 2025)

**Test Period:** 60 days, 5,790 candles (15-min), BTCUSDT

| Pattern | Trades | Win Rate | Status |
|---------|--------|----------|---------|
| hammer | 10 | 40% | Probation |
| morning_star | 10 | 40% | Probation |
| doji | 28 | 46% | Use Sparingly |
| bullish_engulfing | 0 | N/A | Pending Test |

**Key Findings:**
1. ✅ Learning mechanism WORKS (multipliers adjusted correctly)
2. ❌ Simple patterns FAIL (40-46% WR without confirmations)
3. ✅ Infrastructure SOLID (data, tracking, learning all working)
4. 💡 Need ALL confirmations to achieve 60-65% WR

## 🚀 Next Steps

1. **Re-run backtest with full confirmations**
   - Add volume filter (>1.5x avg)
   - Add trend filter (price vs EMA)
   - Add regime filter (detect ADX/VIX)
   - Expected: 60-65% WR ✅

2. **Integrate with live bot**
   - Add handbook check before every trade
   - Block trades with violations
   - Track confirmation ratios

3. **Continuous improvement**
   - Update after every 50 trades
   - Document new failure modes
   - Add validated patterns
   - Remove failing patterns

## 🎓 Philosophy

**"Institutional Memory Beats Individual Genius"**

This handbook captures:
- ✅ What works (with evidence)
- ✅ What doesn't work (learned through pain)
- ✅ Why strategies fail (historical examples)
- ✅ How to adapt (regime-based rules)

**Key Principles:**
1. Evidence-based (peer-reviewed research)
2. Realistic expectations (55-65% WR, not 84%)
3. Documented failures (prevent re-discovery)
4. Continuous learning (update every 50 trades)
5. Risk management first (capital preservation)

## 📖 Academic References

1. **Jegadeesh & Titman (1993)**
   - "Returns to Buying Winners and Selling Losers"
   - Journal of Finance
   - Foundation for momentum strategy

2. **Asness, Moskowitz & Pedersen (2013)**
   - "Value and Momentum Everywhere"
   - Works across asset classes

3. **Barroso & Santa-Clara (2015)**
   - "Momentum Has Its Moments"
   - Volatility-adjusted momentum

## 🔄 Version Control

**Current Version:** 1.0  
**Last Updated:** October 17, 2025  
**Next Review:** After 50 trades with full confirmations  
**Status:** ACTIVE - Validation pending

## 💡 Usage Examples

### Example 1: Reject Bad Trade
```python
trade = {
    'action': 'LONG',
    'risk_amount': 500,  # 5% risk - VIOLATES 2% rule
    'account_balance': 10000,
    'volume_confirmed': False,
    'market_regime': 'HIGH_VOLATILITY',
    'vix': 45
}

approved, violations = handbook.check_trade_against_rules(trade)
# approved = False
# violations = [
#     "Position size 5.0% exceeds 2% rule",
#     "Pattern lacks volume confirmation",
#     "High volatility regime - minimal trading",
#     "VIX 45.0 > 40 - EMERGENCY STOP"
# ]
```

### Example 2: Approve Good Trade
```python
trade = {
    'action': 'LONG',
    'risk_amount': 200,  # 2% risk ✅
    'account_balance': 10000,
    'entry_price': 42000,
    'stop_loss': 41160,  # 2% stop ✅
    'take_profit': 43680,  # 4% TP, 2:1 R/R ✅
    'volume_confirmed': True,
    'trend_confirmed': True,
    'at_key_level': True,
    'market_regime': 'TRENDING',
    'vix': 18
}

approved, violations = handbook.check_trade_against_rules(trade)
# approved = True
# violations = []
```

## 📞 Support

For questions or improvements:
1. Review relevant handbook document
2. Check backtest results in `/scripts/zero_dep_backtest.py`
3. Test with `/scripts/handbook_loader.py`
4. Update handbook based on findings

---

**Remember:** The handbook is a living document. Update it based on real trading results, not hopes or assumptions.

**"Trade the handbook, not your emotions."**
