"""Read-only open-position context evaluation."""

from __future__ import annotations

from dataclasses import dataclass, asdict


@dataclass(frozen=True)
class PositionContext:
    symbol: str
    direction: str
    current_r: float | None
    peak_r: float | None
    giveback_pct: float | None
    range_position_pct: float | None
    nearest_support: float | None
    nearest_resistance: float | None
    opposite_reversal_signal: bool
    trend_thesis: str
    management_label: str

    def to_dict(self) -> dict:
        return asdict(self)


def _directional_r(direction: str, entry: float, current: float, sl: float | None) -> float | None:
    if not entry or not current or not sl:
        return None
    risk = abs(entry - sl)
    if risk <= 0:
        return None
    if str(direction).upper() == "BUY":
        return (current - entry) / risk
    return (entry - current) / risk


def _giveback_pct(current_r: float | None, peak_r: float | None) -> float | None:
    if current_r is None or peak_r is None or peak_r <= 0:
        return None
    giveback = max(0.0, peak_r - current_r)
    return min(100.0, (giveback / peak_r) * 100.0)


def _opposite_reversal(direction: str, indicators: dict) -> bool:
    sweep = indicators.get("liquidity_sweep")
    wick = indicators.get("wick_rejection")
    structure = indicators.get("market_structure")
    retest = indicators.get("retest_quality")
    if str(direction).upper() == "SELL":
        return bool(
            sweep == "bullish_sweep"
            or wick == "bullish_rejection"
            or structure == "bullish_choch"
            or retest == "support_retest_hold"
        )
    return bool(
        sweep == "bearish_sweep"
        or wick == "bearish_rejection"
        or structure == "bearish_choch"
        or retest == "resistance_retest_hold"
    )


def _trend_thesis(direction: str, indicators: dict, opposite_reversal: bool) -> str:
    trend = str(indicators.get("supertrend_direction") or "").lower()
    structure = str(indicators.get("market_structure") or "").lower()
    expected_trend = "long" if str(direction).upper() == "BUY" else "short"
    if opposite_reversal:
        return "broken"
    if trend == expected_trend or expected_trend in structure:
        return "intact"
    if trend or structure:
        return "weakening"
    return "unknown"


def _management_label(current_r: float | None, giveback_pct: float | None, trend_thesis: str) -> str:
    if trend_thesis == "broken" and current_r is not None and current_r <= 0:
        return "EXIT_REQUIRED"
    if giveback_pct is not None and giveback_pct >= 80:
        return "REDUCE_RISK"
    if current_r is not None and current_r > 0.3:
        return "PROTECT"
    return "HOLD"


def evaluate_position_context(position: dict, trade: dict | None = None, indicators: dict | None = None) -> PositionContext:
    """Return a read-only context label for an open position."""
    trade = trade or {}
    indicators = indicators or {}
    symbol = str(position.get("tv_symbol") or position.get("symbol") or trade.get("symbol") or "")
    direction = str(position.get("type") or trade.get("direction") or "").upper()
    entry = float(position.get("openPrice") or trade.get("entry_price") or 0.0)
    current = float(position.get("currentPrice") or entry or 0.0)
    sl = trade.get("sl") or position.get("stopLoss")
    sl_f = float(sl) if sl not in (None, "") else None
    current_r = _directional_r(direction, entry, current, sl_f)

    risk_dollars = float(trade.get("risk_dollars") or 0.0)
    peak_pnl = float(trade.get("peak_pnl") or 0.0)
    peak_r = peak_pnl / risk_dollars if risk_dollars > 0 else None
    giveback = _giveback_pct(current_r, peak_r)
    opposite = _opposite_reversal(direction, indicators)
    thesis = _trend_thesis(direction, indicators, opposite)

    return PositionContext(
        symbol=symbol,
        direction=direction,
        current_r=round(current_r, 4) if current_r is not None else None,
        peak_r=round(peak_r, 4) if peak_r is not None else None,
        giveback_pct=round(giveback, 2) if giveback is not None else None,
        range_position_pct=indicators.get("range_position_pct"),
        nearest_support=indicators.get("support"),
        nearest_resistance=indicators.get("resistance"),
        opposite_reversal_signal=opposite,
        trend_thesis=thesis,
        management_label=_management_label(current_r, giveback, thesis),
    )
