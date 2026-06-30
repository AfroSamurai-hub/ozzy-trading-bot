# ============================================
# HERMES — Webhook endpoint
# ============================================
# Signal flow:
#   1.  Auth (secret check)
#   2.  Parse & validate fields
#   3.  News pause guard
#   4.  Kill zone check
#   5.  Daily drawdown check
#   6.  Open position checks (per-symbol cap + global cap)
#   7.  TAAPI bulk indicators (SuperTrend, RSI, EMA200, ATR, Volume)
#   7a. SuperTrend conflict check
#   7b. RSI exhaustion check (>70 BUY / <30 SELL)
#   7c. Volume confirmation check (below 20-period avg)
#   8.  ATR-based SL / TP calculation
#   9.  SL distance range validation
#  10.  RR verification (must be >= MIN_RR = 2.5)
#  11.  Lot sizing + hard cap
#  12.  Log APPROVED (includes full live indicator snapshot)
#  13.  Execute trade (PAPER_MODE: log only; live: background thread → MetaAPI)
#  14.  Telegram notification
#  15.  Return JSON response

import atexit
import json
import logging
import os
import sys
import threading
import time
from datetime import UTC, date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from flask import Flask, jsonify, render_template, request

# Suppress MetaAPI / engineio INFO noise — must be set before any MetaAPI import
for _logger in (
    "metaapi_cloud_sdk",
    "socketio",
    "socketio.client",
    "engineio",
    "engineio.client",
    "engineio.asyncio_client",
):
    logging.getLogger(_logger).setLevel(logging.CRITICAL)

import trade_db
from binance_connector import (
    TV_TO_BINANCE,
    get_execution_mode,
    validate_binance_credentials,
)
from binance_connector import (
    _get_client as _get_binance_client,
)
from binance_connector import (
    _map_symbol as _map_binance_symbol,
)
from binance_connector import (
    get_balance as binance_get_balance,
)
from binance_connector import (
    get_open_positions as binance_get_positions,
)

# Binance Futures
from binance_connector import (
    place_trade as binance_place_trade,
)
from binance_indicators import calculate_adx
from binance_indicators import get_live_indicators as get_binance_indicators
from bot import CRYPTO_SYMBOLS, calculate_atr_levels, calculate_lot_size, is_kill_zone
from config import (
    ALLOW_PYRAMIDING,
    ASSETS,
    BINANCE_FUTURES_MODE,
    BINANCE_SYMBOLS,
    BINANCE_TESTNET,
    BREAKOUT_SYMBOLS,
    CRYPTO_PULLBACK_ENABLED,
    DAILY_DRAWDOWN_ENABLED,
    DAILY_DRAWDOWN_LIMIT,
    DATA_DRIVEN_LIVE_GATING,
    DATA_GATING_DB,
    DEMO_BALANCE,
    DOGE_SHADOW_ONLY,
    DYNAMIC_THRESHOLDS,
    FAST_ATR_MULTIPLIER,
    GEMINI_API_KEY,
    GRADE_HEALTH_LOOKBACK_TRADES,
    GRADE_HEALTH_MIN_AVG_PNL,
    GRADE_HEALTH_MIN_TRADES,
    GRADE_HEALTH_RED_MAX_AVG_PNL,
    HALT_FILE,
    HERMES_GEMINI_ENABLED,
    HERMES_GEMINI_MODEL,
    HERMES_STATUS_KEY,
    LIVE_MAX_DAILY_FULL_LOSSES,
    LIVE_MAX_DAILY_LOSS_USD,
    LIVE_MICRO_B_GRADE_MIN_VOLUME_RATIO,
    LIVE_MIN_OPPORTUNITY_ENABLED,
    LIVE_MIN_OPPORTUNITY_HOURS,
    LIVE_RISK_ESTIMATED_FEE_USD,
    LIVE_RISK_SLIPPAGE_BUFFER_USD,
    MAX_ENTRY_DRIFT_PCT,
    MAX_LOT_SIZE,
    MAX_POSITIONS,
    MAX_POSITIONS_PER_SYMBOL,
    MAX_REARMED_TRADES_AFTER_SAFETY_INCIDENT,
    MAX_SIGNAL_AGE_SECONDS,
    MICRO_BOOTSTRAP_EQUITY_CEILING_USD,
    MICRO_BOOTSTRAP_MAX_POSITIONS,
    MICRO_BOOTSTRAP_MODE,
    MICRO_BOOTSTRAP_RISK_USD,
    MIN_BALANCE_USD,
    MIN_RR,
    NEWS_PAUSE,
    OPENCLAW_BREAKOUT_RISK_CAP_MULTIPLIER,
    PAPER_MODE,
    POST_FILL_PROTECTION_LIVE_MODE,
    POST_FILL_PROTECTION_TESTNET_MODE,
    PROTECTION_TRUTH_LIVE_ONLY,
    PROTECTION_TRUTH_REQUIRED,
    PULLBACK_SYMBOLS,
    PYRAMID_MIN_PROFIT_PCT,
    QUIET_ATR_MULTIPLIER,
    REARM_RISK_MULTIPLIER,
    RISK_PCT,
    RISK_PERCENT,
    SENTIMENT_FILTER_MODE,
    SENTIMENT_OVERRIDES,
    SETUP_GRADE_C_LIVE,
    SETUP_GRADE_RISK_MULTIPLIERS,
    SMALL_CAP_LAUNCH_MODE,
    STRICT_SCHEMA_VALIDATION,
    SYMBOL_HEAT_LOOKBACK_TRADES,
    SYMBOL_HEAT_MIN_AVG_PNL,
    SYMBOL_HEAT_MIN_TRADES,
    SYMBOL_HEAT_RED_MAX_AVG_PNL,
    WEBHOOK_SECRET,
    build_crypto_entry_config,
    get_default_strategy_for_symbol,
    get_lane_config,
    get_lane_for_signal,
)
from economic_calendar import (
    get_current_action,
    get_next_event,
    get_risk_multiplier,
    get_sl_multiplier,
    is_trading_allowed,
)
from lane_labels import (
    UNKNOWN as UNKNOWN_STRATEGY_LABEL,
)
from lane_labels import (
    canonical_strategy_label,
    derive_entry_setup_label,
    derive_regime_label,
    webhook_port_from_host,
)

# ---------------------------------------------------------------------------
# Day-equity snapshot — used for live daily drawdown calculation
# (inlined after connector.py was removed from the active tree)
# ---------------------------------------------------------------------------
_DAY_EQUITY_FILE = os.getenv("HERMES_DAY_EQUITY_FILE", "/home/rick/ozzy-bot/day_equity.json")
_TRADING_TIMEZONE = ZoneInfo("Africa/Johannesburg")
_daily_halt_alerts: set[tuple[str, str]] = set()
_daily_halt_alerts_lock = threading.Lock()


def _trading_date(now: datetime | None = None) -> date:
    """Return the calendar date used for daily trading risk controls."""
    current = now or datetime.now(tz=_TRADING_TIMEZONE)
    if current.tzinfo is None:
        current = current.replace(tzinfo=_TRADING_TIMEZONE)
    return current.astimezone(_TRADING_TIMEZONE).date()


def _should_send_daily_halt_alert(reason: str, trading_day: date | None = None) -> bool:
    """Allow one halt notification per Johannesburg trading day and reason."""
    day_text = (trading_day or _trading_date()).isoformat()
    normalized_reason = " ".join(str(reason).lower().split())
    key = (day_text, normalized_reason)
    with _daily_halt_alerts_lock:
        stale = {item for item in _daily_halt_alerts if item[0] != day_text}
        _daily_halt_alerts.difference_update(stale)
        if key in _daily_halt_alerts:
            plain_log(
                "DAILY_HALT_ALERT_SUPPRESSED",
                {"trading_date": day_text, "reason": reason},
            )
            return False
        _daily_halt_alerts.add(key)
        return True


def _low_quality_b_grade_reason(
    *,
    strategy_label: str | None,
    setup_grade: str | None,
    volume_ratio: float | None,
    min_volume_ratio: float = LIVE_MICRO_B_GRADE_MIN_VOLUME_RATIO,
) -> str | None:
    """Reject historically weak B-grade 1H continuation setups without muting other lanes."""
    if str(strategy_label or "").upper() != "1H_TREND_CONTINUATION":
        return None
    if str(setup_grade or "").upper() != "B":
        return None
    try:
        ratio = float(volume_ratio)
    except (TypeError, ValueError):
        return None
    if ratio >= min_volume_ratio:
        return None
    return (
        "B-grade 1H continuation volume below live-quality floor — "
        f"{round(ratio, 2)} < {min_volume_ratio}"
    )


def _adx_volume_override_allows(
    symbol: str,
    signal: str,
    strategy: str,
    adx_value: float,
    adx_threshold: float,
    live: dict | None,
    volume_ratio: float | None,
    override_cfg: dict | None,
) -> tuple[bool, dict]:
    """Allow selected low-ADX momentum signals only when volume and trend context are exceptional."""
    cfg = override_cfg or {}
    if not cfg.get("enabled", False):
        return False, {"reason": "override_disabled"}

    normalized_signal = str(signal or "").upper()
    normalized_strategy = str(strategy or "").lower()
    allowed_signals = {str(item).upper() for item in cfg.get("allowed_signals", [])}
    allowed_strategies = {str(item).lower() for item in cfg.get("allowed_strategies", [])}
    if allowed_signals and normalized_signal not in allowed_signals:
        return False, {"reason": "signal_not_allowed"}
    if allowed_strategies and normalized_strategy not in allowed_strategies:
        return False, {"reason": "strategy_not_allowed"}

    min_adx = float(cfg.get("min_adx", adx_threshold))
    if float(adx_value) < min_adx:
        return False, {"reason": "adx_below_override_floor", "adx": adx_value, "min_adx": min_adx}

    try:
        ratio = float(volume_ratio)
    except (TypeError, ValueError):
        ratio = 0.0
    min_volume_ratio = float(cfg.get("min_volume_ratio", 1.8))
    if ratio < min_volume_ratio:
        return False, {
            "reason": "volume_below_override_floor",
            "volume_ratio": ratio,
            "min_volume_ratio": min_volume_ratio,
        }

    live = live or {}
    expected_trend = "long" if normalized_signal == "BUY" else "short"
    if cfg.get("require_supertrend_alignment", True):
        trend = str(live.get("supertrend_direction") or "").lower()
        if trend != expected_trend:
            return False, {"reason": "supertrend_not_aligned", "trend": trend, "expected": expected_trend}

    if cfg.get("require_ema_side", True):
        close = live.get("close")
        ema200 = live.get("ema200")
        try:
            close_f = float(close)
            ema_f = float(ema200)
        except (TypeError, ValueError):
            return False, {"reason": "ema_side_unavailable", "close": close, "ema200": ema200}
        if normalized_signal == "BUY" and close_f <= ema_f:
            return False, {"reason": "buy_below_ema200", "close": close_f, "ema200": ema_f}
        if normalized_signal == "SELL" and close_f >= ema_f:
            return False, {"reason": "sell_above_ema200", "close": close_f, "ema200": ema_f}

    return True, {
        "reason": "volume_override_allowed",
        "symbol": symbol,
        "signal": normalized_signal,
        "strategy": normalized_strategy,
        "adx": adx_value,
        "adx_threshold": adx_threshold,
        "volume_ratio": ratio,
        "min_volume_ratio": min_volume_ratio,
    }


def _apply_strategy_risk_cap(
    adjusted_risk_pct: float,
    base_risk_pct: float,
    strategy_label: str | None,
    cap_multiplier: float = OPENCLAW_BREAKOUT_RISK_CAP_MULTIPLIER,
) -> tuple[float, float]:
    """Cap experimental OpenClaw breakout risk so context boosts cannot oversize it."""
    if str(strategy_label or "").upper() != "BREAKOUT_RETEST":
        return adjusted_risk_pct, 1.0
    cap = max(float(base_risk_pct) * float(cap_multiplier), 0.0)
    if cap <= 0:
        return 0.0, 0.0
    capped = min(float(adjusted_risk_pct), cap)
    multiplier = capped / float(adjusted_risk_pct) if adjusted_risk_pct else 1.0
    return capped, multiplier


def _has_enriched_market_context(live: dict | None) -> bool:
    if not live:
        return False
    required = ("range_position_pct", "wick_rejection", "market_structure", "displacement_score")
    return all(key in live for key in required)


def _save_day_equity(equity: float, trading_day: date | None = None) -> bool:
    """Persist start-of-day equity atomically for the Johannesburg trading day."""
    day_text = (trading_day or _trading_date()).isoformat()
    temporary = f"{_DAY_EQUITY_FILE}.{os.getpid()}.{threading.get_ident()}.tmp"
    try:
        with open(temporary, "w") as f:
            json.dump({"date": day_text, "start_equity": equity}, f)
        os.replace(temporary, _DAY_EQUITY_FILE)
        return True
    except Exception as e:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        plain_log("DAY_EQUITY_SAVE_ERROR", {"error": str(e), "trading_date": day_text})
        return False


def _load_day_equity() -> tuple[float | None, bool]:
    """
    Returns (start_equity: float | None, is_today: bool).
    start_equity is None if file is missing, unreadable, or corrupt.
    """
    try:
        with open(_DAY_EQUITY_FILE) as f:
            data = json.load(f)
        is_today = data.get("date") == _trading_date().isoformat()
        return float(data["start_equity"]), is_today
    except FileNotFoundError:
        return None, False
    except Exception as e:
        plain_log("DAY_EQUITY_LOAD_ERROR", {"error": str(e)})
        return None, False

# ── Dual Execution Backend Imports ──
# Exness / MetaAPI
import live_reconcile
from live_gating import evaluate_live_setup
from logger import plain_log
from market_context import evaluate_market_context
from risk_policy import (
    apply_rearm_risk_multiplier,
    bootstrap_daily_stop,
    effective_max_positions,
    is_micro_bootstrap_active,
    resolve_trade_risk,
)


# ── Smart trade router ──
# v2026-04-25 — Exness paused. Binance is the only active execution backend.
def place_trade(
    signal: str,
    tv_symbol: str,
    lot: float,
    sl_distance: float,
    rr: float,
    clear_pending_fn=None,
    risk_pct_override: float | None = None,
    execution_state_fn=None,
):
    """
    Route approved signal to Binance.
    Unsupported non-Binance symbols are blocked earlier in the webhook flow.
    """
    plain_log("TRADE_ROUTER", {"backend": "binance", "symbol": tv_symbol})
    return binance_place_trade(
        signal,
        tv_symbol,
        lot,
        sl_distance,
        rr,
        clear_pending_fn,
        risk_pct_override=risk_pct_override,
        execution_state_fn=execution_state_fn,
    )


def _signal_age_seconds(timestamp: int | float | str | None, now: float | None = None) -> float | None:
    """Return signal age in seconds; accepts TradingView second or millisecond epochs."""
    if timestamp in (None, ""):
        return None
    try:
        ts = float(timestamp)
    except (TypeError, ValueError):
        return None
    if ts > 10_000_000_000:
        ts /= 1000.0
    return (time.time() if now is None else now) - ts


def _check_signal_age(
    timestamp: int | float | str | None,
    *,
    max_age_seconds: int = MAX_SIGNAL_AGE_SECONDS,
    now: float | None = None,
) -> dict:
    """Fail closed when a TradingView alert is too old to execute safely."""
    age = _signal_age_seconds(timestamp, now=now)
    if age is None:
        return {"allowed": False, "reason": "invalid_signal_timestamp", "age_seconds": None}
    if age > max_age_seconds:
        return {
            "allowed": False,
            "reason": "signal_too_old",
            "age_seconds": age,
            "max_age_seconds": max_age_seconds,
        }
    return {
        "allowed": True,
        "reason": "fresh",
        "age_seconds": age,
        "max_age_seconds": max_age_seconds,
    }


def _check_entry_drift(
    *,
    client,
    symbol: str,
    signal: str,
    alert_price: float,
    max_drift_pct: float = MAX_ENTRY_DRIFT_PCT,
) -> dict:
    """Check adverse live ticker drift from the alert entry price."""
    binance_symbol = _map_binance_symbol(symbol)
    try:
        ticker = client.futures_symbol_ticker(symbol=binance_symbol)
        live_price = float(ticker["price"])
    except Exception as e:
        return {
            "allowed": False,
            "reason": "ticker_fetch_failed",
            "symbol": symbol,
            "binance_symbol": binance_symbol,
            "alert_price": alert_price,
            "error": str(e),
        }

    if alert_price <= 0:
        return {
            "allowed": False,
            "reason": "invalid_alert_price",
            "symbol": symbol,
            "binance_symbol": binance_symbol,
            "alert_price": alert_price,
            "live_price": live_price,
        }

    drift_pct = abs(live_price - alert_price) / alert_price * 100.0
    adverse = (signal == "BUY" and live_price > alert_price) or (signal == "SELL" and live_price < alert_price)
    if adverse and drift_pct > max_drift_pct:
        return {
            "allowed": False,
            "reason": "adverse_entry_drift_exceeded",
            "symbol": symbol,
            "binance_symbol": binance_symbol,
            "signal": signal,
            "alert_price": alert_price,
            "live_price": live_price,
            "drift_pct": drift_pct,
            "max_drift_pct": max_drift_pct,
            "adverse": adverse,
        }
    return {
        "allowed": True,
        "reason": "drift_ok",
        "symbol": symbol,
        "binance_symbol": binance_symbol,
        "signal": signal,
        "alert_price": alert_price,
        "live_price": live_price,
        "drift_pct": drift_pct,
        "max_drift_pct": max_drift_pct,
        "adverse": adverse,
    }


def _log_shadow_profile_trade(
    *,
    signal_id: int | None,
    symbol: str,
    signal: str,
    entry: float,
    sl: float,
    tp: float,
    rr: float,
    regime: str | None,
    strategy: str | None,
    timeframe: str | None,
    setup_grade: str | None,
    atr: float | None,
    volume_ratio: float | None,
    reason: str,
    gate_details: dict | None = None,
) -> int | None:
    """Persist a live-blocked setup into the shadow profile for recovery evidence."""
    try:
        shadow_risk = 50.0
        sl_dist = abs(float(entry) - float(sl))
        contract_size = float(ASSETS.get(symbol, {}).get("contract_size", 1.0))
        qty = round(shadow_risk / (sl_dist * contract_size), 8) if sl_dist > 0 and contract_size > 0 else 0.0
        return trade_db.log_trade(
            signal_id=signal_id,
            symbol=symbol,
            direction=signal,
            entry_price=entry,
            qty=qty,
            sl=sl,
            tp=tp,
            rr=rr,
            regime=regime,
            strategy=strategy,
            timeframe=timeframe,
            mode="paper",
            setup_grade=setup_grade,
            risk_dollars=shadow_risk,
            reward_dollars=shadow_risk * rr if rr is not None else None,
            atr=atr,
            volume_ratio=volume_ratio,
            context={"shadow_profile": "blocked_live_lane", "reason": reason, "gate_details": gate_details or {}},
            execution_state="shadow",
        )
    except Exception as e:
        plain_log("SHADOW_PROFILE_LOG_ERROR", {"symbol": symbol, "signal": signal, "error": str(e)})
        return None


def _status_endpoint_authorized() -> bool:
    """Allow local status/review access or a matching status API token."""
    remote = request.remote_addr or ""
    supplied = request.headers.get("X-Hermes-Status-Key", "")
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        supplied = auth.removeprefix("Bearer ").strip()
    if HERMES_STATUS_KEY and supplied and supplied == HERMES_STATUS_KEY:
        return True

    proxied = bool(
        request.headers.get("X-Forwarded-For")
        or request.headers.get("CF-Connecting-IP")
        or request.headers.get("True-Client-IP")
    )
    return remote in {"127.0.0.1", "::1", "localhost"} and not proxied


def _status_forbidden_response():
    plain_log(
        "STATUS_ENDPOINT_FORBIDDEN",
        {
            "path": request.path,
            "remote_addr": request.remote_addr,
            "has_token": bool(request.headers.get("X-Hermes-Status-Key") or request.headers.get("Authorization")),
        },
    )
    return jsonify({"status": "error", "reason": "forbidden"}), 403


import rejection_tracker
import telegram_client
from context_engine import get_size_multiplier
from crypto_entry_policy import classify_crypto_entry
from filter_policy import ema_overextended, rsi_exhausted, volume_below_threshold
from movement_policy import build_movement_snapshot, get_adjusted_sl_mult, record_signal_outcome
from ozzy_memory import record_setup_event
from request_utils import parse_json_payload, validate_signal_payload
from review_console import build_review_dashboard_context
from sentiment_filter import check_sentiment_conflict
from signal_review import append_review
from trade_journal import append_approved_trade


def _auto_update_thresholds():
    """
    Sync rejection tracker with signal reviews, get suggestions,
    and auto-apply high-confidence threshold adjustments to DYNAMIC_THRESHOLDS.
    Called at the start of every webhook signal cycle.
    """
    try:
        tracker = rejection_tracker.get_tracker()
        # Sync latest outcomes from signal_reviews.json
        tracker.sync_from_signal_reviews()
        # Get suggestions with minimum sample size
        suggestions = tracker.suggest_adjustments(min_sample_size=5, r_threshold=0.5)
        if not suggestions:
            return
        applied = []
        for sugg in suggestions:
            if sugg.confidence < 0.7:
                continue
            fn = sugg.filter_name
            action = sugg.suggested_value  # "loosen" or "tighten"
            # Map filter names to DYNAMIC_THRESHOLDS keys and apply deltas
            delta_map = {
                "rsi_exhaustion": ("rsi_exhaustion", 2.0),
                "pullback_rsi_exhaustion": ("pullback_rsi_exhaustion", 2.0),
                "momentum_rsi_exhaustion": ("momentum_rsi_exhaustion", 2.0),
                "volume_confirmation": ("volume_confirmation", 0.05),
                "ema_overextension": ("ema_overextension", 0.5),
            }
            if fn not in delta_map:
                continue
            key, delta = delta_map[fn]
            old_buy = DYNAMIC_THRESHOLDS[key]["buy_max"]
            old_sell = DYNAMIC_THRESHOLDS[key]["sell_min"]
            if action == "loosen":
                new_buy = old_buy + delta
                new_sell = old_sell - delta
            else:  # tighten
                new_buy = old_buy - delta
                new_sell = old_sell + delta
            DYNAMIC_THRESHOLDS[key]["buy_max"] = round(new_buy, 2)
            DYNAMIC_THRESHOLDS[key]["sell_min"] = round(new_sell, 2)
            tracker.log_adjustment(
                fn,
                {"buy_max": old_buy, "sell_min": old_sell},
                {"buy_max": new_buy, "sell_min": new_sell},
                f"Auto-{action}: confidence={sugg.confidence:.2f}, {sugg.reason}",
            )
            applied.append(f"{fn}: {action} (conf {sugg.confidence:.2f})")
        if applied:
            plain_log("THRESHOLD_AUTO_UPDATE", {"applied": applied, "new_thresholds": dict(DYNAMIC_THRESHOLDS)})
    except Exception as e:
        plain_log("THRESHOLD_AUTO_UPDATE_ERROR", {"error": str(e)})


PAPER_FILE = os.getenv("HERMES_PAPER_FILE", "/home/rick/ozzy-bot/paper_trades.json")
CACHE_TTL = 360  # seconds — reject if MetaAPI cache older than 6 min
CACHE_INTERVAL = 300  # seconds — refresh every 5 min

# ---------------------------------------------------------------------------
# Background MetaAPI cache  (positions + equity, refreshes every 5 minutes)
# One combined connection per cycle: get_positions_and_balance() halves the
# MetaAPI connection overhead vs two separate asyncio.run() calls.
# ---------------------------------------------------------------------------
_pos_cache: dict = {"positions": [], "equity": None, "updated_at": 0.0}
_pos_lock = threading.Lock()

# Process uptime anchor (healthy even if Flask starts slowly after imports)
_PROCESS_BOOT_MONOTONIC = time.monotonic()


def _monitor_entry_gate_status() -> dict:
    """Fail closed for new entries unless the lifecycle monitor service is active."""
    if PAPER_MODE:
        return {"allowed": True, "reason": "paper_mode", "service": None}

    require_monitor = os.getenv("HERMES_REQUIRE_MONITOR_FOR_ENTRIES", "true").strip().lower()
    if require_monitor in {"0", "false", "no", "off"}:
        return {"allowed": True, "reason": "monitor_gate_disabled", "service": None}

    service = os.getenv("HERMES_MONITOR_SERVICE", "ozzybot-monitor.service")
    try:
        import subprocess

        result = subprocess.run(
            ["systemctl", "--user", "is-active", service],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
        active_state = result.stdout.strip()
        if result.returncode == 0 and active_state == "active":
            return {"allowed": True, "reason": "monitor_active", "service": service, "active_state": active_state}
        return {
            "allowed": False,
            "reason": "monitor_not_active",
            "service": service,
            "active_state": active_state or result.stderr.strip() or "unknown",
        }
    except Exception as exc:
        return {
            "allowed": False,
            "reason": "monitor_status_unavailable",
            "service": service,
            "active_state": "unknown",
            "error": str(exc),
        }


def _get_open_positions_for_symbol(symbol: str) -> list:
    """
    Exness is paused in Binance mode, so only Binance positions are considered.
    Unsupported symbols are blocked before this helper is used.
    """
    try:
        positions = binance_get_positions()
        if positions is None:
            plain_log("POSITION_CHECK_FAILED", {"symbol": symbol})
            return []  # fail safe — treat as unchecked, let other guards handle
        return positions
    except Exception as e:
        plain_log("BINANCE_POSITION_CHECK_ERROR", {"symbol": symbol, "error": str(e)})
        return []


def _position_cache_loop():
    """
    Binance-only cache loop.
    Exness is on hold, so skip MetaAPI balance/position calls entirely.
    """
    while True:
        try:
            positions = []
            balance = {}
            try:
                positions = binance_get_positions()
                balance = binance_get_balance()
            except Exception as e:
                plain_log("BINANCE_CACHE_ERROR", {"error": str(e)})

            with _pos_lock:
                _pos_cache["positions"] = positions or []
                _pos_cache["updated_at"] = time.time()
                _pos_cache["equity"] = float((balance or {}).get("equity", 0))

            plain_log(
                "BINANCE_CACHE_WARM",
                {
                    "positions": len(positions or []),
                    "equity": float((balance or {}).get("equity", 0)),
                },
            )

            # Midnight rollover check — auto-refresh day_equity.json
            _check_day_equity_rollover()

        except Exception as e:
            plain_log("POSITION_CACHE_ERROR", {"error": str(e)})
        time.sleep(CACHE_INTERVAL)


def _get_cached_positions():
    """Return (positions, ok). ok=False when cache is stale."""
    if PAPER_MODE:
        return [], True
    with _pos_lock:
        positions = list(_pos_cache["positions"])
        updated_at = _pos_cache["updated_at"]
    ok = updated_at > 0 and (time.time() - updated_at) <= CACHE_TTL
    return positions, ok


def _entry_reconciliation_block_reason(symbol: str, reconciliation: dict) -> str | None:
    """Return a fail-closed entry reason without globally blocking stale symbols."""
    if not reconciliation.get("healthy", False):
        return "Reconciliation critical mismatch — entries frozen"
    normalized = str(symbol or "").upper()
    matching = [
        order for order in (reconciliation.get("stale_algo_orders") or [])
        if str(order.get("symbol") or "").upper() == normalized
    ]
    if matching:
        return f"{normalized} has stale exchange protection orders — symbol entries frozen"
    return None


def _get_live_equity() -> float | None:
    """
    Return cached live equity from MetaAPI, or None if cache not warm.
    Callers must treat None as a block — no fallback to static constants
    for risk decisions. Using DEMO_BALANCE when broker state is unknown
    would make lot sizing and drawdown checks unreliable.
    """
    with _pos_lock:
        return _pos_cache.get("equity")  # None until first successful fetch


def _cache_age_seconds() -> int | None:
    with _pos_lock:
        updated_at = _pos_cache.get("updated_at", 0)
    if not updated_at:
        return None
    return int(time.time() - updated_at)


def _startup_mode_check() -> bool:
    ok, reason = validate_binance_credentials()
    plain_log(
        "STARTUP_MODE_CHECK",
        {
            "backend": "binance",
            "execution_mode": get_execution_mode(),
            "binance_testnet": BINANCE_TESTNET,
            "paper_mode": PAPER_MODE,
            "ok": ok,
            "reason": reason,
        },
    )
    return ok


def _evaluate_live_drawdown() -> dict:
    """Return an explicit daily drawdown decision and its source state."""
    result = {
        "blocked": False,
        "drawdown_blocked": False,
        "baseline_unavailable": False,
        "reason": None,
        "drawdown_pct": None,
    }
    if PAPER_MODE:
        return result

    start_equity, is_today = _load_day_equity()
    current_equity = _get_live_equity()
    if current_equity is None or float(current_equity) <= 0:
        if not is_today or start_equity is None:
            result.update(
                blocked=True,
                baseline_unavailable=True,
                reason="Daily drawdown baseline unavailable — current equity unavailable",
            )
            plain_log("DRAWDOWN_BASELINE_UNAVAILABLE", result)
        return result

    current_equity = float(current_equity)
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
    """Return the legacy boolean decision, or the detailed decision when requested."""
    status = _evaluate_live_drawdown()
    return status if detailed else status["blocked"]


def _unified_daily_stop_status(equity: float | None = None) -> dict:
    """Return the unified daily stop state. Applies to testnet and live equally."""
    live_equity = _get_live_equity() if equity is None else equity
    risk_decision = resolve_trade_risk(float(live_equity or 0), RISK_PCT, RISK_PCT)
    daily_state = trade_db.get_live_daily_loss_state(risk_decision.target_loss_at_sl_usd)
    return bootstrap_daily_stop(
        daily_state,
        target_loss_at_sl_usd=risk_decision.target_loss_at_sl_usd,
        effective_risk_usd=risk_decision.effective_risk_usd,
        equity=float(live_equity or 0),
    )


def _entry_daily_stop_status() -> dict:
    """Return the daily stop model and block decision for a new candidate entry."""
    if not DAILY_DRAWDOWN_ENABLED:
        return {
            "model": "percentage_drawdown_disabled",
            "enabled": False,
            "live_trading_blocked_for_day": False,
            "live_blocked_for_day": False,
            "live_paused_for_safety": False,
            "reason": None,
        }

    daily_stop = _unified_daily_stop_status()
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
    return daily_stop


def _notify_daily_stop(daily_stop: dict, reason: str) -> bool:
    """Send the matching daily-stop alert once without changing the stop decision."""
    if not _should_send_daily_halt_alert(reason):
        return False
    if daily_stop.get("drawdown_blocked"):
        telegram_client.notify_drawdown_halt(DAILY_DRAWDOWN_LIMIT)
    elif daily_stop.get("baseline_unavailable"):
        telegram_client.notify_daily_risk_halt(reason)
    else:
        telegram_client.notify_live_bootstrap_daily_stop(reason)
    return True


def _bootstrap_daily_stop_status(equity: float | None = None) -> dict:
    """Compatibility alias for the unified daily stop status."""
    if not DAILY_DRAWDOWN_ENABLED:
        return {
            "model": "percentage_drawdown_disabled",
            "enabled": False,
            "live_trading_blocked_for_day": False,
            "live_blocked_for_day": False,
            "live_paused_for_safety": False,
            "reason": None,
        }
    return _unified_daily_stop_status(equity)


# ---------------------------------------------------------------------------
# In-process pending trade tracker
# Tracks symbols approved but not yet confirmed by MetaAPI (TRADE_PLACED /
# TRADE_ERROR). Closes the gap where execution fails but the MetaAPI cache
# still shows 0 positions, allowing duplicate signals for the same symbol.
# ---------------------------------------------------------------------------
_pending: dict = {}  # {symbol: approved_ts}
_pending_lock = threading.Lock()


def _mark_pending(symbol: str):
    with _pending_lock:
        _pending[symbol] = time.time()


def _clear_pending(symbol: str):
    with _pending_lock:
        _pending.pop(symbol, None)


def _is_pending(symbol: str, max_age: int = 180) -> bool:
    """True if symbol was approved within the last max_age seconds."""
    with _pending_lock:
        ts = _pending.get(symbol)
    return ts is not None and (time.time() - ts) < max_age


def _position_aliases(symbol: str) -> set[str]:
    aliases = {symbol}
    # Include Binance Futures symbol so position checks match
    binance_sym = TV_TO_BINANCE.get(symbol)
    if binance_sym:
        aliases.add(binance_sym)
    return aliases


def _has_pending_alias(symbol: str) -> bool:
    return any(_is_pending(alias) for alias in _position_aliases(symbol))


def _minutes_to_tf_close(tf: str) -> int:
    tf = tf.strip().lower()
    if tf.endswith("m"):
        interval_seconds = int(tf[:-1]) * 60
    elif tf.endswith("h"):
        interval_seconds = int(tf[:-1]) * 3600
    else:
        return 0

    now = datetime.now(UTC)
    seconds_since_midnight = now.hour * 3600 + now.minute * 60 + now.second
    elapsed = seconds_since_midnight % interval_seconds
    remaining = interval_seconds - elapsed if elapsed else interval_seconds
    return max(1, (remaining + 59) // 60)


def _review_id(decision: str, symbol: str, signal: str, entry: float) -> str:
    ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%f")
    return f"{ts}:{decision}:{symbol}:{signal}:{round(float(entry), 5)}"


def _project_levels(signal: str, entry: float, asset: dict, live: dict | None = None):
    atr = None
    if live is not None:
        atr = live.get("atr")
    if atr:
        sl, tp, sl_distance = calculate_atr_levels(signal, entry, float(atr), asset["atr_sl_mult"], rr=MIN_RR)
        return sl, tp, sl_distance, "taapi_atr"

    offset = float(asset["default_offset"])
    if signal == "BUY":
        sl = round(entry - offset, 5)
        tp = round(entry + offset * MIN_RR, 5)
    else:
        sl = round(entry + offset, 5)
        tp = round(entry - offset * MIN_RR, 5)
    return sl, tp, offset, "default_offset"


def _base_record_signal_review(
    decision: str,
    symbol: str,
    signal: str,
    entry: float,
    asset: dict,
    filter_name: str | None = None,
    filter_value=None,
    filter_reason: str | None = None,
    live: dict | None = None,
    sl: float | None = None,
    tp: float | None = None,
    rr: float | None = None,
    extra: dict | None = None,
    bias: str | None = None,
    structure: str | None = None,
    regime: str | None = None,
    version: str | None = None,
    source: str | None = None,
    timeframe: str | None = None,
    timestamp: int | None = None,
    signal_id: int | None = None,
):
    if entry is None:
        return
    projected_sl = sl
    projected_tp = tp
    sl_distance = None
    level_source = None
    if projected_sl is None or projected_tp is None:
        projected_sl, projected_tp, sl_distance, level_source = _project_levels(signal, float(entry), asset, live=live)
    else:
        sl_distance = abs(float(entry) - float(projected_sl))
        level_source = "explicit"

    if rr is None and sl_distance and sl_distance > 0:
        rr = round(abs(float(projected_tp) - float(entry)) / sl_distance, 4)

    review = {
        "id": _review_id(decision, symbol, signal, float(entry)),
        "ts": datetime.now(UTC).isoformat(),
        "decision": decision,
        "symbol": symbol,
        "signal": signal,
        "entry": round(float(entry), 5),
        "sl": round(float(projected_sl), 5) if projected_sl is not None else None,
        "tp": round(float(projected_tp), 5) if projected_tp is not None else None,
        "rr": rr,
        "filter_name": filter_name,
        "filter_value": filter_value,
        "filter_reason": filter_reason,
        "level_source": level_source,
        "outcome": None,
        "outcome_status": None,
        "r_multiple": None,
        # Pine Script contract v1.1.0 fields — never nil once migration complete
        "bias": bias,
        "structure": structure,
        "regime": regime or "unknown",
        "pine_version": version,
        "pine_source": source,
        "timeframe": timeframe,
        "pine_timestamp": timestamp,
    }
    if extra:
        review.update(extra)
    append_review(review)
    try:
        record_setup_event(
            event_id=review["id"],
            symbol=symbol,
            direction=signal,
            decision=decision,
            timeframe=timeframe,
            grade=review.get("setup_grade"),
            reason=filter_reason,
            reason_json={"filter_name": filter_name, "filter_value": filter_value},
            indicators=live,
            proposed_entry=review.get("entry"),
            proposed_sl=review.get("sl"),
            proposed_tp=review.get("tp"),
            rr=review.get("rr"),
            risk_usd=review.get("risk_dollars"),
            source_trade_id=signal_id,
            live_gating_verdict=review.get("live_gate_verdict"),
            risk_multiplier=review.get("live_gate_risk_multiplier"),
        )
    except Exception as memory_error:
        plain_log("OZZY_MEMORY_ERROR", {"stage": "webhook_review", "error": str(memory_error)})
    # Mirror to SQLite for analytics
    try:
        trade_db.log_gate_decision(
            signal_id=signal_id,
            gate_name=filter_name or "final_approval",
            decision="rejected" if decision == "rejected" else "passed",
            reason=filter_reason,
            filter_json=filter_value,
        )
    except Exception:
        pass


app = Flask(__name__)


def _count_trades_logged_today_sast() -> int:
    """Count trade rows opened today using the runtime DB, not noisy JSON logs."""
    try:
        return trade_db.count_trades_opened_today_sast()
    except Exception as e:
        plain_log("DAILY_REPORT_TRADE_COUNT_ERROR", {"error": str(e)})
        return 0


def _emit_daily_report():
    """Gather metrics and send Telegram; errors are logged."""
    tz = ZoneInfo("Africa/Johannesburg")
    trades_today = _count_trades_logged_today_sast()
    try:
        if PAPER_MODE:
            telegram_client.notify_daily_pnl_report(0, None, None, trades_today, paper_mode=True)
            plain_log(
                "DAILY_REPORT",
                {"timezone": str(tz), "paper": True, "trades_today": trades_today},
            )
            return

        positions_list: list | None = None
        balance: dict | None = None
        try:
            positions_list = binance_get_positions()
            balance = binance_get_balance()
        except Exception as e:
            plain_log("DAILY_REPORT_FETCH_ERROR", {"error": str(e)})

        if positions_list is None or balance is None:
            with _pos_lock:
                if positions_list is None:
                    positions_list = list(_pos_cache.get("positions") or [])
                cached_eq = _pos_cache.get("equity")
            if balance is None and cached_eq is not None:
                balance = {"equity": cached_eq}

        open_n = len(positions_list or [])
        equity_f: float | None = None
        if balance:
            equity_f = float(balance.get("equity", 0))

        drawdown_pct: float | None = None
        start_equity, is_today = _load_day_equity()
        if equity_f is not None and start_equity is not None and start_equity > 0 and is_today:
            drawdown_pct = ((equity_f - float(start_equity)) / float(start_equity)) * 100.0

        telegram_client.notify_daily_pnl_report(open_n, equity_f, drawdown_pct, trades_today, paper_mode=False)
        plain_log(
            "DAILY_REPORT",
            {
                "timezone": str(tz),
                "paper": False,
                "open_positions": open_n,
                "equity": equity_f,
                "drawdown_pct": drawdown_pct,
                "trades_today": trades_today,
            },
        )
    except Exception as e:
        plain_log("DAILY_REPORT_ERROR", {"error": str(e)})


def _start_daily_report_scheduler():
    """Fire daily Telegram summary every day at 08:00 SAST."""
    tz = ZoneInfo("Africa/Johannesburg")
    scheduler = BackgroundScheduler(timezone=tz)
    scheduler.add_job(
        _emit_daily_report,
        CronTrigger(hour=8, minute=0, timezone=tz),
        id="daily_pnl_report",
        replace_existing=True,
        coalesce=True,
        max_instances=1,
    )
    scheduler.start()
    atexit.register(scheduler.shutdown, wait=False)


def _warm_caches() -> bool:
    """
    Synchronously warm Binance positions + equity cache before Flask starts.
    Exness is paused, so only Binance is used for startup validation and equity baseline.

    In PAPER_MODE always returns True.
    """
    if PAPER_MODE:
        return True

    plain_log("CACHE_WARM", {"status": "starting", "backend_mode": "binance_only"})

    try:
        positions = binance_get_positions() or []
        balance = binance_get_balance() or {}
        total_equity = float(balance.get("equity", 0))
    except Exception as e:
        plain_log("CACHE_WARM", {"backend": "binance", "status": "failed", "error": str(e)})
        return False

    with _pos_lock:
        _pos_cache["positions"] = positions
        _pos_cache["updated_at"] = time.time()
        _pos_cache["equity"] = total_equity

    plain_log(
        "CACHE_WARM",
        {
            "backend": "binance",
            "status": "ready",
            "positions": len(positions),
            "equity": total_equity,
        },
    )

    # Write day-equity baseline if we don't have one for today yet.
    _, is_today = _load_day_equity()
    if not is_today:
        _save_day_equity(total_equity)
        plain_log("DAY_EQUITY_SNAPSHOT", {"start_equity": total_equity, "trigger": "startup"})

    return True


_cache_thread: threading.Thread | None = None


def _start_position_cache_thread() -> None:
    """Start runtime cache refresh explicitly instead of on module import."""
    global _cache_thread
    if PAPER_MODE or (_cache_thread is not None and _cache_thread.is_alive()):
        return
    _cache_thread = threading.Thread(target=_position_cache_loop, daemon=True)
    _cache_thread.start()


def _check_day_equity_rollover():
    """Auto-rewrite day_equity.json at midnight rollover."""
    start_equity, is_today = _load_day_equity()
    if not is_today:
        current_equity = _get_live_equity()
        if current_equity:
            if _save_day_equity(current_equity):
                plain_log(
                    "DAY_EQUITY_ROLLOVER",
                    {
                        "previous_start_equity": start_equity,
                        "new_equity": current_equity,
                        "trading_date": _trading_date().isoformat(),
                        "trigger": "midnight_auto",
                    },
                )


@app.route("/webhook", methods=["POST"])
def webhook():
    # Auto-update filter thresholds from rejection tracker before each signal
    _auto_update_thresholds()

    live = None  # populated later by indicator fetch; initialized to prevent UnboundLocalError

    raw_body = request.get_data(as_text=True)
    try:
        data = parse_json_payload(raw_body)

        # ------------------------------------------------------------------
        # 1. Auth
        # ------------------------------------------------------------------
        if data.get("secret") != WEBHOOK_SECRET:
            return jsonify({"status": "error", "reason": "unauthorized"}), 401

        # ------------------------------------------------------------------
        # 1a. Emergency kill switch — reject ALL signals if HALT file exists
        # ------------------------------------------------------------------
        if os.path.exists(HALT_FILE):
            plain_log("HALT_REJECT", {"symbol": data.get("symbol"), "reason": "HALT file active — trading paused"})
            telegram_client.notify_system_event(
                "HALT_REJECT", "Signal rejected — HALT file is active. Use /resume to re-enable."
            )
            return jsonify({"status": "rejected", "reason": "trading halted — /resume to re-enable"})

        # ------------------------------------------------------------------
        # 1b. Schema validation (Pine Script contract v1.1.0)
        # ------------------------------------------------------------------
        is_valid, schema_errors = validate_signal_payload(data)
        if not is_valid:
            plain_log(
                "SCHEMA_VIOLATION",
                {
                    "errors": schema_errors,
                    "payload_keys": list(data.keys()),
                    "strict_mode": STRICT_SCHEMA_VALIDATION,
                },
            )
            if STRICT_SCHEMA_VALIDATION:
                return jsonify(
                    {
                        "status": "error",
                        "reason": "payload schema violation",
                        "errors": schema_errors,
                    }
                ), 400
            # Non-strict: warn and continue (migration mode for old alerts)

        # ------------------------------------------------------------------
        # 2. Parse
        # ------------------------------------------------------------------
        signal = data.get("signal", "").upper()
        symbol = data.get("symbol")
        if not symbol:
            # Migration fallback — old Pine Script v1.0.0 alerts lack symbol
            # TODO: Remove after all TV alerts updated to v1.1.0
            plain_log("MIGRATION_FALLBACK", {"reason": "missing_symbol_in_payload", "defaulting_to": "XAUUSD"})
            symbol = "XAUUSD"
        if symbol not in ASSETS:
            reason = f"Symbol {symbol} is missing from ASSETS config"
            plain_log("REJECTED", {"reason": reason, "symbol": symbol})
            telegram_client.notify_rejected(reason, symbol, signal)
            return jsonify({"status": "error", "reason": reason}), 400
        asset = ASSETS[symbol]

        from dynamic_config import get_param

        current_binance_symbols = get_param("active_symbols", BINANCE_SYMBOLS)
        if BINANCE_FUTURES_MODE and symbol not in current_binance_symbols:
            reason = f"Symbol {symbol} disabled — Exness on hold, Binance-only routing active"
            plain_log("REJECTED", {"reason": reason, "symbol": symbol, "signal": signal})
            telegram_client.notify_rejected(reason, symbol, signal)
            return jsonify({"status": "rejected", "reason": reason})

        try:
            entry = float(data.get("entry", 0))
        except (TypeError, ValueError):
            return jsonify({"status": "error", "reason": "invalid entry price"}), 400

        if not signal or not entry:
            return jsonify({"status": "error", "reason": "missing fields"}), 400
        if signal not in ("BUY", "SELL"):
            return jsonify({"status": "error", "reason": "invalid signal"}), 400

        # ------------------------------------------------------------------
        # 2a. Lifecycle monitor must be active before new risk or exchange I/O.
        # ------------------------------------------------------------------
        monitor_gate = _monitor_entry_gate_status()
        if not monitor_gate["allowed"]:
            reason = "monitor not running"
            plain_log(
                "MONITOR_DOWN_REJECT",
                {"reason": reason, "symbol": symbol, "signal": signal, "monitor_gate": monitor_gate},
            )
            trade_db.log_system_event("webhook_paused", {"reason": "monitor_not_running"})
            telegram_client.notify_rejected(f"Monitor not active — entries frozen: {monitor_gate.get('active_state')}", symbol, signal)
            return jsonify({"status": "rejected", "reason": reason}), 503

        # v2026-04-19 — Capture full Pine Script contract fields for edge analysis and regime tracking
        bias = data.get("bias")
        structure = data.get("structure")
        regime = data.get("regime", "unknown")
        version = data.get("version", "unknown")
        source = data.get("source", "unknown")
        timeframe = data.get("timeframe")
        timestamp = data.get("timestamp")
        strategy = data.get("strategy", "unknown")  # v2.1.0: pullback, momentum, breakout, structure, supertrend
        strategy_label = canonical_strategy_label(data.get("strategy_label"), strategy, timeframe)
        entry_setup_label = str(data.get("entry_setup_label") or derive_entry_setup_label(strategy))
        regime_label = str(data.get("regime_label") or derive_regime_label(regime, structure=structure, bias=bias))
        source_service = str(data.get("source_service") or source)
        webhook_port = data.get("webhook_port") or webhook_port_from_host(request.host)
        execution_mode = str(data.get("execution_mode") or get_execution_mode()).upper()

        age_check = _check_signal_age(timestamp)
        if not age_check["allowed"]:
            reason = (
                f"Signal age gate failed: {age_check['reason']} "
                f"(age={age_check.get('age_seconds')}, max={age_check.get('max_age_seconds')})"
            )
            plain_log(
                "ENTRY_SIGNAL_TOO_OLD",
                {
                    "symbol": symbol,
                    "signal": signal,
                    "timestamp": timestamp,
                    **age_check,
                },
            )
            telegram_client.notify_rejected(reason, symbol, signal)
            return jsonify({"status": "rejected", "reason": reason}), 400

        if BINANCE_FUTURES_MODE and symbol in current_binance_symbols and not PAPER_MODE:
            drift_check = _check_entry_drift(
                client=_get_binance_client(),
                symbol=symbol,
                signal=signal,
                alert_price=entry,
            )
            if not drift_check["allowed"]:
                event = (
                    "ENTRY_DRIFT_CHECK_FAILED_CLOSED"
                    if drift_check["reason"] == "ticker_fetch_failed"
                    else "ENTRY_DRIFT_EXCEEDED"
                )
                reason = (
                    f"Slippage: alert entry price drifted by {drift_check.get('drift_pct', 0.0):.2f}%"
                    if drift_check["reason"] == "adverse_entry_drift_exceeded"
                    else f"Entry drift gate failed: {drift_check['reason']}"
                )
                plain_log(event, drift_check)
                telegram_client.notify_rejected(reason, symbol, signal)
                return jsonify({"status": "rejected", "reason": reason}), 400
            plain_log("ENTRY_DRIFT_OK", drift_check)

        plain_log(
            "SIGNAL_IN",
            {
                "signal": signal,
                "symbol": symbol,
                "entry": entry,
                "bias": bias,
                "structure": structure,
                "regime": regime,
                "version": version,
                "source": source,
                "timeframe": timeframe,
                "timestamp": timestamp,
            },
        )
        raw_volume_ratio = None
        if live is not None:
            vol = live.get("volume")
            vol_avg = live.get("volume_avg20")
            if vol is not None and vol_avg and float(vol_avg) > 0:
                raw_volume_ratio = float(vol) / float(vol_avg)

        signal_id = trade_db.log_signal(
            symbol=symbol,
            direction=signal,
            entry_price=entry,
            bias=bias,
            structure=structure,
            regime=regime,
            version=version,
            source=source,
            timeframe=timeframe,
            pine_ts=timestamp,
            volume_ratio=raw_volume_ratio,
            strategy_label=None if strategy_label == UNKNOWN_STRATEGY_LABEL else strategy_label,
            entry_setup_label=entry_setup_label,
            regime_label=regime_label,
            source_service=source_service,
            webhook_port=webhook_port,
            execution_mode=execution_mode,
            mode="paper" if PAPER_MODE else "live",
        )

        # ------------------------------------------------------------------
        # ChoCh Reversal Gate — alert if incoming signal contradicts open position
        # ------------------------------------------------------------------
        try:
            open_trades = trade_db.get_open_trades(symbol)
            for ot in open_trades:
                if ot["direction"] != signal:
                    # Structure aligns with new direction?
                    structure_conflicts = (signal == "BUY" and structure in ("bullish",)) or (
                        signal == "SELL" and structure in ("bearish",)
                    )
                    if structure_conflicts:
                        trade_db.log_gate_decision(
                            signal_id=signal_id,
                            trade_id=ot["id"],
                            gate_name="choch_reversal",
                            decision="alert",
                            reason=f"ChoCh against open {ot['direction']}: structure={structure}, signal={signal}",
                        )
                        telegram_client.send_message(
                            f"⚠️ <b>ChoCh REVERSAL ALERT</b>\n"
                            f"Open {ot['direction']} on {symbol}\n"
                            f"Incoming signal: {signal}\n"
                            f"Structure: {structure}\n"
                            f"Consider closing the open position."
                        )
                        plain_log(
                            "CHOCH_ALERT",
                            {
                                "symbol": symbol,
                                "open_direction": ot["direction"],
                                "signal_direction": signal,
                                "structure": structure,
                                "trade_id": ot["id"],
                                "signal_id": signal_id,
                            },
                        )
        except Exception:
            pass

        # ------------------------------------------------------------------
        # Gate: ETH Long Blocker
        # ETH longs are unprofitable with current strategy (PF 0.75 vs 1.15 for shorts)
        # This gate blocks BUY signals for ETH while allowing SELL signals
        # ------------------------------------------------------------------
        if symbol in ("ETHUSD", "ETHUSDT") and signal == "BUY":
            reason = "ETH_LONG_BLOCKED"
            plain_log(
                "REJECTED",
                {
                    "reason": reason,
                    "symbol": symbol,
                    "signal": signal,
                    "entry": entry,
                    "message": "ETH long signals blocked — short-only mode",
                },
            )
            try:
                trade_db.log_gate_decision(
                    signal_id=signal_id,
                    gate_name="eth_long_blocker",
                    decision="rejected",
                    reason=reason,
                )
            except Exception:
                pass
            telegram_client.notify_rejected(reason, symbol, signal)
            telegram_client.send_message("🚫 ETH LONG BLOCKED — short-only mode active")
            return jsonify(
                {"status": "rejected", "reason": reason, "message": "ETH long signals blocked — short-only mode"}
            )

        # Local wrapper so every review record carries bias/structure automatically
        def _record_signal_review(decision, symbol, signal, entry, asset, **kwargs):
            return _base_record_signal_review(
                decision,
                symbol,
                signal,
                entry,
                asset,
                bias=bias,
                structure=structure,
                regime=regime,
                version=version,
                source=source,
                timeframe=timeframe,
                timestamp=timestamp,
                signal_id=signal_id,
                **kwargs,
            )

        # ------------------------------------------------------------------
        # 2a. Lane identification and symbol validation
        # ------------------------------------------------------------------
        lane_name = get_lane_for_signal(
            source_service,
            strategy_label,
            entry_setup_label,
        )
        if not lane_name:
            _record_signal_review(
                "rejected",
                symbol,
                signal,
                entry,
                asset,
                filter_name="lane",
                filter_value=None,
                filter_reason="unknown_or_disabled_lane",
            )
            plain_log(
                "REJECTED",
                {"reason": "unknown or disabled lane", "symbol": symbol, "signal": signal},
            )
            return jsonify({"status": "rejected", "reason": "unknown or disabled lane"}), 400
        lane = get_lane_config(lane_name)
        if not lane:
            return jsonify({"status": "rejected", "reason": "lane config missing"}), 500
        if symbol not in lane.symbols:
            reason = f"{symbol} not in lane {lane_name}"
            plain_log("REJECTED", {"reason": reason, "symbol": symbol, "signal": signal})
            return jsonify({"status": "rejected", "reason": reason}), 400

        # ------------------------------------------------------------------
        # 3. Economic Calendar Gate
        # ------------------------------------------------------------------
        if not is_trading_allowed():
            action = get_current_action()
            event = get_next_event()
            reason = f"Economic calendar: {action} — {event.get('event', 'unknown') if event else 'unknown'}"
            _record_signal_review(
                "rejected",
                symbol,
                signal,
                entry,
                asset,
                filter_name="economic_calendar",
                filter_value={"action": action, "event": event},
                filter_reason=reason,
                live=live,
            )
            plain_log("REJECTED", {"reason": reason, "symbol": symbol, "signal": signal})
            telegram_client.notify_rejected(reason, symbol, signal)
            return jsonify({"status": "rejected", "reason": f"economic_calendar_{action}"})

        # ------------------------------------------------------------------
        # 3. News pause
        # ------------------------------------------------------------------
        if NEWS_PAUSE:
            reason = "News pause active"
            _record_signal_review(
                "rejected",
                symbol,
                signal,
                entry,
                asset,
                filter_name="news_pause",
                filter_value={"news_pause": True},
                filter_reason=reason,
            )
            plain_log("REJECTED", {"reason": reason, "symbol": symbol, "signal": signal})
            telegram_client.notify_rejected(reason, symbol, signal)
            return jsonify({"status": "rejected", "reason": reason})

        # ------------------------------------------------------------------
        # 4. Kill zone
        # ------------------------------------------------------------------
        if not is_kill_zone(symbol):
            reason = "Outside trading hours — London 09:00-12:00, New York 14:00-17:00 SAST"
            _record_signal_review(
                "rejected",
                symbol,
                signal,
                entry,
                asset,
                filter_name="kill_zone",
                filter_value={"windows": asset.get("taapi_tf"), "symbol": symbol},
                filter_reason=reason,
            )
            plain_log("REJECTED", {"reason": reason, "symbol": symbol, "signal": signal})
            telegram_client.notify_rejected(reason, symbol, signal)
            return jsonify({"status": "rejected", "reason": "outside kill zone"})

        # ------------------------------------------------------------------
        # 5. Daily drawdown
        # ------------------------------------------------------------------
        daily_stop = _entry_daily_stop_status()
        if daily_stop["live_trading_blocked_for_day"]:
            reason = daily_stop.get("reason") or "Daily risk stop reached"
            plain_log("REJECTED", {"reason": reason, "symbol": symbol, "signal": signal})
            _notify_daily_stop(daily_stop, reason)
            return jsonify({"status": "rejected", "reason": "daily risk stop"})

        # ------------------------------------------------------------------
        # 6. Open position checks
        #    a) global cap  — reject if MAX_POSITIONS already open
        #    b) symbol cap  — reject if this symbol already has a position
        #    Skipped in PAPER_MODE (no real MetaAPI positions to query).
        # ------------------------------------------------------------------
        positions, cache_ok = _get_cached_positions()

        if not cache_ok:
            reason = "Position cache not ready — trade rejected for safety"
            plain_log("REJECTED", {"reason": reason, "symbol": symbol, "signal": signal})
            telegram_client.notify_rejected(reason, symbol, signal)
            return jsonify({"status": "rejected", "reason": reason})

        if not PAPER_MODE:
            reconciliation = live_reconcile.reconcile_live_state(dry_run=True)
            reason = _entry_reconciliation_block_reason(symbol, reconciliation)
            if reason:
                critical = reconciliation.get("critical_mismatches") or []
                matching_stale = [
                    order for order in (reconciliation.get("stale_algo_orders") or [])
                    if str(order.get("symbol") or "").upper() == str(symbol or "").upper()
                ]
                incident_detail = "; ".join(critical) or repr(matching_stale)
                trade_db.record_live_bootstrap_event(
                    "safety_incident",
                    reason=f"entry reconciliation block: {incident_detail}",
                    payload={"reconciliation": reconciliation},
                    event_key=f"reconcile:{incident_detail}",
                )
                plain_log(
                    "REJECTED",
                    {
                        "reason": reason,
                        "symbol": symbol,
                        "signal": signal,
                        "reconciliation": reconciliation,
                    },
                )
                telegram_client.notify_rejected(f"{reason}: {incident_detail}", symbol, signal)
                return jsonify({"status": "rejected", "reason": reason, "reconciliation": reconciliation})

        effective_position_cap = effective_max_positions(MAX_POSITIONS, _get_live_equity())
        if len(positions) >= effective_position_cap:
            reason = f"Max concurrent positions ({effective_position_cap}) reached — {len(positions)} open"
            _record_signal_review(
                "rejected",
                symbol,
                signal,
                entry,
                asset,
                filter_name="max_positions",
                filter_value={
                    "max_positions": effective_position_cap,
                    "configured_max_positions": MAX_POSITIONS,
                    "open_count": len(positions),
                },
                filter_reason=reason,
            )
            plain_log("REJECTED", {"reason": reason, "symbol": symbol, "signal": signal, "open_count": len(positions)})
            telegram_client.notify_rejected(reason, symbol, signal)
            return jsonify({"status": "rejected", "reason": reason})

        alias_symbols = _position_aliases(symbol)
        sym_open = [p for p in positions if p.get("symbol") in alias_symbols]

        # ── Smart Pyramiding Logic ──
        # Pro traders scale into winners. Bot allows multiple positions on same
        # symbol ONLY if existing positions are profitable and guardrails pass.
        if sym_open:
            if not ALLOW_PYRAMIDING:
                reason = f"Position already open for {symbol}"
                plain_log(
                    "REJECTED", {"reason": reason, "symbol": symbol, "signal": signal, "open_count": len(sym_open)}
                )
                telegram_client.notify_rejected(reason, symbol, signal)
                return jsonify({"status": "rejected", "reason": reason})

            # 1. Max positions per symbol
            if len(sym_open) >= MAX_POSITIONS_PER_SYMBOL:
                reason = f"Max {MAX_POSITIONS_PER_SYMBOL} positions already open for {symbol}"
                plain_log(
                    "REJECTED", {"reason": reason, "symbol": symbol, "signal": signal, "open_count": len(sym_open)}
                )
                telegram_client.notify_rejected(reason, symbol, signal)
                return jsonify({"status": "rejected", "reason": reason})

            # 2. Same direction only
            for p in sym_open:
                pos_side = str(p.get("type", "")).upper()
                if signal not in pos_side and pos_side not in signal:
                    reason = f"Opposite position open for {symbol} ({pos_side}) — pyramiding blocked"
                    plain_log("REJECTED", {"reason": reason, "symbol": symbol, "signal": signal})
                    telegram_client.notify_rejected(reason, symbol, signal)
                    return jsonify({"status": "rejected", "reason": reason})

            # 3. Only add to winners (unrealized profit > threshold)
            for p in sym_open:
                pnl = Decimal(str(p.get("profit", 0)))
                existing_entry_price = Decimal(str(p.get("openPrice", 0)))
                if existing_entry_price <= Decimal("0"):
                    continue
                volume = Decimal(str(p.get("volume", 1)))
                pnl_pct = (pnl / (existing_entry_price * volume)) * Decimal("100")
                if pnl_pct < PYRAMID_MIN_PROFIT_PCT:
                    reason = (
                        f"Pyramiding blocked for {symbol}: existing position "
                        f"PnL ({pnl_pct:.2f}%) below minimum ({PYRAMID_MIN_PROFIT_PCT}%)"
                    )
                    plain_log(
                        "REJECTED", {"reason": reason, "symbol": symbol, "signal": signal, "pnl_pct": float(pnl_pct)}
                    )
                    telegram_client.notify_rejected(reason, symbol, signal)
                    return jsonify({"status": "rejected", "reason": reason})

            # 4. Better entry price: buy lower, sell higher
            for p in sym_open:
                existing_entry = float(p.get("openPrice", 0))
                if signal == "BUY" and entry >= existing_entry:
                    reason = f"Pyramiding blocked: new BUY entry ({entry}) not lower than existing ({existing_entry})"
                    plain_log("REJECTED", {"reason": reason, "symbol": symbol, "signal": signal})
                    telegram_client.notify_rejected(reason, symbol, signal)
                    return jsonify({"status": "rejected", "reason": reason})
                if signal == "SELL" and entry <= existing_entry:
                    reason = f"Pyramiding blocked: new SELL entry ({entry}) not higher than existing ({existing_entry})"
                    plain_log("REJECTED", {"reason": reason, "symbol": symbol, "signal": signal})
                    telegram_client.notify_rejected(reason, symbol, signal)
                    return jsonify({"status": "rejected", "reason": reason})

            # All pyramiding checks passed — log it
            plain_log(
                "PYRAMID_APPROVED",
                {
                    "symbol": symbol,
                    "signal": signal,
                    "entry": entry,
                    "existing_positions": len(sym_open),
                },
            )

        # In-process pending check — catches the window between APPROVED and
        # MetaAPI confirming the position (TRADE_PLACED / TRADE_ERROR).
        if not PAPER_MODE and _has_pending_alias(symbol):
            reason = f"Trade already pending for {symbol} — awaiting MetaAPI confirmation"
            plain_log(
                "REJECTED",
                {"reason": reason, "symbol": symbol, "signal": signal, "alias_symbols": sorted(alias_symbols)},
            )
            telegram_client.notify_rejected(reason, symbol, signal)
            return jsonify({"status": "rejected", "reason": reason})

        # ------------------------------------------------------------------
        # [Relocated] Strategy-correlation and local ADX gates
        # Moved below crypto_entry classification block so setup_grade is resolved
        # ------------------------------------------------------------------

        # ------------------------------------------------------------------
        # 7. Live indicator verification (TAAPI bulk)
        #
        #    Crypto  → bulk call: SuperTrend + RSI + EMA200 + ATR + Volume
        #              Three hard filters applied before approving:
        #                a) SuperTrend conflict  — direction must agree with signal
        #                b) RSI exhaustion       — BUY>70 or SELL<30 rejected
        #                c) Low volume           — below 20-period avg rejected
        #
        #    Forex / gold → TAAPI forex exchange not on plan; bulk call will
        #              timeout. Fall back to fixed offset ATR, live checks skipped.
        # ------------------------------------------------------------------
        atr = None
        atr_source = "binance_klines" if BINANCE_FUTURES_MODE else "taapi_bulk"
        tg_note = ""
        live = None  # full indicator dict — logged with every APPROVED

        try:
            # Gate 7: Live indicator verification (Binance native or TAAPI fallback)
            if BINANCE_FUTURES_MODE:
                live = get_binance_indicators(symbol)
                live["atr_source"] = "binance_klines"
            else:
                raise RuntimeError("TAAPI bulk indicators path disabled in Binance-only mode")
            atr = live["atr"]
            event_name = "BINANCE_INDICATORS" if BINANCE_FUTURES_MODE else "TAAPI_BULK"
            plain_log(event_name, {"symbol": symbol, "tf": asset["taapi_tf"], **live})

            bt1_dir = live.get("supertrend_direction")
            bt0_dir = live.get("supertrend_direction_forming")
            expected_dir = "long" if signal == "BUY" else "short"
            bt1_match = bt1_dir == expected_dir
            bt0_match = bt0_dir == expected_dir
            has_forming_supertrend = bt0_dir in {"long", "short"}

            # Emit SETUP_FORMING when confirmed and forming directions differ but at
            # least one matches the expected direction.
            if has_forming_supertrend:
                if bt0_match or bt1_match:
                    if bt0_match != bt1_match:
                        mins_left = _minutes_to_tf_close(asset["taapi_tf"])
                        threshold = live.get("supertrend_value_forming") or live.get("supertrend_value", 0)
                        plain_log(
                            "SETUP_FORMING",
                            {
                                "symbol": symbol,
                                "signal": signal,
                                "tf": asset["taapi_tf"],
                                "mins_to_close": mins_left,
                                "backtrack_1": bt1_dir,
                                "backtrack_0": bt0_dir,
                                "threshold": threshold,
                            },
                        )
                        telegram_client.notify_setup_forming(
                            symbol, signal, mins_left, asset["taapi_tf"].upper(), threshold
                        )
                else:
                    mins_left = _minutes_to_tf_close(asset["taapi_tf"])
                    plain_log(
                        "SETUP_CONFLICT",
                        {
                            "symbol": symbol,
                            "signal": signal,
                            "tf": asset["taapi_tf"],
                            "mins_to_close": mins_left,
                            "backtrack_1": bt1_dir,
                            "backtrack_0": bt0_dir,
                            "expected": expected_dir,
                        },
                    )
            elif not bt1_match:
                mins_left = _minutes_to_tf_close(asset["taapi_tf"])
                plain_log(
                    "SETUP_CONFLICT",
                    {
                        "symbol": symbol,
                        "signal": signal,
                        "tf": asset["taapi_tf"],
                        "mins_to_close": mins_left,
                        "backtrack_1": bt1_dir,
                        "backtrack_0": bt0_dir,
                        "expected": expected_dir,
                    },
                )

        except Exception as e:
            if symbol in CRYPTO_SYMBOLS:
                reason = f"Live indicator fetch failed: {e}"
                _record_signal_review(
                    "rejected",
                    symbol,
                    signal,
                    entry,
                    asset,
                    filter_name="live_data_fetch",
                    filter_value={"error": str(e)},
                    filter_reason=reason,
                )
                plain_log("REJECTED", {"reason": reason, "symbol": symbol, "signal": signal})
                telegram_client.notify_rejected(reason, symbol, signal)
                return jsonify({"status": "rejected", "reason": "live data unavailable"})
            else:
                atr_source = "offset_fallback"
                tg_note = "SL/TP via fixed offset — live checks skipped (TAAPI forex not on plan)"
                plain_log("TAAPI_FALLBACK", {"symbol": symbol, "reason": str(e), "fallback": "fixed offset"})

        if atr is not None:
            atr_pct = (Decimal(str(atr)) / Decimal(str(entry))) * Decimal("100")
            if atr_pct > Decimal("4.0"):
                reason = f"Extreme volatility — ATR {float(atr_pct):.2f}% exceeds 4% of price, skipping"
                plain_log("REJECTED", {"reason": reason, "symbol": symbol, "signal": signal, "atr_pct": float(atr_pct)})
                telegram_client.notify_rejected(reason, symbol, signal)
                return jsonify({"status": "rejected", "reason": reason})
            if atr_pct < Decimal("0.05"):
                reason = f"Dead market — ATR {float(atr_pct):.2f}% below 0.05% of price, skipping"
                plain_log("REJECTED", {"reason": reason, "symbol": symbol, "signal": signal, "atr_pct": float(atr_pct)})
                telegram_client.notify_rejected(reason, symbol, signal)
                return jsonify({"status": "rejected", "reason": reason})

        # ------------------------------------------------------------------
        # 7a. Per-symbol indicator gate  (v2026-04-22)
        #     Routing based on Pine Script v2.1.0 strategy field:
        #
        #     PULLBACK (BTC/ETH):
        #       EMA proximity check — entry must be within 3% of EMA200.
        #       Validates the pullback actually happened (price touched EMA).
        #       RSI tighter: 35-65 (pullbacks occur when RSI cools, not at extremes).
        #
        #     MOMENTUM (BTC/ETH breakout):
        #       NO EMA proximity check — momentum moves don't pull back.
        #       RSI relaxed: up to 80 (momentum often has high RSI).
        #       Volume relaxed: 75% of average (not 85%).
        #
        #     BREAKOUT (XAUUSD, EURUSD):
        #       No indicator gate — the breakout IS the signal.
        #       TV Pine Script already validated swing level break + bias + structure + RSI + EMA.
        #
        #     STRUCTURE (FX/Gold structure flip):
        #       SuperTrend conflict check — ST must agree with signal direction.
        #
        #     SUPER TREND (US500, others):
        #       SuperTrend conflict check as before — ST is the entry trigger here.
        # ------------------------------------------------------------------
        # Determine strategy from alert field (v2.1.1) or fall back to symbol routing
        if strategy == "unknown":
            strategy = get_default_strategy_for_symbol(
                symbol,
                "breakout" if symbol in BREAKOUT_SYMBOLS else "pullback" if symbol in PULLBACK_SYMBOLS else "supertrend",
            )

        setup_grade = None
        setup_volume_ratio = None
        setup_ema_distance_pct = None
        setup_score_reasons = []

        if strategy == "mean_reversion":
            setup_grade = "B"
            setup_score_reasons = ["15m Bollinger/RSI mean reversion with explicit exchange levels"]

        if live is not None and symbol in PULLBACK_SYMBOLS and strategy in ("pullback", "momentum", "trend_continuation"):
            crypto_entry_cfg = build_crypto_entry_config(DYNAMIC_THRESHOLDS, symbol)
            if not CRYPTO_PULLBACK_ENABLED and strategy == "pullback":
                crypto_entry_result = {
                    "mode": "reject",
                    "grade": "reject",
                    "reasons": ["crypto pullback mode disabled in config"],
                    "ema_distance_pct": None,
                    "volume_ratio": 0.0,
                }
            else:
                crypto_entry_result = classify_crypto_entry(
                    signal,
                    entry,
                    live,
                    crypto_entry_cfg,
                    requested_strategy=strategy,
                )

            if crypto_entry_result["mode"] == "reject":
                reason = "; ".join(crypto_entry_result.get("reasons") or ["crypto entry policy rejected setup"])
                _record_signal_review(
                    "rejected",
                    symbol,
                    signal,
                    entry,
                    asset,
                    filter_name="crypto_entry_policy",
                    filter_value={
                        "requested_strategy": strategy,
                        "ema_distance_pct": crypto_entry_result.get("ema_distance_pct"),
                        "volume_ratio": crypto_entry_result.get("volume_ratio"),
                    },
                    filter_reason=reason,
                    live=live,
                )
                plain_log(
                    "REJECTED",
                    {
                        "reason": reason,
                        "symbol": symbol,
                        "signal": signal,
                        "requested_strategy": strategy,
                        "ema_distance_pct": crypto_entry_result.get("ema_distance_pct"),
                        "volume_ratio": crypto_entry_result.get("volume_ratio"),
                    },
                )
                telegram_client.notify_rejected(reason, symbol, signal)
                return jsonify({"status": "rejected", "reason": reason})

            strategy = crypto_entry_result["mode"]
            setup_grade = crypto_entry_result.get("grade")
            setup_volume_ratio = crypto_entry_result.get("volume_ratio")
            setup_ema_distance_pct = crypto_entry_result.get("ema_distance_pct")
            setup_score_reasons = crypto_entry_result.get("score_reasons") or crypto_entry_result.get("reasons", [])

            if setup_grade == "C" and not SETUP_GRADE_C_LIVE:
                reason = "Grade C setup shadow-only — " + "; ".join(setup_score_reasons)
                _record_signal_review(
                    "rejected",
                    symbol,
                    signal,
                    entry,
                    asset,
                    filter_name="setup_grade_shadow",
                    filter_value={
                        "setup_grade": setup_grade,
                        "score_reasons": setup_score_reasons,
                        "volume_ratio": setup_volume_ratio,
                        "ema_distance_pct": setup_ema_distance_pct,
                    },
                    filter_reason=reason,
                    live=live,
                )
                plain_log(
                    "SETUP_SHADOW",
                    {
                        "symbol": symbol,
                        "signal": signal,
                        "setup_grade": setup_grade,
                        "score_reasons": setup_score_reasons,
                    },
                )

                # Calculate SL/TP virtual levels for shadow trade logging
                virtual_sl = None
                virtual_tp = None
                virtual_rr = 2.5  # default RR
                virtual_qty = 0.0

                # Check for explicit sl/tp in payload (e.g. 15m reversion scanner)
                explicit_sl = data.get("sl")
                explicit_tp = data.get("tp")
                if explicit_sl is not None and explicit_tp is not None:
                    virtual_sl = round(float(explicit_sl), 5)
                    virtual_tp = round(float(explicit_tp), 5)
                    sl_dist = abs(entry - virtual_sl)
                    virtual_rr = round(abs(virtual_tp - entry) / sl_dist, 2) if sl_dist > 0 else 2.5
                elif live is not None and "atr" in live and live["atr"] is not None:
                    atr_val = float(live["atr"])
                    sl_mult = float(asset.get("atr_sl_mult", 1.5))
                    sl_dist = atr_val * sl_mult
                    if signal == "BUY":
                        virtual_sl = round(entry - sl_dist, 5)
                        virtual_tp = round(entry + sl_dist * 2.5, 5)
                    else:
                        virtual_sl = round(entry + sl_dist, 5)
                        virtual_tp = round(entry - sl_dist * 2.5, 5)
                else:
                    offset = float(asset.get("default_offset", 1.0))
                    if signal == "BUY":
                        virtual_sl = round(entry - offset, 5)
                        virtual_tp = round(entry + offset * 2.5, 5)
                    else:
                        virtual_sl = round(entry + offset, 5)
                        virtual_tp = round(entry - offset * 2.5, 5)

                # Calculate quantity/lot size virtually
                virtual_risk = 50.00
                sl_dist = abs(entry - virtual_sl)
                if sl_dist > 0:
                    contract_size = float(asset.get("contract_size", 1.0))
                    virtual_qty = round(virtual_risk / (sl_dist * contract_size), 4)

                try:
                    trade_db.log_trade(
                        signal_id=signal_id,
                        symbol=symbol,
                        direction=signal,
                        entry_price=entry,
                        qty=virtual_qty,
                        sl=virtual_sl,
                        tp=virtual_tp,
                        rr=virtual_rr,
                        regime=regime,
                        strategy=strategy,
                        timeframe=timeframe,
                        mode="paper",
                        setup_grade=setup_grade,
                        risk_dollars=virtual_risk,
                        reward_dollars=virtual_risk * virtual_rr,
                        atr=live.get("atr") if live else None,
                        volume_ratio=setup_volume_ratio,
                        context={
                            "shadow": True,
                            "reason": reason,
                            "strategy_label": strategy_label,
                            "entry_setup_label": entry_setup_label,
                            "regime_label": regime_label,
                        },
                        strategy_label=None if strategy_label == UNKNOWN_STRATEGY_LABEL else strategy_label,
                        entry_setup_label=entry_setup_label,
                        regime_label=regime_label,
                        source_service=source_service,
                        webhook_port=webhook_port,
                        execution_mode=execution_mode,
                        lane=lane_name,
                        execution_state="shadow",
                    )
                except Exception as _db_err:
                    plain_log("SHADOW_TRADE_LOG_ERROR", {"error": str(_db_err)})

                telegram_client.notify_shadow(reason, symbol, signal, setup_grade=setup_grade)
                return jsonify({"status": "shadow", "reason": reason, "setup_grade": setup_grade})

            plain_log(
                "CRYPTO_ENTRY_CLASSIFIED",
                {
                    "symbol": symbol,
                    "signal": signal,
                    "requested_strategy": data.get("strategy", "unknown"),
                    "strategy_mode": strategy,
                    "setup_grade": setup_grade,
                    "score_reasons": setup_score_reasons,
                    "volume_ratio": setup_volume_ratio,
                    "ema_distance_pct": setup_ema_distance_pct,
                },
            )

        strategy_label = canonical_strategy_label(strategy_label, strategy, timeframe)
        if strategy_label == UNKNOWN_STRATEGY_LABEL and lane_name == "1H_TREND":
            strategy_label = "1H_TREND_CONTINUATION"
        if not data.get("entry_setup_label"):
            entry_setup_label = derive_entry_setup_label(strategy, setup_grade)
        low_quality_reason = _low_quality_b_grade_reason(
            strategy_label=strategy_label,
            setup_grade=setup_grade,
            volume_ratio=setup_volume_ratio,
        )
        if low_quality_reason:
            _record_signal_review(
                "rejected",
                symbol,
                signal,
                entry,
                asset,
                filter_name="low_quality_b_grade_volume",
                filter_value={
                    "strategy_label": strategy_label,
                    "setup_grade": setup_grade,
                    "volume_ratio": setup_volume_ratio,
                    "min_volume_ratio": LIVE_MICRO_B_GRADE_MIN_VOLUME_RATIO,
                },
                filter_reason=low_quality_reason,
                live=live,
            )
            plain_log(
                "REJECTED",
                {
                    "reason": low_quality_reason,
                    "symbol": symbol,
                    "signal": signal,
                    "strategy_label": strategy_label,
                    "setup_grade": setup_grade,
                    "volume_ratio": setup_volume_ratio,
                },
            )
            telegram_client.notify_rejected(low_quality_reason, symbol, signal)
            return jsonify({"status": "rejected", "reason": low_quality_reason})

        if lane_name == "1H_TREND" and _has_enriched_market_context(live):
            market_context_decision = evaluate_market_context(
                symbol,
                signal,
                entry,
                live,
                strategy=strategy,
                alert_bias=bias,
                alert_structure=structure,
            )
            plain_log(
                "MARKET_CONTEXT_GATE",
                {
                    "symbol": symbol,
                    "signal": signal,
                    "strategy": strategy,
                    "allowed": market_context_decision.allowed,
                    "verdict": market_context_decision.verdict,
                    "reason": market_context_decision.reason,
                    "details": market_context_decision.details,
                },
            )
            if not market_context_decision.allowed:
                _record_signal_review(
                    "rejected",
                    symbol,
                    signal,
                    entry,
                    asset,
                    filter_name="market_context",
                    filter_value=market_context_decision.details,
                    filter_reason=market_context_decision.reason,
                    live=live,
                )
                telegram_client.notify_shadow(market_context_decision.reason, symbol, signal, setup_grade=setup_grade)
                return jsonify({
                    "status": "shadow",
                    "reason": market_context_decision.reason,
                    "verdict": market_context_decision.verdict,
                })

        # ------------------------------------------------------------------
        # 6b. Same-symbol loss cooldown.
        # ------------------------------------------------------------------
        try:
            import loss_cooldowns

            cooldown = loss_cooldowns.check_cooldown(
                symbol=symbol,
                direction=signal,
                setup_grade=setup_grade or "A",
                strategy=strategy or "unknown",
                timeframe=(timeframe or lane.timeframe or "1h"),
                is_live_micro=bool(MICRO_BOOTSTRAP_MODE and not BINANCE_TESTNET),
            )
        except Exception as cooldown_error:
            cooldown = None
            plain_log("LOSS_COOLDOWN_CHECK_ERROR", {"symbol": symbol, "signal": signal, "error": str(cooldown_error)})

        if cooldown:
            reason = "loss_cooldown_active"
            message = "Signal rejected: same-symbol loss cooldown active"
            _record_signal_review(
                "rejected",
                symbol,
                signal,
                entry,
                asset,
                filter_name="loss_cooldown",
                filter_value=cooldown,
                filter_reason=reason,
                live=live,
            )
            plain_log(
                "REJECTED",
                {
                    "reason": reason,
                    "symbol": symbol,
                    "signal": signal,
                    "cooldown": cooldown,
                },
            )
            telegram_client.notify_rejected(message, symbol, signal)
            return jsonify({"status": "rejected", "reason": reason, "message": message, "cooldown": cooldown})

        # ------------------------------------------------------------------
        # 6c. Strategy-correlation guardrail (bootstrap mode only)
        #
        #     Reject a new Grade-A momentum/breakout signal when an existing
        #     open DB trade is also a momentum or breakout setup.
        #
        #     Rationale: momentum/breakout positions across different pairs
        #     are highly correlated (BTC leads alts). A second simultaneous
        #     momentum entry multiplies correlated drawdown risk beyond what
        #     the position-count increase implies.
        #
        #     Gate fires only when ALL of:
        #       1. Bootstrap is active (equity <= MICRO_BOOTSTRAP_EQUITY_CEILING_USD)
        #       2. Incoming signal is Grade-A AND strategy is momentum OR breakout
        #       3. At least one open DB trade carries strategy momentum OR breakout
        # ------------------------------------------------------------------
        _MOMENTUM_BREAKOUT_STRATEGIES = {"momentum", "breakout"}
        if (
            is_micro_bootstrap_active(_get_live_equity())
            and setup_grade == "A"
            and strategy in _MOMENTUM_BREAKOUT_STRATEGIES
        ):
            try:
                all_open = trade_db.get_open_trades()  # cross-pair — no symbol filter
                correlated = [t for t in all_open if (t["strategy"] or "").lower() in _MOMENTUM_BREAKOUT_STRATEGIES]
                if correlated:
                    corr_symbols = [t["symbol"] for t in correlated]
                    reason = (
                        f"Strategy correlation guardrail — Grade-A {strategy} rejected: "
                        f"existing momentum/breakout position(s) open on {corr_symbols}"
                    )
                    _record_signal_review(
                        "rejected",
                        symbol,
                        signal,
                        entry,
                        asset,
                        filter_name="strategy_correlation",
                        filter_value={
                            "incoming_strategy": strategy,
                            "incoming_grade": setup_grade,
                            "correlated_symbols": corr_symbols,
                        },
                        filter_reason=reason,
                        live=live,
                    )
                    plain_log(
                        "REJECTED",
                        {
                            "reason": reason,
                            "symbol": symbol,
                            "signal": signal,
                            "strategy": strategy,
                            "setup_grade": setup_grade,
                            "correlated_open": corr_symbols,
                        },
                    )
                    telegram_client.notify_rejected(reason, symbol, signal)
                    return jsonify({"status": "rejected", "reason": reason})
            except Exception as _corr_err:
                plain_log("STRATEGY_CORRELATION_CHECK_ERROR", {"error": str(_corr_err)})
                # Fail-open: if the DB check throws, do not block the trade

        # ------------------------------------------------------------------
        # 6c. Local ADX regime filter  (bootstrap Grade-A momentum/breakout)
        #
        #     ADX < 25 signals a choppy, non-trending market where momentum
        #     and breakout setups have a materially lower win rate.  This
        #     gate prevents Grade-A entries in low-ADX regimes by computing
        #     ADX locally from Binance klines — no TAAPI or TV alerts used.
        #
        #     Applies only when:
        #       1. Incoming signal is Grade-A AND strategy is momentum OR breakout
        #     (Grade-B pullbacks bypass this gate entirely.)
        #
        #     Threshold: ADX < 25.0  → reject  (market is choppy / ranging)
        #                ADX >= 25.0 → pass    (market is trending)
        #
        #     Fail-open: if the ADX calculation itself fails (network error,
        #     insufficient data), the gate does NOT block the trade.
        # ------------------------------------------------------------------
        if setup_grade == "A" and strategy in _MOMENTUM_BREAKOUT_STRATEGIES:
            from dynamic_config import get_param, get_symbol_param

            _ADX_THRESHOLD = get_param("adx_threshold", 25.0)
            _ADX_INTERVAL = get_param("adx_interval", "1h")
            try:
                adx_value = calculate_adx(symbol, interval=_ADX_INTERVAL)
                if adx_value is not None and adx_value < _ADX_THRESHOLD:
                    override_cfg = get_symbol_param(symbol, "adx_volume_override", None)
                    override_volume_ratio = setup_volume_ratio
                    if override_volume_ratio is None and live:
                        override_volume_ratio = live.get("volume_expansion")
                    override_allowed, override_details = _adx_volume_override_allows(
                        symbol,
                        signal,
                        strategy,
                        adx_value,
                        _ADX_THRESHOLD,
                        live,
                        override_volume_ratio,
                        override_cfg if isinstance(override_cfg, dict) else None,
                    )
                    if override_allowed:
                        plain_log(
                            "ADX_VOLUME_OVERRIDE_PASS",
                            {
                                "symbol": symbol,
                                "signal": signal,
                                "strategy": strategy,
                                **override_details,
                            },
                        )
                    else:
                        reason = (
                            f"Local regime filter — ADX {adx_value} < {_ADX_THRESHOLD} "
                            f"({_ADX_INTERVAL}): market is choppy, Grade-A {strategy} rejected"
                        )
                        _record_signal_review(
                            "rejected",
                            symbol,
                            signal,
                            entry,
                            asset,
                            filter_name="local_regime_filter_adx_low",
                            filter_value={
                                "adx": adx_value,
                                "threshold": _ADX_THRESHOLD,
                                "interval": _ADX_INTERVAL,
                                "strategy": strategy,
                                "setup_grade": setup_grade,
                                "override": override_details,
                            },
                            filter_reason=reason,
                            live=live,
                        )
                        plain_log(
                            "REJECTED",
                            {
                                "reason": reason,
                                "symbol": symbol,
                                "signal": signal,
                                "strategy": strategy,
                                "setup_grade": setup_grade,
                                "adx": adx_value,
                                "adx_threshold": _ADX_THRESHOLD,
                                "adx_interval": _ADX_INTERVAL,
                                "override": override_details,
                            },
                        )
                        telegram_client.notify_rejected(reason, symbol, signal)
                        return jsonify({"status": "rejected", "reason": reason})
                elif adx_value is not None:
                    plain_log(
                        "ADX_REGIME_PASS",
                        {
                            "symbol": symbol,
                            "adx": adx_value,
                            "threshold": _ADX_THRESHOLD,
                            "strategy": strategy,
                        },
                    )
            except Exception as _adx_err:
                plain_log("ADX_REGIME_CHECK_ERROR", {"symbol": symbol, "error": str(_adx_err)})
                # Fail-open: do not block the trade if ADX check itself throws

        # MOMENTUM/TREND: no EMA proximity check (trend/momentum moves don't pull back)
        # BREAKOUT: no EMA check (already validated in Pine Script)

        if live is not None and strategy in ("supertrend", "structure"):
            # SuperTrend conflict check — only for ST/structure symbols
            bt1_dir = live.get("supertrend_direction")
            bt0_dir = live.get("supertrend_direction_forming")
            expected_dir = "long" if signal == "BUY" else "short"
            bt1_match = bt1_dir == expected_dir
            bt0_match = bt0_dir == expected_dir

            if not (bt0_match or bt1_match):
                reason = (
                    f"Live data conflict — SuperTrend conflicts on both backtracks "
                    f"(bt1={bt1_dir}, bt0={bt0_dir}), signal is {signal}"
                )
                _record_signal_review(
                    "rejected",
                    symbol,
                    signal,
                    entry,
                    asset,
                    filter_name="supertrend_conflict",
                    filter_value={"backtrack_1": bt1_dir, "backtrack_0": bt0_dir, "expected": expected_dir},
                    filter_reason=reason,
                    live=live,
                )
                plain_log(
                    "REJECTED",
                    {
                        "reason": reason,
                        "symbol": symbol,
                        "signal": signal,
                        "supertrend_backtrack_1": bt1_dir,
                        "supertrend_backtrack_0": bt0_dir,
                    },
                )
                telegram_client.notify_rejected(reason, symbol, signal)
                return jsonify({"status": "rejected", "reason": reason})

        # ------------------------------------------------------------------
        # 7b. RSI exhaustion check  (per-symbol thresholds v2026-04-22)
        #     BREAKOUT: No RSI gate — breakout momentum can push RSI high,
        #               filtering it removes the best entries.
        #     MOMENTUM: Relaxed thresholds (BUY < 80, SELL > 20) —
        #               momentum moves often have RSI 65-80.
        #     PULLBACK: Tighter thresholds (35-65) — pullbacks occur when RSI
        #               is cooling off, not at extremes.
        #     ST FALLBACK: Original thresholds (80/20).
        # ------------------------------------------------------------------
        crypto_setup_scored = setup_grade in ("A", "B", "C")

        if live is not None and strategy == "pullback" and not crypto_setup_scored:
            rsi = live["rsi"]
            rsi_reason = rsi_exhausted(
                signal,
                rsi,
                buy_max=DYNAMIC_THRESHOLDS["pullback_rsi_exhaustion"]["buy_max"],
                sell_min=DYNAMIC_THRESHOLDS["pullback_rsi_exhaustion"]["sell_min"],
            )
            if rsi_reason:
                _record_signal_review(
                    "rejected",
                    symbol,
                    signal,
                    entry,
                    asset,
                    filter_name="rsi_exhaustion",
                    filter_value={
                        "rsi": rsi,
                        "buy_max": DYNAMIC_THRESHOLDS["pullback_rsi_exhaustion"]["buy_max"],
                        "sell_min": DYNAMIC_THRESHOLDS["pullback_rsi_exhaustion"]["sell_min"],
                    },
                    filter_reason=rsi_reason,
                    live=live,
                )
                plain_log(
                    "REJECTED",
                    {
                        "reason": rsi_reason,
                        "symbol": symbol,
                        "signal": signal,
                        "rsi": rsi,
                        "buy_max": DYNAMIC_THRESHOLDS["pullback_rsi_exhaustion"]["buy_max"],
                        "sell_min": DYNAMIC_THRESHOLDS["pullback_rsi_exhaustion"]["sell_min"],
                    },
                )
                telegram_client.notify_rejected(rsi_reason, symbol, signal)
                return jsonify({"status": "rejected", "reason": rsi_reason})

        if live is not None and strategy == "momentum" and not crypto_setup_scored:
            # Relaxed RSI for momentum breakouts
            rsi = live["rsi"]
            rsi_reason = rsi_exhausted(
                signal,
                rsi,
                buy_max=DYNAMIC_THRESHOLDS["momentum_rsi_exhaustion"]["buy_max"],
                sell_min=DYNAMIC_THRESHOLDS["momentum_rsi_exhaustion"]["sell_min"],
            )
            if rsi_reason:
                _record_signal_review(
                    "rejected",
                    symbol,
                    signal,
                    entry,
                    asset,
                    filter_name="rsi_exhaustion",
                    filter_value={
                        "rsi": rsi,
                        "buy_max": DYNAMIC_THRESHOLDS["momentum_rsi_exhaustion"]["buy_max"],
                        "sell_min": DYNAMIC_THRESHOLDS["momentum_rsi_exhaustion"]["sell_min"],
                    },
                    filter_reason=rsi_reason,
                    live=live,
                )
                plain_log(
                    "REJECTED",
                    {
                        "reason": rsi_reason,
                        "symbol": symbol,
                        "signal": signal,
                        "rsi": rsi,
                        "buy_max": DYNAMIC_THRESHOLDS["momentum_rsi_exhaustion"]["buy_max"],
                        "sell_min": DYNAMIC_THRESHOLDS["momentum_rsi_exhaustion"]["sell_min"],
                    },
                )
                telegram_client.notify_rejected(rsi_reason, symbol, signal)
                return jsonify({"status": "rejected", "reason": rsi_reason})

        if live is not None and strategy in ("supertrend", "structure"):
            rsi = live["rsi"]
            rsi_reason = rsi_exhausted(
                signal,
                rsi,
                buy_max=DYNAMIC_THRESHOLDS["rsi_exhaustion"]["buy_max"],
                sell_min=DYNAMIC_THRESHOLDS["rsi_exhaustion"]["sell_min"],
            )
            if rsi_reason:
                _record_signal_review(
                    "rejected",
                    symbol,
                    signal,
                    entry,
                    asset,
                    filter_name="rsi_exhaustion",
                    filter_value={
                        "rsi": rsi,
                        "buy_max": DYNAMIC_THRESHOLDS["rsi_exhaustion"]["buy_max"],
                        "sell_min": DYNAMIC_THRESHOLDS["rsi_exhaustion"]["sell_min"],
                    },
                    filter_reason=rsi_reason,
                    live=live,
                )
                plain_log(
                    "REJECTED",
                    {
                        "reason": rsi_reason,
                        "symbol": symbol,
                        "signal": signal,
                        "rsi": rsi,
                        "buy_max": DYNAMIC_THRESHOLDS["rsi_exhaustion"]["buy_max"],
                        "sell_min": DYNAMIC_THRESHOLDS["rsi_exhaustion"]["sell_min"],
                    },
                )
                telegram_client.notify_rejected(rsi_reason, symbol, signal)
                return jsonify({"status": "rejected", "reason": rsi_reason})

        # BREAKOUT/MOMENTUM symbols: no RSI gate (handled above)

        # ------------------------------------------------------------------
        # 7c. Volume confirmation check
        #    Crypto only — Polygon-backed forex/gold data does not provide
        #    a reliable volume series for this filter.
        # ------------------------------------------------------------------
        # v2026-04-18 — Volume filter was silently disabled on BTC/ETH USD pairs. Fix applies to all pairs with volume data.
        if live is not None and live.get("volume", 0) > 0:
            vol = live["volume"]
            vol_avg = live.get("volume_avg20", 0)
            if vol_avg <= 0:
                # Volume average not available — skip this filter
                pass
            elif volume_below_threshold(vol, vol_avg, min_ratio=DYNAMIC_THRESHOLDS["volume_confirmation"]["min_ratio"]):
                reason = (
                    f"Low volume confirmation — "
                    f"volume {vol} below {round(DYNAMIC_THRESHOLDS['volume_confirmation']['min_ratio'] * 100, 1)}% of 20-period avg {vol_avg}"
                )
                _record_signal_review(
                    "rejected",
                    symbol,
                    signal,
                    entry,
                    asset,
                    filter_name="volume_confirmation",
                    filter_value={
                        "volume": vol,
                        "volume_avg20": vol_avg,
                        "min_ratio": DYNAMIC_THRESHOLDS["volume_confirmation"]["min_ratio"],
                    },
                    filter_reason=reason,
                    live=live,
                )
                plain_log(
                    "REJECTED",
                    {
                        "reason": reason,
                        "symbol": symbol,
                        "signal": signal,
                        "volume": vol,
                        "volume_avg20": vol_avg,
                        "volume_min_ratio": DYNAMIC_THRESHOLDS["volume_confirmation"]["min_ratio"],
                    },
                )
                telegram_client.notify_rejected(reason, symbol, signal)
                return jsonify({"status": "rejected", "reason": reason})

        # ------------------------------------------------------------------
        # 7d. EMA200 overextension check  (per-symbol v2026-04-22)
        #     BREAKOUT: No gate — breakouts can fire far from EMA200.
        #     MOMENTUM: No gate — momentum moves can be extended.
        #     PULLBACK: Already validated in 7a via ema_pullback_invalid (3% proximity).
        #     ST FALLBACK: Keep 5% overextension check.
        # ------------------------------------------------------------------
        if live is not None and strategy == "supertrend":
            ema200 = live.get("ema200")
            ema_reason = ema_overextended(
                signal,
                entry,
                ema200,
                max_distance_pct=DYNAMIC_THRESHOLDS["ema_overextension"]["max_distance_pct"],
            )
            if ema_reason:
                distance_pct = round(((entry - ema200) / ema200) * 100, 4) if ema200 else None
                _record_signal_review(
                    "rejected",
                    symbol,
                    signal,
                    entry,
                    asset,
                    filter_name="ema_overextension",
                    filter_value={
                        "entry": entry,
                        "ema200": ema200,
                        "distance_pct": distance_pct,
                        "max_distance_pct": DYNAMIC_THRESHOLDS["ema_overextension"]["max_distance_pct"],
                    },
                    filter_reason=ema_reason,
                    live=live,
                )
                plain_log(
                    "REJECTED",
                    {
                        "reason": ema_reason,
                        "symbol": symbol,
                        "signal": signal,
                        "entry": entry,
                        "ema200": ema200,
                        "ema_distance_pct": distance_pct,
                        "ema_max_distance_pct": DYNAMIC_THRESHOLDS["ema_overextension"]["max_distance_pct"],
                    },
                )
                telegram_client.notify_rejected(ema_reason, symbol, signal)
                return jsonify({"status": "rejected", "reason": ema_reason})

        # ------------------------------------------------------------------
        # 7e. Sentiment confluence check
        #     Macro-direction filter — rejects signals fighting the news view.
        #     Technicals gate first; sentiment is the final filter before sizing.
        # ------------------------------------------------------------------
        sentiment_reason = check_sentiment_conflict(symbol, signal)
        if sentiment_reason:
            _record_signal_review(
                "rejected",
                symbol,
                signal,
                entry,
                asset,
                filter_name="sentiment_conflict",
                filter_value={
                    "symbol": symbol,
                    "signal": signal,
                    "sentiment": SENTIMENT_OVERRIDES.get(symbol, "neutral"),
                    "mode": SENTIMENT_FILTER_MODE,
                },
                filter_reason=sentiment_reason,
                live=live,
            )
            plain_log("REJECTED", {"reason": sentiment_reason, "symbol": symbol, "signal": signal})
            telegram_client.notify_rejected(sentiment_reason, symbol, signal)
            return jsonify({"status": "rejected", "reason": sentiment_reason})

        # ------------------------------------------------------------------
        # 8. SL / TP calculation
        #    Crypto  → ATR-based  (SL = 1×ATR, TP = 2.5×ATR)
        #    Forex   → fixed offset from config (TP = offset × MIN_RR = 2.5)
        # ------------------------------------------------------------------
        # Base multiplier from asset config
        effective_sl_mult = asset["atr_sl_mult"]

        # Economic calendar override: widen SL during high-volatility events
        calendar_sl_mult = get_sl_multiplier()
        if calendar_sl_mult != 1.0:
            effective_sl_mult = calendar_sl_mult
            plain_log(
                "ECONOMIC_CALENDAR_SL_ADJUST",
                {
                    "symbol": symbol,
                    "action": get_current_action(),
                    "default_sl_mult": asset["atr_sl_mult"],
                    "calendar_sl_mult": calendar_sl_mult,
                },
            )

        # Dynamic ATR multiplier based on market movement class
        if atr is not None:
            min_sl_val = float(asset.get("min_sl", 0))
            from dynamic_config import get_param

            quiet_mult = float(
                asset.get("quiet_atr_multiplier", get_param("quiet_atr_multiplier", QUIET_ATR_MULTIPLIER))
            )
            fast_mult = float(asset.get("fast_atr_multiplier", get_param("fast_atr_multiplier", FAST_ATR_MULTIPLIER)))
            effective_sl_mult, movement_class_adjusted = get_adjusted_sl_mult(
                atr,
                min_sl_val,
                effective_sl_mult,
                quiet_mult=quiet_mult,
                fast_mult=fast_mult,
            )
            if movement_class_adjusted:
                plain_log(
                    "MOVEMENT_SL_ADJUST",
                    {
                        "symbol": symbol,
                        "movement_class": movement_class_adjusted,
                        "quiet_mult": quiet_mult if movement_class_adjusted == "quiet" else None,
                        "fast_mult": fast_mult if movement_class_adjusted == "fast" else None,
                        "new_sl_mult": round(effective_sl_mult, 2),
                    },
                )

        # Check for explicit stop loss and take profit in the payload (e.g. for Mean Reversion)
        explicit_sl = data.get("sl")
        explicit_tp = data.get("tp")

        if explicit_sl is not None and explicit_tp is not None:
            sl = round(float(explicit_sl), 5)
            tp = round(float(explicit_tp), 5)
            sl_distance = abs(entry - sl)
            if sl_distance > 0:
                rr = round(abs(tp - entry) / sl_distance, 4)
            else:
                rr = MIN_RR
            plain_log(
                "EXPLICIT_LEVELS_ACTIVE", {"symbol": symbol, "sl": sl, "tp": tp, "sl_distance": sl_distance, "rr": rr}
            )
        elif atr is not None:
            sl, tp, sl_distance = calculate_atr_levels(signal, entry, atr, effective_sl_mult, rr=MIN_RR)
        else:
            offset = float(asset["default_offset"])
            sl_distance = offset
            if signal == "BUY":
                sl = round(entry - offset, 5)
                tp = round(entry + offset * MIN_RR, 5)
            else:
                sl = round(entry + offset, 5)
                tp = round(entry - offset * MIN_RR, 5)

        movement = build_movement_snapshot(symbol, asset, live, sl_distance)
        plain_log("MOVEMENT_PROFILE", movement)

        # ------------------------------------------------------------------
        # 8. SL distance range check
        # ------------------------------------------------------------------
        min_sl = float(asset["min_sl"])
        min_sl_buffer = movement["min_sl_buffer"]
        tolerance_pct = movement["tolerance_pct"]

        if sl_distance < min_sl_buffer:
            reason = (
                f"ATR SL {round(sl_distance, 5)} below movement buffer "
                f"{min_sl_buffer} for {symbol} "
                f"(class={movement['movement_class']}, tol={round(tolerance_pct * 100, 1)}%)"
            )
            _record_signal_review(
                "rejected",
                symbol,
                signal,
                entry,
                asset,
                filter_name="sl_too_tight",
                filter_value={
                    "sl_distance": round(sl_distance, 5),
                    "min_sl_buffer": min_sl_buffer,
                    "movement_class": movement["movement_class"],
                    "tolerance_pct": tolerance_pct,
                },
                filter_reason=reason,
                live=live,
            )
            plain_log("REJECTED", {"reason": reason, "symbol": symbol, "signal": signal})
            record_signal_outcome(symbol, "rejected", movement, reason=reason)
            telegram_client.notify_rejected(reason, symbol, signal)
            return jsonify({"status": "rejected", "reason": "SL too tight"})

        if sl_distance < min_sl:
            plain_log(
                "SL_TOLERANCE",
                {
                    "symbol": symbol,
                    "signal": signal,
                    "sl_distance": round(sl_distance, 5),
                    "min_sl": min_sl,
                    "min_sl_buffer": min_sl_buffer,
                    "tolerance_pct": tolerance_pct,
                    "movement_class": movement["movement_class"],
                    "movement_ratio": movement["movement_ratio"],
                    "volume_ratio": movement["volume_ratio"],
                    "decision": "allowed_within_tolerance",
                },
            )

        if sl_distance > asset["max_sl"]:
            reason = f"ATR SL {round(sl_distance, 5)} above maximum {asset['max_sl']} for {symbol}"
            _record_signal_review(
                "rejected",
                symbol,
                signal,
                entry,
                asset,
                filter_name="sl_too_wide",
                filter_value={"sl_distance": round(sl_distance, 5), "max_sl": asset["max_sl"]},
                filter_reason=reason,
                live=live,
            )
            plain_log("REJECTED", {"reason": reason, "symbol": symbol, "signal": signal})
            record_signal_outcome(symbol, "rejected", movement, reason=reason)
            telegram_client.notify_rejected(reason, symbol, signal)
            return jsonify({"status": "rejected", "reason": "SL too wide"})

        # ------------------------------------------------------------------
        # 9. RR verification
        # ------------------------------------------------------------------
        tp_distance = abs(tp - entry)
        rr = round(tp_distance / sl_distance, 2) if sl_distance > 0 else 0

        if rr < MIN_RR:
            reason = f"R:R {rr} below minimum {MIN_RR}"
            _record_signal_review(
                "rejected",
                symbol,
                signal,
                entry,
                asset,
                filter_name="rr_below_minimum",
                filter_value={"rr": rr, "min_rr": MIN_RR},
                filter_reason=reason,
                live=live,
                sl=sl,
                tp=tp,
                rr=rr,
            )
            plain_log("REJECTED", {"reason": reason, "symbol": symbol, "signal": signal})
            telegram_client.notify_rejected(reason, symbol, signal)
            return jsonify({"status": "rejected", "reason": "RR too low"})

        live_gate = None
        if not PAPER_MODE and DATA_DRIVEN_LIVE_GATING:
            live_gate = evaluate_live_setup(symbol, signal, setup_grade, strategy)
            plain_log(
                "DATA_DRIVEN_LIVE_GATE",
                {
                    "symbol": symbol,
                    "signal": signal,
                    "setup_grade": setup_grade,
                    "strategy": strategy,
                    "allowed": live_gate.allowed,
                    "reason": live_gate.reason,
                    "gate": live_gate.gate_name,
                    "details": live_gate.details,
                    "verdict": live_gate.verdict,
                    "risk_multiplier": live_gate.risk_multiplier,
                },
            )
            if not live_gate.allowed:
                _record_signal_review(
                    "rejected",
                    symbol,
                    signal,
                    entry,
                    asset,
                    filter_name=live_gate.gate_name,
                    filter_value=live_gate.details,
                    filter_reason=live_gate.reason,
                    live=live,
                    sl=sl,
                    tp=tp,
                    rr=rr,
                )
                shadow_trade_id = _log_shadow_profile_trade(
                    signal_id=signal_id,
                    symbol=symbol,
                    signal=signal,
                    entry=entry,
                    sl=sl,
                    tp=tp,
                    rr=rr,
                    regime=regime,
                    strategy=strategy,
                    timeframe=timeframe,
                    setup_grade=setup_grade,
                    atr=round(atr, 5) if atr is not None else None,
                    volume_ratio=setup_volume_ratio,
                    reason=live_gate.reason,
                    gate_details=live_gate.details,
                )
                plain_log(
                    "LIVE_GATE_BLOCKED_TO_SHADOW",
                    {
                        "symbol": symbol,
                        "signal": signal,
                        "setup_grade": setup_grade,
                        "strategy": strategy,
                        "shadow_trade_id": shadow_trade_id,
                        "reason": live_gate.reason,
                        "details": live_gate.details,
                    },
                )
                telegram_client.notify_shadow(live_gate.reason, symbol, signal, setup_grade=setup_grade)
                return jsonify(
                    {
                        "status": "shadow",
                        "reason": live_gate.reason,
                        "shadow_trade_id": shadow_trade_id,
                        "live_gate_verdict": live_gate.verdict,
                    }
                )

        # ------------------------------------------------------------------
        # 10. Context engine — dynamic position sizing
        # ------------------------------------------------------------------
        context = get_size_multiplier(symbol, signal, risk_pct=RISK_PCT)

        if context["multiplier"] == 0.0:
            reason = f"Context engine SKIP — {context['reasoning']}"
            plain_log(
                "REJECTED",
                {
                    "reason": reason,
                    "symbol": symbol,
                    "signal": signal,
                    "context": context,
                },
            )
            _record_signal_review(
                "rejected",
                symbol,
                signal,
                entry,
                asset,
                filter_name="context_engine_skip",
                filter_value=context,
                filter_reason=reason,
                live=live,
            )
            telegram_client.notify_rejected(reason, symbol, signal)
            return jsonify({"status": "rejected", "reason": reason})

        # Apply multiplier with 8% hard cap
        adjusted_risk_pct = context["adjusted_risk_pct"]
        grade_risk_multiplier = SETUP_GRADE_RISK_MULTIPLIERS.get(setup_grade or "A", 1.0)
        if grade_risk_multiplier <= 0:
            reason = f"Setup grade {setup_grade} is not live-tradable"
            plain_log(
                "REJECTED",
                {
                    "reason": reason,
                    "symbol": symbol,
                    "signal": signal,
                    "setup_grade": setup_grade,
                    "score_reasons": setup_score_reasons,
                },
            )
            return jsonify({"status": "rejected", "reason": reason})
        if grade_risk_multiplier != 1.0:
            adjusted_risk_pct *= grade_risk_multiplier
            plain_log(
                "SETUP_GRADE_RISK_ADJUST",
                {
                    "symbol": symbol,
                    "signal": signal,
                    "setup_grade": setup_grade,
                    "grade_risk_multiplier": grade_risk_multiplier,
                    "score_reasons": setup_score_reasons,
                    "adjusted_risk_pct": adjusted_risk_pct,
                },
            )
        if live_gate and live_gate.risk_multiplier != 1.0:
            adjusted_risk_pct *= live_gate.risk_multiplier
            plain_log(
                "LIVE_GATE_RISK_ADJUST",
                {
                    "symbol": symbol,
                    "signal": signal,
                    "setup_grade": setup_grade,
                    "live_gate_verdict": live_gate.verdict,
                    "live_gate_reason": live_gate.reason,
                    "live_gate_risk_multiplier": live_gate.risk_multiplier,
                    "adjusted_risk_pct": adjusted_risk_pct,
                },
            )
        rearm_risk_multiplier = 1.0
        if daily_stop.get("rearm_available"):
            adjusted_risk_pct, rearm_risk_multiplier = apply_rearm_risk_multiplier(adjusted_risk_pct, daily_stop)
            plain_log(
                "LIVE_REARM_RISK_ADJUST",
                {
                    "symbol": symbol,
                    "signal": signal,
                    "rearm_risk_multiplier": rearm_risk_multiplier,
                    "rearm_used_count": daily_stop.get("rearm_used_count"),
                    "adjusted_risk_pct": adjusted_risk_pct,
                },
            )

        # Economic calendar override: reduce risk during high-volatility events
        calendar_risk_mult = get_risk_multiplier()
        if calendar_risk_mult != 1.0:
            adjusted_risk_pct *= calendar_risk_mult
            plain_log(
                "ECONOMIC_CALENDAR_RISK_ADJUST",
                {
                    "symbol": symbol,
                    "action": get_current_action(),
                    "original_risk_pct": context["adjusted_risk_pct"],
                    "calendar_risk_mult": calendar_risk_mult,
                    "adjusted_risk_pct": adjusted_risk_pct,
                },
            )

        breakout_risk_cap_multiplier = 1.0
        adjusted_risk_pct, breakout_risk_cap_multiplier = _apply_strategy_risk_cap(
            adjusted_risk_pct,
            RISK_PCT,
            strategy_label,
        )
        if breakout_risk_cap_multiplier != 1.0:
            plain_log(
                "STRATEGY_RISK_CAP",
                {
                    "symbol": symbol,
                    "signal": signal,
                    "strategy_label": strategy_label,
                    "cap_multiplier": OPENCLAW_BREAKOUT_RISK_CAP_MULTIPLIER,
                    "risk_cap_multiplier": breakout_risk_cap_multiplier,
                    "adjusted_risk_pct": adjusted_risk_pct,
                },
            )

        plain_log(
            "CONTEXT_ENGINE",
            {
                "symbol": symbol,
                "signal": signal,
                "multiplier": context["multiplier"],
                "adjusted_risk_pct": adjusted_risk_pct,
                "fear_greed": context["fear_greed"],
                "funding_rate": context["funding_rate"],
                "reasoning": context["reasoning"],
            },
        )

        # ------------------------------------------------------------------
        # 11. Lot sizing (using adjusted risk from context engine)
        # ------------------------------------------------------------------
        live_equity = _get_live_equity()
        if live_equity is None:
            reason = "Live equity unavailable — position cache not warm"
            plain_log("REJECTED", {"reason": reason, "symbol": symbol, "signal": signal})
            telegram_client.notify_rejected(reason, symbol, signal)
            return jsonify({"status": "rejected", "reason": reason})

        live_equity_dec = Decimal(str(live_equity))
        risk_decision = resolve_trade_risk(live_equity, RISK_PCT, adjusted_risk_pct)
        effective_risk_pct = risk_decision.effective_risk_pct
        effective_risk_pct_dec = Decimal(str(effective_risk_pct))
        adjusted_risk_percent = effective_risk_pct_dec * Decimal("100")
        lot = calculate_lot_size(
            live_equity_dec,
            adjusted_risk_percent,
            Decimal(str(sl_distance)),
            Decimal(str(asset["contract_size"])),
        )
        lot = float(min(Decimal(str(lot)), Decimal(str(MAX_LOT_SIZE))))  # hard cap
        risk_dollars_dec = Decimal(str(risk_decision.risk_dollars)).quantize(Decimal("0.01"))
        reward_dollars_dec = (risk_dollars_dec * Decimal(str(rr))).quantize(Decimal("0.01"))
        risk_dollars = float(risk_dollars_dec)
        reward_dollars = float(reward_dollars_dec)

        # ------------------------------------------------------------------
        # 12. Log APPROVED
        # ------------------------------------------------------------------
        approved_payload = {
            "signal": signal,
            "symbol": symbol,
            "entry": entry,
            "sl": sl,
            "tp": tp,
            "lot": lot,
            "atr": round(atr, 5) if atr is not None else None,
            "atr_source": atr_source,
            "sl_distance": round(sl_distance, 5),
            "live_equity": live_equity,
            "risk_dollars": risk_dollars,
            "risk_pct": RISK_PERCENT,
            "adjusted_risk_pct": adjusted_risk_pct,
            "effective_risk_pct": effective_risk_pct,
            "risk_mode": risk_decision.mode,
            "micro_bootstrap_active": risk_decision.bootstrap_active,
            "risk_adjusted_multiplier": risk_decision.adjusted_multiplier,
            "context_multiplier": context["multiplier"],
            "context_fear_greed": context["fear_greed"],
            "context_funding_rate": context["funding_rate"],
            "context_reasoning": context["reasoning"],
            "reward_dollars": reward_dollars,
            "rr": rr,
            "paper": PAPER_MODE,
            "strategy_mode": strategy,
            "strategy_label": strategy_label,
            "entry_setup_label": entry_setup_label,
            "regime_label": regime_label,
            "source_service": source_service,
            "webhook_port": webhook_port,
            "execution_mode": execution_mode,
            "setup_grade": setup_grade,
            "setup_score_reasons": setup_score_reasons,
            "grade_risk_multiplier": grade_risk_multiplier,
            "live_gate_verdict": live_gate.verdict if live_gate else None,
            "live_gate_reason": live_gate.reason if live_gate else None,
            "live_gate_risk_multiplier": live_gate.risk_multiplier if live_gate else 1.0,
            "live_rearm_risk_multiplier": rearm_risk_multiplier,
            "strategy_risk_cap_multiplier": breakout_risk_cap_multiplier,
            "volume_ratio": round(setup_volume_ratio, 4) if setup_volume_ratio is not None else None,
            "ema_distance_pct": round(setup_ema_distance_pct, 4) if setup_ema_distance_pct is not None else None,
            "live": live,  # full indicator snapshot — None for forex fallback
        }
        plain_log("APPROVED", approved_payload)
        _record_signal_review(
            "approved",
            symbol,
            signal,
            entry,
            asset,
            filter_name=None,
            filter_value=None,
            filter_reason=None,
            live=live,
            sl=sl,
            tp=tp,
            rr=rr,
            extra={
                "risk_dollars": risk_dollars,
                "reward_dollars": reward_dollars,
                "live_equity": live_equity,
                "setup_grade": setup_grade,
                "setup_score_reasons": setup_score_reasons,
                "live_gate_verdict": live_gate.verdict if live_gate else None,
                "live_gate_reason": live_gate.reason if live_gate else None,
                "live_gate_risk_multiplier": live_gate.risk_multiplier if live_gate else 1.0,
                "live_rearm_risk_multiplier": rearm_risk_multiplier,
                "strategy_risk_cap_multiplier": breakout_risk_cap_multiplier,
            },
        )
        trade_id = trade_db.log_trade(
            signal_id=signal_id,
            symbol=symbol,
            direction=signal,
            entry_price=entry,
            qty=lot,
            sl=sl,
            tp=tp,
            rr=rr,
            regime=regime,
            strategy=strategy,
            timeframe=timeframe,
            mode="testnet" if BINANCE_TESTNET else "live",
            setup_grade=setup_grade,
            risk_dollars=risk_dollars,
            reward_dollars=reward_dollars,
            atr=round(atr, 5) if atr is not None else None,
            volume_ratio=setup_volume_ratio,
            context={
                "multiplier": context.get("multiplier"),
                "fear_greed": context.get("fear_greed"),
                "funding_rate": context.get("funding_rate"),
                "reasoning": context.get("reasoning"),
                "setup_score_reasons": setup_score_reasons,
                "grade_risk_multiplier": grade_risk_multiplier,
                "live_gate_verdict": live_gate.verdict if live_gate else None,
                "live_gate_reason": live_gate.reason if live_gate else None,
                "live_gate_risk_multiplier": live_gate.risk_multiplier if live_gate else 1.0,
                "live_rearm_risk_multiplier": rearm_risk_multiplier,
                "strategy_risk_cap_multiplier": breakout_risk_cap_multiplier,
                "risk_mode": risk_decision.mode,
                "effective_risk_pct": effective_risk_pct,
                "micro_bootstrap_active": risk_decision.bootstrap_active,
                "strategy_label": strategy_label,
                "entry_setup_label": entry_setup_label,
                "regime_label": regime_label,
                "source_service": source_service,
                "webhook_port": webhook_port,
                "execution_mode": execution_mode,
            },
            strategy_label=strategy_label,
            entry_setup_label=entry_setup_label,
            regime_label=regime_label,
            source_service=source_service,
            webhook_port=webhook_port,
            execution_mode=execution_mode,
            lane=lane_name,
            execution_state="confirmed" if PAPER_MODE else "planned_entry",
        )
        if daily_stop.get("rearm_available") and not PAPER_MODE:
            trade_db.consume_live_rearm(
                trade_id,
                payload={
                    "symbol": symbol,
                    "signal": signal,
                    "risk_multiplier": rearm_risk_multiplier,
                    "risk_dollars": risk_dollars,
                },
            )
        record_signal_outcome(symbol, "approved", movement)
        try:
            journal_added = append_approved_trade(
                {
                    "ts": approved_payload.get("ts"),
                    **approved_payload,
                    "notes": f"APPROVED; paper={PAPER_MODE}; atr_source={atr_source}",
                }
            )
            plain_log(
                "CSV_JOURNAL",
                {
                    "status": "added" if journal_added else "duplicate",
                    "path": "/home/rick/.hermes/trading-journal/Hermes Trading Journal.csv",
                    "symbol": symbol,
                    "signal": signal,
                },
            )
        except Exception as journal_error:
            plain_log("CSV_JOURNAL_ERROR", {"error": str(journal_error), "symbol": symbol, "signal": signal})

        # ------------------------------------------------------------------
        # 12. Execute (background thread in live mode; log only in PAPER_MODE or paper_only assets)
        # ------------------------------------------------------------------
        is_paper_only = asset.get("paper_only", False)

        # Notify that all gates passed and trade is being executed
        telegram_client.notify_all_gates_passed(symbol, signal, entry, sl, tp, risk_dollars, setup_grade=setup_grade)

        if not PAPER_MODE and not is_paper_only:
            _mark_pending(symbol)

        def _record_execution_state(state, payload=None):
            if state == "entry_filled":
                trade_db.update_trade_fill(
                    trade_id,
                    (payload or {}).get("exec_price"),
                    (payload or {}).get("quantity"),
                )
            return trade_db.update_execution_state(
                trade_id,
                state,
                actor="binance_connector",
                payload=payload,
            )

        # Pass the original TV symbol (e.g. BTCUSDT) — not the MT5 symbol (BTCUSDm)
        # The router maps TV symbol → correct backend + exchange symbol
        exec_result = place_trade(
            signal,
            symbol,
            lot,
            sl_distance,
            rr,
            clear_pending_fn=_clear_pending,
            risk_pct_override=effective_risk_pct,
            execution_state_fn=_record_execution_state,
        )
        if not PAPER_MODE and not is_paper_only and not exec_result:
            reason = "Broker execution failed or was fail-closed after protection verification"
            plain_log(
                "EXECUTION_NOT_CONFIRMED",
                {
                    "trade_id": trade_id,
                    "symbol": symbol,
                    "signal": signal,
                    "reason": reason,
                },
            )
            try:
                trade_db.close_trade(
                    trade_id=trade_id,
                    exit_price=entry,
                    pnl=0.0,
                    gross_pnl=0.0,
                    exit_reason="execution_failed",
                    duration_min=0,
                )
                trade_db.log_exit(
                    trade_id=trade_id,
                    exit_type="execution_failed",
                    price=entry,
                    pnl_contribution=0.0,
                    qty_pct=1.0,
                    notes=reason,
                )
            except Exception as execution_db_err:
                plain_log(
                    "EXECUTION_FAILURE_DB_ERROR",
                    {
                        "trade_id": trade_id,
                        "symbol": symbol,
                        "error": str(execution_db_err),
                    },
                )
            telegram_client.notify_execution_fail_closed(signal, symbol, reason)
            return jsonify({"status": "execution_failed", "reason": reason, "symbol": symbol})

        # Update DB with actual executed quantity (Binance connector may adjust)
        if exec_result and exec_result.get("quantity") and trade_id:
            actual_qty = exec_result["quantity"]
            if actual_qty != lot:
                plain_log(
                    "TRADE_QTY_CORRECTED",
                    {
                        "trade_id": trade_id,
                        "symbol": symbol,
                        "planned_qty": lot,
                        "executed_qty": actual_qty,
                    },
                )
            try:
                trade_db.update_trade_qty(trade_id, actual_qty)
            except Exception as qty_update_err:
                plain_log(
                    "TRADE_QTY_UPDATE_ERROR",
                    {
                        "trade_id": trade_id,
                        "symbol": symbol,
                        "error": str(qty_update_err),
                    },
                )
            actual_risk_dollars = exec_result.get("risk_dollars")
            if actual_risk_dollars is not None and abs(float(actual_risk_dollars) - risk_dollars) > 0.005:
                target_risk_dollars = risk_dollars
                risk_dollars = round(float(actual_risk_dollars), 2)
                reward_dollars = round(risk_dollars * rr, 2)
                lot = actual_qty
                try:
                    trade_db.update_trade_risk(trade_id, risk_dollars, reward_dollars)
                except Exception as risk_update_err:
                    plain_log(
                        "TRADE_RISK_UPDATE_ERROR",
                        {
                            "trade_id": trade_id,
                            "symbol": symbol,
                            "error": str(risk_update_err),
                        },
                    )
                if exec_result.get("margin_cap"):
                    tg_note += f" Margin cap reduced target risk ${target_risk_dollars:.2f} -> ${risk_dollars:.2f}."
        if trade_id and exec_result and exec_result.get("execution_state") == "protection_verified":
            trade_db.update_execution_state(
                trade_id,
                "protection_verified",
                actor="webhook",
                payload={"broker_status": exec_result.get("status")},
            )
            if not trade_db.confirm_trade(trade_id):
                reason = "Trade protection verified but DB confirmation lacks SL anchor"
                plain_log("TRADE_CONFIRMATION_BLOCKED", {"trade_id": trade_id, "symbol": symbol, "reason": reason})
                telegram_client.notify_trade_error(signal, symbol, reason)
                return jsonify({"status": "confirmation_blocked", "reason": reason, "symbol": symbol}), 500

        # ------------------------------------------------------------------
        # 13. Telegram
        # ------------------------------------------------------------------
        tg_note_extra = " [PAPER-ONLY MODE]" if is_paper_only else ""
        telegram_client.notify_approved(
            signal,
            symbol,
            entry,
            sl,
            tp,
            lot,
            risk_dollars,
            rr,
            atr if atr is not None else 0.0,
            PAPER_MODE or is_paper_only,
            note=tg_note + tg_note_extra,
            setup_grade=setup_grade,
        )

        # ------------------------------------------------------------------
        # 14. Response
        # ------------------------------------------------------------------
        return jsonify(
            {
                "status": "approved",
                "signal": signal,
                "symbol": symbol,
                "entry": entry,
                "sl": sl,
                "tp": tp,
                "lot": lot,
                "rr": rr,
                "atr": round(atr, 5) if atr is not None else None,
                "paper": PAPER_MODE or is_paper_only,
                "setup_grade": setup_grade,
            }
        )

    except ValueError as e:
        plain_log(
            "ERROR",
            {
                "reason": str(e),
                "content_type": request.headers.get("Content-Type"),
                "user_agent": request.headers.get("User-Agent"),
                "raw_body": raw_body,
            },
        )
        return jsonify({"status": "error", "reason": str(e)}), 400
    except Exception as e:
        plain_log("ERROR", {"reason": str(e)})
        return jsonify({"status": "error", "reason": str(e)}), 500


@app.route("/ping", methods=["GET"])
def ping():
    """Public keep-alive endpoint for health checks and tunnel probes."""
    return jsonify({"status": "ok", "service": "ozzybot-webhook"}), 200


@app.route("/status", methods=["GET"])
def status():
    if not _status_endpoint_authorized():
        return _status_forbidden_response()

    live_equity = _get_live_equity()
    status_risk = resolve_trade_risk(float(live_equity or 0), RISK_PCT, RISK_PCT)
    daily_stop = _bootstrap_daily_stop_status(live_equity)
    if daily_stop is None:
        daily_stop = {
            "model": "percentage_drawdown",
            "daily_drawdown_limit_pct": DAILY_DRAWDOWN_LIMIT,
            "live_trading_blocked_for_day": None,
            "live_blocked_for_day": False,
            "live_paused_for_safety": False,
            "daily_strategy_full_losses": 0,
            "daily_safety_incidents": 0,
            "daily_realized_loss_usd": 0.0,
            "rearm_available": False,
            "rearm_used_count": 0,
            "rearm_risk_multiplier": REARM_RISK_MULTIPLIER,
            "reason": None,
        }

    # Fail-soft status reconciliation payload caching logic (30-second TTL)
    last_state = live_reconcile.get_last_reconcile_state()
    checked_at_str = last_state.get("checked_at")

    should_refresh = True
    if checked_at_str:
        try:
            checked_at = datetime.fromisoformat(checked_at_str)
            age = (datetime.now(UTC) - checked_at).total_seconds()
            if age < 30.0:
                should_refresh = False
        except Exception:
            pass

    reconciliation = last_state
    if should_refresh:
        try:
            reconciliation = live_reconcile.reconcile_live_state(dry_run=True)
        except Exception as e:
            # Fail soft: return cached state with error context to avoid status downtime
            reconciliation = dict(last_state)
            reconciliation["reconciliation_is_stale"] = True
            reconciliation["reconciliation_refresh_error"] = str(e)

    from dynamic_config import get_param

    active_symbols = get_param("active_symbols", BINANCE_SYMBOLS) if BINANCE_FUTURES_MODE else list(ASSETS.keys())
    monitor_gate = _monitor_entry_gate_status()
    status_summary_payload = {}
    try:
        import loss_cooldowns
        from status_summary import build_status_summary

        cached_positions, _cache_ok = _get_cached_positions()
        trade_rows = {
            str(row["symbol"]).upper(): dict(row)
            for row in trade_db.get_open_trades()
            if row["symbol"]
        }
        status_summary_payload = build_status_summary(
            mode=get_execution_mode(),
            binance_testnet=BINANCE_TESTNET,
            live_equity=live_equity,
            positions=cached_positions,
            trade_rows=trade_rows,
            daily_stop=daily_stop,
            reconciliation=reconciliation,
            active_symbols=active_symbols,
            db_path=trade_db.DB_PATH,
            active_cooldowns=len(loss_cooldowns.load_cooldowns()),
            no_new_entries_flag=False,
        )
        if not monitor_gate.get("allowed"):
            reason = f"monitor gate: {monitor_gate.get('reason', 'monitor_not_active')}"
            for section_name in ("live_micro", "testnet"):
                section = status_summary_payload.get(section_name)
                if isinstance(section, dict) and section.get("mode") == get_execution_mode():
                    section["new_entries_enabled"] = False
                    section["blocked"] = True
                    section.setdefault("entry_block_reasons", []).append(reason)
            scanner_state = status_summary_payload.get("scanner_state")
            if isinstance(scanner_state, dict):
                scanner_state["entries_blocked"] = True
                scanner_state.setdefault("entry_block_reasons", []).append(reason)
    except Exception as e:
        status_summary_payload = {
            "product_sync_health": {"status": "unknown", "issues": [f"status_summary_error: {e}"]},
            "memory_sync": {"status": "unknown", "issues": [f"status_summary_error: {e}"]},
            "scanner_state": {
                "mode": get_execution_mode(),
                "active_symbols_count": len(active_symbols),
                "entries_blocked": False,
                "entry_block_reasons": [],
            },
        }

    return jsonify(
        {
            **status_summary_payload,
            "status": "running",
            "dynamic_config": {
                "adx_threshold": get_param("adx_threshold", 25.0),
                "adx_interval": get_param("adx_interval", "1h"),
                "quiet_atr_multiplier": get_param("quiet_atr_multiplier", QUIET_ATR_MULTIPLIER),
                "fast_atr_multiplier": get_param("fast_atr_multiplier", FAST_ATR_MULTIPLIER),
                "breakeven_trigger_r": get_param("breakeven_trigger_r", 1.0),
                "trail_activation_r": get_param("trail_activation_r", 1.0),
                "trail_distance_r": get_param("trail_distance_r", 0.5),
                "momentum_exit_r": get_param("momentum_exit_r", 0.5),
                "momentum_lookback_seconds": get_param("momentum_lookback_seconds", 7200),
                "profit_protect_r": get_param("profit_protect_r", 0.3),
                "time_reduce_hours": get_param("time_reduce_hours", 16),
                "time_exit_hours": get_param("time_exit_hours", 24),
            },
            "backend": "binance" if BINANCE_FUTURES_MODE else "metaapi",
            "execution_mode": get_execution_mode(),
            "binance_testnet": BINANCE_TESTNET,
            "kill_zone": is_kill_zone(),
            "paper_mode": PAPER_MODE,
            "risk_pct": RISK_PCT,
            "effective_max_positions": effective_max_positions(MAX_POSITIONS, live_equity),
            "micro_bootstrap_mode": MICRO_BOOTSTRAP_MODE,
            "micro_bootstrap_active": is_micro_bootstrap_active(live_equity),
            "micro_bootstrap_risk_usd": MICRO_BOOTSTRAP_RISK_USD,
            "micro_bootstrap_equity_ceiling_usd": MICRO_BOOTSTRAP_EQUITY_CEILING_USD,
            "micro_bootstrap_max_positions": MICRO_BOOTSTRAP_MAX_POSITIONS,
            "risk": {
                "bootstrap_mode": status_risk.bootstrap_active,
                "equity_usd": live_equity,
                "live_risk_usd": status_risk.target_loss_at_sl_usd,
                "target_loss_at_sl_usd": status_risk.target_loss_at_sl_usd,
                "live_risk_pct_of_equity": status_risk.effective_risk_pct,
                "estimated_fee_usd": status_risk.estimated_fee_usd,
                "slippage_buffer_usd": status_risk.slippage_buffer_usd,
                "effective_risk_usd": status_risk.effective_risk_usd,
                "warning": status_risk.warning,
            },
            "daily_stop": daily_stop,
            "monitor_gate": monitor_gate,
            "daily_strategy_full_losses": daily_stop.get("daily_strategy_full_losses", 0),
            "daily_safety_incidents": daily_stop.get("daily_safety_incidents", 0),
            "daily_realized_loss_usd": daily_stop.get("daily_realized_loss_usd", 0.0),
            "live_paused_for_safety": daily_stop.get("live_paused_for_safety", False),
            "live_blocked_for_day": daily_stop.get("live_blocked_for_day", False),
            "rearm_available": daily_stop.get("rearm_available", False),
            "rearm_used_count": daily_stop.get("rearm_used_count", 0),
            "live_max_daily_loss_usd": LIVE_MAX_DAILY_LOSS_USD,
            "live_max_daily_full_losses": LIVE_MAX_DAILY_FULL_LOSSES,
            "rearm_risk_multiplier": REARM_RISK_MULTIPLIER,
            "max_rearmed_trades_after_safety_incident": MAX_REARMED_TRADES_AFTER_SAFETY_INCIDENT,
            "live_risk_estimated_fee_usd": LIVE_RISK_ESTIMATED_FEE_USD,
            "live_risk_slippage_buffer_usd": LIVE_RISK_SLIPPAGE_BUFFER_USD,
            "data_driven_live_gating": DATA_DRIVEN_LIVE_GATING,
            "data_gating_db": DATA_GATING_DB,
            "grade_health": {
                "min_trades": GRADE_HEALTH_MIN_TRADES,
                "lookback_trades": GRADE_HEALTH_LOOKBACK_TRADES,
                "min_avg_pnl": GRADE_HEALTH_MIN_AVG_PNL,
                "red_max_avg_pnl": GRADE_HEALTH_RED_MAX_AVG_PNL,
            },
            "symbol_heat": {
                "min_trades": SYMBOL_HEAT_MIN_TRADES,
                "lookback_trades": SYMBOL_HEAT_LOOKBACK_TRADES,
                "min_avg_pnl": SYMBOL_HEAT_MIN_AVG_PNL,
                "red_max_avg_pnl": SYMBOL_HEAT_RED_MAX_AVG_PNL,
            },
            "live_min_opportunity": {
                "enabled": LIVE_MIN_OPPORTUNITY_ENABLED,
                "hours": LIVE_MIN_OPPORTUNITY_HOURS,
            },
            "gemini_advisor": {
                "enabled": HERMES_GEMINI_ENABLED,
                "model": HERMES_GEMINI_MODEL,
                "key_configured": bool(GEMINI_API_KEY),
                "role": "read_only_evidence_advisor",
                "broker_actions_allowed": False,
            },
            "protection_truth_required": PROTECTION_TRUTH_REQUIRED,
            "protection_truth_live_only": PROTECTION_TRUTH_LIVE_ONLY,
            "post_fill_protection_finalizer": {
                "testnet_mode": POST_FILL_PROTECTION_TESTNET_MODE,
                "live_mode": POST_FILL_PROTECTION_LIVE_MODE,
                "active_mode": POST_FILL_PROTECTION_TESTNET_MODE if BINANCE_TESTNET else POST_FILL_PROTECTION_LIVE_MODE,
            },
            "daily_drawdown_limit": DAILY_DRAWDOWN_LIMIT,
            "daily_drawdown_enabled": DAILY_DRAWDOWN_ENABLED,
            "max_positions": MAX_POSITIONS,
            "max_positions_per_symbol": MAX_POSITIONS_PER_SYMBOL,
            "small_cap_launch_mode": SMALL_CAP_LAUNCH_MODE,
            "doge_shadow_only": DOGE_SHADOW_ONLY,
            "active_symbols": active_symbols,
            "cache_age_seconds": _cache_age_seconds(),
            "reconciliation": reconciliation,
        }
    )


@app.route("/health", methods=["GET"])
def health():
    """Lightweight uptime probe (e.g. UptimeRobot heartbeat)."""
    return jsonify({"status": "ok", "uptime_seconds": int(time.monotonic() - _PROCESS_BOOT_MONOTONIC)})


@app.route("/review", methods=["GET"])
def review_console():
    if not _status_endpoint_authorized():
        return _status_forbidden_response()

    context = build_review_dashboard_context()
    return render_template("review_console.html", **context)


def _verify_account_on_startup():
    """
    Runs once in a background thread when the process starts.
    Confirms correct account, live balance, and notifies Telegram.
    Skipped in PAPER_MODE (no MetaAPI connection needed).
    """
    import threading

    def _check():
        if PAPER_MODE:
            plain_log("STARTUP_CHECK", {"mode": "paper", "metaapi": "skipped"})
            telegram_client.notify_startup("N/A", "N/A", 0, 0, paper=True)
            return

        acct = binance_get_balance()
        balance = float((acct or {}).get("balance", 0))
        equity = float((acct or {}).get("equity", 0))
        currency = (acct or {}).get("currency", "USDT")
        status = "OK" if equity >= MIN_BALANCE_USD else "LOW BALANCE"

        plain_log(
            "STARTUP_CHECK",
            {
                "account_id": f"BINANCE_{get_execution_mode()}",
                "execution_mode": get_execution_mode(),
                "currency": currency,
                "balance": balance,
                "equity": equity,
                "status": status,
            },
        )
        telegram_client.notify_startup(f"BINANCE_{get_execution_mode()}", currency, balance, equity, paper=False)
        risk_decision = resolve_trade_risk(equity, RISK_PCT, RISK_PCT)
        if risk_decision.bootstrap_active and risk_decision.warning:
            telegram_client.notify_live_bootstrap_warning(risk_decision.warning)

    t = threading.Thread(target=_check, daemon=True)
    t.start()


if __name__ == "__main__":
    plain_log(
        "STARTUP",
        {
            "kill_zone": is_kill_zone(),
            "paper_mode": PAPER_MODE,
            "backend": "binance" if BINANCE_FUTURES_MODE else "metaapi",
            "execution_mode": get_execution_mode(),
            "binance_testnet": BINANCE_TESTNET,
            "balance": DEMO_BALANCE,
            "min_rr": MIN_RR,
            "max_lot": MAX_LOT_SIZE,
            "min_balance": MIN_BALANCE_USD,
            "account_id": f"BINANCE_{get_execution_mode()}",
        },
    )
    if not _startup_mode_check():
        msg = f"HERMES STARTUP ABORTED — Binance {get_execution_mode()} credentials missing."
        plain_log("STARTUP_ABORT", {"reason": msg})
        telegram_client.send_message(f"<b>HERMES STARTUP FAILED</b>\n{msg}")
        sys.exit(1)
    if not _warm_caches():
        msg = "HERMES STARTUP ABORTED — Binance unreachable. Will retry in 30s."
        plain_log("STARTUP_ABORT", {"reason": msg})
        telegram_client.send_message(f"<b>HERMES STARTUP FAILED</b>\n{msg}")
        sys.exit(1)

    _start_position_cache_thread()
    _start_daily_report_scheduler()
    _verify_account_on_startup()  # async Telegram card
    app.run(host="0.0.0.0", port=int(os.getenv("HERMES_PORT", "5000")), debug=False)

# Gunicorn entry point — runs startup tasks when imported as module
import os as _os

if _os.environ.get("SERVER_SOFTWARE", "").startswith("gunicorn") or "gunicorn" in _os.environ.get("_", ""):
    if not _startup_mode_check():
        sys.exit(1)
    _start_position_cache_thread()
    _start_daily_report_scheduler()
    _verify_account_on_startup()
