# Clean Runtime Epoch Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Start a trustworthy testnet epoch with per-trade exchange accounting, separate executed/shadow reporting, and a coordinated webhook/monitor reload.

**Architecture:** Isolate one flat-to-flat fill cycle before sending fills to the existing ledger reconciler, and make daily reporting explicitly partition closed rows by execution state. Back up runtime databases and reload both services only while Binance is flat.

**Tech Stack:** Python 3, unittest, SQLite, python-binance USD-M Futures testnet, systemd user services.

---

### Task 1: Per-trade exchange fill isolation

**Files:**
- Modify: `binance_monitor.py`
- Modify: `tests/test_trade_accounting.py`

- [ ] **Step 1: Write a failing flat-to-flat cycle test**

Add a test containing one complete SELL/BUY round trip followed by a second SELL/BUY round trip for the same symbol. Assert the selector returns only the first cycle and its terminal fill timestamp.

- [ ] **Step 2: Run the focused test and verify RED**

Run: `venv/bin/python -m unittest tests.test_trade_accounting -v`

Expected: failure because the cycle selector does not exist.

- [ ] **Step 3: Implement minimal cycle isolation**

Add a pure helper that sorts fills by exchange time, accepts only the expected position side, accumulates entry-side quantity, subtracts exit-side quantity, and stops at the first return to zero. Reject cycles without both entry and terminal exit fills.

- [ ] **Step 4: Bound exchange queries and funding**

Use a recorded terminal exit timestamp plus a short fill-settlement allowance when available. Run the cycle selector even when an end bound is available. Query funding only through the selected terminal fill timestamp. Return `complete=False` if the selected cycle cannot reconcile.

- [ ] **Step 5: Verify GREEN**

Run: `venv/bin/python -m unittest tests.test_trade_accounting tests.test_binance_monitor_protective_exits -v`

Expected: all focused accounting and lifecycle tests pass.

### Task 2: Executed versus shadow daily reporting

**Files:**
- Modify: `scripts/report_daily_edge.py`
- Modify: `tests/test_daily_edge_report.py`

- [ ] **Step 1: Write a failing reporting partition test**

Extend the test schema with `execution_state` and `mode`. Insert one executed winner and one larger shadow loss. Assert primary closed count/PnL contains only the executed winner and a separate shadow summary contains only the simulation.

- [ ] **Step 2: Run the focused test and verify RED**

Run: `venv/bin/python -m unittest tests.test_daily_edge_report -v`

Expected: primary PnL incorrectly includes the shadow loss or no shadow summary exists.

- [ ] **Step 3: Implement explicit partitions**

Treat `execution_state='shadow_closed'` or `mode='paper'` as shadow. Primary trade statistics, quality flags, open positions, position pressure, and occupancy use non-shadow rows. Add `shadow_summary` and render it under a clearly labelled simulation section.

- [ ] **Step 4: Verify GREEN against the production database**

Run the focused tests, then build a 24-hour report against `trades.db`. Confirm its executed and shadow totals match direct SQLite queries using the same predicates.

### Task 3: Pre-restart safety and backup

**Files:**
- Use: `scripts/backup_runtime_dbs.py`
- Verify: `trades.db`
- Verify: Binance testnet account

- [ ] **Step 1: Run the full test suite**

Run: `venv/bin/python -m unittest discover -s tests -p 'test_*.py'`

Expected: zero failures and zero errors.

- [ ] **Step 2: Confirm a flat exchange boundary**

Read Binance positions and open orders. Continue only if both counts are zero.

- [ ] **Step 3: Back up runtime databases**

Run: `venv/bin/python scripts/backup_runtime_dbs.py`

Expected: timestamped SQLite backups are created and pass integrity checks.

### Task 4: Coordinated service reload and evidence epoch

**Files:**
- Use: `systemd/ozzybot-webhook.service`
- Use: `systemd/ozzybot-monitor.service`
- Verify: `trades.log`

- [ ] **Step 1: Restart webhook and monitor together**

Run: `systemctl --user restart ozzybot-webhook.service ozzybot-monitor.service`

- [ ] **Step 2: Verify process and HTTP health**

Confirm both units are active, their process start times are newer than the code modification times, and the webhook health endpoint responds successfully.

- [ ] **Step 3: Verify exchange/DB/protection seams**

Run the doctor and reconciliation checks. Require zero exchange positions, zero open orders, no DB ghost positions counted as active, and no critical protection mismatch.

- [ ] **Step 4: Record the epoch boundary**

Record the UTC restart timestamp, webhook PID, monitor PID, git revision, and active lifecycle thresholds in a report under `reports/`. Only trades opened after this timestamp count as post-fix evidence.

- [ ] **Step 5: Roll back on startup failure**

If either unit or seam check fails, stop the monitor from managing entries, preserve logs and backups, and report the exact blocker instead of claiming the epoch active.
