# AGENTS.md — Hermes Trading Bot (OzzyBot)

> **Read this first.** This file is the single source of truth for AI coding agents working on this repository. It assumes you know nothing about the project.

---

## 1. Project Overview

**Hermes** (a.k.a. **OzzyBot**) is an autonomous crypto-futures trading bot written in Python. Signal sources (lanes) POST candidate setups to the local `/webhook`; Flask validates them against lane config and live indicators, then executes on **Binance USD-M Futures**.

- **Name**: `hermes-trading-bot` (`pyproject.toml`)
- **Version**: `2.0.0`
- **Language**: Python >= 3.11
- **Status**: Unified-core migration in progress as of 2026-06-17
- **Execution backend**: Binance USD-M Futures only
- **Mode**: `testnet` or `live` selected by the `BINANCE_TESTNET` flag (loaded from the `HERMES_BINANCE_TESTNET` env var or `HERMES_MODE`)
- **Architecture**: unified core with explicit lanes
- **Active symbols**: defined per lane in `config.LANES`
- **Primary timeframe**: `1H` for the trend lane (other lanes may use `15m`)
- **Risk per trade**: configurable via `RISK_PCT` (default ~2 % of equity)
- **Leverage**: configured per symbol in `binance_connector.py`

### High-Level Signal Flow

1. A lane source (`signal_generator.py`, `scripts/15m_reversion_scanner.py`, `core/openclaw_breakout_executor.py`, etc.) fires a JSON webhook to `/webhook`.
2. `webhook.py` authenticates, validates the schema, resolves the lane, and checks that the lane is enabled and the symbol is in its universe.
3. Live indicators are fetched from Binance public klines via `binance_indicators.py`.
4. Filters run: RSI exhaustion, volume confirmation, EMA proximity, crypto-entry policy (pullback vs momentum), sentiment, SuperTrend conflict.
5. ATR-based SL/TP are calculated; RR must be >= `MIN_RR` (2.5).
6. Position size is computed from risk %; the context engine may scale size up/down based on market regime and funding rates.
7. The trade is sent to **Binance Futures** via `binance_connector.py`.
8. Telegram notifications fire for every approval/rejection/error.
9. Post-entry, `binance_monitor.py` manages breakeven, trailing stops, tiered profit-taking, early-profit protection, reconciliation, and trade-duration warnings.

---

## 2. Technology Stack

| Layer | Technology |
|-------|------------|
| Runtime | Python 3.11+ |
| Web framework | Flask (`webhook.py`) |
| Exchange API | `python-binance` (REST) |
| Indicator data | Binance public klines + `pandas`/`numpy` local calc |
| Telegram | `requests` polling bot (`telegram_command_bot.py`) |
| Data persistence | SQLite (`trades.db`) + JSON files (`signal_reviews.json`, `day_equity.json`, `trades.log`) |
| Position sizing context | `alternative.me` (Fear & Greed), Binance funding-rate API |
| Process supervision | systemd (preferred) |
| Tunnel | `cloudflared` (named tunnel `ozzybot`) |
| Lint / Format | `ruff` (configured in `pyproject.toml` and `.vscode/settings.json`) |
| Testing | `unittest` (standard library) |

### Key Dependencies

There is **no `requirements.txt` or `poetry.lock`** in the repo. Dependencies were installed manually into `venv/`. The following packages are required for the system to run:

- `Flask`
- `python-binance`
- `requests`
- `pandas`
- `numpy`
- `jsonschema`
- `python-dotenv`
- `pytz`
- `google-genai` — optional Gemini Hermes Advisor model client

If you add a new dependency, document it here and install it into the project venv.

---

## 3. Project Structure & Module Map

```
.
├── pyproject.toml               # Project metadata + ruff config only
├── config.py                    # Central config: assets, lanes, thresholds, secrets read from .env
├── .env                         # API keys (NEVER COMMIT)
│
├── webhook.py                   # Flask app — signal validation & execution pipeline
├── bot.py                       # Core trading math (lot size, ATR levels, kill zone, drawdown)
├── binance_connector.py         # Binance Futures REST client — sole execution backend
├── command_center.py            # Trade-management command engine (close, breakeven, trail, update SL/TP)
├── telegram_command_bot.py      # Polling Telegram bot that routes commands to command_center
│
├── binance_monitor.py           # Post-entry monitor (breakeven, trailing stops, tiered exits, PnL reports)
│
├── context_engine.py            # Dynamic position sizing based on Fear & Greed + funding rates
├── crypto_entry_policy.py       # Pullback vs momentum breakout classification for crypto
├── filter_policy.py             # Reusable RSI / volume / EMA validators
├── movement_policy.py           # ATR-based SL validation + market-movement classification
├── sentiment_filter.py          # Macro-direction confluence filter
├── rejection_tracker.py         # Auto-tunes filter thresholds from backfilled signal-review outcomes
├── risk_policy.py               # Daily stop, lane budget, and drawdown enforcement
├── trade_db.py                  # SQLite trade journal (single source of truth)
│
├── signal_review.py             # Signal-review persistence + OHLC outcome backfill
├── review_console.py            # Builds dashboard context for HTML review page
├── binance_indicators.py        # Local indicator calc from Binance public klines
├── historical_ohlc.py           # OHLC fetching for outcome evaluation
├── request_utils.py             # JSON payload parsing + schema validation
├── telegram_client.py           # Telegram notification helpers
├── logger.py                    # Simple JSON line logger → trades.log
├── trade_journal.py             # Local CSV journal for approved trades
│
├── core/                        # Lane executors + macro scout + lifecycle helpers
│   ├── macro_scout.py
│   ├── trend_executor.py
│   └── openclaw_breakout_executor.py
│
├── schemas/signal_payload.json  # Webhook payload contract for signal sources
├── templates/review_console.html# Signal-review dashboard template
├── systemd/                     # systemd service files
├── scripts/                     # health_check.sh, send_health_alert.py, lane scanners, obsidian export
├── tests/                       # unittest modules (see §5)
└── docs/                        # PROJECT.md, DECISIONS.md, PHASES.md, CHANGELOG.md
```

### Critical Module Contracts

- **`webhook.py`** must stay non-blocking. All long-running I/O (trade placement, indicator fetches) happens in background threads or external calls.
- **`binance_connector.py`** is the only execution backend. `webhook.py` and monitors call it directly.
- **`config.py`** is the single source of truth for all constants. `DYNAMIC_THRESHOLDS` is mutated at runtime by `rejection_tracker.py`.
- **`trade_db.py`** is the single source of truth for trade history. The exchange is the only source of truth for open positions.

---

## 4. Configuration & Secrets

### Environment Variables (`.env`)

All secrets live in `.env` and are loaded via `python-dotenv` in `config.py`. The file **must never be committed**.

Variables referenced in `config.py`:

- `HERMES_MODE` — `testnet` or `live`
- `HERMES_BINANCE_TESTNET` — `True`/`False` override for `BINANCE_TESTNET`
- `BINANCE_API_KEY`, `BINANCE_API_SECRET` — live Binance Futures
- `BINANCE_DEMO_API_KEY`, `BINANCE_DEMO_API_SECRET` — Binance testnet
- `TELEGRAM_TOKEN`, `TELEGRAM_CHAT_ID` — Telegram bot
- `WEBHOOK_SECRET` — incoming webhook auth
- `GEMINI_API_KEY` — optional Gemini advisor

### Static Config (`config.py`)

- `PAPER_MODE = False` — set to `True` to log + Telegram without placing real orders.
- `BINANCE_TESTNET = False` — `False` = live futures; `True` = testnet.
- `STRICT_SCHEMA_VALIDATION = True` — rejects malformed payloads.
- `LANES` dict — per-lane specs: symbols, timeframe, risk budget, position caps, enabled flag, signal sources.
- `ASSETS` dict — per-symbol specs: contract size, SL range, leverage.
- `DYNAMIC_THRESHOLDS` — mutable thresholds updated by the rejection tracker.

---

## 5. Build, Run & Test Commands

### Activate Virtual Environment

```bash
source venv/bin/activate
```

### Run the Webhook (standalone)

```bash
python webhook.py
```

Flask binds to port `5000` by default. Mode is selected by env/config, not by running a second instance.

### Run the Binance Monitor (post-entry protection)

```bash
python binance_monitor.py
```

### Run the Telegram Command Bot

```bash
python telegram_command_bot.py
```

### Systemd Services

```bash
# User-level services
systemctl --user enable ozzybot-live-micro-webhook ozzybot-live-micro-monitor ozzybot-telegram-cmd
systemctl --user start ozzybot-live-micro-webhook ozzybot-live-micro-monitor ozzybot-telegram-cmd
```

Additional timers manage signal generation, lane scanners, obsidian export, and health checks (see `systemd/`).

### Health Check

```bash
bash scripts/health_check.sh
```

Sends a Telegram alert on failure via `scripts/send_health_alert.py`.

### Lint / Format

```bash
# Check
ruff check .

# Auto-fix & format
ruff check --fix .
ruff format .
```

VS Code is configured to format on save with ruff (see `.vscode/settings.json`).

### Testing

The project uses **unittest**, **not pytest**.

```bash
# Discover and run all tests
python -m unittest discover -s tests -p "test_*.py" -v

# Run a single module
python -m unittest tests.test_filter_policy -v
```

**Convention:** name new test files `test_<module>.py` and place them in `tests/`.

---

## 6. Code Style Guidelines

- **Formatter**: `ruff` (line length 120, indent 4 spaces, double quotes).
- **Docstrings**: Google convention (`tool.ruff.lint.pydocstyle.convention = "google"`).
- **Imports**: sorted automatically by ruff on save.
- **Typing**: Python 3.11+ syntax is used (`str | None`, `dict[str, Any]`, etc.).
- **Logging**: always use `plain_log(event_name, dict_of_data)` from `logger.py`. Events are JSON lines appended to `trades.log`.
- **Constants**: define in `config.py`; do not hard-code thresholds in business logic.
- **PAPER_MODE**: any code that touches the broker must respect `PAPER_MODE` and skip real orders.
- **Fail-open for notifications**: Telegram must never crash a trade. Wrap Telegram calls in try/except.
- **Fail-closed for risk**: missing data (stale cache, no baseline equity) should block trading, not allow it.

---

## 7. Runtime Architecture

### Webhook Pipeline (`webhook.py`)

Incoming signals pass ~15 sequential gates before execution:

1. Auth (`WEBHOOK_SECRET`)
2. Schema validation (`schemas/signal_payload.json`)
3. Parse signal, lane, symbol, entry price
4. Lane lookup — reject if the lane is undefined, disabled, or the symbol is not in its universe
5. Lane risk-budget and position-cap check
6. News pause guard
7. Kill zone check (London / NY SAST; crypto bypasses)
8. Daily drawdown halt (reads `day_equity.json`)
9. Global open-position caps (`MAX_POSITIONS`, `MAX_POSITIONS_PER_SYMBOL`, pyramiding rules)
10. In-process pending check (prevents duplicates during execution latency)
11. Live indicator fetch (`binance_indicators.py`)
12. Per-strategy indicator gate (breakout / pullback / momentum / structure / SuperTrend)
13. RSI exhaustion check (strategy-dependent thresholds)
14. Volume confirmation check
15. Context-engine size multiplier
16. ATR-based SL/TP calculation + range validation + RR verification
17. Execution → Binance Futures (background thread)
18. Telegram notification + signal review record

### Position Tracking (Duplicate Prevention)

Two layers prevent duplicate orders:

1. **Binance position cache** — background thread in `webhook.py` refreshes every 5 min.
2. **In-process `_pending` dict** — marks a symbol as occupied at "APPROVED", cleared on `TRADE_PLACED` or `TRADE_ERROR`.

### Post-Entry Monitors

- **`binance_monitor.py`** (systemd-managed):
  - Polls Binance positions every 30 s and reconciles them against `trades.db`.
  - Breakeven at 1R profit.
  - Trailing stops (ATR / percent / fixed) triggered via `command_center`.
  - Tiered exits: 50 % at 1.5R, 25 % at 2.5R, 25 % at 3.5R.
  - Early-profit protection (pickpocket rule) on short-term spikes.
  - Trade-age warnings (> `MAX_TRADE_HOURS`).
  - PnL report every 5 min.

### Command Center (`command_center.py`)

Validates and executes trade-management commands with guardrails:

- `status` — show open positions + equity
- `close <symbol> [pct%]` — full or partial close
- `breakeven <symbol>` — move SL to entry
- `trail <symbol> <mode> <param>` — activate trailing stop
- `update_sl / update_tp` — modify SL/TP (guards prevent widening SL or dropping RR below minimum)

The Telegram bot (`telegram_command_bot.py`) parses natural-language-ish commands and routes them here.

---

## 8. Security Considerations

- **Secrets**: all API keys are in `.env`. Never print, log, or commit them.
- **Webhook Auth**: every payload must carry the correct `secret` field.
- **Schema Validation**: `STRICT_SCHEMA_VALIDATION = True` rejects payloads that drift from the signal schema.
- **Telegram Authorization**: the command bot only responds to the configured `TELEGRAM_CHAT_ID`.
- **Binance recvWindow**: set to 60 s to avoid timestamp-skew rejections.
- **Risk Limits**: hard-coded caps (`MAX_LOT_SIZE`, `MAX_POSITIONS`, `DAILY_DRAWDOWN_LIMIT`) are enforced before every trade.
- **Minimum Notional Guard**: `binance_connector.py` bumps quantity to meet Binance’s minimum-notional floor and logs the override.
- **SQLite**: `trades.db` is the canonical trade journal. Back it up before schema migrations.

---

## 9. Deployment & Operations

- **Primary deployment**: systemd user services (`systemd/`).
- **External access**: `cloudflared tunnel run ozzybot` exposes `https://webhook.ozznett.co.za` → `localhost:5000`.
- **Logs**:
  - `trades.log` — structured JSON events from the entire system.
  - `webhook.log` — Flask stdout (managed by systemd journal).
  - `binance_monitor.log` — monitor stdout (managed by systemd journal).
  - `health_check.log` — health-check results.
- **Midnight rollover**: `day_equity.json` is auto-refreshed at midnight by the cache loop in `webhook.py`. If stale, trading halts until restart.

---

## 10. Conventions for Agents

### When Adding a New Filter

1. Implement the validation logic in a dedicated module (e.g., `filter_policy.py`, `crypto_entry_policy.py`).
2. Wire it into `webhook.py` at the appropriate gate.
3. On rejection, call `_record_signal_review(..., filter_name="your_filter", filter_value=..., filter_reason=...)` so the rejection tracker can analyze it.
4. If the filter should be auto-tuned, add its name to `rejection_tracker.py` `delta_map` and `config.py` `DYNAMIC_THRESHOLDS`.

### When Modifying Execution

- Mirror changes across `binance_connector.py` and `command_center.py` if they affect SL/TP placement or position closing.
- Remember Binance stores SL/TP as **separate orders** (`STOP_MARKET` / `TAKE_PROFIT_MARKET`), not fields on the position object.
- Respect `PAPER_MODE`.

### When Adding a New Symbol

1. Add the symbol to the appropriate lane in `config.py` `LANES`.
2. Add an entry to `config.py` `ASSETS` with correct `contract_size`, `min_sl`, `max_sl`, and leverage.
3. Add symbol/leverage mapping in `binance_connector.py` if it is not already covered.
4. Add to `KILL_ZONE_BYPASS_SYMBOLS` if it trades 24/7.
5. Update tests.

### When Changing Risk Parameters

- Update both the static constant in `config.py` **and** the `DYNAMIC_THRESHOLDS` dict if the parameter is auto-tuned.
- Document the change in `docs/CHANGELOG.md` and `docs/DECISIONS.md`.

---

## 11. Useful Reference Files

| File | Purpose |
|------|---------|
| `docs/PROJECT.md` | Master project document — current state, success metrics, hard rules |
| `docs/DECISIONS.md` | Decision log with rationales |
| `docs/PHASES.md` | Rollout plan |
| `docs/CHANGELOG.md` | Chronological change history |
| `docs/superpowers/specs/2026-06-17-ozzybot-unified-core-design.md` | Unified-core architecture specification |
| `CLAUDE.md` | Operational cheat-sheet (commands, log files, SuperTrend params) |
| `schemas/signal_payload.json` | signal_generator ↔ webhook contract schema |
| `systemd/*.service` | systemd unit definitions |

---

*Last updated: 2026-06-17*  
*If you change project conventions, build steps, or deployment procedures, update this file immediately.*
