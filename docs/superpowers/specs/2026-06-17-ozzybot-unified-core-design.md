# OzzyBot Unified Trading Core — Design Specification

**Date:** 2026-06-17  
**Status:** Approved — ready for implementation plan  
**Approach:** A — Unified Trading Core with Explicit Lanes  
**Author:** Kimi Code CLI  
**Scope:** `/home/rick/ozzy-bot`

---

## 1. Context

OzzyBot (Hermes) has evolved into a fragmented system. At time of writing the trading stack is halted, monitors are stopped, Telegram is in a polling conflict, and two parallel instances (testnet on port 5000 and live-micro on port 5001) maintain separate databases, logs, and state. Dead MetaAPI/Exness code, standalone OpenClaw loops, and orphaned adapter packages still live in the repo. The result is that the system cannot be trusted: it is unclear whether execution is active, whether open positions are protected, or whether reports reflect reality.

This specification defines a unified architecture with explicit trading lanes, a single source of truth, and a clear operator model.

---

## 2. Design Goals

1. **One runtime, one database, one truth.** All trade state lives in a single SQLite database. `testnet` vs `live` is a single environment flag, not a parallel deployment.
2. **Lanes are first-class configuration objects.** A lane is a signal source + symbol universe + timeframe + risk budget + on/off switch. Lanes run inside the unified core.
3. **Fail-closed by default.** Missing monitor, missing DB, missing exchange connection, or active HALT stops new risk.
4. **No misleading telemetry.** Telegram and Obsidian report only verified state. Unknown state is reported as unknown.
5. **Delete the dead.** MetaAPI, legacy monitors, standalone OpenClaw V2, and orphaned adapters are removed.
6. **5-year maintainability.** Every module has one clear purpose and one clear owner.

---

## 3. Decision: Approach A

We reject the alternatives:

- **Approach B (Lane-as-a-Service)** preserves the split-brain complexity we are trying to eliminate.
- **Approach C (Surgical cleanup only)** will restart trading but will not prevent the same fragmentation from recurring.

**Approach A — Unified Trading Core with Explicit Lanes** is selected because it directly addresses the root cause: multiple independent runtimes with overlapping responsibilities.

---

## 4. Target Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│  Signal sources (lanes)                                         │
│  ├─ 1H trend lane        → signal_generator.py                  │
│  ├─ 15m mean-reversion   → scripts/15m_reversion_scanner.py     │
│  ├─ 15m reversal capture → scripts/15m_reversal_capture_scanner │
│  └─ OpenClaw macro lane  → core/macro_scout.py                  │
│                            → core/trend_executor.py             │
│                            → core/openclaw_breakout_executor.py │
└────────────────────────────┬────────────────────────────────────┘
                             │ POST /webhook
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│  Hermes Core (single process)                                   │
│  ├─ webhook.py        — auth, schema, HALT, gates, execution    │
│  ├─ risk_policy.py    — daily stop, lane budget, drawdown       │
│  ├─ binance_connector.py — Binance USD-M REST execution         │
│  ├─ command_center.py — operator commands                       │
│  └─ trade_db.py       — SQLite journal (single source of truth) │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│  Lifecycle Monitor (single process)                             │
│  ├─ binance_monitor.py — breakeven, trailing, tiered exits      │
│  ├─ reconciliation   — exchange vs DB, orphan repair            │
│  └─ health reporter  — Telegram + Obsidian                      │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│  Operator & Knowledge interfaces                                │
│  ├─ telegram_command_bot.py — commands + truthful alerts        │
│  ├─ scripts/export_obsidian_journal.py — vault export           │
│  ├─ ozzybot_doctor.py — watchdog + scorecard                    │
│  └─ scripts/health_check.sh — liveness probe                    │
└─────────────────────────────────────────────────────────────────┘
```

### 4.1 Runtime boundaries

| Process | Responsibility | Must be running to trade? |
|---|---|---|
| `webhook.py` | Signal ingestion, validation, execution | Yes |
| `binance_monitor.py` | Post-entry protection, reconciliation | Yes |
| `telegram_command_bot.py` | Operator commands | No (trading can continue) |
| `export_obsidian_journal.py` | Knowledge export | No |
| `ozzybot_doctor.py` | Health watchdog | No |

If the monitor process is not running, the webhook must reject new signals until it returns.

---

## 5. Lanes

A **lane** is the only way a signal reaches execution. Lanes are defined in `config.py` and are immutable at runtime except for an `enabled` flag controlled by the operator.

### 5.1 Lane schema

```python
LANES: dict[str, LaneConfig] = {
    "1H_TREND": {
        "symbols": ["ETHUSDT", "SOLUSDT", "LINKUSDT", "SUIUSDT"],
        "timeframe": "1h",
        "risk_budget_pct": 0.40,
        "max_positions": 4,
        "max_positions_per_symbol": 1,
        "enabled": True,
        "signal_sources": ["signal_generator"],
    },
    "15M_MEAN_REVERSION": {
        "symbols": ["LINKUSDT", "BNBUSDT"],
        "timeframe": "15m",
        "risk_budget_pct": 0.30,
        "max_positions": 2,
        "max_positions_per_symbol": 1,
        "enabled": True,
        "signal_sources": ["15m_reversion_scanner"],
    },
    "OPENCLAW_BREAKOUT": {
        "symbols": ["# TODO: define symbol universe in Open Question 1"],
        "timeframe": "15m",
        "risk_budget_pct": 0.30,
        "max_positions": 3,
        "max_positions_per_symbol": 1,
        "enabled": True,
        "signal_sources": ["openclaw_breakout_executor"],
        "setup_types": {"BREAKOUT", "RETEST"},
    },
}
```

### 5.2 Lane enforcement in webhook.py

For every incoming signal the webhook must:

1. Identify the lane from `strategy_label` / `source_service` / `entry_setup_label`.
2. Reject if the lane is not defined or not enabled.
3. Reject if the symbol is not in the lane's symbol list.
4. Reject if the lane has exhausted its daily risk budget.
5. Reject if the lane has reached `max_positions` or `max_positions_per_symbol`.
6. Record the lane on every DB row and log line.

### 5.3 Risk budget

- Daily risk budget = `DAILY_LOSS_PCT * start_equity`.
- Each lane gets `risk_budget_pct` of that total.
- When a lane exhausts its budget, no new signals from that lane are accepted.
- Unused lane budget does **not** spill over to other lanes.

### 5.4 Early Profit Protection (Pickpocket Rule)

Because crypto moves fast, the system must treat unrealized profit as temporary until it is locked in. Every lane has an `early_profit_protection` block that acts on short-term spikes without waiting for full R-multiple milestones.

#### Default policy

```python
EARLY_PROFIT_PROTECTION = {
    "enabled": True,
    "first_scale": {
        "profit_r": 0.50,      # when trade reaches +0.5R
        "close_pct": 0.25,     # close 25% of position
        "move_sl_to_breakeven": True,
    },
    "second_scale": {
        "profit_r": 1.00,      # when trade reaches +1.0R
        "close_pct": 0.25,     # close another 25% (total 50% out)
        "move_sl_to_breakeven": True,
    },
    "giveback_guard": {
        "min_peak_r": 0.30,        # only after trade has peaked at +0.3R
        "giveback_pct": 50.0,      # close remaining if it gives back 50% of peak R
        "reason": "early_giveback",
    },
}
```

#### Example

Your trade spikes **+$50** (≈ +1.25R). The monitor sees this on its next 30-second tick:

1. First scale at +0.5R: close 25%, move SL to entry.
2. Second scale at +1.0R: close another 25%.
3. Price reverses and gives back 50% of the peak. Giveback guard closes the remaining 50%.

Result: most of the +$50 is banked. The trade cannot turn into a -$70 loss.

#### Lane-level override

Each lane can tune or disable the rule:

```python
"early_profit_protection": {
    "enabled": True,
    "first_scale": {"profit_r": 0.30, "close_pct": 0.20, "move_sl_to_breakeven": True},
    "giveback_guard": {"min_peak_r": 0.20, "giveback_pct": 40.0},
}
```

#### Awareness, not perfection

- The rule is evaluated every monitor tick, so the very fastest wicks may be missed.
- If the price crashes through the peak faster than one tick, the giveback guard still fires on the next tick if the threshold is breached.
- All actions are logged and Telegram-alerted so the operator knows exactly what was locked in and why.

---

## 6. State Ownership

| State | Owner | Canonical Store |
|---|---|---|
| Open positions + live orders | Exchange | Binance USD-M Futures API |
| Planned / approved / closed trades | `webhook.py` + `binance_monitor.py` | `trades.db` |
| Daily equity baseline | `webhook.py` | `day_equity.json` (derived from DB at midnight) |
| Lane budget consumption | `risk_policy.py` | `trades.db` |
| Market regimes / blueprints | `core/macro_scout.py` | `shared/market_regimes.json` |
| Operator commands | `telegram_command_bot.py` → `command_center.py` | `trades.db` action log |
| Notifications | `telegram_client.py` | Telegram API (stateless) |
| Knowledge base | `export_obsidian_journal.py` | Obsidian vault |

**Rule:** `trades.db` is the only source of truth for trade history. The exchange is the only source of truth for open positions. Reconciliation runs every monitor tick.

---

## 7. Data Flow

### 7.1 Signal → Execution

```
signal source (lane)
  → POST /webhook
    → auth (WEBHOOK_SECRET)
    → HALT check
    → schema validation
    → lane lookup + enabled check
    → symbol / risk-budget / position-cap check
    → live indicators (binance_indicators.py)
    → strategy filters
    → SL/TP/RR calculation
    → lot sizing
    → risk_policy daily stop check
    → trade_db.log_trade(state="planned_entry")
    → binance_connector.place_trade()
      → market entry
      → STOP_MARKET SL
      → TAKE_PROFIT_MARKET TP1 + TP2
      → protection verification
    → trade_db.upsert_binance_order_state()
    → telegram notify
    → HTTP response
```

### 7.2 Post-entry lifecycle

```
binance_monitor.py loop (every 30 s)
  → get_open_positions() from exchange
  → reconcile_orphan_positions()
  → repair_missing_protection()
  → per position:
      → check_breakeven()
      → check_fixed_milestones()
      → check_tiered_exits()
      → check_trailing_stop()
      → check_time_based_exit()
  → report_pnl()
```

### 7.3 Reporting

```
trades.db + shared/*.json
  → export_obsidian_journal.py (every 15 min)
    → Obsidian vault: trade cards, label pages, regime map, daily bleed review
  → report_derivatives_shadow.py (every 6 h)
    → reports/derivatives_shadow_report_YYYYMMDD.md
  → ozzybot_doctor.py (every 10 min)
    → Telegram watchdog alerts
  → health_check.sh (every 5 min)
    → health_check.log + Telegram on failure
```

---

## 8. Health & Operator Model

### 8.1 System states

| State | Meaning | New signals? | Operator action |
|---|---|---|---|
| `HEALTHY` | All required services up, exchange connected, no drawdown halt, no HALT. | Yes | None. |
| `PAUSED` | HALT set, or daily drawdown hit, or monitor down, or DB unreachable. | No | Investigate, then `/resume`. |
| `DEGRADED` | Non-critical issue (Telegram conflict, stale regime file). | Yes | Review, fix when convenient. |

### 8.2 HALT behavior

- HALT is a file (`HALT`) with an optional reason inside.
- When HALT exists, `webhook.py` rejects every signal with reason `HALT_REJECT`.
- Setting HALT also stops signal-generation timers.
- Resuming clears HALT, verifies monitor is running, then restarts timers.

### 8.3 Operator commands

| Command | Effect |
|---|---|
| `/status` | Show system state, open positions, equity, lane health, recent events. |
| `/pause <reason>` | Set HALT, stop signal timers. |
| `/resume` | Verify monitor health, clear HALT, restart timers. |
| `/close <symbol> [pct]` | Manual full or partial close. |
| `/breakeven <symbol>` | Move SL to entry. |
| `/panic` | Close all positions, set HALT. |

### 8.4 Telegram bot conflict resolution

- On startup, `telegram_command_bot.py` calls `deleteWebhook()` and uses a single `getUpdates` polling session.
- A watchdog detects 409 errors and terminates duplicate bot processes.
- Only one bot instance is permitted per token.

---

## 9. Error Handling

| Failure | Behavior |
|---|---|
| Exchange API error during entry | Log, Telegram alert, mark trade as `ERROR`, fail closed. |
| Monitor not running | Webhook returns `PAUSED`; no new signals accepted. |
| DB unwritable | Webhook returns `PAUSED`; system goes fail-closed. |
| Telegram failure | Wrapped in try/except; never blocks trade execution. |
| Obsidian export failure | Logged; never blocks trading. |
| Stale market regime file | Lane marked `DEGRADED`; OpenClaw lane pauses until fresh. |

---

## 10. Database Consolidation

### 10.1 Single database

- `trades.db` becomes the only database.
- `live_micro/trades_live.db` is migrated into `trades.db` with a `lane` / `mode` column, then archived.
- `ozzy_memory.db`, `hermes.db`, and `data/trade_journal.db` are audited; useful data migrated, empty files deleted.

### 10.2 Required schema additions

```sql
ALTER TABLE signals ADD COLUMN lane TEXT NOT NULL DEFAULT 'UNKNOWN';
ALTER TABLE signals ADD COLUMN mode TEXT NOT NULL DEFAULT 'testnet';
ALTER TABLE trades ADD COLUMN lane TEXT NOT NULL DEFAULT 'UNKNOWN';
ALTER TABLE trades ADD COLUMN mode TEXT NOT NULL DEFAULT 'testnet';
ALTER TABLE exits ADD COLUMN lane TEXT;
ALTER TABLE exits ADD COLUMN mode TEXT;
```

A new table `system_events` records operator commands, HALT/resume, and state transitions.

---

## 11. Systemd Service Consolidation

### 11.1 Services to keep

| Service | Runs |
|---|---|
| `ozzybot-webhook.service` | `webhook.py` (mode from env) |
| `ozzybot-monitor.service` | `binance_monitor.py` |
| `ozzybot-telegram-cmd.service` | `telegram_command_bot.py` |
| `ozzybot-signal.timer` + `.service` | `signal_generator.py` |
| `ozzybot-15m-reversion.timer` + `.service` | `scripts/15m_reversion_scanner.py` |
| `ozzybot-openclaw-macro-scout.timer` + `.service` | `core/macro_scout.py` |
| `ozzybot-openclaw-trend-executor.timer` + `.service` | `core/trend_executor.py` |
| `ozzybot-openclaw-breakout-executor.timer` + `.service` | `core/openclaw_breakout_executor.py` |
| `ozzybot-obsidian-export.timer` + `.service` | `scripts/export_obsidian_journal.py` |
| `ozzybot-doctor.timer` + `.service` | `ozzybot_doctor.py` |

### 11.2 Services to remove

- `ozzybot-live-micro-webhook.service`
- `ozzybot-live-micro-monitor.service`
- `ozzybot-live-micro-signal.timer` / `.service`
- `ozzybot-live-micro-15m.timer` / `.service`
- `ozzybot-breakeven.service` (renamed/unified into `ozzybot-monitor.service`)
- `ozzybot-testnet-15m.service` (already retired)

Mode is selected by `/etc/default/ozzybot` or a single env file loaded by all services.

---

## 12. Dead Code Removal

The following files/directories are to be deleted or moved to `archive/`:

- `connector.py` — MetaAPI/Exness wrapper.
- `breakeven_monitor.py` — legacy MetaAPI monitor.
- `run.py` — legacy supervisor.
- `openclaw.py` — standalone V2 loop superseded by `core/` timers.
- `adapters/` package — only consumed by dead `openclaw.py`.
- `executors/` package — only consumed by dead `openclaw.py`.
- `core/position_manager.py`, `core/setup_detector.py`, `core/regime_wind.py` — only consumed by dead `openclaw.py`.
- `data/ohlcv_fetcher.py` — only consumed by dead `openclaw.py`.
- `taapi_client.py` — legacy fallback; crypto uses `binance_indicators.py`.
- `twelvedata_client.py` — not imported by active code.
- `paper_tracker.py` — no active consumer.
- `weekly_report.py`, `win_rate_tracker.py` — no schedule.
- `signal_review_sync.py` — no active caller.
- `migrate_trades_log.py`, `verify_migration.py` — one-off utilities.
- `fix_rejection_reasons.py`, `extract_rejection_reasons.py` — one-off cleanup.
- `audit_and_fix_outcomes.py`, `final_audit.py` — one-off audits.
- `binance_scalper.py` — no active caller.
- `chart_generator.py` — no active caller.
- `milestone_report.py` — no active caller.
- `analyze_volume_thresholds.py` — one-off analysis.
- `data/trade_journal.db` — 0 bytes.
- `hermes.db` — 0 bytes.
- `freqtrade/` — separate project, not referenced.
- `ARCHIVE_TV/`, `archive/deprecated/` — already archive.
- Backup test files in `tests/`.

**Caveat:** Some legacy files are still imported by `webhook.py` (e.g., `connector`, `rejection_tracker`). They will be removed in dependency order during implementation.

---

## 13. Migration Phases

### Phase 1 — Stop the bleeding

1. Set explicit HALT with reason.
2. Kill duplicate Telegram bot processes.
3. Confirm zero open positions on exchange.
4. Merge or archive `live_micro/trades_live.db` into `trades.db`.
5. Document current equity and drawdown.

### Phase 2 — Remove dead code

1. Delete files/directories listed in §12.
2. Remove MetaAPI env vars from `.env` and `config.py`.
3. Update imports in `webhook.py` and `binance_monitor.py`.
4. Update `AGENTS.md` and `CLAUDE.md`.

### Phase 3 — Unify runtime

1. Collapse to one `webhook.py` instance controlled by `BINANCE_TESTNET` env var.
2. Collapse to one `binance_monitor.py`.
3. Introduce `LANES` config in `config.py`.
4. Add lane enforcement to `webhook.py`.

### Phase 4 — Harden lifecycle

1. Move reconciliation loop into `binance_monitor.py` as a first-class phase.
2. Run protection-order truth finalizer on every monitor tick.
3. Make webhook auto-pause if monitor is not running.
4. Add `system_events` table for operator actions.
5. Implement `EARLY_PROFIT_PROTECTION` in `binance_monitor.py` with first scale, second scale, and giveback guard per §5.4.

### Phase 5 — Reporting truth

1. Update `export_obsidian_journal.py` to read only from unified `trades.db`.
2. Fix derivatives shadow outcome correlation using DB data.
3. Fix `ozzy_context_observer.py` and `ozzybot_doctor.py` to check `ActiveState`, not just log greps.
4. Schedule ad-hoc reports or delete them.

---

## 14. Risks & Mitigations

| Risk | Mitigation |
|---|---|
| Deleting code that is still needed | Audit imports before deletion; archive rather than delete where uncertain. |
| DB merge loses data | Backup both DBs first; migration script is idempotent and tested. |
| Lane isolation too rigid | Start with conservative budgets; adjust after first week of live data. |
| Monitor auto-pause creates false stops | Health check uses `ActiveState` plus a recent heartbeat file. |
| Single process becomes a bottleneck | Profile before optimizing; current volume is far below any single-process limit. |

---

## 15. Success Criteria

1. Only one `trades.db`, one `webhook.py`, one `binance_monitor.py`.
2. Every signal is tagged with a lane; undefined lanes are rejected.
3. `/status` reports real `ActiveState` of services, not log greps.
4. Telegram 409 conflict is eliminated.
5. Obsidian reports reflect unified DB state within 15 minutes.
6. No MetaAPI/Exness code remains in the hot path or imports.
7. `AGENTS.md` and `CLAUDE.md` accurately describe the new architecture.
8. Early profit protection (§5.4) is active and locks in partial gains on short-term spikes.
9. System can be stopped, started, and understood by a new developer in one day.

---

## 16. Open Questions

1. Which symbols should be in each lane in the first release?
2. What daily risk percentage and per-lane allocation are appropriate?
3. Should the OpenClaw `RETEST` setup remain shadow-only or be promoted to live?
4. Should ad-hoc reports (`report_no_peak_entries.py`, `simulate_auto_protect.py`, etc.) be scheduled or deleted?
5. What is the desired retention policy for `system_events` and `decision_log.md`?
6. What are the per-lane early-profit-protection thresholds? Default is +0.5R / +1.0R scales with 50% giveback guard.

---

*Next step: write implementation plan via `writing-plans` skill.*
