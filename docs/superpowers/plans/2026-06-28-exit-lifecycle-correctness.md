# Exit Lifecycle Correctness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prevent overlapping exit actions, false peak-R promotion, stale post-close protection, and fee-blind trade accounting across every OzzyBot symbol.

**Architecture:** Keep the existing monitor policies but place a per-position execution latch around broker mutations so only one quantity-changing action can run from a position snapshot. Track price-derived peak R separately from stop-management state, perform verified terminal cleanup for normal and algo orders, and reconstruct closed-trade accounting from exchange fills and commissions.

**Tech Stack:** Python 3, unittest, SQLite, python-binance USD-M Futures testnet.

---

### Task 1: Runtime Safety Cleanup

**Files:**
- Use: `scripts/cleanup_stale_algo_orders.py`
- Use: `trade_db.py`

- [ ] **Step 1: Reconfirm there is no BTCUSDT exchange position and exactly two orphaned reduce-only algo orders**

Run a read-only query through `binance_connector.get_open_positions()` and `get_open_algo_orders()`.

- [ ] **Step 2: Cancel only the confirmed BTCUSDT orphaned algo orders**

Run:

```bash
venv/bin/python scripts/cleanup_stale_algo_orders.py --symbols BTCUSDT --execute
```

Expected: the two recorded BTCUSDT algo IDs are cancelled; no position mutation occurs.

- [ ] **Step 3: Delete only HYPEUSDT and WLDUSDT order-state rows after confirming neither has an exchange position or order**

Use `trade_db.delete_binance_order_state(symbol)` for the two confirmed stale symbols.

- [ ] **Step 4: Verify runtime truth**

Expected: zero positions, zero stale algo orders, zero persisted-order-state warnings.

### Task 2: True Peak-R Semantics and One Action Per Snapshot

**Files:**
- Modify: `binance_monitor.py`
- Modify: `tests/test_early_profit_protection.py`
- Modify: `tests/test_binance_monitor_protective_exits.py`

- [ ] **Step 1: Write failing peak-R regression test**

Model the BTC lifecycle: peak `0.52R`, breakeven moved, current `0.39R`. Assert that profit protection does not promote `_peak_r` to `1.0` and early giveback does not close at a 33% threshold.

- [ ] **Step 2: Run the focused test and confirm the current implementation fails**

Run:

```bash
venv/bin/python -m unittest tests.test_binance_monitor_protective_exits -v
```

- [ ] **Step 3: Remove synthetic 1R promotion**

Change `_check_profit_protection` so only an actual `1R_breakeven` milestone or price-derived `peak_r >= 1.0` proves 1R. `breakeven_moved` remains stop state only.

- [ ] **Step 4: Write failing one-action regression test**

At a snapshot satisfying early-profit and `milestone_0`, assert only the first successful quantity-changing policy executes and later policies receive no broker call.

- [ ] **Step 5: Add a per-snapshot exit-action latch**

Reset the latch at the start of each position loop. Every partial/full broker mutation claims it only after a successful broker response; subsequent quantity-changing rules skip until the next fresh position snapshot.

- [ ] **Step 6: Run focused tests**

Expected: peak-R and one-action regressions pass without changing configured thresholds.

### Task 3: Verified Terminal Cleanup

**Files:**
- Modify: `binance_monitor.py`
- Modify: `tests/test_binance_monitor_protective_exits.py`

- [ ] **Step 1: Write failing terminal-cleanup tests**

Assert `_prune_state` cancels standard and algo orders even when the DB trade is already marked closed, then deletes local order state only after cleanup is attempted.

- [ ] **Step 2: Confirm the tests fail because the closed-row fast path currently skips exchange cleanup**

- [ ] **Step 3: Centralize idempotent terminal cleanup**

Reuse `_cancel_stale_reduce_only_orders(symbol)` on every terminal prune path. Log cancellation failures and retain a visible warning path rather than silently claiming cleanup.

- [ ] **Step 4: Run terminal-cleanup and reconciliation tests**

Run:

```bash
venv/bin/python -m unittest tests.test_binance_monitor_protective_exits tests.test_live_reconcile -v
```

### Task 4: Exchange-Fill Accounting

**Files:**
- Modify: `trade_db.py`
- Modify: `binance_monitor.py`
- Modify: `tests/test_trade_accounting.py`
- Modify: `tests/test_partial_fill_reconciliation.py`

- [ ] **Step 1: Write a failing BTC ledger regression**

Use the actual fills: entry `0.24 @ 60044.20`, exits `0.06 @ 59918.80`, `0.045 @ 59919.10`, `0.045 @ 59919.10`, `0.09 @ 59919.10`, commissions totalling `11.51646960`. Assert gross `30.042`, fees `11.51646960`, and net `18.52553040`.

- [ ] **Step 2: Confirm current alert-price/zero-fee accounting fails**

- [ ] **Step 3: Reconstruct terminal accounting from exchange fills**

Persist actual weighted entry, weighted terminal exit, realized PnL, and commissions. Record terminal remainder as the remaining original fraction rather than another `1.0` quantity fraction.

- [ ] **Step 4: Quarantine incomplete ledgers**

If fills or commissions cannot be fetched, mark accounting `unchecked` or `dirty`; never label reconstructed zero-fee math `corrected`.

- [ ] **Step 5: Run accounting tests**

Expected: exact BTC ledger values pass and existing partial-fill idempotency remains green.

### Task 5: Verification and Safe Service Reload

**Files:**
- Verify: `binance_monitor.py`
- Verify: `trade_db.py`
- Verify: `webhook.py`

- [ ] **Step 1: Run focused lifecycle suites**

```bash
venv/bin/python -m unittest tests.test_early_profit_protection tests.test_binance_monitor_protective_exits tests.test_partial_fill_reconciliation tests.test_trade_accounting tests.test_live_reconcile tests.test_system_sync -v
```

- [ ] **Step 2: Run the full suite**

```bash
venv/bin/python -m unittest discover -s tests -p 'test_*.py'
```

- [ ] **Step 3: Review the exact diff against the dirty worktree**

Confirm only task-scoped hunks and new tests/docs are included; preserve all unrelated user changes.

- [ ] **Step 4: Restart only the monitor service after confirming no open positions**

```bash
systemctl --user restart ozzybot-monitor.service
```

- [ ] **Step 5: Verify runtime health**

Expected: monitor active, reconciliation healthy, no stale order warnings, and no startup errors.
