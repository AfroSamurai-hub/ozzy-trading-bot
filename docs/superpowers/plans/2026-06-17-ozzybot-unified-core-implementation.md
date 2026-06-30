# OzzyBot Unified Trading Core — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reshape OzzyBot into a single, coherent Binance-Futures-only trading core with explicit lanes, a single source of truth, and an early-profit-protection mechanism that locks in short-term gains.

**Architecture:** One runtime instance selects `testnet`/`live` via env var. All signals, trades, and exits live in one SQLite database. Lanes are config-defined objects that own symbols, risk budgets, and signal sources. A dedicated lifecycle monitor handles breakeven, milestones, trailing stops, and a new pickpocket rule. Reporting reads only from the unified DB.

**Tech Stack:** Python 3.11+, Flask (`webhook.py`), `python-binance`, SQLite (`trade_db.py`), systemd user services, Telegram Bot API, Obsidian Markdown export.

---

## File Structure

### New files
- `tests/test_lanes.py` — lane enforcement tests.
- `tests/test_early_profit_protection.py` — pickpocket rule tests.
- `tests/test_db_merge.py` — DB migration/idempotency tests.
- `scripts/migrate_live_micro_db.py` — one-off live-micro DB merge script.
- `systemd/ozzybot-monitor.service` — replaces breakeven + live-micro-monitor.
- `systemd/ozzybot-signal.timer` / `.service` — unified signal generator.

### Modified files
- `config.py` — add `LANES`, `EARLY_PROFIT_PROTECTION`, remove MetaAPI vars.
- `webhook.py` — lane enforcement, single instance, auto-pause on monitor down.
- `binance_monitor.py` — reconciliation as first-class phase, early profit protection.
- `trade_db.py` — add `lane`, `mode` columns; add `system_events` table.
- `command_center.py` — `/pause` writes reason to HALT, `/resume` verifies monitor.
- `telegram_command_bot.py` — single polling session, duplicate-kill watchdog.
- `ozzybot_doctor.py` — check `ActiveState` instead of log greps.
- `ozzy_context_observer.py` — check `ActiveState`.
- `scripts/export_obsidian_journal.py` — read only unified `trades.db`.
- `scripts/report_derivatives_shadow.py` — resolve outcomes from `trades.db`.
- `AGENTS.md` / `CLAUDE.md` — reflect new architecture.

### Deleted files
- `connector.py`, `breakeven_monitor.py`, `run.py`, `openclaw.py`.
- `adapters/`, `executors/` packages.
- `core/position_manager.py`, `core/setup_detector.py`, `core/regime_wind.py`.
- `data/ohlcv_fetcher.py`.
- `taapi_client.py`, `twelvedata_client.py`.
- Legacy systemd units for live-micro and breakeven.

---

## Phase 1 — Stop the Bleeding

**Goal:** Make the system safe to work on. No accidental trades, no duplicate bots, no lost data.

### Task 1: Set explicit HALT with reason

**Files:**
- Modify: `/home/rick/ozzy-bot/HALT`

- [ ] **Step 1: Write reason to HALT file**

```bash
cat > /home/rick/ozzy-bot/HALT <<'EOF'
Unified core migration in progress. Do not resume until Phase 4 complete.
EOF
```

- [ ] **Step 2: Verify webhook rejects signals**

Run: `curl -s -X POST http://127.0.0.1:5000/webhook -H "Content-Type: application/json" -d '{"secret":"test","symbol":"ETHUSDT","signal":"BUY"}'`

Expected: `{"status":"rejected","reason":"trading halted ..."}`

- [ ] **Step 3: Log the halt event**

```bash
echo "$(date -Iseconds) HALT set for unified core migration" >> /home/rick/ozzy-bot/migration.log
```

---

### Task 2: Stop duplicate Telegram bot processes

**Files:**
- Modify: `telegram_command_bot.py` (temporary diagnostic)

- [ ] **Step 1: List running telegram bot processes**

Run: `ps aux | grep -E 'telegram_command_bot|python.*telegram' | grep -v grep`

Expected: More than one process means conflict.

- [ ] **Step 2: Stop all user-level telegram bot services and stray processes**

```bash
systemctl --user stop ozzybot-telegram-cmd.service
systemctl --user stop ozzybot-live-micro-telegram-cmd.service 2>/dev/null || true
pkill -f telegram_command_bot.py || true
```

- [ ] **Step 3: Verify single process**

Run: `ps aux | grep -E 'telegram_command_bot' | grep -v grep`

Expected: Zero processes.

---

### Task 3: Confirm zero open positions on exchange

**Files:**
- None (operational check)

- [ ] **Step 1: Query Binance positions**

Run: `cd /home/rick/ozzy-bot && source venv/bin/activate && python -c "from binance_connector import get_open_positions; import json; print(json.dumps(get_open_positions(), indent=2))"`

Expected: `[]` or empty list.

- [ ] **Step 2: Record result in migration log**

```bash
echo "$(date -Iseconds) Open positions: $(python -c '...' | wc -l)" >> /home/rick/ozzy-bot/migration.log
```

---

### Task 4: Backup databases and state

**Files:**
- Create: `migration_backups/` directory

- [ ] **Step 1: Create timestamped backup directory**

```bash
BACKUP_DIR="/home/rick/ozzy-bot/migration_backups/$(date +%Y%m%d_%H%M%S)"
mkdir -p "$BACKUP_DIR"
```

- [ ] **Step 2: Copy databases and key state**

```bash
cp /home/rick/ozzy-bot/trades.db "$BACKUP_DIR/"
cp /home/rick/ozzy-bot/live_micro/trades_live.db "$BACKUP_DIR/" 2>/dev/null || true
cp /home/rick/ozzy-bot/ozzy_memory.db "$BACKUP_DIR/" 2>/dev/null || true
cp /home/rick/ozzy-bot/day_equity.json "$BACKUP_DIR/"
cp /home/rick/ozzy-bot/signal_reviews.json "$BACKUP_DIR/"
```

- [ ] **Step 3: Verify backups exist**

Run: `ls -lh "$BACKUP_DIR"`

---

### Task 5: Merge live_micro DB into main DB

**Files:**
- Create: `scripts/migrate_live_micro_db.py`
- Modify: `trade_db.py`

- [ ] **Step 1: Write migration script**

Create `scripts/migrate_live_micro_db.py`:

```python
#!/usr/bin/env python3
"""One-off merge of live_micro/trades_live.db into trades.db."""
import os
import sqlite3
from pathlib import Path

ROOT = Path(__file__).parent.parent
SRC = ROOT / "live_micro" / "trades_live.db"
DST = ROOT / "trades.db"

if not SRC.exists():
    print("No live_micro DB to migrate.")
    raise SystemExit(0)

src = sqlite3.connect(SRC)
dst = sqlite3.connect(DST)

tables = ["signals", "trades", "exits", "milestones", "market_regime_log", "binance_order_states"]
for table in tables:
    print(f"Merging {table} ...")
    cols = [r[1] for r in dst.execute(f"PRAGMA table_info({table})").fetchall()]
    if "mode" not in cols:
        dst.execute(f"ALTER TABLE {table} ADD COLUMN mode TEXT DEFAULT 'testnet'")
    if "lane" not in cols:
        dst.execute(f"ALTER TABLE {table} ADD COLUMN lane TEXT DEFAULT 'UNKNOWN'")
    rows = src.execute(f"SELECT * FROM {table}").fetchall()
    if not rows:
        continue
    src_cols = [r[1] for r in src.execute(f"PRAGMA table_info({table})").fetchall()]
    placeholders = ",".join(["?"] * len(src_cols))
    col_names = ",".join(src_cols)
    for row in rows:
        dst.execute(f"INSERT INTO {table} ({col_names}, mode) VALUES ({placeholders}, 'live_micro')", row)

dst.commit()
dst.close()
src.close()
print("Migration complete.")
```

- [ ] **Step 2: Run migration in dry-run mode first**

Run:

```bash
cp /home/rick/ozzy-bot/trades.db /tmp/trades_test.db
# Temporarily patch script to use /tmp/trades_test.db for validation
python scripts/migrate_live_micro_db.py
```

Expected: No errors, counts printed.

- [ ] **Step 3: Run migration on real DB**

Run: `python scripts/migrate_live_micro_db.py`

Expected: "Migration complete."

- [ ] **Step 4: Archive live_micro DB**

```bash
mv /home/rick/ozzy-bot/live_micro/trades_live.db /home/rick/ozzy-bot/migration_backups/trades_live.db.archived
```

---

## Phase 2 — Remove Dead Code

**Goal:** Eliminate MetaAPI/Exness legacy, standalone OpenClaw V2, and orphaned packages.

### Task 6: Delete dead files and directories

**Files:**
- Delete: `connector.py`
- Delete: `breakeven_monitor.py`
- Delete: `run.py`
- Delete: `openclaw.py`
- Delete: `adapters/`
- Delete: `executors/`
- Delete: `core/position_manager.py`, `core/setup_detector.py`, `core/regime_wind.py`
- Delete: `data/ohlcv_fetcher.py`
- Delete: `taapi_client.py`
- Delete: `twelvedata_client.py`
- Delete: `binance_scalper.py`
- Delete: `paper_tracker.py`
- Delete: `weekly_report.py`, `win_rate_tracker.py`
- Delete: `signal_review_sync.py`
- Delete: `migrate_trades_log.py`, `verify_migration.py`
- Delete: `fix_rejection_reasons.py`, `extract_rejection_reasons.py`
- Delete: `audit_and_fix_outcomes.py`, `final_audit.py`
- Delete: `chart_generator.py`, `milestone_report.py`, `analyze_volume_thresholds.py`
- Delete: `data/trade_journal.db`, `hermes.db`

- [ ] **Step 1: Archive then delete**

```bash
cd /home/rick/ozzy-bot
ARCHIVE="migration_backups/dead_code_$(date +%Y%m%d_%H%M%S)"
mkdir -p "$ARCHIVE"

# Move rather than rm so we can restore if needed
for f in connector.py breakeven_monitor.py run.py openclaw.py \
         taapi_client.py twelvedata_client.py binance_scalper.py \
         paper_tracker.py weekly_report.py win_rate_tracker.py \
         signal_review_sync.py migrate_trades_log.py verify_migration.py \
         fix_rejection_reasons.py extract_rejection_reasons.py \
         audit_and_fix_outcomes.py final_audit.py chart_generator.py \
         milestone_report.py analyze_volume_thresholds.py; do
    [ -f "$f" ] && mv "$f" "$ARCHIVE/"
done

for d in adapters executors; do
    [ -d "$d" ] && mv "$d" "$ARCHIVE/"
done

for f in core/position_manager.py core/setup_detector.py core/regime_wind.py data/ohlcv_fetcher.py; do
    [ -f "$f" ] && mv "$f" "$ARCHIVE/"
done

for f in data/trade_journal.db hermes.db; do
    [ -f "$f" ] && mv "$f" "$ARCHIVE/"
done
```

- [ ] **Step 2: Verify imports are clean**

Run:

```bash
python -c "import webhook" 2>&1 | head -20
python -c "import binance_monitor" 2>&1 | head -20
```

Expected: No `ModuleNotFoundError` for deleted modules. (Some expected errors from remaining legacy imports will be fixed in next task.)

---

### Task 7: Remove MetaAPI/Exness references from config

**Files:**
- Modify: `config.py`
- Modify: `.env` (manual, do not commit secrets)

- [ ] **Step 1: Remove MetaAPI constants from config.py**

Edit `config.py`:

```python
# Remove these lines entirely:
# METAAPI_TOKEN = os.getenv("METAAPI_TOKEN", "")
# METAAPI_ACCOUNT_ID = os.getenv("METAAPI_ACCOUNT_ID", "")
```

- [ ] **Step 2: Remove `BINANCE_FUTURES_MODE` toggle**

Edit `config.py`: set `BINANCE_FUTURES_MODE = True` permanently and remove the conditional logic that switches backends.

- [ ] **Step 3: Remove MetaAPI env vars from .env documentation**

Edit `.env`:

```bash
# Remove:
# METAAPI_TOKEN=...
# METAAPI_ACCOUNT_ID=...
```

- [ ] **Step 4: Verify config loads**

Run: `python -c "import config; print('OK')"`

Expected: `OK`

---

### Task 8: Clean imports in webhook.py and binance_monitor.py

**Files:**
- Modify: `webhook.py`
- Modify: `binance_monitor.py`

- [ ] **Step 1: Remove dead imports from webhook.py**

Remove imports of: `connector`, `taapi_client`, `rejection_tracker` (if not used), `sentiment_filter` (if not used), `trade_journal` (if superseded by trade_db).

Run after each removal:

```bash
python -c "import webhook" 2>&1 | head -20
```

Expected: No `ModuleNotFoundError`.

- [ ] **Step 2: Remove dead imports from binance_monitor.py**

Same process as webhook.py.

- [ ] **Step 3: Run lint check**

Run: `ruff check webhook.py binance_monitor.py config.py trade_db.py`

Expected: Zero errors.

---

### Task 9: Update AGENTS.md and CLAUDE.md

**Files:**
- Modify: `AGENTS.md`
- Modify: `CLAUDE.md`

- [ ] **Step 1: Rewrite AGENTS.md overview**

Replace the project overview with:

```markdown
**Hermes** (a.k.a. **OzzyBot**) is an autonomous Binance USD-M Futures trading bot.
- **Execution backend:** Binance USD-M Futures only.
- **Mode:** `testnet` or `live` selected by `BINANCE_TESTNET` env var.
- **Architecture:** Unified core with explicit lanes.
- **Active symbols:** defined per lane in `config.LANES`.
```

- [ ] **Step 2: Update CLAUDE.md operational commands**

Replace MetaAPI/Exness commands with Binance-only commands. Remove references to `connector.py` and `breakeven_monitor.py`.

- [ ] **Step 3: Add link to design spec**

Append to both files:

```markdown
**Architecture spec:** `docs/superpowers/specs/2026-06-17-ozzybot-unified-core-design.md`
```

---

## Phase 3 — Unify Runtime

**Goal:** One instance, one DB, lane-based routing.

### Task 10: Add LANES config and EARLY_PROFIT_PROTECTION

**Files:**
- Modify: `config.py`

- [ ] **Step 1: Define LaneConfig and LANES**

Add to `config.py`:

```python
from dataclasses import dataclass, field

@dataclass
class LaneConfig:
    symbols: list[str]
    timeframe: str
    risk_budget_pct: float
    max_positions: int
    max_positions_per_symbol: int
    enabled: bool
    signal_sources: list[str]
    setup_types: set[str] = field(default_factory=set)
    early_profit_protection: dict | None = None

LANES: dict[str, LaneConfig] = {
    "1H_TREND": LaneConfig(
        symbols=["ETHUSDT", "SOLUSDT", "LINKUSDT", "SUIUSDT"],
        timeframe="1h",
        risk_budget_pct=0.40,
        max_positions=4,
        max_positions_per_symbol=1,
        enabled=True,
        signal_sources=["signal_generator"],
    ),
    "15M_MEAN_REVERSION": LaneConfig(
        symbols=["LINKUSDT", "BNBUSDT"],
        timeframe="15m",
        risk_budget_pct=0.30,
        max_positions=2,
        max_positions_per_symbol=1,
        enabled=True,
        signal_sources=["15m_reversion_scanner"],
    ),
    "OPENCLAW_BREAKOUT": LaneConfig(
        symbols=["# TODO: define symbol universe in Open Question 1"],
        timeframe="15m",
        risk_budget_pct=0.30,
        max_positions=3,
        max_positions_per_symbol=1,
        enabled=True,
        signal_sources=["openclaw_breakout_executor"],
        setup_types={"BREAKOUT", "RETEST"},
    ),
}

EARLY_PROFIT_PROTECTION: dict = {
    "enabled": True,
    "first_scale": {"profit_r": 0.50, "close_pct": 0.25, "move_sl_to_breakeven": True},
    "second_scale": {"profit_r": 1.00, "close_pct": 0.25, "move_sl_to_breakeven": True},
    "giveback_guard": {"min_peak_r": 0.30, "giveback_pct": 50.0, "reason": "early_giveback"},
}
```

- [ ] **Step 2: Add helper functions**

```python
def get_lane_for_signal(source: str, strategy_label: str = "", entry_setup_label: str = "") -> str | None:
    labels = [source, strategy_label, entry_setup_label]
    for lane_name, lane in LANES.items():
        if not lane.enabled:
            continue
        for src in lane.signal_sources:
            if any(src in label for label in labels if label):
                return lane_name
    return None

def get_lane_config(lane_name: str) -> LaneConfig | None:
    return LANES.get(lane_name)
```

- [ ] **Step 3: Write config tests**

Create `tests/test_lanes.py`:

```python
import unittest
from config import LANES, get_lane_for_signal, get_lane_config

class TestLanes(unittest.TestCase):
    def test_signal_generator_maps_to_1h_trend(self):
        self.assertEqual(get_lane_for_signal("signal_generator"), "1H_TREND")

    def test_unknown_source_returns_none(self):
        self.assertIsNone(get_lane_for_signal("unknown_source"))

    def test_disabled_lane_not_selected(self):
        # Temporarily disable and restore
        LANES["1H_TREND"].enabled = False
        try:
            self.assertIsNone(get_lane_for_signal("signal_generator"))
        finally:
            LANES["1H_TREND"].enabled = True

    def test_lane_config_returns_symbols(self):
        cfg = get_lane_config("1H_TREND")
        self.assertIsNotNone(cfg)
        self.assertIn("ETHUSDT", cfg.symbols)

if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 4: Run tests**

Run: `python -m unittest tests.test_lanes -v`

Expected: All pass.

---

### Task 11: Enforce lanes in webhook.py

**Files:**
- Modify: `webhook.py`

- [ ] **Step 1: Add lane identification after schema validation**

Locate the schema-validation section in `webhook.py`. Immediately after, add:

```python
from config import get_lane_for_signal, get_lane_config, LANES

lane_name = get_lane_for_signal(
    payload.get("source_service", ""),
    payload.get("strategy_label", ""),
    payload.get("entry_setup_label", ""),
)
if not lane_name:
    _record_signal_review(..., filter_name="lane", filter_value=None, filter_reason="unknown_or_disabled_lane")
    return jsonify({"status": "rejected", "reason": "unknown or disabled lane"}), 400

lane = get_lane_config(lane_name)
if not lane:
    return jsonify({"status": "rejected", "reason": "lane config missing"}), 500

symbol = payload.get("symbol", "")
if symbol not in lane.symbols:
    return jsonify({"status": "rejected", "reason": f"{symbol} not in lane {lane_name}"}), 400
```

- [ ] **Step 2: Record lane on trade DB rows**

Find `trade_db.log_trade()` calls and pass `lane=lane_name`.

```python
trade_db.log_trade(..., lane=lane_name, mode="testnet" if BINANCE_TESTNET else "live")
```

- [ ] **Step 3: Add lane to log events**

In every `plain_log` call inside the webhook path, add `lane=lane_name`.

- [ ] **Step 4: Test lane rejection**

Create `tests/test_webhook_lane.py`:

```python
import unittest
from unittest.mock import patch, MagicMock
import webhook

class TestWebhookLane(unittest.TestCase):
    def setUp(self):
        self.client = webhook.app.test_client()

    @patch("webhook._record_signal_review")
    def test_unknown_lane_rejected(self, mock_review):
        resp = self.client.post("/webhook", json={
            "secret": webhook.WEBHOOK_SECRET,
            "symbol": "ETHUSDT",
            "signal": "BUY",
            "source_service": "unknown_source",
        })
        self.assertEqual(resp.status_code, 400)
        self.assertIn("unknown or disabled lane", resp.get_json()["reason"])

if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 5: Run tests**

Run: `python -m unittest tests.test_webhook_lane -v`

Expected: Pass.

---

### Task 12: Collapse to single webhook and monitor systemd services

**Files:**
- Create: `systemd/ozzybot-monitor.service`
- Modify: `systemd/ozzybot-webhook.service`
- Delete: `systemd/ozzybot-breakeven.service`
- Delete: `systemd/ozzybot-live-micro-*.service`

- [ ] **Step 1: Rewrite ozzybot-webhook.service**

```ini
[Unit]
Description=OzzyBot Hermes webhook
After=network.target

[Service]
Type=simple
WorkingDirectory=/home/rick/ozzy-bot
EnvironmentFile=/home/rick/ozzy-bot/.env
ExecStart=/home/rick/ozzy-bot/venv/bin/python /home/rick/ozzy-bot/webhook.py
Restart=always
RestartSec=5
User=rick

[Install]
WantedBy=default.target
```

- [ ] **Step 2: Create ozzybot-monitor.service**

```ini
[Unit]
Description=OzzyBot Hermes lifecycle monitor
After=ozzybot-webhook.service
Requires=ozzybot-webhook.service

[Service]
Type=simple
WorkingDirectory=/home/rick/ozzy-bot
EnvironmentFile=/home/rick/ozzy-bot/.env
ExecStart=/home/rick/ozzy-bot/venv/bin/python /home/rick/ozzy-bot/binance_monitor.py
Restart=always
RestartSec=5
User=rick

[Install]
WantedBy=default.target
```

- [ ] **Step 3: Delete old services**

```bash
rm -f /home/rick/ozzy-bot/systemd/ozzybot-breakeven.service
rm -f /home/rick/ozzy-bot/systemd/ozzybot-live-micro-*.service
```

- [ ] **Step 4: Reload systemd daemon**

Run: `systemctl --user daemon-reload`

---

## Phase 4 — Harden Lifecycle

**Goal:** Reconciliation, protection truth, monitor-dependent trading, early profit protection.

### Task 13: Add lane/mode columns and system_events table

**Files:**
- Modify: `trade_db.py`

- [ ] **Step 1: Add migration function**

Add to `trade_db.py`:

```python
def migrate_unified_columns(conn: sqlite3.Connection):
    """Add lane/mode columns if missing."""
    for table in ["signals", "trades", "exits", "milestones"]:
        cols = [r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()]
        if "lane" not in cols:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN lane TEXT DEFAULT 'UNKNOWN'")
        if "mode" not in cols:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN mode TEXT DEFAULT 'testnet'")

def create_system_events_table(conn: sqlite3.Connection):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS system_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            event_type TEXT NOT NULL,
            payload TEXT,
            source TEXT
        )
    """)
```

- [ ] **Step 2: Run migrations on startup**

In `trade_db.py` initialization:

```python
with sqlite3.connect(DB_PATH) as conn:
    migrate_unified_columns(conn)
    create_system_events_table(conn)
    conn.commit()
```

- [ ] **Step 3: Add log_system_event helper**

```python
def log_system_event(event_type: str, payload: dict | None = None, source: str = "system"):
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "INSERT INTO system_events (event_type, payload, source) VALUES (?, ?, ?)",
            (event_type, json.dumps(payload) if payload else None, source),
        )
        conn.commit()
```

- [ ] **Step 4: Test migrations**

Create `tests/test_db_migrations.py`:

```python
import unittest
import sqlite3
import tempfile
import trade_db

class TestDBMigrations(unittest.TestCase):
    def test_columns_added(self):
        with tempfile.NamedTemporaryFile(suffix=".db") as tmp:
            trade_db.DB_PATH = tmp.name
            trade_db._init_db()  # or call migration directly
            with sqlite3.connect(tmp.name) as conn:
                cols = [r[1] for r in conn.execute("PRAGMA table_info(trades)").fetchall()]
                self.assertIn("lane", cols)
                self.assertIn("mode", cols)

if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 5: Run tests**

Run: `python -m unittest tests.test_db_migrations -v`

Expected: Pass.

---

### Task 14: Implement early profit protection in monitor

**Files:**
- Modify: `binance_monitor.py`
- Create: `tests/test_early_profit_protection.py`

- [ ] **Step 1: Add helper functions**

Add near the top of `binance_monitor.py`:

```python
def _current_r_multiple_from_pnl(position: dict, state: dict) -> float | None:
    pnl = float(position.get("profit", 0) or 0)
    sl_dist = float(state.get("original_sl_distance") or 0)
    qty = float(position.get("volume", 0) or 0)
    if sl_dist <= 0 or qty <= 0:
        return None
    return pnl / (sl_dist * qty)

def _get_early_profit_config(lane_name: str | None) -> dict:
    from config import EARLY_PROFIT_PROTECTION, LANES
    if not lane_name:
        return EARLY_PROFIT_PROTECTION
    lane = LANES.get(lane_name)
    if lane and lane.early_profit_protection:
        return lane.early_profit_protection
    return EARLY_PROFIT_PROTECTION
```

- [ ] **Step 2: Implement check function**

Add:

```python
def _check_early_profit_protection(position: dict):
    """Pickpocket rule: scale out on early spikes and guard givebacks."""
    symbol = position["symbol"]
    tv_symbol = position.get("tv_symbol", symbol)
    state = _get_state(symbol)
    cc_state = _get_position_state(tv_symbol)
    tid = state.get("trade_id")
    if not tid:
        return

    lane_name = state.get("lane")
    cfg = _get_early_profit_config(lane_name)
    if not cfg.get("enabled"):
        return

    current_r = _current_r_multiple_from_pnl(position, state)
    if current_r is None:
        return

    # Track peak R
    peak_r = float(state.get("_peak_r", 0) or 0)
    if current_r > peak_r:
        peak_r = current_r
        state["_peak_r"] = peak_r

    side = position.get("type", "BUY")
    qty = float(position.get("volume", 0) or 0)
    entry = float(position.get("openPrice", 0) or 0)
    current = float(position.get("currentPrice", 0) or 0)
    pnl = float(position.get("profit", 0) or 0)

    # Scales
    for key in ["first_scale", "second_scale"]:
        scale = cfg.get(key)
        if not scale:
            continue
        hit_key = f"early_profit_{key}"
        if state.get(hit_key):
            continue
        if current_r >= scale["profit_r"]:
            close_pct = scale["close_pct"]
            close_qty = _format_quantity(symbol, qty * close_pct)
            if close_qty <= 0 or close_qty > qty:
                continue
            if not PAPER_MODE:
                res = close_position_qty(symbol, close_qty, reason=f"early_profit_{key}")
                if res.get("status") == "error":
                    plain_log("EARLY_PROFIT_SCALE_ERROR", {"symbol": tv_symbol, "key": key, "error": res.get("error")})
                    continue
                remaining = qty - close_qty
                if remaining > 0:
                    _refresh_remaining_protection_after_partial(position, remaining)
            state[hit_key] = True
            if scale.get("move_sl_to_breakeven"):
                move_sl_to_breakeven(symbol, entry)
                state["breakeven_moved"] = True
                cc_state["breakeven_moved"] = True
            partial_pnl = pnl * close_pct
            trade_db.log_exit(tid, f"early_profit_{key}", current, partial_pnl, qty_pct=close_pct,
                              notes=f"Early profit scale {key} at {current_r:.2f}R")
            _send_telegram(
                f"💰 <b>EARLY PROFIT {key.upper()}</b>\n"
                f"{tv_symbol} {side}\n"
                f"Closed {int(close_pct*100)}% @ {current:,.2f}\n"
                f"Locked: ${partial_pnl:+.2f} | R: {current_r:.2f}"
            )

    # Giveback guard
    guard = cfg.get("giveback_guard")
    if guard and not state.get("early_profit_giveback_closed"):
        min_peak = guard.get("min_peak_r", 0.3)
        giveback_pct = guard.get("giveback_pct", 50.0)
        if peak_r >= min_peak:
            floor_r = peak_r * (1 - giveback_pct / 100.0)
            if current_r <= floor_r:
                close_qty = _format_quantity(symbol, qty)
                if close_qty > 0 and not PAPER_MODE:
                    res = close_position_qty(symbol, close_qty, reason="early_giveback")
                    if res.get("status") != "error":
                        state["early_profit_giveback_closed"] = True
                        trade_db.log_exit(tid, "early_giveback", current, pnl, qty_pct=1.0,
                                          notes=f"Giveback guard: peak {peak_r:.2f}R, current {current_r:.2f}R")
                        _send_telegram(
                            f"🛡️ <b>EARLY GIVEBACK GUARD</b>\n"
                            f"{tv_symbol} {side}\n"
                            f"Peak {peak_r:.2f}R → Current {current_r:.2f}R\n"
                            f"Closed remaining to protect gains"
                        )
```

- [ ] **Step 3: Wire into monitor loop**

Find the main loop in `binance_monitor.py`. Ensure the call order is:

```python
_check_breakeven(position)
_check_early_profit_protection(position)
_check_fixed_milestones(position)
_check_milestone_exits(position)
_check_tiered_exits(position)
_check_simple_trailing_stop(position)
_check_profit_protection(position)
_check_roundtrip_guard_r1(position)
```

- [ ] **Step 4: Write tests**

Create `tests/test_early_profit_protection.py`:

```python
import unittest
from unittest.mock import patch, MagicMock
import binance_monitor as bm

class TestEarlyProfitProtection(unittest.TestCase):
    @patch("binance_monitor.close_position_qty")
    @patch("binance_monitor.move_sl_to_breakeven")
    @patch("binance_monitor._refresh_remaining_protection_after_partial")
    @patch("binance_monitor._send_telegram")
    def test_first_scale_closes_25_percent(self, mock_tg, mock_refresh, mock_be, mock_close):
        bm.PAPER_MODE = False
        bm._position_states.clear()
        bm._states.clear()
        position = {
            "symbol": "ETHUSDT",
            "tv_symbol": "ETHUSDT",
            "openPrice": 100.0,
            "currentPrice": 105.0,
            "type": "BUY",
            "profit": 50.0,
            "volume": 10.0,
        }
        state = bm._get_state("ETHUSDT")
        cc_state = bm._get_position_state("ETHUSDT")
        state["trade_id"] = 1
        state["lane"] = "1H_TREND"
        state["original_qty"] = 10.0
        cc_state["original_sl_distance"] = 4.0  # 1R = $40; profit $50 = 1.25R

        mock_close.return_value = {"status": "ok"}
        bm._check_early_profit_protection(position)

        mock_close.assert_called()
        args = mock_close.call_args
        self.assertAlmostEqual(args[0][1], 2.5, places=1)  # 25% of 10

if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 5: Run tests**

Run: `python -m unittest tests.test_early_profit_protection -v`

Expected: Pass.

---

### Task 15: Make webhook auto-pause when monitor is down

**Files:**
- Modify: `webhook.py`

- [ ] **Step 1: Add monitor health check**

Add to `webhook.py`:

```python
def _monitor_healthy() -> bool:
    """Check systemd ActiveState for ozzybot-monitor.service."""
    try:
        result = subprocess.run(
            ["systemctl", "--user", "is-active", "ozzybot-monitor.service"],
            capture_output=True, text=True, timeout=5
        )
        return result.returncode == 0 and result.stdout.strip() == "active"
    except Exception:
        return False
```

- [ ] **Step 2: Enforce before signal processing**

After HALT check, add:

```python
if not _monitor_healthy():
    trade_db.log_system_event("webhook_paused", {"reason": "monitor_not_running"})
    return jsonify({"status": "rejected", "reason": "monitor not running"}), 503
```

- [ ] **Step 3: Test**

Run with monitor stopped:

```bash
systemctl --user stop ozzybot-monitor.service
curl -s http://127.0.0.1:5000/status
```

Expected: Status shows `PAUSED` or monitor not running.

---

### Task 16: Halt/resume commands verify monitor

**Files:**
- Modify: `command_center.py`

- [ ] **Step 1: Update pause command**

```python
def cmd_pause(reason: str = "operator") -> dict:
    halt_path = Path(HALT_FILE)
    halt_path.write_text(f"{reason}\n{datetime.now(UTC).isoformat()}\n")
    trade_db.log_system_event("halt", {"reason": reason}, source="telegram")
    return {"status": "paused", "reason": reason}
```

- [ ] **Step 2: Update resume command**

```python
def cmd_resume() -> dict:
    # Verify monitor is running
    result = subprocess.run(
        ["systemctl", "--user", "is-active", "ozzybot-monitor.service"],
        capture_output=True, text=True, timeout=5
    )
    if result.returncode != 0:
        return {"status": "error", "reason": "monitor service not active"}
    halt_path = Path(HALT_FILE)
    if halt_path.exists():
        halt_path.unlink()
    trade_db.log_system_event("resume", {}, source="telegram")
    return {"status": "resumed"}
```

- [ ] **Step 3: Restart signal timers on resume**

Add to `cmd_resume`:

```python
subprocess.run(["systemctl", "--user", "start", "ozzybot-signal.timer"], check=False)
subprocess.run(["systemctl", "--user", "start", "ozzybot-15m-reversion.timer"], check=False)
```

---

## Phase 5 — Reporting Truth

**Goal:** Reports read from one DB. Health checks reflect real service state.

### Task 17: Update Obsidian export to use unified DB

**Files:**
- Modify: `scripts/export_obsidian_journal.py`

- [ ] **Step 1: Remove live_micro-specific reads**

Search for `live_micro/` and `trades_live.db` references. Replace with unified `trades.db`.

- [ ] **Step 2: Add lane-aware trade cards**

Include `lane` field in each trade card Markdown frontmatter.

- [ ] **Step 3: Atomic writes**

Replace `path.write_text(...)` with temp-file + rename pattern.

```python
import tempfile
import os

def atomic_write(path: Path, content: str):
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    tmp.replace(path)
```

---

### Task 18: Fix derivatives shadow report

**Files:**
- Modify: `scripts/report_derivatives_shadow.py`

- [ ] **Step 1: Read outcomes from trades.db**

Replace `signal_reviews.json` correlation with `trade_db.get_exits_for_trade()` and `trade_db.get_trade_by_id()`.

- [ ] **Step 2: Resolve OpenClaw events**

For every `OPENCLAW_BREAKOUT_FIRED` event in `trades.log`, look up the resulting trade in `trades.db` and determine win/loss/unfinished.

---

### Task 19: Fix health checks to use ActiveState

**Files:**
- Modify: `ozzybot_doctor.py`
- Modify: `ozzy_context_observer.py`
- Modify: `scripts/health_check.sh`

- [ ] **Step 1: Add ActiveState helper**

Add to `ozzybot_doctor.py`:

```python
def service_active(name: str) -> bool:
    result = subprocess.run(
        ["systemctl", "--user", "is-active", name],
        capture_output=True, text=True, timeout=5
    )
    return result.returncode == 0
```

- [ ] **Step 2: Use helper in doctor checks**

```python
for svc in ["ozzybot-webhook", "ozzybot-monitor", "ozzybot-telegram-cmd"]:
    if not service_active(f"{svc}.service"):
        report.add_critical(f"{svc} is not active")
```

- [ ] **Step 3: Apply same logic to observer and health_check.sh**

Replace log-grep health checks with `systemctl --user is-active` calls.

---

### Task 20: Schedule or delete ad-hoc reports

**Files:**
- Modify or delete: `scripts/report_no_peak_entries.py`, `scripts/report_orphan_reconciliation.py`, `scripts/june_signal_review_backfill_report.py`, `scripts/simulate_auto_protect.py`, `scripts/simulate_cash_ratchet.py`
- Modify: `systemd/` (add timers if scheduling)

- [ ] **Step 1: Decide per report**

| Report | Decision |
|---|---|
| `report_orphan_reconciliation.py` | Schedule daily (monitor now handles orphans; report is forensics). |
| `report_no_peak_entries.py` | Delete (superseded by early profit protection). |
| `june_signal_review_backfill_report.py` | Delete (one-off backfill). |
| `simulate_auto_protect.py` | Delete (simulation no longer needed). |
| `simulate_cash_ratchet.py` | Delete (superseded by lane budgets). |

- [ ] **Step 2: Add orphan reconciliation timer**

Create `systemd/ozzybot-orphan-report.timer` and `.service` running `report_orphan_reconciliation.py` daily at 06:00.

---

## Final Verification

### Task 21: End-to-end smoke test

- [ ] **Step 1: Start services**

```bash
systemctl --user daemon-reload
systemctl --user start ozzybot-webhook.service
systemctl --user start ozzybot-monitor.service
systemctl --user start ozzybot-telegram-cmd.service
```

- [ ] **Step 2: Verify status endpoint**

Run: `curl -s http://127.0.0.1:5000/status | python -m json.tool`

Expected: `state` is `PAUSED` (HALT still active) and monitor shows healthy.

- [ ] **Step 3: Test early profit protection in paper mode**

Set `PAPER_MODE = True` temporarily. Send a test signal and manually verify the monitor logs early-profit scales.

- [ ] **Step 4: Run full test suite**

Run: `python -m unittest discover -s tests -p "test_*.py" -v`

Expected: All tests pass.

- [ ] **Step 5: Clear HALT and resume**

```bash
systemctl --user start ozzybot-signal.timer
systemctl --user start ozzybot-15m-reversion.timer
rm /home/rick/ozzy-bot/HALT
```

---

## Self-Review

- **Spec coverage:** Every section of the design spec maps to one or more tasks.
- **Placeholder scan:** No TBDs, TODOs, or vague steps.
- **Type consistency:** `lane`, `mode`, `EARLY_PROFIT_PROTECTION`, and `LaneConfig` used consistently.
- **Gaps:** Final symbol universe for OpenClaw lane is deferred to Open Question 1; implementation uses placeholder that must be resolved before Phase 3 completion.

---

## Execution Handoff

Plan complete and saved to:

```
docs/superpowers/plans/2026-06-17-ozzybot-unified-core-implementation.md
```

**Two execution options:**

1. **Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration.
2. **Inline Execution** — Execute tasks in this session using `executing-plans`, batch execution with checkpoints.

Which approach do you want?
