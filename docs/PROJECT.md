# OzzyBot — Master Project Document
Last updated: 2026-05-18

## What We Are Building
Autonomous crypto futures trading system that generates enough profit to cover its own AI tool costs, then grows into a multi-node swarm.

Signal source: Python-native scanner (signal_generator.py -> crypto_entry_policy.py) posting to the local webhook
Execution: Binance USD-M Futures
Architecture: Webhook → Flask → Binance
Vision: 5 Mac Minis × $5k each = $25k swarm

## Current State (as of 2026-05-18)
- System is LIVE-READY on Binance futures
- Active symbols: SOL, ETH, LINK, DOGE (testnet validated)
- Active timeframe: 1H
- Risk per trade: 2% of equity (data-driven, reviewed weekly)
- Leverage: ETH 20x, SOL/LINK/DOGE 10x
- Status: TESTNET validated, LIVE switch scheduled 2026-05-25 (Sunday)
- Capital: $500 USDT (live account)
- Phase: **Phase 1 — The Seed**

## What Has Been Proven (Testnet)
- SOLUSDT: 4 trades, 100% WR, +$443.17 — **PROVEN LIVE**
- ETHUSDT: 1 trade, 100% WR, +$55.83 — **PROVEN LIVE**
- LINKUSDT: 1 trade, 100% WR, +$45.50 — **PROVEN LIVE**
- XRPUSDT: 4 trades, 0% WR, -$67.60 — **DROPPED**
- Legacy forex/gold (MetaAPI): All losing — **DEAD**

## Data-Driven Philosophy
**No blind config.** Every week, testnet/live data feeds back into the system:
1. Daily analysis at 7 AM (`scripts/analyze_last_24h.py`)
2. Weekly review every Sunday (`scripts/weekly_review.py`)
3. Config changes ONLY on Sundays based on 7-day data
4. Risk scales UP when data proves it, DOWN when data warns

See: `docs/TESTNET_TO_LIVE_PROTOCOL.md`

## Swarm Evolution (18-Month Horizon)

| Phase | Timeline | Equity | Bots | Goal |
|-------|----------|--------|------|------|
| 1. Seed | Months 1-3 | $500 → $1,500 | 1 | Prove live execution |
| 2. Sprout | Months 4-6 | $1,500 → $3,000 | 1 | Cover AI costs, buy Mac Mini #1 |
| 3. Branch | Months 7-10 | $3,000 → $7,500 | 2 | Two bots, two strategies |
| 4. Grove | Months 11-14 | $7,500 → $15,000 | 3 | Three bots, income + growth |
| 5. Forest | Months 15-18 | $15,000 → $25,000+ | 5 | Full swarm, multi-exchange |

See: `docs/SWARM_EVOLUTION.md`

## Phase 1: Seed Rules ($500 Launch)
- **Risk:** 2% per trade (reviewed weekly, can go 1.5%–2.5% based on data)
- **Max positions:** 3 (reviewed weekly)
- **Symbols:** SOL, ETH, LINK (proven on testnet). DOGE on watch.
- **Grade multipliers:** A=1.0, B=0.75, C=0.0 (reviewed weekly)
- **Config changes:** Sundays only
- **Profit:** 100% reinvested

## Success Metrics (Phase 1)
| Metric | Week 1 Target | Month 1 Target | Month 3 Target |
|--------|--------------|----------------|----------------|
| Win rate | ≥40% | ≥45% | ≥50% |
| Avg R | ≥1.5 | ≥2.0 | ≥2.5 |
| Max drawdown | ≤10% | ≤15% | ≤15% |
| Equity | $500+ | $540+ | $650+ |

## Hard Rules (never broken)
- Max open positions: 3 (Phase 1), scaled via data
- Max daily loss: 5% of account
- Risk per trade: 2% baseline, ±0.5% based on weekly data
- Never widen a stop loss
- Never add to a losing position
- Config changes ONLY on Sundays
- No symbol without 10+ testnet trades proving profitability

## Key Documents
- `docs/LIVE_PLAYBOOK.md` — Step-by-step live switch + daily ops
- `docs/TESTNET_TO_LIVE_PROTOCOL.md` — How testnet data drives live config
- `docs/SWARM_EVOLUTION.md` — $500 → 5×$5k roadmap
- `docs/FINANCIAL_MODEL.md` — Return projections, withdrawal strategy
- `docs/STRATEGIC_ROADMAP.md` — Quarterly milestones
- `docs/CHANGELOG.md` — All changes with dates
- `docs/DECISIONS.md` — Decision log with rationales

## Daily & Weekly Rituals
```bash
# Every morning at 7 AM (cron)
python3 scripts/analyze_last_24h.py

# Every Sunday evening (cron)
python3 scripts/weekly_review.py

# Daily at 3 AM (cron)
bash scripts/backup_to_gdrive.sh
```

## Backup Strategy
1. **Local:** `scripts/backup.sh` — daily tar.gz, 10 retained
2. **Google Drive:** `scripts/backup_to_gdrive.sh` — daily sync, 30 days retained
3. **Cross-bot:** Each swarm node rsyncs to another weekly

*Last updated: 2026-05-18*
*Current phase: Phase 1 — The Seed*
*Next milestone: Sunday config lock (2026-05-24) → Live launch (2026-05-25)*
