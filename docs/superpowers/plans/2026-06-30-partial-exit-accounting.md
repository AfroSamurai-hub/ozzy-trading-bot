# Partial Exit Accounting Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Record every partial and terminal exit as the exchange-evidenced quantity divided by the immutable original quantity, repair the two proven BNBUSDT fractions, and deploy only from a flat exchange state.

**Architecture:** `binance_connector.close_position_qty` will return structured execution evidence without changing the requested reduction. `binance_monitor` will own one fraction calculator and one partial-exit recorder used by every writer, while `trade_db.log_exit` remains the persistence boundary. A one-trade repair utility will verify hard-coded exchange evidence, create a SQLite online backup, and refuse mutation unless the exchange is flat.

**Tech Stack:** Python 3.13, python-binance USDⓈ-M Futures client, SQLite, `unittest`/`pytest`, user-level systemd.

---

## File map

- Modify `binance_connector.py`: preserve Binance execution evidence in quantity-close results and expose cached `LOT_SIZE.stepSize`.
- Modify `binance_monitor.py`: calculate original-position fractions, centralize audit notes, update all partial writers, and correct terminal fallbacks.
- Modify `tests/test_binance_safety.py`: verify Binance response/query/fill precedence and fallback behavior.
- Modify `tests/test_early_profit_protection.py`: verify sequential current-position reductions produce original-position fractions.
- Modify `tests/test_milestone_upgrades.py`: verify time-decay, normal milestone, and regime-aware milestone accounting.
- Modify `tests/test_binance_monitor_protective_exits.py`: verify time-reduction, tiered, missing-denominator, and external-terminal accounting.
- Modify `tests/test_binance_safety.py`: verify exchange-detected TP milestone accounting.
- Create `scripts/repair_bnb_partial_exit_qty.py`: dry-run-first, evidence-locked repair for trade `100373` only.
- Create `tests/test_repair_bnb_partial_exit_qty.py`: prove the repair refuses ambiguity/open positions and changes only two fractions after backup.

### Task 1: Preserve Binance execution quantity evidence

**Files:**
- Modify: `binance_connector.py:1861-1910`
- Test: `tests/test_binance_safety.py`

- [ ] **Step 1: Write failing connector evidence tests**

Add a focused fake client and tests covering create response, order query, fill aggregation, and fallback:

```python
class QuantityCloseClient:
    def __init__(self, create_order, queried_order=None, fills=None):
        self.create_order = create_order
        self.queried_order = queried_order or {}
        self.fills = fills or []
        self.create_payload = None

    def futures_position_information(self, symbol):
        return [{"symbol": symbol, "positionSide": "SHORT", "positionAmt": "-10"}]

    def futures_create_order(self, **payload):
        self.create_payload = payload
        return self.create_order

    def futures_get_order(self, symbol, orderId):
        return self.queried_order

    def futures_account_trades(self, symbol, orderId):
        return self.fills


def test_close_position_qty_prefers_result_executed_qty(self):
    client = QuantityCloseClient({
        "orderId": 41,
        "status": "FILLED",
        "executedQty": "2.49",
        "cumQty": "2.49",
    })
    with patch.object(binance_connector, "PAPER_MODE", False), patch.object(
        binance_connector, "_get_client", return_value=client
    ):
        result = binance_connector.close_position_qty("BNBUSDT", 2.5, position_side="SHORT")

    self.assertEqual(client.create_payload["newOrderRespType"], "RESULT")
    self.assertEqual(result["quantity"], 2.49)
    self.assertEqual(result["requested_quantity"], 2.5)
    self.assertEqual(result["quantity_source"], "create_response.executedQty")
    self.assertTrue(result["accounting_confirmed"])


def test_close_position_qty_queries_order_before_fills(self):
    client = QuantityCloseClient(
        {"orderId": 42, "status": "NEW", "executedQty": "0"},
        {"orderId": 42, "status": "FILLED", "executedQty": "2.48"},
        [{"id": 901, "orderId": 42, "qty": "2.47"}],
    )
    with patch.object(binance_connector, "PAPER_MODE", False), patch.object(
        binance_connector, "_get_client", return_value=client
    ):
        result = binance_connector.close_position_qty("BNBUSDT", 2.5, position_side="SHORT")

    self.assertEqual(result["quantity"], 2.48)
    self.assertEqual(result["quantity_source"], "order_query.executedQty")
    self.assertEqual(result["fill_ids"], [])


def test_close_position_qty_aggregates_same_order_fills(self):
    client = QuantityCloseClient(
        {"orderId": 43, "status": "NEW", "executedQty": "0"},
        {"orderId": 43, "status": "NEW", "executedQty": "0"},
        [
            {"id": 902, "orderId": 43, "qty": "1.20"},
            {"id": 903, "orderId": 43, "qty": "1.29"},
            {"id": 904, "orderId": 99, "qty": "8.00"},
        ],
    )
    with patch.object(binance_connector, "PAPER_MODE", False), patch.object(
        binance_connector, "_get_client", return_value=client
    ):
        result = binance_connector.close_position_qty("BNBUSDT", 2.5, position_side="SHORT")

    self.assertEqual(result["quantity"], 2.49)
    self.assertEqual(result["quantity_source"], "account_trade_qty_sum")
    self.assertEqual(result["fill_ids"], ["902", "903"])


def test_close_position_qty_labels_unconfirmed_rounded_fallback(self):
    client = QuantityCloseClient(
        {"orderId": 44, "status": "NEW", "executedQty": "0"},
        {"orderId": 44, "status": "NEW", "executedQty": "0"},
        [],
    )
    with patch.object(binance_connector, "PAPER_MODE", False), patch.object(
        binance_connector, "_get_client", return_value=client
    ):
        result = binance_connector.close_position_qty("BNBUSDT", 2.5, position_side="SHORT")

    self.assertEqual(result["quantity"], 2.5)
    self.assertEqual(result["quantity_source"], "requested_rounded_unconfirmed")
    self.assertFalse(result["accounting_confirmed"])


def test_quantity_step_size_uses_exchange_lot_size_and_cache(self):
    client = Mock()
    client.futures_exchange_info.return_value = {
        "symbols": [{
            "symbol": "BNBUSDT",
            "filters": [{"filterType": "LOT_SIZE", "stepSize": "0.01"}],
        }]
    }
    binance_connector._quantity_step_cache.clear()
    self.assertEqual(binance_connector.get_quantity_step_size("BNBUSDT", client=client), 0.01)
    self.assertEqual(binance_connector.get_quantity_step_size("BNBUSDT", client=client), 0.01)
    client.futures_exchange_info.assert_called_once()
```

- [ ] **Step 2: Run the connector tests and verify failure**

Run:

```bash
python3 -m pytest tests/test_binance_safety.py -k 'close_position_qty_' -v
```

Expected: the new tests fail because `newOrderRespType`, `requested_quantity`, `quantity_source`, `fill_ids`, and `accounting_confirmed` are absent.

- [ ] **Step 3: Add execution-evidence helpers and enrich the close result**

Add above `close_position_qty`:

```python
_EXECUTED_ORDER_STATUSES = {"FILLED", "PARTIALLY_FILLED"}


def _positive_order_quantity(order: dict, source_prefix: str) -> tuple[float | None, str | None]:
    status = str(order.get("status") or "").upper()
    if status not in _EXECUTED_ORDER_STATUSES:
        return None, None
    for field in ("executedQty", "cumQty"):
        raw = order.get(field)
        if raw in (None, ""):
            continue
        try:
            quantity = abs(float(raw))
        except (TypeError, ValueError):
            continue
        if quantity > 0:
            return quantity, f"{source_prefix}.{field}"
    return None, None


def _resolve_close_execution(client, symbol: str, order: dict, requested_qty: float) -> dict:
    order_id = order.get("orderId")
    quantity, source = _positive_order_quantity(order, "create_response")
    if quantity is not None:
        return {"quantity": quantity, "quantity_source": source, "fill_ids": [], "accounting_confirmed": True}

    if order_id is not None:
        try:
            queried = client.futures_get_order(symbol=symbol, orderId=order_id)
        except Exception:
            queried = {}
        quantity, source = _positive_order_quantity(queried, "order_query")
        if quantity is not None:
            return {"quantity": quantity, "quantity_source": source, "fill_ids": [], "accounting_confirmed": True}

        try:
            fills = client.futures_account_trades(symbol=symbol, orderId=order_id)
        except Exception:
            fills = []
        matched = [row for row in fills or [] if str(row.get("orderId")) == str(order_id)]
        fill_qty = sum(abs(float(row.get("qty") or 0.0)) for row in matched)
        if fill_qty > 0:
            return {
                "quantity": fill_qty,
                "quantity_source": "account_trade_qty_sum",
                "fill_ids": [str(row.get("id")) for row in matched if row.get("id") is not None],
                "accounting_confirmed": True,
            }

    return {
        "quantity": requested_qty,
        "quantity_source": "requested_rounded_unconfirmed",
        "fill_ids": [],
        "accounting_confirmed": False,
    }
```

Move the existing precision map out of `_format_quantity` into `_QUANTITY_PRECISION`, add `_quantity_step_cache: dict[str, float] = {}`, and expose the cached exchange step:

```python
_QUANTITY_PRECISION = {
    "BTCUSDT": 3, "ETHUSDT": 2, "SOLUSDT": 0, "XRPUSDT": 0,
    "LINKUSDT": 2, "DOGEUSDT": 0, "SUIUSDT": 1, "HYPEUSDT": 2,
    "BNBUSDT": 2, "XAUUSDT": 3, "WLDUSDT": 0, "ZECUSDT": 3,
    "DRIFTUSDT": 0, "INJUSDT": 1, "NEARUSDT": 1, "ONDOUSDT": 1,
    "RENDERUSDT": 1, "ENAUSDT": 0, "SEIUSDT": 0,
}
_quantity_step_cache: dict[str, float] = {}


def _format_quantity(symbol: str, raw_qty: float) -> float:
    return round(raw_qty, _QUANTITY_PRECISION.get(symbol, 3))


def get_quantity_step_size(symbol: str, client=None) -> float:
    mapped = _map_symbol(symbol)
    if mapped in _quantity_step_cache:
        return _quantity_step_cache[mapped]
    exchange = client or _get_client()
    try:
        info = exchange.futures_exchange_info()
        symbol_info = next(row for row in info.get("symbols", []) if row.get("symbol") == mapped)
        lot_filter = next(row for row in symbol_info.get("filters", []) if row.get("filterType") == "LOT_SIZE")
        step = abs(float(lot_filter.get("stepSize") or 0.0))
    except (StopIteration, TypeError, ValueError):
        step = 10 ** (-_QUANTITY_PRECISION.get(mapped, 3))
    if step <= 0:
        step = 10 ** (-_QUANTITY_PRECISION.get(mapped, 3))
    _quantity_step_cache[mapped] = step
    return step
```

Change the market payload and result assembly:

```python
payload = {
    "symbol": symbol,
    "side": side,
    "type": "MARKET",
    "quantity": close_qty,
    "newOrderRespType": "RESULT",
}
# preserve the existing positionSide/reduceOnly branch
order = client.futures_create_order(**payload)
execution = _resolve_close_execution(client, symbol, order, close_qty)
return {
    "status": "partial_closed",
    "symbol": symbol,
    "position_side": pos_side,
    "order_id": order.get("orderId"),
    "requested_quantity": close_qty,
    "reason": reason,
    **execution,
}
```

Make the PAPER result use the same keys with `quantity_source="paper_simulated"` and `accounting_confirmed=True`. This confirms deterministic simulated accounting without claiming Binance evidence and prevents false accounting warnings in PAPER mode.

- [ ] **Step 4: Run focused connector tests**

Run:

```bash
python3 -m pytest tests/test_binance_safety.py -k 'close_position_qty_' -v
```

Expected: all selected tests pass, including existing quantity-close safety tests and the cached exchange-step test.

- [ ] **Step 5: Commit connector evidence**

```bash
git add binance_connector.py tests/test_binance_safety.py
git commit -m "fix: preserve partial close execution quantity"
```

### Task 2: Introduce the original-position accounting boundary

**Files:**
- Modify: `binance_monitor.py:2514-2550`
- Test: `tests/test_binance_monitor_protective_exits.py`

- [ ] **Step 1: Write failing fraction and recorder tests**

Add:

```python
def test_original_position_fraction_uses_float_epsilon_only(self):
    self.assertAlmostEqual(
        binance_monitor._original_position_fraction(100.0, 25.0),
        0.25,
        delta=1e-12,
    )
    self.assertEqual(
        binance_monitor._original_position_fraction(100.0, 100.0 + 5e-8),
        1.0,
    )
    self.assertIsNone(
        binance_monitor._original_position_fraction(100.0, 100.001),
    )
    self.assertIsNone(binance_monitor._original_position_fraction(0.0, 1.0))


def test_record_partial_exit_uses_confirmed_quantity_and_audit_fields(self):
    state = {"trade_id": 700, "original_qty": 100.0}
    result = {
        "quantity": 18.75,
        "requested_quantity": 18.75,
        "quantity_source": "create_response.executedQty",
        "accounting_confirmed": True,
        "order_id": 1234,
        "fill_ids": ["81", "82"],
    }
    with patch.object(binance_monitor.trade_db, "log_exit") as log_exit, patch.object(
        binance_monitor.trade_db, "update_trade_accounting_status"
    ) as update_status:
        binance_monitor._record_partial_exit(
            trade_id=700,
            exit_type="milestone_0",
            price=105.0,
            pnl_contribution=12.0,
            state=state,
            close_result=result,
            requested_qty=18.75,
            configured_close_pct=0.25,
            base_notes="milestone",
        )

    self.assertAlmostEqual(log_exit.call_args.kwargs["qty_pct"], 0.1875, delta=1e-12)
    notes = log_exit.call_args.kwargs["notes"]
    self.assertIn("closed_qty=18.75", notes)
    self.assertIn("original_qty=100", notes)
    self.assertIn("qty_source=create_response.executedQty", notes)
    self.assertIn("order_id=1234", notes)
    self.assertIn("fill_ids=81,82", notes)
    update_status.assert_not_called()


def test_unconfirmed_partial_is_recorded_unknown_and_marks_accounting_unchecked(self):
    state = {"trade_id": 701, "original_qty": 0.0}
    result = {
        "quantity": 2.5,
        "quantity_source": "requested_rounded_unconfirmed",
        "accounting_confirmed": False,
        "order_id": 55,
        "fill_ids": [],
    }
    with patch.object(binance_monitor.trade_db, "log_exit") as log_exit, patch.object(
        binance_monitor.trade_db, "update_trade_accounting_status"
    ) as update_status, patch.object(binance_monitor, "plain_log") as plain_log:
        binance_monitor._record_partial_exit(
            trade_id=701,
            exit_type="partial",
            price=100.0,
            pnl_contribution=None,
            state=state,
            close_result=result,
            requested_qty=2.5,
            configured_close_pct=0.25,
            base_notes="fallback",
        )

    self.assertIsNone(log_exit.call_args.kwargs["qty_pct"])
    update_status.assert_called_once()
    self.assertEqual(update_status.call_args.args[:2], (701, "unchecked"))
    self.assertIn("PARTIAL_EXIT_ACCOUNTING_WARNING", [call.args[0] for call in plain_log.call_args_list])


def test_quantity_reconciliation_uses_one_exchange_step(self):
    with patch.object(binance_monitor, "get_quantity_step_size", return_value=0.01):
        self.assertTrue(binance_monitor._quantities_reconcile("BNBUSDT", 10.00, 10.01))
        self.assertFalse(binance_monitor._quantities_reconcile("BNBUSDT", 10.00, 10.0101))


def test_known_exit_fraction_sum_ignores_unknown_rows(self):
    exits = [{"qty_pct": 0.25}, {"qty_pct": None}, {"qty_pct": 0.1875}]
    self.assertAlmostEqual(binance_monitor._known_exit_fraction_sum(exits), 0.4375, delta=1e-12)
```

- [ ] **Step 2: Run tests and verify failure**

```bash
python3 -m pytest tests/test_binance_monitor_protective_exits.py -k 'original_position_fraction or record_partial_exit or unconfirmed_partial' -v
```

Expected: failures because the new helpers do not exist, `_remaining_original_fraction` still returns `1.0` for a missing denominator, and reconciliation still uses hard-coded `0.001`/percentage tolerances.

- [ ] **Step 3: Implement the pure fraction helper and recorder**

Replace `_remaining_original_fraction` and add the shared recorder:

```python
def _original_position_fraction(original_qty: float, closed_qty: float) -> float | None:
    try:
        original = abs(float(original_qty))
        closed = abs(float(closed_qty))
    except (TypeError, ValueError):
        return None
    if original <= 0 or closed <= 0:
        return None
    epsilon = max(1e-12, original * 1e-9)
    if closed > original + epsilon:
        return None
    return min(1.0, closed / original)


def _remaining_original_fraction(state: dict, remaining_qty: float) -> float | None:
    """Return a terminal slice as a fraction of immutable original quantity."""
    return _original_position_fraction(state.get("original_qty"), remaining_qty)


def _record_partial_exit(
    *,
    trade_id: int,
    exit_type: str,
    price: float | None,
    pnl_contribution: float | None,
    state: dict,
    close_result: dict,
    requested_qty: float,
    configured_close_pct: float,
    base_notes: str,
) -> float | None:
    original_qty = abs(float(state.get("original_qty") or 0.0))
    closed_qty = abs(float(close_result.get("quantity") or requested_qty or 0.0))
    qty_source = str(close_result.get("quantity_source") or "requested_rounded_unconfirmed")
    qty_pct = _original_position_fraction(original_qty, closed_qty)
    order_id = close_result.get("order_id")
    fill_ids = ",".join(str(value) for value in close_result.get("fill_ids") or [])
    notes = (
        f"{base_notes}; closed_qty={closed_qty:.12g}; original_qty={original_qty:.12g}; "
        f"qty_pct={qty_pct if qty_pct is not None else 'unknown'}; "
        f"configured_current_pct={configured_close_pct:.12g}; qty_source={qty_source}; "
        f"order_id={order_id if order_id is not None else 'unknown'}; "
        f"fill_ids={fill_ids or 'none'}"
    )
    trade_db.log_exit(
        trade_id=trade_id,
        exit_type=exit_type,
        price=price,
        pnl_contribution=pnl_contribution,
        qty_pct=qty_pct,
        notes=notes,
    )
    confirmed = bool(close_result.get("accounting_confirmed"))
    if qty_pct is None or not confirmed:
        reason = "partial exit quantity is unconfirmed or has invalid original quantity"
        trade_db.update_trade_accounting_status(trade_id, "unchecked", f"{reason}; {notes}")
        plain_log("PARTIAL_EXIT_ACCOUNTING_WARNING", {
            "trade_id": trade_id,
            "exit_type": exit_type,
            "closed_qty": closed_qty,
            "original_qty": original_qty,
            "quantity_source": qty_source,
        })
    return qty_pct


def _quantity_reconciliation_tolerance(symbol: str) -> float:
    step = abs(float(get_quantity_step_size(symbol) or 0.0))
    return max(step, 1e-12)


def _quantities_reconcile(symbol: str, exchange_qty: float, expected_qty: float) -> bool:
    tolerance = _quantity_reconciliation_tolerance(symbol)
    epsilon = max(1e-12, abs(float(expected_qty)) * 1e-9)
    return abs(float(exchange_qty) - float(expected_qty)) <= tolerance + epsilon


def _known_exit_fraction_sum(exits: list) -> float:
    return sum(float(_row_get(row, "qty_pct", 0.0) or 0.0) for row in exits or [])
```

Import `get_quantity_step_size` from `binance_connector`. Replace every direct `sum(float(e["qty_pct"]) ...)` in the monitor with `_known_exit_fraction_sum(existing_exits)` so an intentionally unknown fraction cannot crash reconciliation. Then use these comparisons:

```python
# _roundtrip_guard_safe_context
qty_tolerance = _quantity_reconciliation_tolerance(symbol)
if not _quantities_reconcile(symbol, exchange_qty, expected_qty):
    detail.update({
        "reason": "qty_mismatch", "exchange_qty": exchange_qty,
        "expected_qty": expected_qty, "qty_tolerance": qty_tolerance,
    })
    return False, detail

# _check_sluggish_invalidation
if not _quantities_reconcile(symbol, exch_qty, db_expected_remaining_qty):
    return

# reconcile_missing_partial_exits
qty_tolerance = _quantity_reconciliation_tolerance(symbol)
if exch_qty >= db_expected_remaining_qty - qty_tolerance:
    if exch_qty > db_expected_remaining_qty + qty_tolerance:
        plain_log("POSITION_QTY_MISMATCH", {
            "symbol": symbol, "trade_id": trade_id,
            "exchange_qty": exch_qty, "db_qty": db_expected_remaining_qty,
            "qty_tolerance": qty_tolerance,
            "note": "Exchange quantity is larger than expected",
        })
    return
if not recorded_any and unexplained_missing_qty > qty_tolerance:
    sum_qty_pct = _known_exit_fraction_sum(existing_exits)
    db_expected_remaining_qty = original_qty * (1.0 - sum_qty_pct)
    new_unexplained = db_expected_remaining_qty - exch_qty
    if new_unexplained > qty_tolerance:
        plain_log("PARTIAL_EXIT_RECONCILIATION_UNRESOLVED", {
            "trade_id": trade_id, "symbol": symbol,
            "reason": f"Unexplained quantity mismatch of {new_unexplained:.12g}",
            "qty_tolerance": qty_tolerance,
        })

# _reconcile_orphan_positions
if _quantities_reconcile(symbol, exch_qty, expected_remaining_qty):
    plain_log("POSITION_QTY_RECONCILED", {
        "symbol": symbol, "trade_id": matched_trade["id"],
        "exchange_qty": exch_qty, "expected_qty": expected_remaining_qty,
    })
```

- [ ] **Step 4: Run helper tests**

```bash
python3 -m pytest tests/test_binance_monitor_protective_exits.py tests/test_partial_fill_reconciliation.py tests/test_system_sync.py -k 'original_position_fraction or record_partial_exit or unconfirmed_partial or terminal_exit_fraction or quantity' -v
```

Expected: all selected tests pass after updating the existing missing-denominator assertion to expect `None`; a difference of one BNB quantity step reconciles and a larger difference does not.

- [ ] **Step 5: Commit the accounting boundary**

```bash
git add binance_monitor.py tests/test_binance_monitor_protective_exits.py tests/test_partial_fill_reconciliation.py tests/test_system_sync.py
git commit -m "fix: define original position exit fractions"
```

### Task 3: Route every partial writer through the accounting boundary

**Files:**
- Modify: `binance_monitor.py:930-961,1524-1601,1686-1759,1771-1914,2291-2364,2552-2610`
- Test: `tests/test_early_profit_protection.py`
- Test: `tests/test_milestone_upgrades.py`
- Test: `tests/test_binance_monitor_protective_exits.py`
- Test: `tests/test_binance_safety.py`

- [ ] **Step 1: Strengthen existing writer tests with exact fractions**

Use broker-result dictionaries containing `quantity`, `quantity_source`, and `accounting_confirmed`. Add these assertions to the corresponding existing tests:

```python
# Early-profit: first close is 25% of 10; second is 25% of the fresh 7.5 snapshot.
mock_close.side_effect = [
    {"status": "partial_closed", "quantity": 2.5, "quantity_source": "create_response.executedQty", "accounting_confirmed": True},
    {"status": "partial_closed", "quantity": 1.875, "quantity_source": "create_response.executedQty", "accounting_confirmed": True},
]
first_position = self._make_position(volume=10.0, current_price=110.0, profit=100.0)
second_position = self._make_position(volume=7.5, current_price=110.0, profit=75.0)
bm._check_early_profit_protection(first_position)
state["_exit_action_claimed"] = False
bm._check_early_profit_protection(second_position)
self.assertAlmostEqual(mock_log_exit.call_args_list[0].kwargs["qty_pct"], 0.25, delta=1e-12)
self.assertAlmostEqual(mock_log_exit.call_args_list[1].kwargs["qty_pct"], 0.1875, delta=1e-12)
self.assertAlmostEqual(sum(call.kwargs["qty_pct"] for call in mock_log_exit.call_args_list), 0.4375, delta=1e-12)

# Time decay: requested 0.15 of original 1.0 remains 0.15.
self.assertAlmostEqual(mock_trade_db.log_exit.call_args.kwargs["qty_pct"], 0.15, delta=1e-12)

# Regime-aware and ordinary milestone: 25% of a current 75-unit snapshot against original 100.
self.assertAlmostEqual(mock_trade_db.log_exit.call_args.kwargs["qty_pct"], 0.1875, delta=1e-12)

# Time reduction: 50% of current 6 against original 10.
self.assertAlmostEqual(log_exit.call_args.kwargs["qty_pct"], 0.3, delta=1e-12)

# Exchange-detected TP: executedQty 0.5 against original 2.0.
self.assertAlmostEqual(mock_log_exit.call_args.kwargs["qty_pct"], 0.25, delta=1e-12)
self.assertIn("qty_source=filled_order.executedQty", mock_log_exit.call_args.kwargs["notes"])
```

Add this tiered-exit test:

```python
def test_tiered_exit_records_fraction_of_original_not_current_position(self):
    state = binance_monitor._get_state("SOLUSDT")
    state.update({"trade_id": 704, "original_qty": 100.0, "tiered_exits": []})
    cc_state = binance_monitor._get_position_state("SOLUSDT")
    cc_state["original_sl_distance"] = 10.0
    position = {
        "symbol": "SOLUSDT", "tv_symbol": "SOLUSDT", "type": "BUY",
        "openPrice": 100.0, "currentPrice": 115.0, "profit": 750.0, "volume": 50.0,
    }
    close_result = {
        "status": "partial_closed", "quantity": 25.0, "requested_quantity": 25.0,
        "quantity_source": "create_response.executedQty", "accounting_confirmed": True,
        "order_id": 705, "fill_ids": [],
    }
    with patch.object(binance_monitor, "PAPER_MODE", False), patch.object(
        binance_monitor, "close_position_qty", return_value=close_result
    ), patch.object(binance_monitor.trade_db, "log_exit") as log_exit, patch.object(
        binance_monitor, "_send_telegram"
    ):
        binance_monitor._check_tiered_exits(position)

    self.assertAlmostEqual(log_exit.call_args.kwargs["qty_pct"], 0.25, delta=1e-12)
```

- [ ] **Step 2: Run writer tests and verify the old configured percentages fail**

```bash
python3 -m pytest \
  tests/test_early_profit_protection.py \
  tests/test_milestone_upgrades.py \
  tests/test_binance_monitor_protective_exits.py \
  tests/test_binance_safety.py \
  -k 'early_profit or time_decay or milestone or regime_aware or tiered or time_reduce' -v
```

Expected: new fraction assertions fail on the existing hard-coded `close_pct`, `close_frac`, `0.15`, and `0.5` writers.

- [ ] **Step 3: Update time-decay and early-profit writers**

For PAPER branches, construct an explicit simulated result:

```python
result = {
    "status": "partial_closed",
    "quantity": close_qty,
    "requested_quantity": close_qty,
    "quantity_source": "paper_simulated",
    "accounting_confirmed": True,
    "order_id": None,
    "fill_ids": [],
}
```

For broker branches, assign `result = _close_position_once(...)`. Replace the time-decay `trade_db.log_exit` call with:

```python
_record_partial_exit(
    trade_id=tid,
    exit_type="15m_time_decay_trim",
    price=current,
    pnl_contribution=pnl * 0.15,
    state=state,
    close_result=result,
    requested_qty=close_qty,
    configured_close_pct=0.15,
    base_notes="15m Time-Decay Trim Executed (Closed 15% & SL to entry after 60m)",
)
```

Replace the early-profit `trade_db.log_exit` call with:

```python
_record_partial_exit(
    trade_id=tid,
    exit_type=f"early_profit_{key}",
    price=current,
    pnl_contribution=partial_pnl,
    state=state,
    close_result=result,
    requested_qty=close_qty,
    configured_close_pct=close_pct,
    base_notes=f"Early profit scale {key} at {current_r:.2f}R",
)
```

- [ ] **Step 4: Update normal and regime-aware milestone writers**

Use the same `result` shape for PAPER mode and preserve the connector result for exchange mode. Replace the common milestone writer with:

```python
_record_partial_exit(
    trade_id=tid,
    exit_type=gate_name,
    price=current,
    pnl_contribution=partial_pnl,
    state=state,
    close_result=result,
    requested_qty=close_qty,
    configured_close_pct=float(ms["close_pct"]),
    base_notes=f"{gate_name}: closed {int(ms['close_pct'] * 100)}% at R={round(current_r, 2)}",
)
```

This single call covers configured milestones and the injected `regime_aware_chop_profit_taken` path.

- [ ] **Step 5: Update exchange-detected TP milestone accounting**

Resolve `executedQty` first and `cumQty` only if absent, then pass a synthetic confirmed result:

```python
raw_executed = o.get("executedQty")
filled_field = "executedQty"
if raw_executed in (None, ""):
    raw_executed = o.get("cumQty")
    filled_field = "cumQty"
o_qty = abs(float(raw_executed or 0.0))
filled_result = {
    "status": "partial_closed",
    "quantity": o_qty,
    "requested_quantity": o_qty,
    "quantity_source": f"filled_order.{filled_field}",
    "accounting_confirmed": o_qty > 0,
    "order_id": o.get("orderId") or o.get("algoId"),
    "fill_ids": [],
}
_record_partial_exit(
    trade_id=trade_id,
    exit_type=milestone_name,
    price=o_price,
    pnl_contribution=realized_pnl,
    state=state,
    close_result=filled_result,
    requested_qty=o_qty,
    configured_close_pct=0.25,
    base_notes=f"Milestone TP1 filled on exchange @ {o_price:,.4f}",
)
```

Do not fall back from missing `executedQty`/`cumQty` to `origQty`; a requested protective-order quantity is not proof of a fill.

- [ ] **Step 6: Update tiered and time-reduction writers**

Replace the tiered writer with:

```python
_record_partial_exit(
    trade_id=tid,
    exit_type="partial",
    price=current,
    pnl_contribution=None,
    state=state,
    close_result=result,
    requested_qty=close_qty,
    configured_close_pct=close_frac,
    base_notes=f"Tiered exit {label} at {target_r}R",
)
```

Replace the time-reduction writer with:

```python
_record_partial_exit(
    trade_id=tid,
    exit_type="time_reduce",
    price=float(position.get("currentPrice", 0)),
    pnl_contribution=0,
    state=state,
    close_result=result,
    requested_qty=reduce_qty,
    configured_close_pct=0.5,
    base_notes=f"No 1R in {time_reduce_hours}h — reduce 50%",
)
```

- [ ] **Step 7: Run all writer tests**

```bash
python3 -m pytest \
  tests/test_early_profit_protection.py \
  tests/test_milestone_upgrades.py \
  tests/test_binance_monitor_protective_exits.py \
  tests/test_binance_safety.py -v
```

Expected: all four files pass; sequential reductions sum to `0.4375` and leave `0.5625`.

- [ ] **Step 8: Prove no configured percentage remains as persisted accounting**

```bash
rg -n 'qty_pct=(close_pct|close_frac|ms\["close_pct"\]|0\.15|0\.5)' binance_monitor.py
```

Expected: no matches.

- [ ] **Step 9: Commit all partial writers**

```bash
git add binance_monitor.py tests/test_early_profit_protection.py tests/test_milestone_upgrades.py tests/test_binance_monitor_protective_exits.py tests/test_binance_safety.py
git commit -m "fix: record actual partial exit fractions"
```

### Task 4: Correct terminal-exit fractions

**Files:**
- Modify: `binance_monitor.py:540-660,2578-2595,2613-3330`
- Test: `tests/test_binance_monitor_protective_exits.py`

- [ ] **Step 1: Write failing terminal tests**

Add assertions for missing original quantity, explicit terminal close response quantity, and an externally detected final slice after partials:

```python
def test_terminal_fraction_never_invents_full_close_without_original(self):
    self.assertIsNone(binance_monitor._remaining_original_fraction({}, 7.0))
    self.assertIsNone(binance_monitor._remaining_original_fraction({"original_qty": 10.0}, 0.0))


def test_time_exit_uses_broker_confirmed_terminal_quantity(self):
    state = binance_monitor._get_state("SOLUSDT")
    state.update({"trade_id": 702, "original_qty": 10.0})
    close_result = {
        "status": "closed",
        "quantity": 5.625,
        "quantity_source": "create_response.executedQty",
        "accounting_confirmed": True,
    }
    with patch.object(binance_monitor.trade_db, "get_trade_by_id", return_value=trade_row(25)), patch.object(
        binance_monitor.trade_db, "milestone_exists", return_value=False
    ), patch.object(binance_monitor.trade_db, "log_exit") as log_exit, patch.object(
        binance_monitor, "close_position_qty", return_value=close_result
    ), patch.object(binance_monitor, "_send_telegram"):
        binance_monitor._check_time_based_exit(self._position(volume=5.625))

    self.assertAlmostEqual(log_exit.call_args.kwargs["qty_pct"], 0.5625, delta=1e-12)


def test_external_close_records_only_unlogged_final_slice(self):
    state = binance_monitor._get_state("BNBUSDT")
    state.update({"trade_id": 703, "original_qty": 100.0, "entry_price": 100.0, "first_seen": 1.0})
    trade = {"id": 703, "symbol": "BNBUSDT", "direction": "SELL", "qty": 100.0, "exit_price": None}
    with patch.object(binance_monitor.trade_db, "get_open_trades", return_value=[]), patch.object(
        binance_monitor.trade_db, "get_trade_by_id", return_value=trade
    ), patch.object(binance_monitor.trade_db, "get_realized_exit_qty_pct", return_value=0.4375), patch.object(
        binance_monitor.trade_db, "log_exit"
    ) as log_exit, patch.object(binance_monitor.trade_db, "close_trade"), patch.object(
        binance_monitor.trade_db, "delete_binance_order_state"
    ), patch.object(binance_monitor, "_cancel_stale_reduce_only_orders", return_value=True), patch.object(
        binance_monitor, "_fetch_exchange_trade_ledger", return_value={
            "complete": True, "entry_price": 100.0, "entry_qty": 100.0, "exit_price": 95.0,
            "net_pnl": 500.0, "gross_pnl": 500.0, "fees": 0.0, "funding": 0.0,
        }
    ), patch.object(binance_monitor, "_send_telegram"):
        binance_monitor._prune_state(set())

    self.assertAlmostEqual(log_exit.call_args.kwargs["qty_pct"], 0.5625, delta=1e-12)


def test_time_reduce_is_not_misclassified_as_a_terminal_protective_exit(self):
    with patch.object(binance_monitor.trade_db, "get_exits_for_trade", return_value=[
        {"exit_type": "time_reduce", "qty_pct": 0.5, "price": 99.0},
    ]):
        self.assertIsNone(binance_monitor._latest_protective_exit(703))
```

- [ ] **Step 2: Run terminal tests and verify failure**

```bash
python3 -m pytest tests/test_binance_monitor_protective_exits.py -k 'terminal or time_exit or external_close' -v
```

Expected: the missing-original and external-close tests fail; the current prune path records `1.0`, and `time_reduce` is incorrectly returned as if it were terminal.

- [ ] **Step 3: Use confirmed broker quantities for explicit terminal writers**

Add a shared terminal recorder next to `_record_partial_exit`:

```python
def _record_terminal_exit(
    *,
    trade_id: int,
    exit_type: str,
    price: float | None,
    pnl_contribution: float | None,
    state: dict,
    close_result: dict,
    requested_qty: float,
    base_notes: str,
) -> float | None:
    terminal_qty = abs(float(close_result.get("quantity") or requested_qty or 0.0))
    terminal_fraction = _remaining_original_fraction(state, terminal_qty)
    qty_source = str(close_result.get("quantity_source") or "requested_rounded_unconfirmed")
    notes = (
        f"{base_notes}; closed_qty={terminal_qty:.12g}; "
        f"original_qty={abs(float(state.get('original_qty') or 0.0)):.12g}; "
        f"qty_pct={terminal_fraction if terminal_fraction is not None else 'unknown'}; terminal=true; "
        f"qty_source={qty_source}; order_id={close_result.get('order_id', 'unknown')}"
    )
    trade_db.log_exit(
        trade_id=trade_id,
        exit_type=exit_type,
        price=price,
        pnl_contribution=pnl_contribution,
        qty_pct=terminal_fraction,
        notes=notes,
    )
    if terminal_fraction is None or not close_result.get("accounting_confirmed"):
        trade_db.update_trade_accounting_status(
            trade_id,
            "unchecked",
            f"terminal quantity unconfirmed; {notes}",
        )
        plain_log("TERMINAL_EXIT_ACCOUNTING_WARNING", {
            "trade_id": trade_id,
            "exit_type": exit_type,
            "quantity_source": qty_source,
        })
    return terminal_fraction
```

Remove `"time_reduce"` from `PROTECTIVE_EXIT_TYPES`; it is a partial writer and must not suppress the later terminal row or become a terminal fill-query boundary.

Update `trade_db.get_realized_exit_qty_pct` with `AND COALESCE(notes, '') NOT LIKE '%terminal=true%'`, and add a regression test proving a `0.4375` partial plus a `0.5625` terminal row returns only `0.4375` from the partial-only helper.

Replace the six explicit terminal writers with these exact calls:

```python
# _check_time_based_exit
_record_terminal_exit(
    trade_id=tid, exit_type="time_exit", price=float(position.get("currentPrice", 0)),
    pnl_contribution=None, state=state, close_result=result, requested_qty=qty,
    base_notes=f"No 1R in {time_exit_hours}h — close remaining",
)

# _check_momentum_reversal
_record_terminal_exit(
    trade_id=tid, exit_type="momentum_exit", price=float(position.get("currentPrice", 0)),
    pnl_contribution=None, state=state, close_result=result, requested_qty=qty,
    base_notes=f"Peak {round(peak_r, 2)}R -> current {round(current_r, 2)}R (drop {round(peak_r - current_r, 2)}R)",
)

# _check_early_giveback_guard
_record_terminal_exit(
    trade_id=tid, exit_type=reason, price=float(position.get("currentPrice", 0)),
    pnl_contribution=None, state=state, close_result=result, requested_qty=qty,
    base_notes=f"Peak {round(peak_r, 2)}R gave back {giveback_pct:.1f}% to {round(current_r, 2)}R",
)

# _check_profit_protection
_record_terminal_exit(
    trade_id=tid, exit_type="profit_protect", price=float(position.get("currentPrice", 0)),
    pnl_contribution=None, state=state, close_result=result, requested_qty=qty,
    base_notes=f"Hit {round(peak_r, 2)}R then pulled back to {round(current_r, 2)}R (floor {round(floor_r, 2)}R)",
)

# _check_roundtrip_guard_r1
_record_terminal_exit(
    trade_id=trade_id, exit_type="roundtrip_guard_r1",
    price=float(position.get("currentPrice", 0) or 0.0), pnl_contribution=current_pnl,
    state=state, close_result=result, requested_qty=detail["exchange_qty"],
    base_notes=f"R1 roundtrip guard: peak_r={peak_r:.2f}, current_r={current_r:.2f}, giveback={giveback_pct:.1f}%",
)

# _check_sluggish_invalidation
_record_terminal_exit(
    trade_id=tid, exit_type="live_micro_sluggish_invalidation", price=exit_price,
    pnl_contribution=current_pnl, state=state, close_result=result, requested_qty=exch_qty,
    base_notes=f"Sluggish invalidation triggered at {round(age_minutes, 1)}m (peak_r={round(peak_r, 2)}R, current_r={round(current_r, 2)}R)",
)
```

- [ ] **Step 4: Correct the externally detected close path**

Before `trade_db.log_exit` in `_prune_state`, derive the final unlogged slice:

```python
partial_fraction = trade_db.get_realized_exit_qty_pct(tid)
original_qty = abs(float(state.get("original_qty") or _row_get(existing_trade, "qty", 0.0) or 0.0))
final_slice_qty = original_qty * max(0.0, 1.0 - partial_fraction)
terminal_fraction = _original_position_fraction(original_qty, final_slice_qty)
if terminal_fraction is None:
    trade_db.update_trade_accounting_status(
        tid,
        "unchecked",
        "externally detected close has no valid original/final slice quantity",
    )
trade_db.log_exit(
    trade_id=tid,
    exit_type=exit_reason,
    price=last_price,
    qty_pct=terminal_fraction,
    notes=f"Position closed via {exit_reason}; final_slice_qty={final_slice_qty:.12g}; original_qty={original_qty:.12g}",
)
```

Keep the existing guard that avoids writing a second terminal row when a protective exit is already logged.

- [ ] **Step 5: Run terminal and accounting tests**

```bash
python3 -m pytest tests/test_binance_monitor_protective_exits.py tests/test_trade_accounting.py tests/test_partial_fill_reconciliation.py -v
```

Expected: all selected files pass; no invalid denominator becomes `1.0`, and external final slice is `0.5625` after `0.4375` partials.

- [ ] **Step 6: Commit terminal fixes**

```bash
git add binance_monitor.py tests/test_binance_monitor_protective_exits.py
git commit -m "fix: preserve terminal exit slice accounting"
```

### Task 5: Build and verify the one-trade BNB repair

**Files:**
- Create: `scripts/repair_bnb_partial_exit_qty.py`
- Create: `tests/test_repair_bnb_partial_exit_qty.py`

- [ ] **Step 1: Write failing repair tests**

Create the test module with these fixtures and assertions:

```python
import sqlite3
from datetime import UTC, datetime

import pytest

from scripts import repair_bnb_partial_exit_qty as repair


FIXED_UTC_TIME = datetime(2026, 6, 30, 10, 0, 0, tzinfo=UTC)


def exact_fills():
    return [
        {"id": 143517400, "orderId": 1775544504, "time": 1782792512398, "side": "BUY", "positionSide": "SHORT", "qty": "4.53"},
        {"id": 143517525, "orderId": 1775555147, "time": 1782792554141, "side": "BUY", "positionSide": "SHORT", "qty": "3.40"},
    ]


def make_db(tmp_path):
    db_path = tmp_path / "trades.db"
    with sqlite3.connect(db_path) as conn:
        conn.executescript("""
            CREATE TABLE trades (id INTEGER PRIMARY KEY, symbol TEXT, direction TEXT, qty REAL);
            CREATE TABLE exits (
                id INTEGER PRIMARY KEY, trade_id INTEGER, exit_type TEXT,
                pnl_contribution REAL, qty_pct REAL, notes TEXT
            );
            INSERT INTO trades VALUES (100373, 'BNBUSDT', 'SELL', 18.13);
            INSERT INTO exits VALUES (1027, 100373, 'milestone_0', 5.85737090535025, 0.25, 'milestone note');
            INSERT INTO exits VALUES (1028, 100373, 'regime_aware_chop_profit_taken', 4.646296655, 0.25, 'chop note');
            INSERT INTO exits VALUES (1029, 999999, 'unrelated', 1.0, 0.25, 'untouched');
        """)
    return db_path


def snapshot_all_rows(db_path):
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        return {row["id"]: dict(row) for row in conn.execute("SELECT * FROM exits ORDER BY id")}


class FakeClient:
    def __init__(self, positions=None, normal_orders=None, algo_orders=None):
        self.positions = positions or []
        self.normal_orders = normal_orders or []
        self.algo_orders = algo_orders or []

    def futures_position_information(self):
        return self.positions

    def futures_get_open_orders(self):
        return self.normal_orders

    def futures_get_open_algo_orders(self):
        return self.algo_orders


def test_validate_evidence_requires_exact_unique_fill_mapping():
    fills = exact_fills()
    mapping = repair.validate_exchange_evidence(fills)
    assert mapping[1027]["orderId"] == 1775544504
    assert mapping[1028]["id"] == 143517525


def test_validate_evidence_rejects_competing_candidate():
    fills = exact_fills() + [
        {"id": 999, "orderId": 888, "time": 1782792515000, "side": "BUY", "positionSide": "SHORT", "qty": "4.53"}
    ]
    with pytest.raises(RuntimeError, match="ambiguous"):
        repair.validate_exchange_evidence(fills)


def test_apply_repair_backs_up_then_changes_only_two_qty_fractions(tmp_path):
    db_path = make_db(tmp_path)
    before = snapshot_all_rows(db_path)
    backup_path = repair.apply_repair(db_path, exact_fills(), now=FIXED_UTC_TIME)
    after = snapshot_all_rows(db_path)
    assert backup_path.exists()
    assert after[1027]["qty_pct"] == pytest.approx(4.53 / 18.13)
    assert after[1028]["qty_pct"] == pytest.approx(3.40 / 18.13)
    assert before[1027]["notes"] == after[1027]["notes"]
    assert before[1028]["pnl_contribution"] == after[1028]["pnl_contribution"]
    assert before[1029] == after[1029]


def test_apply_mode_refuses_any_open_exchange_position():
    client = FakeClient(positions=[{"symbol": "BTCUSDT", "positionAmt": "0.01"}])
    with pytest.raises(RuntimeError, match="exchange is not flat"):
        repair.assert_flat_exchange(client)
```

- [ ] **Step 2: Run repair tests and verify failure**

```bash
python3 -m pytest tests/test_repair_bnb_partial_exit_qty.py -v
```

Expected: import failure because the repair module does not exist.

- [ ] **Step 3: Implement strict constants, validation, backup, and mutation**

Create `scripts/repair_bnb_partial_exit_qty.py` with these locked values and interfaces:

```python
#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sqlite3
import sys
from datetime import UTC, datetime
from pathlib import Path

BOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BOT_DIR))

import trade_db
from binance_connector import _get_client

TRADE_ID = 100373
ORIGINAL_QTY = 18.13
EXPECTED = {
    1027: {"exit_type": "milestone_0", "fill_id": 143517400, "order_id": 1775544504, "qty": 4.53, "time": 1782792512398},
    1028: {"exit_type": "regime_aware_chop_profit_taken", "fill_id": 143517525, "order_id": 1775555147, "qty": 3.40, "time": 1782792554141},
}


def assert_flat_exchange(client) -> None:
    positions = client.futures_position_information()
    nonflat = [row for row in positions or [] if abs(float(row.get("positionAmt") or 0.0)) > 0]
    normal_orders = client.futures_get_open_orders()
    try:
        algo_orders = client.futures_get_open_algo_orders()
    except Exception as exc:
        raise RuntimeError(f"cannot verify exchange algo-order state: {exc}") from exc
    if nonflat or normal_orders or algo_orders:
        raise RuntimeError("exchange is not flat or still has open orders")


def validate_exchange_evidence(fills: list[dict]) -> dict[int, dict]:
    mapping = {}
    for exit_id, expected in EXPECTED.items():
        candidates = []
        for row in fills or []:
            if str(row.get("side") or "").upper() != "BUY":
                continue
            if str(row.get("positionSide") or "").upper() != "SHORT":
                continue
            if abs(float(row.get("qty") or 0.0) - expected["qty"]) > 1e-12:
                continue
            if abs(int(row.get("time") or 0) - expected["time"]) > 10_000:
                continue
            candidates.append(row)
        if len(candidates) != 1:
            raise RuntimeError(f"ambiguous exchange evidence for exit {exit_id}: {len(candidates)} candidates")
        row = candidates[0]
        if int(row.get("id")) != expected["fill_id"] or int(row.get("orderId")) != expected["order_id"]:
            raise RuntimeError(f"exchange identifiers changed for exit {exit_id}")
        mapping[exit_id] = row
    return mapping


def sqlite_online_backup(db_path: Path, now: datetime) -> Path:
    backup_dir = db_path.parent / "backups" / now.astimezone(UTC).strftime("%Y-%m-%d")
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup_path = backup_dir / f"{db_path.stem}_pre_partial_exit_repair_{now.astimezone(UTC).strftime('%H%M%S')}.db"
    if backup_path.exists():
        raise FileExistsError(backup_path)
    with sqlite3.connect(db_path) as source, sqlite3.connect(backup_path) as destination:
        source.backup(destination)
    return backup_path


def validate_db_state(db_path: Path) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        trade = conn.execute("SELECT id, symbol, direction, qty FROM trades WHERE id = ?", (TRADE_ID,)).fetchone()
        if not trade or trade["symbol"] != "BNBUSDT" or trade["direction"] != "SELL" or abs(float(trade["qty"]) - ORIGINAL_QTY) > 1e-12:
            raise RuntimeError("trade 100373 identity does not match repair contract")
        rows = conn.execute("SELECT * FROM exits WHERE id IN (1027, 1028) ORDER BY id").fetchall()
        if len(rows) != 2:
            raise RuntimeError("target exit rows are missing")
        for row in rows:
            expected = EXPECTED[row["id"]]
            if row["trade_id"] != TRADE_ID or row["exit_type"] != expected["exit_type"] or abs(float(row["qty_pct"]) - 0.25) > 1e-12:
                raise RuntimeError(f"exit {row['id']} no longer matches pre-repair state")


def apply_repair(db_path: Path, fills: list[dict], now: datetime | None = None) -> Path:
    validate_exchange_evidence(fills)
    validate_db_state(db_path)
    stamp = now or datetime.now(UTC)
    backup_path = sqlite_online_backup(db_path, stamp)
    with sqlite3.connect(db_path) as conn:
        conn.execute("BEGIN IMMEDIATE")
        for exit_id, expected in EXPECTED.items():
            cursor = conn.execute(
                "UPDATE exits SET qty_pct = ? WHERE id = ? AND trade_id = ? AND abs(qty_pct - 0.25) <= 1e-12",
                (expected["qty"] / ORIGINAL_QTY, exit_id, TRADE_ID),
            )
            if cursor.rowcount != 1:
                raise RuntimeError(f"compare-and-set failed for exit {exit_id}")
        conn.commit()
    return backup_path


def fetch_repair_fills(client) -> list[dict]:
    return client.futures_account_trades(
        symbol="BNBUSDT",
        startTime=1782791900000,
        endTime=1782792700000,
        limit=100,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Repair BNB trade 100373 partial-exit fractions")
    parser.add_argument("--apply", action="store_true", help="apply after exact evidence and flat-state checks")
    parser.add_argument("--db", type=Path, default=Path(trade_db.DB_PATH))
    args = parser.parse_args(argv)

    client = _get_client()
    fills = fetch_repair_fills(client)
    mapping = validate_exchange_evidence(fills)
    validate_db_state(args.db)
    for exit_id in sorted(EXPECTED):
        row = mapping[exit_id]
        expected = EXPECTED[exit_id]
        print(
            f"exit={exit_id} fill_id={row['id']} order_id={row['orderId']} "
            f"qty={expected['qty']} qty_pct={expected['qty'] / ORIGINAL_QTY:.12f}"
        )
    if not args.apply:
        print("DRY RUN: database unchanged")
        return 0

    assert_flat_exchange(client)
    backup_path = apply_repair(args.db, fills)
    print(f"backup={backup_path}")
    print("updated_exit_ids=1027,1028")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run repair tests**

```bash
python3 -m pytest tests/test_repair_bnb_partial_exit_qty.py -v
```

Expected: all repair tests pass and temporary backups are created only in test directories.

- [ ] **Step 5: Run the real repair utility in dry-run mode only**

```bash
python3 scripts/repair_bnb_partial_exit_qty.py
```

Expected: it prints the exact two exit/fill/order mappings and proposed values `4.53/18.13` and `3.40/18.13`; `trades.db` remains byte-for-byte unchanged.

- [ ] **Step 6: Commit the repair utility without applying it**

```bash
git add scripts/repair_bnb_partial_exit_qty.py tests/test_repair_bnb_partial_exit_qty.py
git commit -m "fix: add evidence locked BNB accounting repair"
```

### Task 6: Verify, review, merge, and perform the flat-state rollout

**Files:**
- Verify: all modified files
- Runtime targets after merge: `/home/rick/ozzy-bot/binance_connector.py`, `/home/rick/ozzy-bot/binance_monitor.py`, `/home/rick/ozzy-bot/scripts/repair_bnb_partial_exit_qty.py`

- [ ] **Step 1: Run focused accounting regression tests**

```bash
python3 -m pytest \
  tests/test_binance_safety.py \
  tests/test_early_profit_protection.py \
  tests/test_milestone_upgrades.py \
  tests/test_binance_monitor_protective_exits.py \
  tests/test_trade_accounting.py \
  tests/test_partial_fill_reconciliation.py \
  tests/test_repair_bnb_partial_exit_qty.py -v
```

Expected: all selected tests pass.

- [ ] **Step 2: Run the complete suite**

```bash
python3 -m pytest -q
```

Expected: exit code `0` with no failed or errored tests.

- [ ] **Step 3: Run static and diff checks**

```bash
python3 -m compileall -q binance_connector.py binance_monitor.py scripts/repair_bnb_partial_exit_qty.py
git diff --check origin/main...HEAD
rg -n 'qty_pct=(close_pct|close_frac|ms\["close_pct"\]|0\.15|0\.5)' binance_monitor.py
git status --short
```

Expected: compilation and diff checks succeed, the `rg` command prints no matches, and status contains only intentional committed changes.

- [ ] **Step 4: Request code review before merge**

Invoke `superpowers:requesting-code-review`. Review must check every writer listed in the spec, connector fallback semantics, terminal paths, and repair refusal behavior. Resolve all blocking findings and rerun Steps 1–3.

- [ ] **Step 5: Merge through the approved GitHub workflow**

Push `codex/fix-partial-exit-accounting`, open a PR against `main`, verify GitHub checks, and merge only after review. Record the resulting `origin/main` commit SHA. Do not restart services yet.

- [ ] **Step 6: Enforce the dynamic flat-state gate**

Run the existing read-only exchange/database/protection diagnostics and the repair dry run. Confirm:

```text
exchange positions = 0
normal open orders = 0
algo open orders = 0
DB open trades = 0
repair evidence rows = exactly 2
```

If any count is nonzero, stop rollout. Leave services and `trades.db` unchanged and report which gate failed.

- [ ] **Step 7: Deploy only the reviewed files into the active runtime checkout**

First prove the release worktree is clean and pinned to the merged SHA, then apply that merged diff for the three runtime targets to `/home/rick/ozzy-bot` without touching unrelated dirty-worktree files:

```bash
test -z "$(git status --porcelain)"
test "$(git rev-parse HEAD)" = "$(git rev-parse origin/main)"
diff -u /home/rick/.config/superpowers/worktrees/ozzy-bot/partial-exit-accounting/binance_connector.py /home/rick/ozzy-bot/binance_connector.py
diff -u /home/rick/.config/superpowers/worktrees/ozzy-bot/partial-exit-accounting/binance_monitor.py /home/rick/ozzy-bot/binance_monitor.py
diff -u /home/rick/.config/superpowers/worktrees/ozzy-bot/partial-exit-accounting/scripts/repair_bnb_partial_exit_qty.py /home/rick/ozzy-bot/scripts/repair_bnb_partial_exit_qty.py
```

Expected: all three commands produce no output and return exit code `0`.

- [ ] **Step 8: Recheck flat state, apply the repair, and restart together**

Re-run Step 6 immediately. If still flat:

```bash
cd /home/rick/ozzy-bot
python3 scripts/repair_bnb_partial_exit_qty.py --apply
systemctl --user restart ozzybot-webhook.service ozzybot-monitor.service
```

Expected: the utility prints a timestamped SQLite online-backup path and exactly two updated exit IDs; both services restart successfully.

- [ ] **Step 9: Verify database values and service health**

```bash
sqlite3 -header -column /home/rick/ozzy-bot/trades.db \
  "SELECT id, trade_id, exit_type, qty_pct, notes FROM exits WHERE id IN (1027,1028) ORDER BY id;"
systemctl --user is-active ozzybot-webhook.service ozzybot-monitor.service
journalctl --user -u ozzybot-webhook.service -u ozzybot-monitor.service --since '-5 minutes' --no-pager
```

Expected:

```text
exit 1027 qty_pct = 4.53 / 18.13
exit 1028 qty_pct = 3.40 / 18.13
notes unchanged
ozzybot-webhook.service = active
ozzybot-monitor.service = active
no startup traceback or PARTIAL_EXIT_ACCOUNTING_WARNING
```

- [ ] **Step 10: Audit the first runtime use of each writer**

For the first post-deployment partial exit, compare `closed_qty`, `original_qty`, `qty_pct`, `qty_source`, `order_id`, and `fill_ids` against Binance account trades. Mark the shared mechanism operationally proven only when they agree. Maintain a checklist for first use of exchange milestone, time decay, early profit, normal/regime milestone, tiered, and time reduction; any mismatch marks that trade unchecked and raises an alert without sending another broker action.
