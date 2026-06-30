# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Hermes is an autonomous trading bot built around a **unified core with explicit lanes**. Signal sources (lanes) POST candidate setups to `/webhook`; Flask validates lane membership, cross-references against live Binance indicators, and Binance USD-M Futures executes the trade. A post-entry monitor manages open positions.

Mode is selected by the `BINANCE_TESTNET` flag (loaded from the `HERMES_BINANCE_TESTNET` env var or `HERMES_MODE`). There is only one runtime instance; testnet vs live is an environment switch, not a parallel deployment.

See the full architecture specification at:
`docs/superpowers/specs/2026-06-17-ozzybot-unified-core-design.md`

## Running the system

```bash
# Start the webhook (mode comes from env / config)
python3 webhook.py

# Start the lifecycle monitor
python3 binance_monitor.py

# Start the Telegram command bot
python3 telegram_command_bot.py

# Or use systemd user services
systemctl --user start ozzybot-webhook ozzybot-monitor ozzybot-telegram-cmd

# Test a signal end-to-end (webhook resolves lane from source/strategy/setup fields)
curl -s -X POST http://127.0.0.1:5000/webhook \
  -H "Content-Type: application/json" \
  -d "{\"secret\":\"YOUR_WEBHOOK_SECRET\",\"signal\":\"BUY\",\"symbol\":\"ETHUSDT\",\"entry\":1633.96,\"source\":\"signal_generator\",\"strategy\":\"pullback\",\"version\":\"2.2.2\",\"timestamp\":$(date +%s),\"regime\":\"smc_pro\",\"structure\":\"bullish_bos\",\"bias\":\"bullish\"}"

# Check system status
curl -s http://127.0.0.1:5000/status

# Verify Binance Futures balance + positions
python3 -c "from binance_connector import get_open_positions, get_balance; import json; print(json.dumps({'positions': get_open_positions(), 'balance': get_balance()}, indent=2))"

# Pull live Binance indicators for a symbol
python3 -c "from binance_indicators import get_live_indicators; import json; print(json.dumps(get_live_indicators('ETHUSDT', '1h'), indent=2))"
```

## Signal validation pipeline (`webhook.py`)

Every incoming signal passes ~15 sequential gates before execution:

1. Auth — `WEBHOOK_SECRET` header check
2. Schema validation (`schemas/signal_payload.json`)
3. Parse signal, **lane**, symbol, entry price
4. **Lane enforcement** — reject if lane is undefined, disabled, or symbol is not in the lane universe
5. **Lane risk budget / position cap** — reject if the lane has exhausted its budget or caps
6. News pause — `NEWS_PAUSE` flag in config
7. Kill zone — London 09:00–12:00 / NY 14:00–17:00 SAST; crypto always passes
8. Daily drawdown halt (reads `day_equity.json`)
9. Global open-position caps (`MAX_POSITIONS`, `MAX_POSITIONS_PER_SYMBOL`, pyramiding rules)
10. In-process pending check (prevents duplicates during execution latency)
11. Live indicator fetch (Binance local klines via `binance_indicators.py`)
11a. SuperTrend conflict — rejects if live direction disagrees with signal direction
11b. RSI exhaustion — strategy-dependent thresholds
11c. Volume confirmation — current volume vs 20-period average
11d. EMA overextension / proximity gate
12. ATR-based SL/TP calculation + range validation + RR verification
13. Lot sizing + hard cap + margin cap + notional floor
14. Log `APPROVED` — includes full `live` indicator snapshot
15. Execute — `binance_connector.place_trade()` places entry + SL/TP on Binance Futures
16. Telegram — `notify_approved()` or `notify_rejected()`
17. Return JSON

## Indicator data

Local Binance kline calculation is the primary data source. All crypto indicators are computed locally from Binance klines via `binance_indicators.py`.

- **ETHUSDT, SOLUSDT, LINKUSDT, SUIUSDT, etc.** — live 1H/15m ATR + SuperTrend/RSI/EMA/Volume

## Binance execution architecture

`binance_connector.py` places trades directly via `python-binance`. Hedge Mode is enforced with `positionSide`. Each call is a direct REST request; no long-lived socket connection is required.

`place_trade()` places:

1. Market entry
2. `STOP_MARKET` SL at 1R
3. `TAKE_PROFIT_MARKET` TP1 at 0.5R
4. `TAKE_PROFIT_MARKET` TP2 at full RR

Before finalization it runs `confirm_placed_protection()` to verify SL/TP are visible on the exchange.

## Position tracking

Two layers prevent duplicate orders for the same symbol:

1. **Binance position cache** — background state refreshed from exchange open positions + algo orders
2. **In-process `_pending` dict** — marks a symbol as occupied at `APPROVED`, cleared when trade placement resolves

## Key operational facts

- **Signal sources** — `signal_generator.py` and lane scanners run on timers and POST JSON to the local `/webhook`; execution still goes through the same `/webhook` path
- **Symbol style** — use `ETHUSDT`, `SOLUSDT`, etc.
- **Lot sizing** — coin quantity derived from risk dollars / SL distance, bounded by leverage + step size + notional floor
- **Mode** — `testnet` or `live` selected by `BINANCE_TESTNET` (env var `HERMES_BINANCE_TESTNET` or `HERMES_MODE`)
- **Lanes** — every signal must resolve to a defined, enabled lane in `config.LANES`; the symbol must be in that lane's universe
- **PAPER_MODE** — set `PAPER_MODE = True` in `config.py` to log and Telegram without placing real orders. All other pipeline logic runs identically.
- **Monitor** — `binance_monitor.py` polls positions every 30 s, reconciles exchange vs `trades.db`, repairs missing protection, and runs early-profit protection (pickpocket rule).

## Log files

| File | Written by | Contents |
|------|-----------|----------|
| `trades.log` | `logger.py`, systemd services | All events: `SIGNAL_IN`, `APPROVED`, `REJECTED`, `TRADE_PLACED`, `TRADE_ERROR`, `BREAKEVEN`, `MILESTONE` |
| `webhook.log` | systemd journal | Flask HTTP access log + unhandled stderr |
| `binance_monitor.log` | systemd journal | Monitor events, PnL reports, protection changes, reconciliation |
| `paper_trades.json` | `bot.py` / paper tracking | Trade outcomes used for drawdown/paper tracking |

## Indicator parameters

`_ST_PERIOD = 10`, `_ST_MULTIPLIER = 3` (in `binance_indicators.py`). ATR and RSI are calculated locally from Binance klines for the main crypto universe.
