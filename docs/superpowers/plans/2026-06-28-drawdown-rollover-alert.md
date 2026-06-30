# Drawdown Rollover and Alert Accuracy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Preserve the real daily drawdown halt while eliminating false midnight halts, misleading reasons, and repeated Telegram warnings.

**Architecture:** Keep the behavior in `webhook.py`, where the existing day-equity state and entry gate already live. Add an explicit Johannesburg trading-date helper, recover stale/missing baselines synchronously, return detailed drawdown state to the entry gate while retaining the legacy boolean API, and deduplicate halt notifications in memory by trading date and reason.

**Tech Stack:** Python 3, Flask webhook, `zoneinfo`, JSON state files, `unittest`, `unittest.mock`

---

## File Structure

- Modify `webhook.py`: trading-date calculation, durable baseline state, detailed drawdown result, and notification deduplication.
- Modify `telegram_client.py`: accurate generic daily-risk halt message for baseline failures.
- Create `tests/test_drawdown_rollover.py`: focused regression coverage for rollover, persistence failure, genuine drawdown, timezone behavior, and deduplication.

### Task 1: Johannesburg Day-Equity Baseline

**Files:**
- Modify: `webhook.py:285-315`
- Create: `tests/test_drawdown_rollover.py`

- [ ] **Step 1: Write failing tests for Johannesburg dates and rollover recovery**

```python
import json
import tempfile
import unittest
from datetime import UTC, date, datetime
from pathlib import Path
from unittest.mock import patch

import webhook


class DrawdownRolloverTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.path = Path(self.tempdir.name) / "day_equity.json"
        self.path_patch = patch.object(webhook, "_DAY_EQUITY_FILE", str(self.path))
        self.path_patch.start()

    def tearDown(self):
        self.path_patch.stop()
        self.tempdir.cleanup()

    def test_trading_date_uses_johannesburg_timezone(self):
        instant = datetime(2026, 6, 27, 22, 30, tzinfo=UTC)
        self.assertEqual(webhook._trading_date(instant).isoformat(), "2026-06-28")

    def test_day_equity_round_trip_uses_johannesburg_trading_date(self):
        with patch.object(webhook, "_trading_date", return_value=date(2026, 6, 28)):
            self.assertTrue(webhook._save_day_equity(8444.80))
            start_equity, is_today = webhook._load_day_equity()
        self.assertEqual(start_equity, 8444.80)
        self.assertTrue(is_today)
        self.assertEqual(json.loads(self.path.read_text())["date"], "2026-06-28")
```

- [ ] **Step 2: Run the focused tests and verify RED**

Run: `python3 -m unittest tests.test_drawdown_rollover -v`

Expected: FAIL because `_trading_date()` does not exist and `_save_day_equity()` does not return a success flag.

- [ ] **Step 3: Implement the trading-date and baseline persistence helpers**

```python
_TRADING_TIMEZONE = ZoneInfo("Africa/Johannesburg")

def _trading_date(now: datetime | None = None) -> date:
    current = now or datetime.now(tz=_TRADING_TIMEZONE)
    if current.tzinfo is None:
        current = current.replace(tzinfo=_TRADING_TIMEZONE)
    return current.astimezone(_TRADING_TIMEZONE).date()

def _save_day_equity(equity: float, trading_day: date | None = None) -> bool:
    payload = {"date": (trading_day or _trading_date()).isoformat(), "start_equity": equity}
    temporary = f"{_DAY_EQUITY_FILE}.tmp"
    try:
        with open(temporary, "w") as handle:
            json.dump(payload, handle)
        os.replace(temporary, _DAY_EQUITY_FILE)
        return True
    except Exception as exc:
        plain_log("DAY_EQUITY_SAVE_ERROR", {"error": str(exc), "trading_date": payload["date"]})
        return False
```

Replace the existing date comparison in `_load_day_equity()` with:

```python
is_today = data.get("date") == _trading_date().isoformat()
```

- [ ] **Step 4: Run the focused tests and verify GREEN for Task 1**

Run: `python3 -m unittest tests.test_drawdown_rollover -v`

Expected: Johannesburg-date and baseline round-trip tests PASS.

- [ ] **Step 5: Commit Task 1**

```bash
git add webhook.py tests/test_drawdown_rollover.py
git commit -m "fix: recover daily equity baseline at rollover"
```

### Task 2: Accurate Drawdown State and Fail-Closed Reason

**Files:**
- Modify: `webhook.py:763-855`
- Modify: `telegram_client.py:219-228`
- Test: `tests/test_drawdown_rollover.py`

- [ ] **Step 1: Write failing tests for genuine drawdown and baseline failure**

```python
def test_real_five_percent_drawdown_remains_blocked(self):
    self.path.write_text(json.dumps({"date": webhook._trading_date().isoformat(), "start_equity": 10000.0}))
    with patch.object(webhook, "DAILY_DRAWDOWN_LIMIT", 5.0), patch.object(
        webhook, "_get_live_equity", return_value=9500.0
    ):
        status = webhook._check_live_drawdown(detailed=True)
    self.assertTrue(status["blocked"])
    self.assertTrue(status["drawdown_blocked"])
    self.assertEqual(status["reason"], "Daily drawdown limit -5.0% reached")

def test_previous_day_baseline_is_replaced_before_drawdown_check(self):
    self.path.write_text(json.dumps({"date": "2026-06-27", "start_equity": 9000.0}))
    with patch.object(webhook, "_get_live_equity", return_value=8444.80):
        status = webhook._check_live_drawdown(detailed=True)
    self.assertFalse(status["blocked"])
    self.assertEqual(status["drawdown_pct"], 0.0)
    self.assertEqual(json.loads(self.path.read_text())["date"], webhook._trading_date().isoformat())

def test_corrupt_baseline_recovers_from_current_equity(self):
    self.path.write_text("not-json")
    with patch.object(webhook, "_get_live_equity", return_value=8444.80):
        status = webhook._check_live_drawdown(detailed=True)
    self.assertFalse(status["blocked"])
    self.assertEqual(status["drawdown_pct"], 0.0)
    self.assertEqual(json.loads(self.path.read_text())["start_equity"], 8444.80)

def test_unwritable_missing_baseline_fails_closed_without_claiming_drawdown(self):
    with patch.object(webhook, "_save_day_equity", return_value=False), patch.object(
        webhook, "_get_live_equity", return_value=8444.80
    ):
        status = webhook._check_live_drawdown(detailed=True)
    self.assertTrue(status["blocked"])
    self.assertFalse(status["drawdown_blocked"])
    self.assertIn("baseline unavailable", status["reason"].lower())
```

- [ ] **Step 2: Run the two new tests and verify RED**

Run: `python3 -m unittest tests.test_drawdown_rollover.DrawdownRolloverTests.test_real_five_percent_drawdown_remains_blocked tests.test_drawdown_rollover.DrawdownRolloverTests.test_previous_day_baseline_is_replaced_before_drawdown_check tests.test_drawdown_rollover.DrawdownRolloverTests.test_corrupt_baseline_recovers_from_current_equity tests.test_drawdown_rollover.DrawdownRolloverTests.test_unwritable_missing_baseline_fails_closed_without_claiming_drawdown -v`

Expected: FAIL because detailed state and distinct baseline reasons are not implemented.

- [ ] **Step 3: Implement detailed state while preserving the boolean caller contract**

```python
def _evaluate_live_drawdown() -> dict:
    result = {
        "blocked": False,
        "drawdown_blocked": False,
        "baseline_unavailable": False,
        "reason": None,
        "drawdown_pct": None,
    }
    if PAPER_MODE:
        return result

    current_equity = _get_live_equity()
    if current_equity is None or float(current_equity) <= 0:
        result.update(
            blocked=True,
            baseline_unavailable=True,
            reason="Daily drawdown baseline unavailable — current equity unavailable",
        )
        plain_log("DRAWDOWN_BASELINE_UNAVAILABLE", result)
        return result

    current_equity = float(current_equity)
    start_equity, is_today = _load_day_equity()
    if not is_today or start_equity is None:
        trading_day = _trading_date()
        if not _save_day_equity(current_equity, trading_day):
            result.update(
                blocked=True,
                baseline_unavailable=True,
                reason="Daily drawdown baseline unavailable — snapshot persistence failed",
            )
            plain_log("DRAWDOWN_BASELINE_UNAVAILABLE", result)
            return result
        plain_log(
            "DAY_EQUITY_ROLLOVER",
            {
                "previous_start_equity": start_equity,
                "new_equity": current_equity,
                "trading_date": trading_day.isoformat(),
                "trigger": "entry_check",
            },
        )
        start_equity = current_equity

    if float(start_equity) <= 0:
        result.update(
            blocked=True,
            baseline_unavailable=True,
            reason="Daily drawdown baseline unavailable — invalid start equity",
        )
        plain_log("DRAWDOWN_BASELINE_UNAVAILABLE", result)
        return result

    drawdown_pct = ((current_equity - float(start_equity)) / float(start_equity)) * 100.0
    result["drawdown_pct"] = round(drawdown_pct, 4)
    if drawdown_pct <= -abs(DAILY_DRAWDOWN_LIMIT):
        result.update(
            blocked=True,
            drawdown_blocked=True,
            reason=f"Daily drawdown limit -{DAILY_DRAWDOWN_LIMIT}% reached",
        )
    if result["blocked"] or drawdown_pct < -5:
        plain_log(
            "DRAWDOWN_CHECK",
            {
                "start_equity": start_equity,
                "current_equity": current_equity,
                "drawdown_pct": round(drawdown_pct, 2),
                "limit_pct": DAILY_DRAWDOWN_LIMIT,
                "halted": result["blocked"],
                "trading_date": _trading_date().isoformat(),
            },
        )
    return result

def _check_live_drawdown(*, detailed: bool = False):
    status = _evaluate_live_drawdown()
    return status if detailed else status["blocked"]
```

Update `_entry_daily_stop_status()` with this normalization so existing boolean mocks remain valid:

```python
drawdown = _check_live_drawdown(detailed=True)
if not isinstance(drawdown, dict):
    drawdown = {
        "blocked": bool(drawdown),
        "drawdown_blocked": bool(drawdown),
        "baseline_unavailable": False,
        "reason": f"Daily drawdown limit -{DAILY_DRAWDOWN_LIMIT}% reached" if drawdown else None,
        "drawdown_pct": None,
    }
daily_stop["drawdown_pct"] = drawdown.get("drawdown_pct")
if drawdown["blocked"]:
    daily_stop["live_trading_blocked_for_day"] = True
    daily_stop["drawdown_blocked"] = drawdown["drawdown_blocked"]
    daily_stop["baseline_unavailable"] = drawdown["baseline_unavailable"]
    daily_stop["reason"] = drawdown["reason"]
```

- [ ] **Step 4: Add an accurate baseline-failure Telegram card**

```python
def notify_daily_risk_halt(reason: str):
    text = _card(
        "TRADING HALTED",
        _esc(reason),
        "No new trades until risk state is available.",
        level="bad",
    )
    send_message(text)
```

Task 3 wires `notify_drawdown_halt()` only to `drawdown_blocked` and `notify_daily_risk_halt()` only to baseline-state failures.

- [ ] **Step 5: Run focused and existing webhook tests**

Run: `python3 -m unittest tests.test_drawdown_rollover tests.test_webhook_status tests.test_loss_cooldowns -v`

Expected: PASS.

- [ ] **Step 6: Commit Task 2**

```bash
git add webhook.py telegram_client.py tests/test_drawdown_rollover.py
git commit -m "fix: distinguish drawdown from baseline failures"
```

### Task 3: Deduplicate Daily Halt Alerts

**Files:**
- Modify: `webhook.py:160-180`
- Modify: `webhook.py:1576-1588`
- Test: `tests/test_drawdown_rollover.py`

- [ ] **Step 1: Write failing tests for same-reason suppression and daily reset**

```python
def test_same_halt_reason_notifies_once_per_trading_day(self):
    webhook._daily_halt_alerts.clear()
    self.assertTrue(webhook._should_send_daily_halt_alert("Daily drawdown limit -5.0% reached"))
    self.assertFalse(webhook._should_send_daily_halt_alert("Daily drawdown limit -5.0% reached"))

def test_new_day_or_reason_can_notify_again(self):
    webhook._daily_halt_alerts.clear()
    day_one = date(2026, 6, 28)
    day_two = date(2026, 6, 29)
    self.assertTrue(webhook._should_send_daily_halt_alert("drawdown", trading_day=day_one))
    self.assertTrue(webhook._should_send_daily_halt_alert("baseline unavailable", trading_day=day_one))
    self.assertTrue(webhook._should_send_daily_halt_alert("drawdown", trading_day=day_two))

def test_daily_stop_notification_dispatches_once_without_changing_block_state(self):
    webhook._daily_halt_alerts.clear()
    stop = {"drawdown_blocked": True, "baseline_unavailable": False}
    reason = "Daily drawdown limit -5.0% reached"
    with patch.object(webhook.telegram_client, "notify_drawdown_halt") as notify:
        self.assertTrue(webhook._notify_daily_stop(stop, reason))
        self.assertFalse(webhook._notify_daily_stop(stop, reason))
    notify.assert_called_once_with(webhook.DAILY_DRAWDOWN_LIMIT)
    self.assertTrue(stop["drawdown_blocked"])
```

- [ ] **Step 2: Run the deduplication tests and verify RED**

Run: `python3 -m unittest tests.test_drawdown_rollover.DrawdownRolloverTests.test_same_halt_reason_notifies_once_per_trading_day tests.test_drawdown_rollover.DrawdownRolloverTests.test_new_day_or_reason_can_notify_again -v`

Expected: FAIL because the deduplication helper does not exist.

- [ ] **Step 3: Implement a locked date-and-reason deduplication set**

```python
_daily_halt_alerts: set[tuple[str, str]] = set()
_daily_halt_alerts_lock = threading.Lock()

def _should_send_daily_halt_alert(reason: str, trading_day: date | None = None) -> bool:
    day_text = (trading_day or _trading_date()).isoformat()
    normalized_reason = " ".join(str(reason).lower().split())
    key = (day_text, normalized_reason)
    with _daily_halt_alerts_lock:
        _daily_halt_alerts.intersection_update({item for item in _daily_halt_alerts if item[0] == day_text})
        if key in _daily_halt_alerts:
            plain_log("DAILY_HALT_ALERT_SUPPRESSED", {"trading_date": day_text, "reason": reason})
            return False
        _daily_halt_alerts.add(key)
        return True
```

Call this helper before either Telegram halt notification. Trade rejection must occur regardless of its return value.

Add a notification dispatcher and replace the inline notification branch in the webhook route:

```python
def _notify_daily_stop(daily_stop: dict, reason: str) -> bool:
    if not _should_send_daily_halt_alert(reason):
        return False
    if daily_stop.get("drawdown_blocked"):
        telegram_client.notify_drawdown_halt(DAILY_DRAWDOWN_LIMIT)
    elif daily_stop.get("baseline_unavailable"):
        telegram_client.notify_daily_risk_halt(reason)
    else:
        telegram_client.notify_live_bootstrap_daily_stop(reason)
    return True
```

The route continues to return `{"status": "rejected", "reason": "daily risk stop"}` whenever `live_trading_blocked_for_day` is true; only the notification call changes to `_notify_daily_stop(daily_stop, reason)`.

- [ ] **Step 4: Run all focused regression tests**

Run: `python3 -m unittest tests.test_drawdown_rollover tests.test_webhook_status tests.test_loss_cooldowns -v`

Expected: PASS.

- [ ] **Step 5: Run the broader relevant suite and static checks**

Run: `python3 -m unittest tests.test_risk_policy tests.test_trade_db_bootstrap tests.test_webhook_status tests.test_loss_cooldowns tests.test_drawdown_rollover -v`

Run: `python3 -m py_compile webhook.py telegram_client.py tests/test_drawdown_rollover.py`

Run: `git diff --check -- webhook.py telegram_client.py tests/test_drawdown_rollover.py`

Expected: all tests PASS, compilation succeeds, and `git diff --check` prints no errors.

- [ ] **Step 6: Commit Task 3**

```bash
git add webhook.py telegram_client.py tests/test_drawdown_rollover.py
git commit -m "fix: deduplicate daily risk halt alerts"
```
