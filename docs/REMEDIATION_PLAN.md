# OzzyBot Hedge Mode Remediation Plan

This remediation plan categorizes and prioritizing the issues identified in the order-writer audit. By addressing these systematically, we will guarantee absolute Hedge Mode safety, eliminate all `-4061` errors, and maintain ironclad protection on all lanes.

---

## Issue Classification Matrix

### P0: Critical Vulnerability (Risk of Unprotected Positions)
* **Description**: Defects that can leave a position completely or partially unprotected, or cause manual/automated close commands to fail silently or crash without closing the active risk.
* **Issues**:
  1. **`command_center.py:cmd_close` Partial Close Failure (Line 438)**:
     * **Symptom**: Raw market order placement with `reduceOnly=True` and no `positionSide` fails with a `-4061` error.
     * **Blast Radius**: When the user or AI issues a partial close command (e.g., `/close pct=50`), the order is completely rejected. The position remains fully open at original risk. The state might out-of-sync if the bot assumes the close succeeded, leading to a major gap in active risk management.
     * **Remediation**: Replace the direct `client.futures_create_order` call in `cmd_close` with a clean call to `close_position_qty(binance_sym, close_qty, reason="manual_close", position_side=position_side)`.

---

### P1: Degraded Protective Management (Stale Protection / No Adjustments)
* **Description**: Existing protection remains active (preventing liquidation or major losses), but automated/manual adjustments (like moving stops or take profits) are blocked by exchange rejections.
* **Issues**:
  1. **`command_center.py:_replace_protection_order_verified` Manual SL/TP Updates (Line 265)**:
     * **Symptom**: Calling `_place_sl_tp_order` without passing `position_side` causes updates via `/update_sl` or `/update_tp` to fail with a `-4061` error.
     * **Blast Radius**: The active position retains its old protective orders (so it remains protected), but the user or AI cannot manual move, lock, or adjust SL/TP orders. The stop adjustments are degraded, and alert spam begins.
     * **Remediation**:
       1. Modify `_replace_protection_order_verified` to accept a keyword argument `position_side: Optional[str] = None`.
       2. Pass `position_side=position_side` in the inner call to `_place_sl_tp_order`.
       3. In `cmd_update_sl` and `cmd_update_tp`, infer the position side:
          `position_side = "LONG" if side == "BUY" else "SHORT"` (where `side` is `pos.get("type")`)
          and pass it to `_replace_protection_order_verified`.
  2. **`binance_scalper.py` Standalone Strategy (Lines 155, 164, 172)**:
     * **Symptom**: Legacies raw placements using `reduceOnly` fail under Hedge Mode.
     * **Blast Radius**: The scalper is completely unusable if the account is in Hedge Mode.
     * **Remediation**: Add a large warning header and formally deprecate or disable this standalone script.

---

### P2: Observability & Alert Spacing (Observability / Spam Prevention)
* **Description**: Operational issues that cause high volumes of Telegram spam, log pollution, or unnecessary background loops but do not directly compromise protection.
* **Issues**:
  1. **Telegram Alert Spam from Failed Stop Updates**:
     * **Symptom**: When a trailing stop or breakeven update fails, the bot logs and alerts continuously.
     * **Blast Radius**: Flood of Telegram messages that can overwhelm channels and cause real emergencies to be missed.
     * **Remediation**: Ensure that `BINANCE_TRAIL_REPLACE_FAILED_OLD_SL_KEPT` logs are throttled/rate-limited and do not spam the channel.
  2. **`get_open_positions` Returning All Symbols**:
     * **Symptom**: The function returns a dictionary for all available symbols on the exchange, even those with zero volume.
     * **Blast Radius**: Background loops process a large list, creating potential performance/API lag.
     * **Remediation**: In a future refactor, ensure `get_open_positions` filters out any symbol where `volume == 0` or position is flat, keeping active tracking clean.

---

### P3: Structural Health & Code Hygiene
* **Description**: Structural improvements to prevent future regressions by enforcing cleaner boundaries.
* **Issues**:
  1. **Command Center Direct Connector Wrappers**:
     * **Remediation**: Establish a strict codebase standard where strategy and control layers (`command_center.py`, `webhook.py`) never import private helpers (like `_place_sl_tp_order`) or construct raw orders. They must always use public connector interfaces (`close_position`, `close_position_qty`, `place_trade`).
