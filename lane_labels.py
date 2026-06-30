"""Stable strategy-lane labels for analytics and status summaries."""

from __future__ import annotations

from urllib.parse import urlparse


ONE_HOUR_TREND = "1H_TREND_CONTINUATION"
MEAN_REVERSION_15M = "15M_MEAN_REVERSION"
REVERSAL_CAPTURE_15M = "15M_REVERSAL_CAPTURE"
BREAKOUT_RETEST = "BREAKOUT_RETEST"
UNKNOWN = "UNKNOWN"

STABLE_STRATEGY_LABELS = {
    ONE_HOUR_TREND,
    MEAN_REVERSION_15M,
    REVERSAL_CAPTURE_15M,
    BREAKOUT_RETEST,
}


def normalize_timeframe(timeframe: str | int | None) -> str:
    raw = str(timeframe or "").strip().lower()
    if raw in {"15", "15m", "m15"}:
        return "15"
    if raw in {"60", "1h", "h1"}:
        return "60"
    return raw


def derive_strategy_label(strategy: str | None, timeframe: str | int | None = None) -> str:
    """Return the stable lane label for a strategy/timeframe pair."""
    strategy_norm = str(strategy or "").strip().lower()
    tf = normalize_timeframe(timeframe)

    if strategy_norm == "mean_reversion" and tf == "15":
        return MEAN_REVERSION_15M
    if strategy_norm == "reversal_capture" and tf == "15":
        return REVERSAL_CAPTURE_15M
    if strategy_norm in {"trend_continuation", "momentum", "pullback", "supertrend"} and tf in {"60", "1h"}:
        return ONE_HOUR_TREND
    if strategy_norm in {"breakout_retest", "breakout"}:
        return BREAKOUT_RETEST
    return UNKNOWN


def canonical_strategy_label(
    strategy_label: str | None,
    strategy: str | None,
    timeframe: str | int | None,
) -> str:
    """Return a stable analytics label, repairing source-name placeholders."""
    provided = str(strategy_label or "").strip().upper()
    if provided in STABLE_STRATEGY_LABELS:
        return provided
    derived = derive_strategy_label(strategy, timeframe)
    if derived != UNKNOWN:
        return derived
    return provided or UNKNOWN


def derive_entry_setup_label(strategy: str | None, setup_grade: str | None = None) -> str:
    strategy_norm = str(strategy or "unknown").strip().lower()
    grade = str(setup_grade or "").strip().upper()
    return f"{strategy_norm.upper()}_{grade}" if grade else strategy_norm.upper()


def derive_regime_label(regime: str | None, structure: str | None = None, bias: str | None = None) -> str:
    parts = [str(regime or "unknown").strip().upper()]
    if structure:
        parts.append(str(structure).strip().upper())
    elif bias:
        parts.append(str(bias).strip().upper())
    return "_".join(part for part in parts if part)


def webhook_port_from_url(url: str | None) -> int | None:
    if not url:
        return None
    try:
        parsed = urlparse(url)
        return parsed.port
    except Exception:
        return None


def webhook_port_from_host(host: str | None) -> int | None:
    if not host:
        return None
    try:
        if ":" in host:
            return int(str(host).rsplit(":", 1)[1])
    except Exception:
        return None
    return None
