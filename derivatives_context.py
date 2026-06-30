"""Advisory derivatives-positioning context for OpenClaw.

This module is deliberately advisory-only. It does not place orders, size risk,
or block trades. It converts independent Binance derivatives signals into a
small context object that can be logged beside normal OHLCV breakout decisions.
"""

from __future__ import annotations

from typing import Any

import requests

BINANCE_FAPI_BASE = "https://fapi.binance.com"
FUNDING_CROWDED_LONG = 0.0010   # +0.10% per 8h: longs are paying meaningful premium
FUNDING_CROWDED_SHORT = -0.0010 # -0.10% per 8h: shorts are paying meaningful premium
TAKER_BUY_SUPPORT = 0.55
TAKER_SELL_SUPPORT = 0.45
MIN_OI_CONFIRM_PCT = 0.5


def _as_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def pct_change(start: float | None, end: float | None) -> float | None:
    """Return percentage change from start to end, or None on bad input."""
    start_f = _as_float(start)
    end_f = _as_float(end)
    if start_f is None or end_f is None or start_f == 0:
        return None
    return ((end_f - start_f) / start_f) * 100.0


def taker_buy_ratio_from_kline(kline: list[Any] | tuple[Any, ...] | dict[str, Any]) -> float | None:
    """Extract taker-buy ratio from one Binance kline payload.

    Binance REST kline arrays expose total volume at index 5 and taker-buy base
    volume at index 9. Some internal call sites may pass dict-shaped rows.
    """
    if isinstance(kline, dict):
        volume = _as_float(kline.get("volume"))
        taker_buy = _as_float(kline.get("taker_buy_base") or kline.get("taker_buy_base_asset_volume"))
    else:
        if len(kline) <= 9:
            return None
        volume = _as_float(kline[5])
        taker_buy = _as_float(kline[9])
    if volume is None or taker_buy is None or volume <= 0:
        return None
    return round(taker_buy / volume, 4)


def evaluate_derivatives_positioning(
    *,
    direction: str,
    price_change_pct: float | None,
    open_interest_delta_pct: float | None,
    funding_rate: float | None,
    taker_buy_ratio: float | None,
) -> dict[str, Any]:
    """Score derivatives-positioning context for a proposed BUY/SELL.

    Verdicts are advisory:
    - supportive: independent derivatives evidence agrees with the trade
    - mixed: some evidence agrees, some warns
    - crowded: funding/crowding risk is high for the proposed direction
    - unavailable: insufficient independent data
    """
    side = str(direction or "").upper()
    price_delta = _as_float(price_change_pct)
    oi_delta = _as_float(open_interest_delta_pct)
    funding = _as_float(funding_rate)
    taker_ratio = _as_float(taker_buy_ratio)

    if price_delta is None and oi_delta is None and funding is None and taker_ratio is None:
        return {
            "verdict": "unavailable",
            "score": 0,
            "reasons": ["derivatives_data_unavailable"],
            "metrics": {
                "price_change_pct": None,
                "open_interest_delta_pct": None,
                "funding_rate": None,
                "taker_buy_ratio": None,
            },
        }

    score = 0
    reasons: list[str] = []
    crowded = False

    if side == "BUY":
        if funding is not None and funding >= FUNDING_CROWDED_LONG:
            crowded = True
            score -= 2
            reasons.append("positive_funding_crowded_longs")
        elif funding is not None and funding < 0:
            score += 1
            reasons.append("negative_funding_long_squeeze_potential")

        if price_delta is not None and oi_delta is not None:
            if price_delta > 0 and oi_delta >= MIN_OI_CONFIRM_PCT:
                score += 2
                reasons.append("oi_confirms_new_longs")
            elif price_delta > 0 and oi_delta < 0:
                score -= 1
                reasons.append("price_up_oi_down_possible_short_squeeze")
            elif price_delta < 0 and oi_delta >= MIN_OI_CONFIRM_PCT:
                score -= 1
                reasons.append("oi_rising_against_buy")

        if taker_ratio is not None:
            if taker_ratio >= TAKER_BUY_SUPPORT:
                score += 1
                reasons.append("aggressive_buy_flow")
            elif taker_ratio <= TAKER_SELL_SUPPORT:
                score -= 1
                reasons.append("aggressive_sell_flow_against_buy")

    elif side == "SELL":
        if funding is not None and funding <= FUNDING_CROWDED_SHORT:
            crowded = True
            score -= 2
            reasons.append("negative_funding_crowded_shorts")
        elif funding is not None and funding > 0:
            score += 1
            reasons.append("positive_funding_short_squeeze_potential")

        if price_delta is not None and oi_delta is not None:
            if price_delta < 0 and oi_delta >= MIN_OI_CONFIRM_PCT:
                score += 2
                reasons.append("oi_confirms_new_shorts")
            elif price_delta < 0 and oi_delta < 0:
                score -= 1
                reasons.append("price_down_oi_down_possible_long_liquidation")
            elif price_delta > 0 and oi_delta >= MIN_OI_CONFIRM_PCT:
                score -= 1
                reasons.append("oi_rising_against_sell")

        if taker_ratio is not None:
            if taker_ratio <= TAKER_SELL_SUPPORT:
                score += 1
                reasons.append("aggressive_sell_flow")
            elif taker_ratio >= TAKER_BUY_SUPPORT:
                score -= 1
                reasons.append("aggressive_buy_flow_against_sell")
    else:
        reasons.append("invalid_direction")

    if not reasons:
        reasons.append("derivatives_context_neutral")

    if crowded:
        verdict = "crowded"
    elif score >= 2:
        verdict = "supportive"
    elif score <= -2:
        verdict = "conflict"
    else:
        verdict = "mixed"

    return {
        "verdict": verdict,
        "score": score,
        "reasons": reasons,
        "metrics": {
            "price_change_pct": round(price_delta, 4) if price_delta is not None else None,
            "open_interest_delta_pct": round(oi_delta, 4) if oi_delta is not None else None,
            "funding_rate": funding,
            "taker_buy_ratio": round(taker_ratio, 4) if taker_ratio is not None else None,
        },
    }


def _get_json(url: str, params: dict[str, Any], timeout: int = 10) -> Any:
    response = requests.get(url, params=params, timeout=timeout)
    response.raise_for_status()
    return response.json()


def fetch_open_interest_delta_pct(symbol: str, period: str = "15m", limit: int = 4) -> float | None:
    rows = _get_json(
        f"{BINANCE_FAPI_BASE}/futures/data/openInterestHist",
        {"symbol": symbol.upper(), "period": period, "limit": max(2, limit)},
    )
    if not rows or len(rows) < 2:
        return None
    return pct_change(rows[0].get("sumOpenInterest"), rows[-1].get("sumOpenInterest"))


def fetch_recent_price_change_and_taker_ratio(symbol: str, interval: str = "15m", limit: int = 4) -> tuple[float | None, float | None]:
    rows = _get_json(
        f"{BINANCE_FAPI_BASE}/fapi/v1/klines",
        {"symbol": symbol.upper(), "interval": interval, "limit": max(2, limit)},
    )
    if not rows or len(rows) < 2:
        return None, None
    price_delta = pct_change(_as_float(rows[0][1]), _as_float(rows[-1][4]))
    taker_ratio = taker_buy_ratio_from_kline(rows[-1])
    return price_delta, taker_ratio


def fetch_latest_funding_rate(symbol: str) -> float | None:
    rows = _get_json(
        f"{BINANCE_FAPI_BASE}/fapi/v1/fundingRate",
        {"symbol": symbol.upper(), "limit": 1},
    )
    if not rows:
        return None
    return _as_float(rows[0].get("fundingRate"))


def fetch_derivatives_positioning_context(symbol: str, direction: str, interval: str = "15m") -> dict[str, Any]:
    """Fetch and evaluate live Binance derivatives context.

    Fail-open by design: API errors return an unavailable advisory record rather
    than blocking or modifying trade execution.
    """
    try:
        price_delta, taker_ratio = fetch_recent_price_change_and_taker_ratio(symbol, interval=interval)
        oi_delta = fetch_open_interest_delta_pct(symbol, period=interval)
        funding = fetch_latest_funding_rate(symbol)
        evaluation = evaluate_derivatives_positioning(
            direction=direction,
            price_change_pct=price_delta,
            open_interest_delta_pct=oi_delta,
            funding_rate=funding,
            taker_buy_ratio=taker_ratio,
        )
        return {"status": "ok", "symbol": symbol.upper(), "direction": str(direction).upper(), **evaluation}
    except Exception as exc:
        return {
            "status": "unavailable",
            "symbol": symbol.upper(),
            "direction": str(direction).upper(),
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
