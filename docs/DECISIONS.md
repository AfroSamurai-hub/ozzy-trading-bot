# Decision Log

## 2026-05-22 - Gemini joins Hermes as evidence advisor
Why: Hermes now has richer setup memory, LIVE/TESTNET separation, chart and
     operator context, and repeated questions that need synthesis rather than
     another trade filter.
What we chose: Add a Gemini-backed `Hermes Advisor` role over bounded Ozzy
              Memory evidence. The advisor returns structured observations,
              risks, and hypotheses while Hermes core retains signals, risk,
              execution, protection, and exits.
Boundary: Gemini has no broker/order/risk authority in Phase 1 and cannot
          hard-block trades from model opinion.
Evidence note: Evidence Pack v2 gives the advisor bounded LIVE and TESTNET
               status/trade/exit/milestone/incident views. It excludes secrets,
               raw DB dumps, migrated/ghost trade rows, and unsupported root
               cause claims.

## 2026-05-21 - Live micro stabilization and memory evidence
Why: LIVE micro is intentionally using a $5 target loss-at-SL while equity is
     still small. That is a high-risk bootstrap posture and must be explicit,
     bounded by dollar loss, and backed by exchange protection truth.
What we chose: Keep LIVE at ETH/LINK and max one position. Use daily live
              dollar/full-loss stops during bootstrap, soften early strategy
              lane blocks into watch/reduced participation, add read-only LIVE
              reconciliation, and store setup memory in local SQLite before
              adding any vector or external prediction layer.
Sizing note: If the fixed bootstrap target risk does not fit Binance available
             entry margin, reduce executable quantity and record actual risk
             instead of letting Binance reject the entry at the last step.
Backup note: `python scripts/backup_runtime_dbs.py` copies `trades.db`,
             unified `trades.db`, and `ozzy_memory.db` into
             `backups/YYYY-MM-DD/`. Restore by stopping writers first and
             replacing the matching DB from the chosen timestamped copy.
Exit note: Recent testnet trades repeatedly reached meaningful favorable
           excursion before giving profit back. The monitor now takes a small
           default 25% partial at 0.5R, while the later 1.5R/3R milestones keep
           the remaining position available for continuation. Exit analytics
           must preserve protective reasons such as `momentum_exit` instead of
           relabeling them as stop losses.

## 2026-05-01 — ETH skips candle-direction filter (v2.2.2-patch)
Why: Backtest proved v2.2.2 accuracy filters improve SOL and XRP
     but degrade ETH by −$513 (−58%). Candle-direction filter removes
     more ETH winners than losers (21 win / 12 loss reduction).
     ETH pullback/momentum entries often occur on candles that wick
     against the direction and close near open.
What we chose: ETH keeps volume + cooldown, skips candle direction.
               SOL and XRP retain full v2.2.2 filters.
What we rejected: One-size-fits-all accuracy filters.
                 Reverting ETH entirely to v2.2.1 (volume/cooldown help).
Pending: ETH-only backtest with candle OFF to confirm recovery.

## 2026-04-28 — Go live on Binance futures
Why: System proven end-to-end on testnet.
     NTP fixed. Health check fixed. Secrets secured.
     Rejection tracker wired in.
What we chose: BINANCE_TESTNET = False
What we rejected: Waiting longer

## 2026-04-28 — ETH and SOL only (not BTC, not XRP)  
Why: Backtest across 1,298 trades.
     BTC PF 0.818 (losing). XRP PF 0.912 (losing).
     ETH PF 1.217 (profitable). SOL PF 1.524 (profitable).
What we chose: ETH + SOL as active symbols
What we rejected: BTC (dropped), XRP (dropped)
**Superseded by 2026-05-21:** LIVE micro now tracks ETH/LINK only and keeps
max one position during bootstrap. Testnet remains the wider evidence lane.

## 2026-04-28 — 5% risk per trade (not 2%)
Why: At $200 capital, 2% risk = $4/trade.
     Fees dominate. No meaningful compounding.
     5% gives real position size while remaining
     within professional risk management bounds.
What we chose: RISK_PCT = 0.05
What we rejected: 2% (too small), 10%+ (too aggressive)
**Superseded by 2026-05-21:** LIVE micro uses an intentional $5 target
loss-at-SL while bootstrap is active under the configured equity ceiling.
Percentage risk still applies outside bootstrap mode.

## 2026-04-28 — Keep 1H timeframe (not 15M)
Why: 15M is noisier. Backtest not run on 15M.
     1H proven. Do not change what works.
What we chose: 1H as primary (15M added in Phase 3 only)
What we rejected: Switching to 15M prematurely

## 2026-04-28 — Firecrawl position sizing engine
Why: Same signal quality with bigger size on
     high-conviction setups = more profit.
     Extreme fear + buy signal = best setup.
     We size up, not skip.
What we built: Dynamic multiplier 0x to 1.75x
     based on Fear/Greed, Funding Rate
     Hard cap at 8% max risk per trade
What we rejected:
     - Firecrawl for news (overkill, adds paid dependency,
       false positives on keyword matching)
     - Coinglass for funding (requires paid API key)
     - Binary approve/reject filter (reduces trades)
What we chose instead:
     - alternative.me for Fear/Greed (free, no key)
     - Binance native API for funding rates (free, no key)
     - Skip news for Phase 1, add in Phase 2
Expected impact:
     10-15% of trades get 1.75x size (best setups)
     5% of trades get 0.5x size (elevated risk)
     <1% of trades skipped (breaking danger news)
     Net result: MORE profit per month, not less

## 2026-04-28 — Leverage set to 20x ETH, 10x SOL
Why: $14 live account. Binance ETHUSDT minimum
     notional is $20. At 5% risk, wide SLs produce
     notional below $20 causing silent order rejection.
     20x keeps margin requirement at $1 per trade.
     100x rejected — 1% move wipes 14% of account.
What we chose: ETH 20x, SOL 10x
What we rejected: 10x ETH (insufficient for minimums),
                  100x (liquidation risk on micro account)

## 2026-04-28 — Phase-based rollout (not big bang)
Why: Every new component adds risk.
     Prove each phase before adding next.
     Single bot proven → add tier 2 → add tier 3.
What we chose: Phase 1 first, nothing else until 30 trades
What we rejected: Building everything at once
