# Ozzy Simple — Research Plan

A structured plan to evaluate and evolve the system holistically.

## Objectives

- Stabilize short-term performance (avoid crisis days) while maintaining healthy long-term growth.
- Validate AI-optimized parameters vs baseline across rolling windows.
- Understand sensitivity to time-of-day, symbol, and market regime.

## Core metrics

- Win rate, Profit factor (PF)
- Sharpe (trade-level), Maximum drawdown (absolute and %)
- Avg win / avg loss (R:R), Avg P&L/trade
- Volume: trades/day, trades/hour in allowed window
- Segment metrics by symbol, side (LONG/SHORT), hour, confidence bucket

## Datasets

- Historical: `ozzy_simple.db` (signals, trades)
- Live: ongoing trades + signals
- Synthetic: optional via `turbo_mode.py` for ablations (label clearly when synthetic)

## Experiments

1. Time-of-day windows

- Goal: Identify sub-windows within 10:00–21:00 that maximize PF and reduce variance.
- Design: Evaluate 10–12, 12–14, 14–17, 17–21 by symbol; use rolling 2-week windows.
- Success: PF > 2.0 with stable win rate and no deep hour-specific drawdowns.

1. Confidence threshold sweep

- Goal: Optimize MIN_CONFIDENCE around 35–55 while tracking volume.
- Design: Sweep in 2–3 point increments; measure PF, trade count, avg trade.
- Success: Clear peak with robust PF ≥ 2.5 and sustainable trade volume.

1. LONG vs SHORT regime

- Goal: Detect market regimes where SHORTs underperform; gate or rebalance.
- Design: Compare PF and win rate by side; introduce short bias flag during bear trends.
- Success: SHORT gating improves overall PF/Sharpe without starving trade flow.

1. Symbol selection and weighting

- Goal: Focus on symbols with stable PF; downweight or exclude laggards.
- Design: Rank symbols weekly by PF, win rate; simulate top-3 vs all-5.
- Success: Top-k portfolio yields equal or higher PF with lower variance.

1. Volatility-aware sizing

- Goal: Adjust risk sizing by ATR% and spread; avoid wide-spread low-liquidity conditions.
- Design: Incorporate ATR% bands and spread thresholds; simulate effect on PF and MDD.
- Success: Lower MDD and tail risk with minimal PF impact.

1. A/B: time filter

- Goal: Validate benefit of avoiding specific hours (e.g., 22:00–02:00).
- Design: Use `TimeFilterWrapper` test tags; compare 50 trades per variant.
- Success: Test group shows improved PF/Sharpe with statistical significance.

## Evaluation protocol

- Rolling windows (e.g., last 200 trades, last 2 weeks) to avoid stale conclusions.
- Pre-AI vs Post-AI cutover tracking (already implemented in `PROJECT_REPORT.md`).
- Significance: Use bootstrap CIs on PF and win rate; avoid overfitting on small Ns.
- Guardrails: Daily loss limit enforced; stop trading if PF < 1.0 over last 20 trades.

## Tools and automation

- `scripts/generate_project_report.py`: single source of truth report; schedule hourly.
- `dashboard.py`: live equities and KPIs; add charts for PF by hour/symbol.
- `analytics.py`: deeper metrics, watch mode for live monitoring.
- `scripts/ai_optimizer_emergency.py`: reproducible param search; log trial stats.

## Next steps (initial 1–2 weeks)

- Let AI config run for ~20–50 trades; monitor with `analyze_ai_performance.py` and reports.
- Run Experiment 1 and 2 in parallel (analysis-only first with DB):
  - Hour windows by symbol
  - Confidence sweep (simulate filtering) over historical trades
- Implement guardrail: halt trading automatically if last-20 PF < 1.0 or win rate < 35%.
- Align config names across modules (see ARCHITECTURE.md “Gaps and alignment”).

## Deliverables

- Weekly research memo with charts: equity, PF by hour/symbol, side performance.
- Parameter change log with justification and backtest/live slices.
- Updated `CONFIG_CHANGES.md` documenting each revision and outcome.
