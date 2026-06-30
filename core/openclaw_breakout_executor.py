#!/usr/bin/env python3
"""OpenClaw multi-setup trigger executor for TESTNET.

Consumes ``shared/active_orders.json`` blueprints produced by ``trend_executor.py``.
This module watches live 15m price action, confirms the armed trigger according to
the blueprint's ``assigned_setup_type`` (BREAKOUT, RETEST, PULLBACK, CONTINUATION,
or SHADOW_ONLY), then either POSTs a normal OzzyBot webhook payload or logs the
candidate to ``shared/openclaw_shadow_opportunities.json`` when shadow mode is on.

Execution policy (closed by design):
    * BREAKOUT is the only setup that may POST the webhook today.
    * RETEST / PULLBACK / CONTINUATION are evaluated and shadow-logged.
    * SHADOW_ONLY symbols are never promoted to live/testnet execution.
    * Setting ``HERMES_OPENCLAW_SHADOW_MODE=true`` disables all webhook posting
      and routes every setup type into the shadow opportunity log.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from lane_labels import BREAKOUT_RETEST, webhook_port_from_url
from logger import plain_log
from scripts.local_indicators import calculate_indicators, fetch_klines, get_live_indicators_dict
from config import WEBHOOK_SECRET as CONFIG_WEBHOOK_SECRET
from derivatives_context import fetch_derivatives_positioning_context

ACTIVE_ORDERS_PATH = Path(os.getenv("HERMES_OPENCLAW_ACTIVE_ORDERS", str(ROOT / "shared" / "active_orders.json")))
STATE_PATH = Path(os.getenv("HERMES_OPENCLAW_BREAKOUT_STATE", str(ROOT / "shared" / "openclaw_breakout_state.json")))
WEBHOOK_URL = os.getenv("HERMES_OPENCLAW_BREAKOUT_WEBHOOK_URL", "http://127.0.0.1:5001/webhook")
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET") or CONFIG_WEBHOOK_SECRET
TIMEFRAME = os.getenv("HERMES_OPENCLAW_BREAKOUT_TIMEFRAME", "15m")

# v2026-06-15b — Post-loss hardening from RENDER/HYPE testnet bleed.
# Evidence: RENDER fired from B/MIXED on body_atr=0.2703, volume=1.164,
# derivatives=mixed; HYPE fired from A on body_atr=0.30, volume=0.696 while
# 1H was hot/extended. Keep OpenClaw active, but require closed 15m candles,
# tier-specific impulse quality, and a 1H anti-chase context check.
USE_CLOSED_CANDLE = os.getenv("HERMES_OPENCLAW_BREAKOUT_USE_CLOSED_CANDLE", "true").lower() in {
    "1",
    "true",
    "yes",
    "on",
}
MIN_VOLUME_RATIO = float(os.getenv("HERMES_OPENCLAW_BREAKOUT_MIN_VOLUME_RATIO", "1.00"))
MIN_BODY_ATR = float(os.getenv("HERMES_OPENCLAW_BREAKOUT_MIN_BODY_ATR", "0.35"))
MAX_REJECTION_WICK = float(os.getenv("HERMES_OPENCLAW_BREAKOUT_MAX_REJECTION_WICK", "0.45"))
B_LANE_MIN_VOLUME_RATIO = float(os.getenv("HERMES_OPENCLAW_B_LANE_MIN_VOLUME_RATIO", "1.25"))
B_LANE_MIN_BODY_ATR = float(os.getenv("HERMES_OPENCLAW_B_LANE_MIN_BODY_ATR", "0.45"))
B_LANE_MAX_REJECTION_WICK = float(os.getenv("HERMES_OPENCLAW_B_LANE_MAX_REJECTION_WICK", "0.35"))
C_LANE_EXECUTE = os.getenv("HERMES_OPENCLAW_C_LANE_EXECUTE", "false").lower() in {"1", "true", "yes", "on"}
ANTI_CHASE_1H_RSI_BUY_MAX = float(os.getenv("HERMES_OPENCLAW_ANTI_CHASE_1H_RSI_BUY_MAX", "74"))
ANTI_CHASE_1H_RSI_SELL_MIN = float(os.getenv("HERMES_OPENCLAW_ANTI_CHASE_1H_RSI_SELL_MIN", "26"))
ANTI_CHASE_1H_EMA_DISTANCE_PCT = float(os.getenv("HERMES_OPENCLAW_ANTI_CHASE_1H_EMA_DISTANCE_PCT", "10"))
MAX_PROXIMITY_PCT = float(os.getenv("HERMES_OPENCLAW_BREAKOUT_MAX_PROXIMITY_PCT", "0.005"))
MAX_PROXIMITY_ATR_MULT = float(os.getenv("HERMES_OPENCLAW_BREAKOUT_MAX_PROXIMITY_ATR_MULT", "0.25"))
RR = float(os.getenv("HERMES_OPENCLAW_BREAKOUT_RR", "2.5"))
COOLDOWN_SECONDS = int(os.getenv("HERMES_OPENCLAW_BREAKOUT_COOLDOWN_SECONDS", str(4 * 60 * 60)))
EXECUTE = os.getenv("HERMES_OPENCLAW_BREAKOUT_EXECUTE", "true").lower() in {"1", "true", "yes", "on"}

# ── Multi-setup / shadow-mode configuration ───────────────────────────────────
SHADOW_MODE = os.getenv("HERMES_OPENCLAW_SHADOW_MODE", "false").lower() in {"1", "true", "yes", "on"}
SHADOW_OPPORTUNITIES_PATH = Path(
    os.getenv("HERMES_OPENCLAW_SHADOW_OPPORTUNITIES", str(ROOT / "shared" / "openclaw_shadow_opportunities.json"))
)
OPPORTUNITY_STATE_PATH = Path(
    os.getenv("HERMES_OPENCLAW_OPPORTUNITY_STATE", str(ROOT / "shared" / "openclaw_opportunity_state.json"))
)
RETEST_FRESHNESS_HOURS = float(os.getenv("HERMES_OPENCLAW_RETEST_FRESHNESS_HOURS", "12"))
RETEST_EXPIRY_CANDLES = int(os.getenv("HERMES_OPENCLAW_RETEST_EXPIRY_CANDLES", "48"))
PULLBACK_EMA_TIMEFRAME = os.getenv("HERMES_OPENCLAW_PULLBACK_EMA_TIMEFRAME", "1h")
PULLBACK_EMA_PROXIMITY_PCT = float(os.getenv("HERMES_OPENCLAW_PULLBACK_EMA_PROXIMITY_PCT", "0.004"))
CONTINUATION_LOOKBACK_TIMEFRAME = "15m"
CONTINUATION_LOOKBACK_CANDLES = 40
CONTINUATION_MIN_VOLUME_RATIO = 0.65
SHADOW_MIN_VOLUME_RATIO = float(os.getenv("HERMES_OPENCLAW_SHADOW_MIN_VOLUME_RATIO", "0.65"))
SHADOW_MIN_BODY_ATR = float(os.getenv("HERMES_OPENCLAW_SHADOW_MIN_BODY_ATR", "0.20"))
SHADOW_MAX_REJECTION_WICK = float(os.getenv("HERMES_OPENCLAW_SHADOW_MAX_REJECTION_WICK", "0.50"))
SHADOW_OPPORTUNITIES_MAX_ENTRIES = int(os.getenv("HERMES_OPENCLAW_SHADOW_OPPORTUNITIES_MAX_ENTRIES", "1000"))

# Closed execution allowlist. Promotion of RETEST/PULLBACK/CONTINUATION requires
# explicit human approval and a separate config/service change.
OPENCLAW_TESTNET_ENABLED_SETUPS = {"BREAKOUT"}


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _as_float(value: Any, default: float | None = None) -> float | None:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def load_active_blueprints(path: Path = ACTIVE_ORDERS_PATH) -> list[dict[str, Any]]:
    """Return armed OpenClaw macro-breakout blueprints from active_orders.json."""
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8") or "{}")
    rows: list[dict[str, Any]] = []
    for key, value in data.items():
        if str(key).startswith("_") or not isinstance(value, dict):
            continue
        status = str(value.get("status") or "").upper()
        if status != "ARMED":
            continue
        symbol = str(value.get("symbol") or key).upper()
        side = str(value.get("side") or "").upper()
        entry = _as_float(value.get("entry_price"))
        if symbol and side in {"BUY", "SELL"} and entry and entry > 0:
            rows.append({**value, "symbol": symbol, "side": side, "entry_price": entry})
    return sorted(rows, key=lambda row: row["symbol"])


def load_state(path: Path = STATE_PATH) -> dict[str, Any]:
    if not path.exists():
        return {"fired": {}, "last_scan": None, "last_results": []}
    try:
        return json.loads(path.read_text(encoding="utf-8") or "{}")
    except json.JSONDecodeError:
        return {"fired": {}, "last_scan": None, "last_results": []}


def save_state(state: dict[str, Any], path: Path = STATE_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")


def _breakout_key(blueprint: dict[str, Any]) -> str:
    return f"{blueprint['symbol']}:{blueprint['side']}:{float(blueprint['entry_price']):.8f}"


def _cooldown_active(blueprint: dict[str, Any], state: dict[str, Any], now: datetime | None = None) -> bool:
    now = now or utc_now()
    fired = state.get("fired") or {}
    row = fired.get(_breakout_key(blueprint))
    if not row:
        return False
    try:
        fired_at = datetime.fromisoformat(str(row.get("fired_at")).replace("Z", "+00:00"))
        if fired_at.tzinfo is None:
            fired_at = fired_at.replace(tzinfo=timezone.utc)
    except Exception:
        return False
    return (now - fired_at).total_seconds() < COOLDOWN_SECONDS


def _lane_tier(blueprint: dict[str, Any]) -> str:
    tier = str(blueprint.get("openclaw_lane_tier") or "").upper()
    if tier in {"A", "B", "C"}:
        return tier
    label = str(blueprint.get("entry_setup_label") or "").upper()
    if "B_MIXED" in label:
        return "B"
    if "C_MODERATE" in label:
        return "C"
    return "A"


def _tier_thresholds(blueprint: dict[str, Any]) -> tuple[float, float, float]:
    tier = _lane_tier(blueprint)
    if tier == "B":
        return B_LANE_MIN_VOLUME_RATIO, B_LANE_MIN_BODY_ATR, B_LANE_MAX_REJECTION_WICK
    return MIN_VOLUME_RATIO, MIN_BODY_ATR, MAX_REJECTION_WICK


def _assigned_setup_type(blueprint: dict[str, Any]) -> str:
    return str(blueprint.get("assigned_setup_type") or "BREAKOUT").upper()


def _breakout_memory_key(symbol: str, side: str, trigger: float) -> str:
    return f"{symbol.upper()}:{side.upper()}:{float(trigger):.8f}"


def load_opportunity_state(path: Path = OPPORTUNITY_STATE_PATH) -> dict[str, Any]:
    """Load the retest-breakout memory state file."""
    if not path.exists():
        return {"version": 1, "updated_at": None, "breakouts": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8") or "{}")
        if not isinstance(data, dict):
            return {"version": 1, "updated_at": None, "breakouts": {}}
        data.setdefault("version", 1)
        data.setdefault("updated_at", None)
        data.setdefault("breakouts", {})
        return data
    except json.JSONDecodeError:
        return {"version": 1, "updated_at": None, "breakouts": {}}


def save_opportunity_state(state: dict[str, Any], path: Path = OPPORTUNITY_STATE_PATH) -> None:
    """Persist the retest-breakout memory state file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")


def record_breakout_memory(
    blueprint: dict[str, Any],
    indicators: dict[str, Any],
    now: datetime | None = None,
) -> dict[str, Any]:
    """Record a fresh breakout event so that RETEST mode can reference it later."""
    now = now or utc_now()
    symbol = str(blueprint.get("symbol") or "").upper()
    side = str(blueprint.get("side") or "").upper()
    trigger = float(blueprint["entry_price"])
    close = _as_float(indicators.get("close"), trigger) or trigger
    key = _breakout_memory_key(symbol, side, trigger)
    expires_at = now + timedelta(hours=RETEST_FRESHNESS_HOURS)
    record: dict[str, Any] = {
        "symbol": symbol,
        "side": side,
        "trigger": trigger,
        "breakout_time": now.isoformat(),
        "breakout_timeframe": TIMEFRAME,
        "breakout_candle_close": close,
        "expires_at": expires_at.isoformat(),
        "freshness_hours": RETEST_FRESHNESS_HOURS,
        "expiry_candles": RETEST_EXPIRY_CANDLES,
        "source": "openclaw_opportunity_engine",
    }
    state = load_opportunity_state()
    state.setdefault("breakouts", {})[key] = record
    state["updated_at"] = now.isoformat()
    save_opportunity_state(state)
    return record


def prior_breakout_fresh(
    blueprint: dict[str, Any],
    state: dict[str, Any],
    now: datetime | None = None,
) -> tuple[bool, dict[str, Any] | None]:
    """Return (is_fresh, record) for a prior breakout keyed by symbol:side:trigger."""
    now = now or utc_now()
    symbol = str(blueprint.get("symbol") or "").upper()
    side = str(blueprint.get("side") or "").upper()
    trigger = _as_float(blueprint.get("entry_price"), 0.0) or 0.0
    key = _breakout_memory_key(symbol, side, trigger)
    record = (state or {}).get("breakouts", {}).get(key)
    if not record:
        return False, None
    try:
        expires_at = datetime.fromisoformat(str(record.get("expires_at")).replace("Z", "+00:00"))
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
    except Exception:
        return False, record
    return now < expires_at, record


def load_shadow_opportunities(path: Path = SHADOW_OPPORTUNITIES_PATH) -> list[dict[str, Any]]:
    """Load the rolling shadow opportunity log."""
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8") or "[]")
        return data if isinstance(data, list) else []
    except json.JSONDecodeError:
        return []


def save_shadow_opportunities(rows: list[dict[str, Any]], path: Path = SHADOW_OPPORTUNITIES_PATH) -> None:
    """Persist the shadow opportunity log, keeping the most recent entries."""
    path.parent.mkdir(parents=True, exist_ok=True)
    trimmed = rows[-SHADOW_OPPORTUNITIES_MAX_ENTRIES:]
    path.write_text(json.dumps(trimmed, indent=2, default=str), encoding="utf-8")


def log_shadow_opportunity(
    blueprint: dict[str, Any],
    verdict: dict[str, Any],
    indicators: dict[str, Any],
    path: Path = SHADOW_OPPORTUNITIES_PATH,
) -> dict[str, Any]:
    """Append a would-fire candidate to the shadow opportunity log."""
    entry, sl, tp, _rr = _derive_levels(blueprint, indicators)
    record: dict[str, Any] = {
        "symbol": str(blueprint.get("symbol") or verdict.get("symbol") or "").upper(),
        "setup": verdict.get("assigned_setup_type") or _assigned_setup_type(blueprint),
        "direction": str(blueprint.get("side") or verdict.get("signal") or "").upper(),
        "confidence": 0.85 if verdict.get("would_fire") else 0.25,
        "entry_price": float(blueprint.get("entry_price") or entry),
        "sl": sl,
        "tp": tp,
        "reason": verdict.get("reason"),
        "grade": str(blueprint.get("openclaw_lane_tier") or "A"),
        "timestamp": utc_now().isoformat(),
        "status": verdict.get("status"),
        "would_fire": verdict.get("would_fire"),
    }
    rows = load_shadow_opportunities(path)
    rows.append(record)
    save_shadow_opportunities(rows, path)
    return record


def setup_execution_enabled(setup_type: str) -> bool:
    """Return True when a setup type is allowed to POST the webhook today."""
    if SHADOW_MODE:
        return False
    return str(setup_type).upper() in OPENCLAW_TESTNET_ENABLED_SETUPS


def should_post_webhook(result: dict[str, Any]) -> bool:
    """Return True only when a verdict is both valid and enabled for execution."""
    return result.get("passed") is True and result.get("execution_enabled") is True


def get_higher_timeframe_context(symbol: str, interval: str = "1h") -> dict[str, Any] | None:
    """Return closed-candle 1H RSI/EMA extension context for anti-chase checks."""
    df = fetch_klines(symbol, interval=interval, limit=240)
    if df is None or len(df) < 205:
        return None
    df = calculate_indicators(df)
    df["ema200"] = df["close"].ewm(span=200, adjust=False).mean()
    latest = df.iloc[-2]
    close = float(latest["close"])
    ema200 = float(latest["ema200"])
    if ema200 <= 0:
        return None
    return {
        "interval": interval,
        "open_time": latest["open_datetime"].isoformat(),
        "close": round(close, 8),
        "ema200": round(ema200, 8),
        "ema_distance_pct": round(((close - ema200) / ema200) * 100, 4),
        "rsi": round(float(latest["rsi"]), 2),
    }


def _anti_chase_reason(side: str, context: dict[str, Any] | None) -> str | None:
    if not context:
        return "missing_1h_context"
    rsi = _as_float(context.get("rsi"))
    ema_distance = _as_float(context.get("ema_distance_pct"))
    if rsi is None or ema_distance is None:
        return "missing_1h_context"
    if side == "BUY" and rsi > ANTI_CHASE_1H_RSI_BUY_MAX and ema_distance > ANTI_CHASE_1H_EMA_DISTANCE_PCT:
        return "overextended_1h_rsi_ema_chase"
    if side == "SELL" and rsi < ANTI_CHASE_1H_RSI_SELL_MIN and ema_distance < -ANTI_CHASE_1H_EMA_DISTANCE_PCT:
        return "overextended_1h_rsi_ema_chase"
    return None


def evaluate_breakout_setup(
    blueprint: dict[str, Any],
    indicators: dict[str, Any],
    higher_tf_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Confirm a decisive breakout through the armed trigger with closed-candle quality."""
    side = str(blueprint.get("side") or "").upper()
    tier = _lane_tier(blueprint)
    if SHADOW_MODE:
        min_volume_ratio = SHADOW_MIN_VOLUME_RATIO
        min_body_atr = SHADOW_MIN_BODY_ATR
        max_rejection_wick = SHADOW_MAX_REJECTION_WICK
    else:
        min_volume_ratio, min_body_atr, max_rejection_wick = _tier_thresholds(blueprint)

    trigger = float(blueprint["entry_price"])
    close = float(indicators["close"])
    open_price = float(indicators["open"])
    high = float(indicators["high"])
    low = float(indicators["low"])
    volume_ratio = _as_float(indicators.get("volume_ratio"), 0.0) or 0.0
    atr = _as_float(indicators.get("atr"), 0.0) or 0.0
    body = abs(close - open_price)
    body_atr = body / atr if atr > 0 else 0.0
    proximity_distance = abs(close - trigger)
    pct_limit = abs(trigger) * MAX_PROXIMITY_PCT
    atr_limit = atr * MAX_PROXIMITY_ATR_MULT if atr > 0 else pct_limit
    proximity_limit = min(pct_limit, atr_limit) if atr_limit > 0 else pct_limit

    reasons: list[str] = []
    if tier == "C" and not C_LANE_EXECUTE:
        reasons.append("c_lane_observe_only")
    if side == "BUY":
        if close < trigger:
            reasons.append("close_not_beyond_trigger")
        elif proximity_distance > proximity_limit:
            reasons.append("chasing_avoided_price_too_far_above_trigger")
        if high < trigger:
            reasons.append("trigger_not_touched")
        if float(indicators.get("top_wick_pct") or 0.0) > max_rejection_wick:
            reasons.append("bearish_rejection_wick_too_large")
        signal = "BUY"
    elif side == "SELL":
        if close > trigger:
            reasons.append("close_not_beyond_trigger")
        elif proximity_distance > proximity_limit:
            reasons.append("chasing_avoided_price_too_far_below_trigger")
        if low > trigger:
            reasons.append("trigger_not_touched")
        if float(indicators.get("bottom_wick_pct") or 0.0) > max_rejection_wick:
            reasons.append("bullish_rejection_wick_too_large")
        signal = "SELL"
    else:
        reasons.append("invalid_side")
        signal = side

    if volume_ratio < min_volume_ratio:
        reasons.append("volume_expansion_missing")
    if body_atr < min_body_atr:
        reasons.append("displacement_body_too_small")
    chase_reason = _anti_chase_reason(side, higher_tf_context)
    if chase_reason:
        reasons.append(chase_reason)

    would_fire = not reasons
    execution_enabled = setup_execution_enabled("BREAKOUT")
    if SHADOW_MODE:
        passed = False
        status = "SHADOW_WOULD_FIRE" if would_fire else "SHADOW_WAIT"
    else:
        passed = would_fire
        status = "BREAKOUT_CONFIRMED" if passed else "WAIT"

    return {
        "symbol": blueprint.get("symbol"),
        "signal": signal,
        "passed": passed,
        "would_fire": would_fire,
        "execution_enabled": execution_enabled,
        "status": status,
        "reason": "breakout_confirmed" if would_fire else "breakout_not_confirmed",
        "reasons": reasons,
        "trigger": trigger,
        "close": close,
        "volume_ratio": round(volume_ratio, 4),
        "body_atr": round(body_atr, 4),
        "proximity_pct": round((proximity_distance / trigger) * 100, 4) if trigger else None,
        "proximity_limit": round(proximity_limit, 8),
        "timeframe": TIMEFRAME,
        "use_closed_candle": USE_CLOSED_CANDLE,
        "assigned_setup_type": "BREAKOUT",
        "secondary_setup_type": blueprint.get("secondary_setup_type", "NONE") or "NONE",
        "lane_tier": tier,
        "min_volume_ratio": min_volume_ratio,
        "min_body_atr": min_body_atr,
        "max_rejection_wick": max_rejection_wick,
        "higher_tf_context": higher_tf_context,
    }


def evaluate_retest_setup(
    blueprint: dict[str, Any],
    indicators: dict[str, Any],
    state: dict[str, Any] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Confirm a retest of a prior breakout level with rejection/wick evidence."""
    side = str(blueprint.get("side") or "").upper()
    symbol = blueprint.get("symbol")
    trigger = float(blueprint["entry_price"])
    close = float(indicators["close"])
    open_price = float(indicators.get("open") or close)
    high = float(indicators["high"])
    low = float(indicators["low"])
    atr = _as_float(indicators.get("atr"), 0.0) or 0.0
    bottom_wick_pct = float(indicators.get("bottom_wick_pct") or 0.0)
    top_wick_pct = float(indicators.get("top_wick_pct") or 0.0)

    effective_state = state if state is not None else load_opportunity_state()
    fresh, _record = prior_breakout_fresh(blueprint, effective_state, now)

    reasons: list[str] = []
    if not fresh:
        reasons.append("no_fresh_prior_breakout")

    buffer = max(abs(trigger) * 0.002, atr * 0.15)
    if side == "BUY":
        if low > trigger + buffer:
            reasons.append("price_not_near_retest_zone")
        if close <= trigger:
            reasons.append("close_not_above_trigger")
        if bottom_wick_pct < 0.30 and close <= open_price:
            reasons.append("missing_bullish_rejection_wick")
        signal = "BUY"
    elif side == "SELL":
        if high < trigger - buffer:
            reasons.append("price_not_near_retest_zone")
        if close >= trigger:
            reasons.append("close_not_below_trigger")
        if top_wick_pct < 0.30 and close >= open_price:
            reasons.append("missing_bearish_rejection_wick")
        signal = "SELL"
    else:
        reasons.append("invalid_side")
        signal = side

    would_fire = not reasons
    execution_enabled = setup_execution_enabled("RETEST")
    passed = execution_enabled and would_fire
    status = "OPENCLAW_RETEST_CONFIRMED" if would_fire else "WAIT"

    return {
        "symbol": symbol,
        "signal": signal,
        "passed": passed,
        "would_fire": would_fire,
        "execution_enabled": execution_enabled,
        "status": status,
        "reason": status if would_fire else reasons[0] if reasons else "retest_wait",
        "reasons": reasons,
        "trigger": trigger,
        "close": close,
        "retest_buffer": round(buffer, 8),
        "atr": round(atr, 4),
        "timeframe": TIMEFRAME,
        "assigned_setup_type": "RETEST",
        "secondary_setup_type": blueprint.get("secondary_setup_type", "NONE") or "NONE",
    }


def evaluate_pullback_setup(
    blueprint: dict[str, Any],
    indicators: dict[str, Any],
    higher_tf_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Confirm a mean-reverting pullback to the 1H EMA200 value zone."""
    side = str(blueprint.get("side") or "").upper()
    symbol = blueprint.get("symbol")
    close = float(indicators["close"])
    open_price = float(indicators.get("open") or close)
    rsi = _as_float(indicators.get("rsi"))
    bottom_wick_pct = float(indicators.get("bottom_wick_pct") or 0.0)
    top_wick_pct = float(indicators.get("top_wick_pct") or 0.0)

    ema200 = _as_float(indicators.get("ema200_1h"))
    if ema200 is None and higher_tf_context is not None:
        ema200 = _as_float(higher_tf_context.get("ema200"))

    reasons: list[str] = []
    if ema200 is None or ema200 <= 0:
        reasons.append("missing_1h_ema200")
    else:
        distance_pct = abs(close - ema200) / ema200
        if distance_pct > PULLBACK_EMA_PROXIMITY_PCT:
            reasons.append("price_not_near_1h_ema200")

    if rsi is None:
        reasons.append("missing_rsi")
    elif side == "BUY" and rsi > 45:
        reasons.append("rsi_not_cooled_for_buy")
    elif side == "SELL" and rsi < 55:
        reasons.append("rsi_not_cooled_for_sell")

    if side == "BUY":
        if close <= open_price and bottom_wick_pct < 0.45:
            reasons.append("missing_bullish_reclaim")
        signal = "BUY"
    elif side == "SELL":
        if close >= open_price and top_wick_pct < 0.45:
            reasons.append("missing_bearish_reclaim")
        signal = "SELL"
    else:
        reasons.append("invalid_side")
        signal = side

    would_fire = not reasons
    execution_enabled = setup_execution_enabled("PULLBACK")
    passed = execution_enabled and would_fire
    status = "OPENCLAW_PULLBACK_VALUE_RECLAIM" if would_fire else "WAIT"

    return {
        "symbol": symbol,
        "signal": signal,
        "passed": passed,
        "would_fire": would_fire,
        "execution_enabled": execution_enabled,
        "status": status,
        "reason": status if would_fire else reasons[0] if reasons else "pullback_wait",
        "reasons": reasons,
        "trigger": float(blueprint["entry_price"]),
        "close": close,
        "ema200_1h": ema200,
        "rsi": rsi,
        "timeframe": TIMEFRAME,
        "assigned_setup_type": "PULLBACK",
        "secondary_setup_type": blueprint.get("secondary_setup_type", "NONE") or "NONE",
    }


def evaluate_continuation_setup(
    blueprint: dict[str, Any],
    indicators: dict[str, Any],
    recent_candles: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Confirm a continuation break out of a 40-candle 15m compression range."""
    side = str(blueprint.get("side") or "").upper()
    symbol = blueprint.get("symbol")
    close = float(indicators["close"])
    volume_ratio = _as_float(indicators.get("volume_ratio"), 0.0) or 0.0

    reasons: list[str] = []
    if not recent_candles or len(recent_candles) < CONTINUATION_LOOKBACK_CANDLES:
        reasons.append(f"missing_{CONTINUATION_LOOKBACK_CANDLES}_closed_15m_candles")
        range_high = None
        range_low = None
    else:
        lookback = recent_candles[-CONTINUATION_LOOKBACK_CANDLES:]
        range_high = max(float(c["high"]) for c in lookback)
        range_low = min(float(c["low"]) for c in lookback)
        if side == "BUY" and close <= range_high:
            reasons.append("close_not_above_minor_range_high")
        elif side == "SELL" and close >= range_low:
            reasons.append("close_not_below_minor_range_low")

    if volume_ratio < CONTINUATION_MIN_VOLUME_RATIO:
        reasons.append("volume_expansion_missing")

    would_fire = not reasons
    execution_enabled = setup_execution_enabled("CONTINUATION")
    passed = execution_enabled and would_fire
    status = "OPENCLAW_CONTINUATION_FLAG_BREAK" if would_fire else "WAIT"

    return {
        "symbol": symbol,
        "signal": side if side in {"BUY", "SELL"} else "UNKNOWN",
        "passed": passed,
        "would_fire": would_fire,
        "execution_enabled": execution_enabled,
        "status": status,
        "reason": status if would_fire else reasons[0] if reasons else "continuation_wait",
        "reasons": reasons,
        "trigger": float(blueprint["entry_price"]),
        "close": close,
        "volume_ratio": round(volume_ratio, 4),
        "range_high": range_high,
        "range_low": range_low,
        "timeframe": TIMEFRAME,
        "assigned_setup_type": "CONTINUATION",
        "secondary_setup_type": blueprint.get("secondary_setup_type", "NONE") or "NONE",
    }


def evaluate_shadow_setup(blueprint: dict[str, Any]) -> dict[str, Any]:
    """Terminal observation-only handler for bench-watch symbols."""
    side = str(blueprint.get("side") or "").upper()
    return {
        "symbol": blueprint.get("symbol"),
        "signal": side,
        "passed": False,
        "would_fire": False,
        "execution_enabled": False,
        "status": "SHADOW_OBSERVE",
        "reason": "bench_watch_observation_only",
        "reasons": ["bench_watch_observation_only"],
        "assigned_setup_type": "SHADOW_ONLY",
        "secondary_setup_type": blueprint.get("secondary_setup_type", "NONE") or "NONE",
        "timeframe": TIMEFRAME,
    }


def evaluate_blueprint_trigger(
    blueprint: dict[str, Any],
    indicators: dict[str, Any],
    higher_tf_context: dict[str, Any] | None = None,
    state: dict[str, Any] | None = None,
    recent_candles: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Dispatch a blueprint to its assigned setup evaluator and return a verdict."""
    side = str(blueprint.get("side") or "").upper()
    assigned_setup_type = _assigned_setup_type(blueprint)
    secondary_setup_type = str(blueprint.get("secondary_setup_type") or "NONE") or "NONE"

    if assigned_setup_type == "SHADOW_ONLY":
        if SHADOW_MODE:
            return evaluate_shadow_setup(blueprint)
        return {
            "symbol": blueprint.get("symbol"),
            "signal": side,
            "passed": False,
            "would_fire": False,
            "execution_enabled": False,
            "status": "SHADOW_OBSERVE",
            "reason": "bench_watch_observation_only",
            "reasons": ["bench_watch_observation_only"],
            "assigned_setup_type": assigned_setup_type,
            "secondary_setup_type": secondary_setup_type,
            "timeframe": TIMEFRAME,
        }

    if assigned_setup_type == "BREAKOUT":
        return evaluate_breakout_setup(blueprint, indicators, higher_tf_context)

    if assigned_setup_type == "RETEST":
        inner = evaluate_retest_setup(blueprint, indicators, state, utc_now())
    elif assigned_setup_type == "PULLBACK":
        inner = evaluate_pullback_setup(blueprint, indicators, higher_tf_context)
    elif assigned_setup_type == "CONTINUATION":
        inner = evaluate_continuation_setup(blueprint, indicators, recent_candles)
    else:
        return {
            "symbol": blueprint.get("symbol"),
            "signal": side,
            "passed": False,
            "would_fire": False,
            "execution_enabled": False,
            "status": "WAIT",
            "reason": "unknown_setup_type",
            "reasons": ["unknown_setup_type"],
            "assigned_setup_type": assigned_setup_type,
            "secondary_setup_type": secondary_setup_type,
            "timeframe": TIMEFRAME,
        }

    if SHADOW_MODE:
        inner["passed"] = False
        inner["execution_enabled"] = False
        inner["status"] = "SHADOW_WOULD_FIRE" if inner.get("would_fire") else "SHADOW_WAIT"
        inner["assigned_setup_type"] = assigned_setup_type
        inner["secondary_setup_type"] = secondary_setup_type
        return inner

    # Non-shadow, non-breakout setups are observed-only until explicitly promoted.
    # The legacy reason string is preserved so existing live-micro behavior/tests
    # remain stable; the real evaluator result is available in ``inner_result``.
    return {
        "symbol": blueprint.get("symbol"),
        "signal": side,
        "passed": False,
        "would_fire": inner.get("would_fire"),
        "execution_enabled": False,
        "status": "WOULD_FIRE_OBSERVE" if inner.get("would_fire") else "WAIT",
        "reason": "setup_not_enabled_for_breakout_executor",
        "reasons": ["setup_not_enabled_for_breakout_executor"],
        "assigned_setup_type": assigned_setup_type,
        "secondary_setup_type": secondary_setup_type,
        "inner_result": inner,
        "timeframe": TIMEFRAME,
    }


def attach_derivatives_context(
    verdict: dict[str, Any],
    fetcher=fetch_derivatives_positioning_context,
) -> dict[str, Any]:
    """Attach derivatives context without changing pass/fail outcome.

    This is advisory-only evidence for review/backtesting. It must not mutate
    reasons or flip ``passed`` because phase 1 is observation, not a new gate.
    """
    enriched = dict(verdict)
    symbol = str(enriched.get("symbol") or "").upper()
    direction = str(enriched.get("signal") or "").upper()
    try:
        enriched["derivatives_context"] = fetcher(symbol, direction)
    except Exception as exc:
        enriched["derivatives_context"] = {
            "status": "unavailable",
            "symbol": symbol,
            "direction": direction,
            "verdict": "unavailable",
            "score": 0,
            "reasons": ["derivatives_context_fetch_failed"],
            "error": str(exc),
            "metrics": {
                "price_change_pct": None,
                "open_interest_delta_pct": None,
                "funding_rate": None,
                "taker_buy_ratio": None,
            },
        }
    return enriched


def _derive_levels(blueprint: dict[str, Any], indicators: dict[str, Any]) -> tuple[float, float, float, float]:
    signal = str(blueprint["side"]).upper()
    entry = float(indicators.get("close") or blueprint["entry_price"])
    sl = _as_float(blueprint.get("stop_loss"))
    if sl is None or sl <= 0 or sl == entry:
        atr = _as_float(indicators.get("atr"), 0.0) or 0.0
        fallback_distance = atr * 1.5 if atr > 0 else abs(entry * 0.015)
        sl = entry - fallback_distance if signal == "BUY" else entry + fallback_distance
    risk = abs(entry - sl)
    tp = entry + risk * RR if signal == "BUY" else entry - risk * RR
    return round(entry, 8), round(sl, 8), round(tp, 8), round(RR, 4)


def build_breakout_payload(blueprint: dict[str, Any], indicators: dict[str, Any]) -> dict[str, Any]:
    """Build a schema-valid OzzyBot webhook payload for a confirmed OpenClaw breakout."""
    signal = str(blueprint["side"]).upper()
    entry, sl, tp, rr = _derive_levels(blueprint, indicators)
    now_ms = int(utc_now().timestamp() * 1000)
    return {
        "secret": WEBHOOK_SECRET,
        "symbol": str(blueprint["symbol"]).upper(),
        "signal": signal,
        "entry": entry,
        "sl": sl,
        "tp": tp,
        "rr": rr,
        "bias": "bullish" if signal == "BUY" else "bearish",
        "structure": "bullish_bos" if signal == "BUY" else "bearish_bos",
        "regime": "smc_pro",
        "version": "2.2.2",
        "source": "signal_generator",
        "source_service": "openclaw_breakout_executor",
        "timeframe": "15",
        "timestamp": now_ms,
        "strategy": "breakout",
        "strategy_label": BREAKOUT_RETEST,
        "entry_setup_label": str(blueprint.get("entry_setup_label") or "OPENCLAW_BREAKOUT"),
        "regime_label": str(blueprint.get("regime_label") or "OPENCLAW_4H_MACRO_BREAKOUT"),
        "webhook_port": webhook_port_from_url(WEBHOOK_URL) or 5001,
        "execution_mode": "TESTNET",
    }


def post_webhook(payload: dict[str, Any]) -> dict[str, Any]:
    """POST the confirmed breakout payload to the configured webhook URL."""
    if not EXECUTE:
        return {"status": "shadow", "response": {"status": "shadow"}}
    response = requests.post(
        WEBHOOK_URL, json=payload, headers={"Content-Type": "application/json"}, timeout=15
    )
    response.raise_for_status()
    return {"status": "sent", "status_code": response.status_code, "response": response.json()}


def _recent_closed_15m_candles(symbol: str, count: int = CONTINUATION_LOOKBACK_CANDLES) -> list[dict[str, Any]]:
    """Return the last ``count`` closed 15m candles as plain dicts."""
    df = fetch_klines(symbol, interval="15m", limit=count + 10)
    if df is None or len(df) < count + 1:
        return []
    closed = df.iloc[-(count + 1) : -1]
    return [
        {
            "time": row["open_datetime"].isoformat(),
            "open": float(row["open"]),
            "high": float(row["high"]),
            "low": float(row["low"]),
            "close": float(row["close"]),
            "volume": float(row["volume"]),
        }
        for _, row in closed.iterrows()
    ]


def scan_once() -> dict[str, Any]:
    """Evaluate all armed blueprints once and either fire, shadow-log, or wait."""
    state = load_state()
    opportunity_state = load_opportunity_state()
    results: list[dict[str, Any]] = []
    fired_count = 0
    for blueprint in load_active_blueprints():
        symbol = blueprint["symbol"]
        if _cooldown_active(blueprint, state):
            results.append({"symbol": symbol, "status": "COOLDOWN", "key": _breakout_key(blueprint)})
            continue
        indicators = get_live_indicators_dict(symbol, TIMEFRAME, use_closed=USE_CLOSED_CANDLE)
        if not indicators:
            results.append({"symbol": symbol, "status": "NO_INDICATORS"})
            continue
        higher_tf_context = get_higher_timeframe_context(symbol)
        recent_candles = _recent_closed_15m_candles(symbol)
        verdict = evaluate_blueprint_trigger(
            blueprint, indicators, higher_tf_context, opportunity_state, recent_candles
        )
        verdict = attach_derivatives_context(verdict)
        plain_log("OPENCLAW_BREAKOUT_CHECK", {"blueprint": blueprint, "verdict": verdict})

        if should_post_webhook(verdict):
            if verdict.get("assigned_setup_type") == "BREAKOUT":
                record_breakout_memory(blueprint, indicators)
            payload = build_breakout_payload(blueprint, indicators)
            send_result = post_webhook(payload)
            event = {
                "symbol": symbol,
                "status": "FIRED" if send_result.get("status") == "sent" else "SHADOW",
                "payload": {k: ("<redacted>" if k == "secret" else v) for k, v in payload.items()},
                "verdict": verdict,
                "webhook": send_result,
                "key": _breakout_key(blueprint),
                "fired_at": utc_now().isoformat(),
            }
            plain_log("OPENCLAW_BREAKOUT_FIRED", event)
            state.setdefault("fired", {})[_breakout_key(blueprint)] = {
                "fired_at": event["fired_at"],
                "symbol": symbol,
                "side": blueprint["side"],
                "trigger": blueprint["entry_price"],
                "webhook_status": send_result.get("response", {}).get("status"),
            }
            results.append(event)
            fired_count += 1
        elif verdict.get("would_fire"):
            log_shadow_opportunity(blueprint, verdict, indicators)
            results.append({"symbol": symbol, "status": verdict.get("status"), **verdict})
        else:
            results.append({"symbol": symbol, "status": "WAIT", **verdict})

    state["last_scan"] = utc_now().isoformat()
    state["last_results"] = results[-50:]
    save_state(state)
    summary = {
        "checked": len(results),
        "fired": fired_count,
        "execute": EXECUTE,
        "shadow_mode": SHADOW_MODE,
        "results": results,
    }
    plain_log(
        "OPENCLAW_BREAKOUT_SCAN_DONE",
        {"checked": len(results), "fired": fired_count, "execute": EXECUTE, "shadow_mode": SHADOW_MODE},
    )
    return summary


def main() -> None:
    """Run one OpenClaw scan and print the summary."""
    summary = scan_once()
    print(json.dumps(summary, indent=2, default=str))


if __name__ == "__main__":
    main()
