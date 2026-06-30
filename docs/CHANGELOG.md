# Changelog

## 2026-05-27
- Hardened Binance post-fill protection confirmation. Exchange-visible fallback
  now validates current close side, quantity, and expected SL/TP trigger prices
  before allowing a `TRADE CONFIRMED` Telegram message. Missing TP repair now
  upgrades to clean confirmation only after the repaired TP is verified live.
- Hardened milestone partial exits. After any live partial close, the Binance
  monitor now places and verifies fresh reduce-only SL/TP for the remaining
  runner quantity before canceling captured old protection, preventing partial
  profit-taking from leaving a reduced runner unprotected.
- Expanded the testnet scouting universe with `WLDUSDT`, `ZECUSDT`,
  `DRIFTUSDT`, `INJUSDT`, `RENDERUSDT`, `ENAUSDT`, and `SEIUSDT`.
  The additions are wired as Binance-native, 24/7, testnet research symbols
  with explicit strategy profiles, asset specs, min-notional metadata, and
  precision rules. Live micro remains unchanged on `XAUUSDT,HYPEUSDT,LINKUSDT`.
- Added explicit live-micro bootstrap context to the read-only `Hermes Advisor`
  prompt and evidence contract. The advisor now understands live micro as an
  intentional small-account growth lane while still reporting the true
  percentage risk, labeling it high-risk bootstrap, and refusing to call the
  risk normal or scalable without clean forward execution/protection evidence.
- Added `xau_sweep_continuation_v1`, a narrow XAUUSDT-only momentum SELL
  context exception. It permits early sweep-continuation shorts only when
  price is with EMA/SuperTrend direction, range position is above 20%,
  displacement is strong, volume expansion is at least 0.75, and no bullish
  rejection wick is present. Global liquidity-sweep blocking remains intact.
- Raised the default testnet concurrent-position cap from 5 to 10 to accelerate
  clean forward-sample collection across symbol profiles. Live micro remains
  governed separately by `config/live-micro.env` and is not loosened by this
  testnet sampling change.
- Added Phase 4 Truth Layer accounting classification. Closed trades are now
  classified as `clean`, `corrected`, `dirty`, or `unchecked`; dirty rows and
  fail-closed execution rows are excluded from default lane expectancy stats.
  The Binance monitor marks reconstructed close PnL as `corrected`, and
  `scripts/classify_trade_accounting.py` can backfill old rows from DB/log
  evidence.
- Rotated the live-micro growth experiment seats from `BNBUSDT,BTCUSDT,LINKUSDT`
  to `XAUUSDT,HYPEUSDT,LINKUSDT`. The 1h live-micro scanner now watches those
  three symbols, while 15m mean reversion is constrained to `LINKUSDT` so XAU
  and HYPE keep their profile-specific 1h momentum/trend-continuation roles.

## 2026-05-26
- Updated the read-only `Hermes Advisor` prompt into a profit-driven risk and
  performance auditor: it now explicitly evaluates multiplier quality, slippage
  and friction, asset-specific profile fit, and evidence-before-expansion rules.
- Added centralized `SYMBOL_STRATEGY_OVERRIDES` in `config.py` for BTC, NEAR,
  HYPE, SOL, SUI, ONDO, XAU, ETH, BNB, and LINK so symbol-specific strategy
  behavior no longer lives in hardcoded `webhook.py` branches.
- Kept global risk rails unchanged: signal age, entry drift, spread checks,
  reconciliation, position caps, daily-loss stops, minimum RR, protection
  verification, and live-gating still apply after any symbol profile override.
- Kept HYPE in testnet observation while its new `trend_continuation` profile
  collects evidence; no global rule loosening was introduced.

## 2026-05-22
- Added the Phase 1 read-only `Hermes Advisor` Gemini model role with explicit
  config, `/status` visibility, structured Ozzy Memory evidence prompts, and
  `scripts/hermes_ai_brief.py`.
- Expanded Gemini briefs to Evidence Pack v2 with bounded LIVE/TESTNET status,
  recent trade, exit quality, milestone, incident, and Ozzy Memory views plus
  explicit insufficient-evidence output fields.
- Added a default `0.5R` first partial milestone that closes 25% before the existing later runner milestones.
- Fixed monitor prune handling so an already-logged `momentum_exit` stays a protective exit instead of being relabeled as `sl`.
- Disabled high-frequency `TRAIL_DEBUG` structured log spam by default; enable with `HERMES_MONITOR_TRAIL_DEBUG_LOGS=true` only when tracing trailing behavior.

## 2026-05-18 — Live Launch Prep Complete

### Dynamic ATR Multiplier
- `movement_policy.py`: Quiet markets get `* 1.33` ATR multiplier, fast markets `* 0.80`
- Prevents stop-runs in low-volatility conditions, tightens stops in volatile regimes

### Position & Risk Hardening
- `MAX_POSITIONS`: 3 → 5 (later tuned to 3 for $500 launch)
- `MAX_LOT_SIZE`: Fixed `0.1` → `1000.0` for Binance coin-quantity assets
- `binance_connector.py`: Respects webhook `lot` parameter, syncs DB via `trade_db.update_trade_qty()`

### Monitor Stability & State Recovery
- `binance_monitor.py`: Added `_recover_state_from_db()` — restores `original_qty`, `milestones_hit`, `breakeven_moved`, `trailing_active`, `current_sl`, `peak_pnl` from SQLite after restart
- Fixed `positionAmt` → `volume` bug across all monitor functions
- Fixed undefined `amt` variable in milestone/tiered/choch functions
- Breakeven duplicate protection: `_check_breakeven` checks DB `milestones` table before moving SL
- Exit reason inference: Distinguishes `TRAILING_STOP_MARKET`, `STOP_MARKET`, `MARKET` closes
- `_prune_state` uses inferred exit reason for accurate `close_trade` logging

### Infrastructure & Monitoring
- `scripts/health_check.sh`: Checks the active live-micro webhook/monitor path before alerting
- Cron bug fixed: `&&` → `;` between health check and alert sender; added `XDG_RUNTIME_DIR=/run/user/1000`
- Systemd auto-start fixed: `WantedBy=multi-user.target` → `default.target`; moved `StartLimitIntervalSec`/`StartLimitBurst` to `[Unit]`
- `scripts/backup.sh`: Creates timestamped tar.gz with DB, logs, configs; keeps last 10 backups

### Documentation
- Added `docs/FINANCIAL_MODEL.md`: 12-month return projections, phased risk scaling, withdrawal strategy
- Added `docs/STRATEGIC_ROADMAP.md`: Quarterly milestones from live launch through Q1 2027
- Added `docs/LIVE_PLAYBOOK.md`: Step-by-step live switch checklist, daily ops, emergency procedures

### Live Validation (Testnet)
- **ETH short**: 3.2 ETH @ $2,144.50 → Milestones at 1R/1.5R/3R, runner stopped at breakeven ~$2,116.86. Total locked ~$172.77
- **LINK short**: 385.61 @ $9.72 → 50% partial at 1.5R (~$42.42), runner closed via trailing stop at ~$9.48 (~$45.50). Total ~$87.92
- Both trades validated monitor logic: breakeven, milestones, partial closes, trailing stops, state recovery

## 2026-05-01 11:30 SAST
- **BACKTEST:** Completed v2.2.1 vs v2.2.2 comparison across ETH, SOL, XRP
  - XRP: flipped from −$393 to +$574 (PF 0.92 → 1.15) — filters are surgical
  - SOL: +$156 improvement (PF 1.52 → 1.77)
  - ETH: −$513 degradation (PF 1.22 → 1.10) — candle filter too aggressive
- **PINE SCRIPT v2.2.2-patch:** ETH candle-direction override
  - ETH skips `bullishClose`/`bearishClose` but keeps volume + cooldown
  - SOL/XRP retain full accuracy filters
  - Updated `hermes_smc_pro_v222.pine` and `hermes_backtest.pine`
- **TEST FIX:** Made `metaapi_cloud_sdk` import lazy in `connector.py`
  - Installed missing `jsonschema` and `python-binance` into venv
  - All 38 tests now pass

## 2026-04-28 20:xx SAST
- **context_engine.py:** Dynamic position sizing engine added
- Sources: Fear & Greed (alternative.me, free) + Funding Rate (Binance native, free)
- JSON file cache: `fear_greed.json` (6hr TTL), `funding_rate.json` (4hr TTL)
- Sizing logic: 0x skip → 0.5x down → 1.0x normal → 1.75x up
- Hard cap: max 8% risk per trade regardless of multiplier
- Wired into `webhook.py` after all filters, before APPROVED log
- `binance_connector.py`: accepts `risk_pct_override` parameter
- Firecrawl for news deferred to Phase 2
- Coinglass rejected — Binance native funding rates used instead

## 2026-04-28 19:xx SAST
- **binance_connector.py:** Added `BINANCE_MIN_NOTIONAL` guard
- Bumps ETH notional to $20 floor if calculated size falls short
- Logs `BINANCE_MIN_NOTIONAL_BUMP` when triggered
- ETH leverage: 5x → 20x
- SOL leverage: 5x → 10x

## 2026-04-28
- **LIVE:** Switched from Binance testnet to live futures trading
- **FIX:** NTP clock sync enabled — eliminated `recvWindow` timestamp errors
- **FIX:** Health check updated — removed dead `breakeven_monitor.py` dependency, added auto-midnight `day_equity.json` rollover
- **SECURITY:** All API keys moved from `config.py` to `.env` file (12 secrets)
- **RISK:** Changed from static `$2` risk to percentage-based `RISK_PCT = 0.05` (5% of equity per trade)
- **AUTO-TUNE:** Wired `rejection_tracker.py` into `webhook.py` — filter thresholds now auto-update on each signal cycle based on backfilled outcomes
- **SYMBOLS:** Dropped BTC and XRP. Active symbols: ETH + SOL only.
  - BTC PF 0.818 (losing), XRP PF 0.912 (losing)
  - ETH PF 1.217 (profitable), SOL PF 1.524 (profitable)
- **PINE SCRIPT:** Updated `hermes_smc_pro.pine` to v2.2.1 — toxic hour filter now uses `hour(time, "UTC")` instead of chart-local timezone

## 2026-04-27
- Added `binance_monitor.py` as systemd service — position protector with breakeven, trailing stops, tiered profit-taking
- Added `review_console.py` + `templates/review_console.html` — local signal review dashboard at `/review`
- Added `crypto_entry_policy.py` v2026-04-25b — modular pullback vs momentum breakout classification

## 2026-04-25
- Switched execution routing from MetaAPI/Exness to Binance Futures
- Added `binance_connector.py` — drop-in Binance Futures REST API client
- Added per-symbol toxic hour filter (v2.2.0) blocking statistically losing UTC hours per symbol
- Created `docs/plans/` directory with planning documents

## 2026-04-22
- Added `binance_indicators.py` — local indicator engine using Binance public klines
- Lowered volume threshold from 0.85 to 0.75

## 2026-04-19
- Enabled `STRICT_SCHEMA_VALIDATION = True` in `config.py`
- Fixed `historical_ohlc.py` entry-time bug that caused false outcome evaluations
- Added `signal_review.py` closed-loop system: log → review → OHLC backfill → filter impact analysis

## 2026-04-18
- Added `sentiment_filter.py` — macro-direction confluence layer
- Added `movement_policy.py` — ATR SL validation + market movement classification
- Added `filter_policy.py` — reusable RSI/volume/EMA validators
- EMA overextension check added (max 5% from EMA200)

## 2026-04-17
- Kill zone bypass added for EUR/GBP/JPY (data showed 100% win rate when blocked)
- RSI thresholds adjusted: BUY max 78→80, SELL min 22→20 (signal review showed 4/4 blocked winners)
- `paper_tracker.py` created for paper trade sync

## 2026-04-16
- Project initialized with `webhook.py`, `bot.py`, `config.py`, `connector.py`
- MetaAPI/Exness integration for FX/Gold trading
- Telegram notification system
