#!/usr/bin/env python3
"""
Binance Native Indicators
Fetches live candles directly from Binance public API and calculates
indicators locally using TA-Lib + pandas.

Eliminates dependency on taapi.io for crypto pairs and removes
rate-limit (429) risk entirely.

SuperTrend implementation is Pine-Script-compatible (recursive,
hl2 source, 10-period ATR, factor 3.0) matching hermes_smc_v3.pine.
"""
import requests
import pandas as pd
import numpy as np
import talib
from logger import plain_log

# Binance Public APIs (no auth needed)
BINANCE_SPOT_KLINE_URL = "https://api.binance.com/api/v3/klines"
BINANCE_FUTURES_KLINE_URL = "https://fapi.binance.com/fapi/v1/klines"


def normalize_binance_symbol(symbol: str) -> str:
    """Normalize a raw asset or symbol to Binance USD-M perpetual format."""
    if not symbol:
        return ""
    s = symbol.strip().upper().replace("/", "")
    if s.endswith("USDT"):
        return s
    # Handle legacy USD-margined spot-style pairs by preferring USDT perpetual.
    if s.endswith("USD"):
        s = s[:-3]
    return f"{s}USDT"


def get_binance_klines(symbol: str, interval: str = "1h", limit: int = 250) -> pd.DataFrame:
    """
    Fetch Klines from Binance public APIs.

    Prefer spot candles when available; fall back to USD-M futures candles for
    futures-only symbols such as HYPEUSDT.
    Returns empty DataFrame on any error (logged).
    """
    # Normalise symbol to Binance format (USDT pairs)
    binance_sym = symbol.replace("/", "").replace("USDT", "").upper() + "USDT"
    # Deduplicate if already ends with USDT
    if not binance_sym.endswith("USDT"):
        binance_sym += "USDT"

    params = {"symbol": binance_sym, "interval": interval, "limit": limit}
    last_error = None
    try:
        for source, url in (("spot", BINANCE_SPOT_KLINE_URL), ("futures", BINANCE_FUTURES_KLINE_URL)):
            try:
                resp = requests.get(url, params=params, timeout=10)
                resp.raise_for_status()
                data = resp.json()
                if not data:
                    continue

                df = pd.DataFrame(
                    data,
                    columns=[
                        "timestamp", "open", "high", "low", "close", "volume",
                        "close_time", "quote_volume", "trades", "taker_buy_base",
                        "taker_buy_quote", "ignore",
                    ],
                )
                for col in ("open", "high", "low", "close", "volume"):
                    df[col] = df[col].astype(float)
                df.attrs["source"] = source
                return df
            except Exception as e:
                last_error = str(e)
                continue
    except Exception as e:
        last_error = str(e)

    plain_log("BINANCE_KLINE_ERROR", {"symbol": symbol, "interval": interval, "error": last_error})
    return pd.DataFrame()


def _pine_supertrend(df: pd.DataFrame, length: int = 10, factor: float = 3.0):
    """
    Pine-Script-compatible SuperTrend using hl2 source.
    Matches hermes_smc_v3.py implementation exactly.

    Returns:
        st_line   – pd.Series of SuperTrend line values
        direction – pd.Series of "long" / "short"
    """
    atr = talib.ATR(df["high"], df["low"], df["close"], timeperiod=length)
    atr = atr.bfill()
    hl2 = (df["high"] + df["low"]) / 2.0
    st_upper = hl2 + factor * atr
    st_lower = hl2 - factor * atr

    st_line = pd.Series(index=df.index, dtype=float)
    direction = pd.Series(index=df.index, dtype=object)

    # Bar 0 init — same as Pine: var float stLine = 0.0
    st_line.iloc[0] = st_lower.iloc[0]
    direction.iloc[0] = "long" if df["close"].iloc[0] > st_line.iloc[0] else "short"

    for i in range(1, len(df)):
        close = df["close"].iloc[i]
        prev_st = st_line.iloc[i - 1]
        if close > prev_st:
            st_line.iloc[i] = max(st_lower.iloc[i], prev_st)
            direction.iloc[i] = "long"
        else:
            st_line.iloc[i] = min(st_upper.iloc[i], prev_st)
            direction.iloc[i] = "short"

    return st_line, direction


def calculate_indicators(df: pd.DataFrame) -> dict:
    """
    Calculate confirmed indicators from Binance klines.

    Binance returns the currently forming candle as the last row.
    For webhook validation right after TradingView fires on bar close,
    the *confirmed* signal candle is the penultimate row (iloc[-2]).
    """
    if df.empty or len(df) < 2:
        return {}

    confirmed_idx = -2
    close = df["close"]
    high = df["high"]
    low = df["low"]

    # 1. RSI (14) — TA-Lib
    rsi = talib.RSI(close, timeperiod=14)

    # 2. EMA (200) — TA-Lib
    ema200 = talib.EMA(close, timeperiod=200)

    # 3. ATR (14) — TA-Lib
    atr = talib.ATR(high, low, close, timeperiod=14)

    # 4. Volume Average (20)
    vol_avg20 = df["volume"].rolling(window=20).mean()

    # 5. SuperTrend (10, 3) — Pine-compatible recursive
    st_line, st_direction = _pine_supertrend(df, length=10, factor=3.0)

    # Current/confirmed values
    current_close = close.iloc[confirmed_idx]
    current_rsi = rsi.iloc[confirmed_idx]
    current_ema200 = ema200.iloc[confirmed_idx]
    current_atr = atr.iloc[confirmed_idx]
    current_volume = df["volume"].iloc[confirmed_idx]
    current_vol_avg20 = vol_avg20.iloc[confirmed_idx]
    current_st_dir = st_direction.iloc[confirmed_idx]
    current_st_value = st_line.iloc[confirmed_idx]
    current_open = df["open"].iloc[confirmed_idx] if "open" in df else current_close
    current_high = high.iloc[confirmed_idx]
    current_low = low.iloc[confirmed_idx]

    range_window = df.iloc[max(0, len(df) + confirmed_idx - 40): len(df) + confirmed_idx]
    if len(range_window) >= 5:
        range_high = float(range_window["high"].max())
        range_low = float(range_window["low"].min())
    else:
        range_high = float(high.iloc[:confirmed_idx].max()) if len(df) > 2 else float(current_high)
        range_low = float(low.iloc[:confirmed_idx].min()) if len(df) > 2 else float(current_low)

    candle_range = float(current_high - current_low)
    candle_body = abs(float(current_close - current_open))
    bottom_wick = min(float(current_open), float(current_close)) - float(current_low)
    top_wick = float(current_high) - max(float(current_open), float(current_close))
    bottom_wick_pct = bottom_wick / candle_range if candle_range > 0 else 0.0
    top_wick_pct = top_wick / candle_range if candle_range > 0 else 0.0
    close_position_pct = ((float(current_close) - float(current_low)) / candle_range) * 100 if candle_range > 0 else 50.0
    candle_body_pct = (candle_body / candle_range) * 100 if candle_range > 0 else 0.0
    range_span = range_high - range_low
    range_position_pct = ((float(current_close) - range_low) / range_span) * 100 if range_span > 0 else 50.0
    support_distance_pct = ((float(current_close) - range_low) / float(current_close)) * 100 if current_close else None
    resistance_distance_pct = ((float(current_close) - range_high) / float(current_close)) * 100 if current_close else None
    volume_ratio = float(current_volume / current_vol_avg20) if pd.notna(current_vol_avg20) and current_vol_avg20 else None
    displacement_score = candle_body / float(current_atr) if pd.notna(current_atr) and current_atr else None

    liquidity_sweep = "none"
    if len(range_window) >= 5:
        if float(current_low) < range_low and float(current_close) > range_low:
            liquidity_sweep = "bullish_sweep"
        elif float(current_high) > range_high and float(current_close) < range_high:
            liquidity_sweep = "bearish_sweep"

    wick_rejection = "none"
    if bottom_wick_pct >= 0.45 and bottom_wick_pct > top_wick_pct:
        wick_rejection = "bullish_rejection"
    elif top_wick_pct >= 0.45 and top_wick_pct > bottom_wick_pct:
        wick_rejection = "bearish_rejection"

    market_structure = "range"
    if len(range_window) >= 5:
        if float(current_close) > range_high:
            market_structure = "bullish_bos"
        elif float(current_close) < range_low:
            market_structure = "bearish_bos"
        elif pd.notna(current_ema200):
            market_structure = "bullish" if float(current_close) >= float(current_ema200) else "bearish"

    retest_quality = "none"
    if wick_rejection == "bullish_rejection" and abs(support_distance_pct or 999.0) <= 0.35:
        retest_quality = "support_retest_hold"
    elif wick_rejection == "bearish_rejection" and abs(resistance_distance_pct or 999.0) <= 0.35:
        retest_quality = "resistance_retest_hold"

    # Forming candle values (for parity with taapi backtrack_0)
    forming_st_dir = st_direction.iloc[-1] if len(df) >= 1 else None
    forming_st_value = st_line.iloc[-1] if len(df) >= 1 else None

    return {
        "rsi": round(current_rsi, 2) if pd.notna(current_rsi) else None,
        "ema200": round(current_ema200, 2) if pd.notna(current_ema200) else None,
        "atr": round(current_atr, 2) if pd.notna(current_atr) else None,
        "supertrend_direction": current_st_dir,
        "supertrend_value": round(current_st_value, 2) if pd.notna(current_st_value) else None,
        "supertrend_direction_forming": forming_st_dir,
        "supertrend_value_forming": round(forming_st_value, 2) if pd.notna(forming_st_value) else None,
        "close": round(current_close, 2),
        "open": round(current_open, 2),
        "high": round(current_high, 2),
        "low": round(current_low, 2),
        "volume": round(current_volume, 2),
        "volume_avg20": round(current_vol_avg20, 2) if pd.notna(current_vol_avg20) else None,
        "volume_expansion": round(volume_ratio, 4) if volume_ratio is not None else None,
        "range_high": round(range_high, 5),
        "range_low": round(range_low, 5),
        "support": round(range_low, 5),
        "resistance": round(range_high, 5),
        "range_position_pct": round(max(0.0, min(100.0, range_position_pct)), 2),
        "support_distance_pct": round(support_distance_pct, 4) if support_distance_pct is not None else None,
        "resistance_distance_pct": round(resistance_distance_pct, 4) if resistance_distance_pct is not None else None,
        "liquidity_sweep": liquidity_sweep,
        "wick_rejection": wick_rejection,
        "retest_quality": retest_quality,
        "market_structure": market_structure,
        "prior_structure_bias": "range",
        "displacement_score": round(displacement_score, 4) if displacement_score is not None else None,
        "close_position_pct": round(close_position_pct, 2),
        "candle_body_pct": round(candle_body_pct, 2),
        "upper_wick_pct": round(top_wick_pct * 100, 2),
        "lower_wick_pct": round(bottom_wick_pct * 100, 2),
        "kline_source": df.attrs.get("source"),
    }


def get_live_indicators(symbol: str, interval: str = "1h") -> dict:
    """
    Main entry point. Fetches candles and returns indicators dict.
    Matches the format expected by webhook.py (formerly get_bulk_indicators).
    """
    df = get_binance_klines(symbol, interval)
    if df.empty:
        return {}
    return calculate_indicators(df)


def calculate_adx(
    symbol: str,
    interval: str = "1h",
    period: int = 14,
    limit: int = 50,
) -> float | None:
    """Calculate the 14-period ADX for a symbol using Binance klines and TA-Lib.

    Returns the ADX value from the last *confirmed* closed candle (iloc[-2]),
    consistent with how all other indicators in this module are read.

    Returns None on any error (empty klines, insufficient data, TA-Lib failure).
    Callers must treat None as 'unknown' and decide whether to fail-open or
    fail-closed.

    Args:
        symbol:   Binance/TradingView symbol, e.g. 'ETHUSDT'
        interval: Kline interval string, e.g. '1h', '4h'
        period:   ADX smoothing period (standard = 14)
        limit:    Number of candles to fetch. Must be >= 2 * period + 2 to
                  produce at least one valid ADX value. Default 50 is safe.
    """
    df = get_binance_klines(symbol, interval=interval, limit=limit)
    if df.empty or len(df) < period * 2 + 2:
        plain_log(
            "ADX_INSUFFICIENT_DATA",
            {"symbol": symbol, "interval": interval, "rows": len(df)},
        )
        return None
    try:
        adx_series = talib.ADX(df["high"], df["low"], df["close"], timeperiod=period)
        # Use iloc[-2]: last *confirmed* closed candle (iloc[-1] is still forming)
        adx_value = adx_series.iloc[-2]
        if pd.isna(adx_value):
            plain_log(
                "ADX_NAN",
                {"symbol": symbol, "interval": interval, "period": period},
            )
            return None
        return float(round(adx_value, 2))
    except Exception as e:
        plain_log(
            "ADX_CALCULATION_ERROR",
            {"symbol": symbol, "interval": interval, "error": str(e)},
        )
        return None
