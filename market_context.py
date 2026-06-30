"""Deterministic market-context confluence gate.

This module is intentionally small and data-only. It gives the execution
pipeline a chart-context veto without putting an LLM or discretionary agent in
the live order path.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from config import get_symbol_strategy_profile, normalize_strategy_symbol


@dataclass(frozen=True)
class MarketContextDecision:
    allowed: bool
    verdict: str
    reason: str
    details: dict[str, Any]


def _expected_trend(signal: str) -> str:
    return "long" if str(signal).upper() == "BUY" else "short"


def _ema_distance_pct(price: float | None, ema200: float | None) -> float | None:
    if price is None or not ema200:
        return None
    return ((float(price) - float(ema200)) / float(ema200)) * 100.0


def _direction_side(signal: str, price: float | None, ema200: float | None) -> str:
    if price is None or ema200 is None:
        return "unknown"
    if signal.upper() == "BUY":
        return "with_ema_side" if price >= ema200 else "against_ema_side"
    return "with_ema_side" if price <= ema200 else "against_ema_side"


def _derive_context_bias(live: dict[str, Any], price: float | None) -> str:
    structure = str(live.get("market_structure") or "")
    if structure.startswith("bullish"):
        return "bullish_structure"
    if structure.startswith("bearish"):
        return "bearish_structure"

    ema200 = live.get("ema200")
    trend = live.get("supertrend_direction")
    if price is None or ema200 is None:
        return "unknown"
    above_ema = float(price) >= float(ema200)
    if above_ema and trend == "long":
        return "bullish"
    if not above_ema and trend == "short":
        return "bearish"
    if above_ema and trend == "short":
        return "bullish_support_mixed"
    if not above_ema and trend == "long":
        return "bearish_resistance_mixed"
    return "mixed"


def _derive_structure(live: dict[str, Any], price: float | None) -> str:
    structure = live.get("market_structure")
    if structure and structure != "unknown":
        return str(structure)

    ema200 = live.get("ema200")
    rsi = live.get("rsi")
    if price is None or ema200 is None:
        return "unknown"
    if float(price) >= float(ema200):
        if rsi is not None and float(rsi) >= 50.0:
            return "bullish_above_ema"
        return "ema_support_hold"
    if rsi is not None and float(rsi) <= 50.0:
        return "bearish_below_ema"
    return "ema_resistance_retest"


def _metric_at_least(value: Any, floor: float) -> bool:
    try:
        return value is not None and float(value) >= float(floor)
    except (TypeError, ValueError):
        return False


def _xau_sweep_continuation_allowed(
    *,
    normalized_symbol: str,
    normalized_signal: str,
    strategy: str | None,
    liquidity_sweep: str,
    wick_rejection: str,
    ema_side: str,
    trend: str | None,
    expected_trend: str,
    live: dict[str, Any],
    rules: dict[str, Any],
) -> bool:
    """Allow the narrow XAU momentum short pattern that survives sweep context."""
    exception = rules.get("xau_sweep_continuation_v1") or {}
    if not exception.get("enabled"):
        return False
    if normalized_symbol != "XAUUSDT":
        return False
    if normalized_signal != str(exception.get("signal", "SELL")).upper():
        return False
    if strategy and str(strategy) != str(exception.get("strategy", "momentum")):
        return False
    if liquidity_sweep != str(exception.get("liquidity_sweep", "bullish_sweep")):
        return False
    if wick_rejection == str(exception.get("blocked_wick_rejection", "bullish_rejection")):
        return False
    if ema_side != "with_ema_side":
        return False
    if trend != expected_trend:
        return False
    if not _metric_at_least(live.get("range_position_pct"), float(exception.get("min_range_position_pct", 20.0))):
        return False
    if not _metric_at_least(live.get("displacement_score"), float(exception.get("min_displacement_score", 1.5))):
        return False
    if not _metric_at_least(live.get("volume_expansion"), float(exception.get("min_volume_expansion", 0.75))):
        return False
    return True


TEST_BYPASS_ENABLED = False

DEFAULT_MARKET_CONTEXT_RULES: dict[str, Any] = {
    "require_ema_side": True,
    "sell_requires_below_ema200": True,
    "buy_requires_above_ema200": False,
    "block_structure_conflict": True,
    "block_liquidity_sweep_conflict": True,
    "block_wick_rejection_conflict": True,
    "block_bad_range_location": True,
    "block_alert_bias_conflict": True,
    "xau_sweep_continuation_v1": {
        "enabled": True,
        "signal": "SELL",
        "strategy": "momentum",
        "liquidity_sweep": "bullish_sweep",
        "blocked_wick_rejection": "bullish_rejection",
        "min_range_position_pct": 20.0,
        "min_displacement_score": 1.5,
        "min_volume_expansion": 0.75,
    },
}


def _merged_rules(profile_rules: dict[str, Any] | None) -> dict[str, Any]:
    rules = dict(DEFAULT_MARKET_CONTEXT_RULES)
    for key, value in (profile_rules or {}).items():
        if isinstance(value, dict) and isinstance(rules.get(key), dict):
            nested = dict(rules[key])
            nested.update(value)
            rules[key] = nested
        else:
            rules[key] = value
    return rules


def evaluate_market_context(
    symbol: str,
    signal: str,
    entry: float,
    live: dict[str, Any] | None,
    strategy: str | None = None,
    alert_bias: str | None = None,
    alert_structure: str | None = None,
) -> MarketContextDecision:
    if TEST_BYPASS_ENABLED:
        price = float(live.get("close") or entry) if live else entry
        ema200 = live.get("ema200") if live else None
        ema_distance = _ema_distance_pct(price, ema200)
        ema_side = _direction_side(symbol.upper(), price, ema200)
        context_bias = _derive_context_bias(live, price) if live else "bullish"
        context_structure = _derive_structure(live, price) if live else "bullish"
        expected_trend = _expected_trend(symbol.upper())
        details = {
            "symbol": symbol.upper(),
            "signal": signal.upper(),
            "strategy": strategy,
            "price": price,
            "ema200": ema200,
            "ema_distance_pct": ema_distance,
            "ema_side": ema_side,
            "expected_trend": expected_trend,
            "context_bias": context_bias,
            "context_structure": context_structure,
        }
        return MarketContextDecision(
            allowed=True,
            verdict="allow",
            reason="market_context_ok",
            details=details,
        )
    normalized_symbol = normalize_strategy_symbol(symbol)
    normalized_signal = str(signal).upper()
    profile = get_symbol_strategy_profile(normalized_symbol)
    rules = _merged_rules(profile.get("market_context") or {})

    if not live:
        return MarketContextDecision(
            allowed=False,
            verdict="block",
            reason="Market context unavailable",
            details={"symbol": normalized_symbol, "signal": normalized_signal},
        )

    price = float(live.get("close") or entry)
    ema200 = live.get("ema200")
    trend = live.get("supertrend_direction")
    ema_distance = _ema_distance_pct(price, ema200)
    ema_side = _direction_side(normalized_signal, price, ema200)
    context_bias = _derive_context_bias(live, price)
    context_structure = _derive_structure(live, price)
    expected_trend = _expected_trend(normalized_signal)

    details = {
        "symbol": normalized_symbol,
        "signal": normalized_signal,
        "strategy": strategy,
        "price": price,
        "ema200": ema200,
        "ema_distance_pct": ema_distance,
        "ema_side": ema_side,
        "supertrend_direction": trend,
        "expected_trend": expected_trend,
        "context_bias": context_bias,
        "context_structure": context_structure,
        "market_structure": live.get("market_structure"),
        "prior_structure_bias": live.get("prior_structure_bias"),
        "support": live.get("support"),
        "resistance": live.get("resistance"),
        "support_distance_pct": live.get("support_distance_pct"),
        "resistance_distance_pct": live.get("resistance_distance_pct"),
        "range_high": live.get("range_high"),
        "range_low": live.get("range_low"),
        "range_position_pct": live.get("range_position_pct"),
        "liquidity_sweep": live.get("liquidity_sweep"),
        "wick_rejection": live.get("wick_rejection"),
        "displacement_score": live.get("displacement_score"),
        "volume_expansion": live.get("volume_expansion"),
        "retest_quality": live.get("retest_quality"),
        "alert_bias": alert_bias,
        "alert_structure": alert_structure,
        "rules": rules,
    }

    allowed_directions = {str(d).upper() for d in rules.get("live_allowed_directions", [])}
    if allowed_directions and normalized_signal not in allowed_directions:
        return MarketContextDecision(
            allowed=False,
            verdict="shadow",
            reason=(
                f"Market context: {normalized_symbol} {normalized_signal} is shadow-only; "
                f"live directions are {sorted(allowed_directions)}"
            ),
            details=details,
        )

    blocked_directions = {str(d).upper() for d in rules.get("shadow_directions", [])}
    if normalized_signal in blocked_directions:
        return MarketContextDecision(
            allowed=False,
            verdict="shadow",
            reason=f"Market context: {normalized_symbol} {normalized_signal} is configured shadow-only",
            details=details,
        )

    if rules.get("block_alert_bias_conflict") and alert_bias:
        normalized_bias = str(alert_bias).lower()
        if normalized_signal == "SELL" and normalized_bias.startswith("bull"):
            return MarketContextDecision(
                allowed=False,
                verdict="shadow",
                reason=f"Market context: SELL conflicts with alert bias {alert_bias}",
                details=details,
            )
        if normalized_signal == "BUY" and normalized_bias.startswith("bear"):
            return MarketContextDecision(
                allowed=False,
                verdict="shadow",
                reason=f"Market context: BUY conflicts with alert bias {alert_bias}",
                details=details,
            )

    if rules.get("block_structure_conflict"):
        market_structure = str(live.get("market_structure") or "")
        if normalized_signal == "SELL" and market_structure.startswith("bullish"):
            return MarketContextDecision(
                allowed=False,
                verdict="shadow",
                reason=f"Market context: SELL conflicts with Binance structure {market_structure}",
                details=details,
            )
        if normalized_signal == "BUY" and market_structure.startswith("bearish"):
            return MarketContextDecision(
                allowed=False,
                verdict="shadow",
                reason=f"Market context: BUY conflicts with Binance structure {market_structure}",
                details=details,
            )

    if rules.get("sell_requires_below_ema200") and normalized_signal == "SELL" and ema_side == "against_ema_side":
        return MarketContextDecision(
            allowed=False,
            verdict="shadow",
            reason="Market context: SELL blocked while price is holding above EMA200 support",
            details=details,
        )

    if rules.get("buy_requires_above_ema200") and normalized_signal == "BUY" and ema_side == "against_ema_side":
        return MarketContextDecision(
            allowed=False,
            verdict="shadow",
            reason="Market context: BUY blocked while price is below EMA200 resistance",
            details=details,
        )

    if rules.get("require_ema_side") and ema_side == "against_ema_side":
        return MarketContextDecision(
            allowed=False,
            verdict="shadow",
            reason=(
                f"Market context: {normalized_signal} is against EMA200 side "
                f"({round(ema_distance or 0.0, 2)}%)"
            ),
            details=details,
        )

    if rules.get("block_liquidity_sweep_conflict", True):
        liquidity_sweep = str(live.get("liquidity_sweep") or "none")
        wick_rejection = str(live.get("wick_rejection") or "none")
        sweep_exception = _xau_sweep_continuation_allowed(
            normalized_symbol=normalized_symbol,
            normalized_signal=normalized_signal,
            strategy=strategy,
            liquidity_sweep=liquidity_sweep,
            wick_rejection=wick_rejection,
            ema_side=ema_side,
            trend=trend,
            expected_trend=expected_trend,
            live=live,
            rules=rules,
        )
        if sweep_exception:
            details["liquidity_sweep_exception"] = "xau_sweep_continuation_v1"
        if normalized_signal == "SELL" and liquidity_sweep == "bullish_sweep" and not sweep_exception:
            return MarketContextDecision(
                allowed=False,
                verdict="shadow",
                reason="Market context: SELL blocked after bullish liquidity sweep below support",
                details=details,
            )
        if normalized_signal == "BUY" and liquidity_sweep == "bearish_sweep":
            return MarketContextDecision(
                allowed=False,
                verdict="shadow",
                reason="Market context: BUY blocked after bearish liquidity sweep above resistance",
                details=details,
            )

    if rules.get("block_wick_rejection_conflict", True):
        wick_rejection = str(live.get("wick_rejection") or "none")
        if normalized_signal == "SELL" and wick_rejection == "bullish_rejection":
            return MarketContextDecision(
                allowed=False,
                verdict="shadow",
                reason="Market context: SELL blocked by bullish rejection wick",
                details=details,
            )
        if normalized_signal == "BUY" and wick_rejection == "bearish_rejection":
            return MarketContextDecision(
                allowed=False,
                verdict="shadow",
                reason="Market context: BUY blocked by bearish rejection wick",
                details=details,
            )

    range_position = live.get("range_position_pct")
    if range_position is not None and rules.get("block_bad_range_location", True):
        range_position = float(range_position)
        trend_continuation_sell_floor = 65.0 if str(strategy or "") == "trend_continuation" else 15.0
        min_sell_position = float(rules.get("min_range_position_pct_for_sell", trend_continuation_sell_floor))
        max_buy_position = float(rules.get("max_range_position_pct_for_buy", 85.0))
        if normalized_signal == "SELL" and range_position <= min_sell_position:
            if str(strategy or "") == "trend_continuation":
                return MarketContextDecision(
                    allowed=False,
                    verdict="shadow",
                    reason=(
                        "Market context: trend continuation SELL blocked below range trigger "
                        f"({round(range_position, 1)}% < {round(min_sell_position, 1)}%)"
                    ),
                    details=details,
                )
            return MarketContextDecision(
                allowed=False,
                verdict="shadow",
                reason=f"Market context: SELL blocked near range low ({round(range_position, 1)}%)",
                details=details,
            )
        if normalized_signal == "BUY" and range_position >= max_buy_position:
            return MarketContextDecision(
                allowed=False,
                verdict="shadow",
                reason=f"Market context: BUY blocked near range high ({round(range_position, 1)}%)",
                details=details,
            )

    min_displacement = rules.get("min_displacement_score")
    if min_displacement is not None:
        displacement = live.get("displacement_score")
        if displacement is None or float(displacement) < float(min_displacement):
            return MarketContextDecision(
                allowed=False,
                verdict="shadow",
                reason=(
                    f"Market context: displacement too weak "
                    f"({round(float(displacement or 0.0), 2)} < {float(min_displacement)})"
                ),
                details=details,
            )

    return MarketContextDecision(
        allowed=True,
        verdict="allow",
        reason="market_context_ok",
        details=details,
    )
