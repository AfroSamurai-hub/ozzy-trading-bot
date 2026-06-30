# Testnet → Live Data Protocol

> We have ONE WEEK of testnet left. Every trade this week is data. Data drives the live config.
> Last updated: 2026-05-18

---

## Philosophy

**No blind copy-paste from testnet to live.** We watch, we measure, we decide. The testnet is our laboratory. Live is our battlefield. We don't walk onto the battlefield with untested gear.

**What we measure this week:**
1. Symbol-level win rate and R-multiple
2. Grade A vs Grade B vs Grade C performance
3. Time-of-day performance (which hours produce winners?)
4. Filter rejection accuracy (are we blocking winners?)
5. Monitor behavior (breakeven hits, trail activations, partial closes)

---

## Current Testnet Data (Last 30 Days)

| Symbol | Trades | Win Rate | PnL | Verdict |
|--------|--------|----------|-----|---------|
| **SOLUSDT** | 4 | 100% | +$443.17 | 🟢 **LIVE — proven** |
| **ETHUSDT** | 1 | 100% | +$55.83 | 🟢 **LIVE — proven** |
| **LINKUSDT** | 1 | 100% | +$45.50 | 🟢 **LIVE — proven** |
| XRPUSDT | 4 | 0% | -$67.60 | 🔴 **DROP — losing** |
| BTCUSD (legacy) | 6 | 0% | $0 | 🔴 **Already dead** |
| ETHUSD (legacy) | 7 | 0% | $0 | 🔴 **Already dead** |
| XAUUSD (legacy) | 3 | 0% | $0 | 🔴 **Already dead** |
| EURUSD (legacy) | 1 | 0% | $0 | 🔴 **Already dead** |

**Key insight:** SOL, ETH, LINK on Binance Futures USDT pairs are the only symbols printing green. Everything else is red or dead.

---

## This Week's Mission (May 18–24)

### Daily Data Collection

Every morning at 7 AM SAST, run:

```bash
cd /home/rick/ozzy-bot
source venv/bin/activate
python3 scripts/analyze_last_24h.py
```

This produces a JSON report: `reports/daily_YYYY-MM-DD.json`

### What We Track

| Metric | Target | Action If Missed |
|--------|--------|------------------|
| Grade A win rate | ≥55% | Lower risk to 1.5% for Grade A |
| Grade B win rate | ≥40% | Keep at 2%, maybe drop to 1.5% |
| Grade C win rate | ≥30% | Set `SETUP_GRADE_RISK_MULTIPLIERS["C"] = 0.0` (skip) |
| Avg R (all grades) | ≥2.0 | Tighten SL or widen TP filters |
| Breakeven hit rate | ≥60% of winners | Monitor trail activation working |
| 1.5R partial rate | ≥40% of winners | Validate milestone logic |

### Daily Review Questions

1. **Did any Grade A signal lose?** If yes, what filter could have caught it?
2. **Did any rejection turn into a big winner?** If yes, which filter was wrong?
3. **Did the monitor behave correctly?** Breakeven at 1R? Trail after 1.5R?
4. **Any duplicate orders or missed exits?** DB state recovery working?

---

## Live Config Decision Matrix

### Based on This Week's Data

| Scenario | Win Rate | Avg R | Live Action |
|----------|----------|-------|-------------|
| **Bull case** | ≥50% | ≥2.5 | Risk 2.5%, 4 max positions, all 3 symbols |
| **Base case** | 40-50% | 2.0-2.5 | Risk 2%, 3 max positions, SOL+ETH+LINK |
| **Bear case** | <40% | <2.0 | Risk 1.5%, 2 max positions, SOL+LINK only |

### Grade Risk Multipliers (Tuned Weekly)

```python
# Default for $500 launch
SETUP_GRADE_RISK_MULTIPLIERS = {
    "A": 1.0,   # Full 2% risk
    "B": 0.75,  # 1.5% risk
    "C": 0.0,   # Skip entirely
}

# If data shows Grade B winning ≥45%:
# "B": 1.0

# If data shows Grade A crushing it (≥60% WR):
# "A": 1.25  (2.5% risk for A setups)
```

### Symbol Activation Tiers

| Tier | Symbols | Condition to Activate |
|------|---------|----------------------|
| **Core** | SOL, ETH, LINK | Always active — proven profitable |
| **Trial** | DOGE | Add if core 3 maintain ≥45% WR for 2 weeks |
| **Watchlist** | BTC, XRP | Need 50+ backtested signals + 20 live testnet trades before activation |
| **Legacy** | XAU, EUR | MetaAPI only — paused indefinitely |

---

## The Data Loop

```
Testnet Trade → DB Record → Daily Analysis → Filter Tuning → Config Update → Live Launch
                     ↑                                               |
                     └────────────── Live Feedback ──────────────────┘
```

**Rule:** Config changes only happen on Sundays. No mid-week panic changes.

### Sunday Review Ritual (Every Week)

```bash
# 1. Pull weekly stats
python3 scripts/weekly_review.py

# 2. Compare to targets
# 3. Vote: keep config, tighten, or loosen
# 4. Update config.py if voted
# 5. Document decision in docs/DECISIONS.md
# 6. Restart services
```

---

## Emergency Override Rules

Even with data, these rules are absolute:

1. **Never increase risk mid-loss-streak.** 3 losers in a row = freeze risk for 1 week.
2. **Never add a symbol mid-green-streak.** Winning feels good. Don't get greedy.
3. **Never remove a symbol mid-red-streak.** Losing feels bad. Don't get fearful.
4. **Only change on Sunday.** Data needs time to mean something.

---

## This Week's Assignments

| Day | Task |
|-----|------|
| Mon 18 | ✅ Protocol created. Baseline data captured. |
| Tue 19 | Watch Grade A vs B performance. Monitor 2 open SOL positions. |
| Wed 20 | Mid-week check: any filter blocking winners? |
| Thu 21 | Stress test: restart monitor mid-trade, verify DB recovery. |
| Fri 22 | Full week data pull. Begin live config draft. |
| Sat 23 | Final review. Lock live config. |
| Sun 24 | **GO LIVE** with data-validated settings. |

---

*Last updated: 2026-05-18*
*Next review: 2026-05-19 (Tuesday morning data check)*
