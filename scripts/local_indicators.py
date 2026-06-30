#!/usr/bin/env python3
"""
OzzyBot Local Technical Indicators Calculator
Fetches 15m raw candlestick data directly from Binance Futures API
and computes Bollinger Bands, RSI, Volume SMA, and ATR locally using Pandas/Numpy.

Completely independent of TAAPI or external indicators services.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
import numpy as np
import pandas as pd
import requests

BINANCE_FUTURES_URL = "https://fapi.binance.com/fapi/v1/klines"


def fetch_klines(symbol: str, interval: str = "15m", limit: int = 100) -> pd.DataFrame | None:
    """Fetch recent klines from Binance Futures API and return as parsed DataFrame."""
    params = {"symbol": symbol.upper(), "interval": interval, "limit": limit}
    try:
        resp = requests.get(BINANCE_FUTURES_URL, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()

        # Columns: Open time, Open, High, Low, Close, Volume, Close time, ...
        df = pd.DataFrame(
            data,
            columns=[
                "open_time",
                "open",
                "high",
                "low",
                "close",
                "volume",
                "close_time",
                "quote_asset_volume",
                "number_of_trades",
                "taker_buy_base_asset_volume",
                "taker_buy_quote_asset_volume",
                "ignore",
            ],
        )

        # Cast numeric fields to floats
        for col in ["open", "high", "low", "close", "volume"]:
            df[col] = df[col].astype(float)

        # Convert times to datetimes
        df["open_datetime"] = pd.to_datetime(df["open_time"], unit="ms", utc=True)
        return df
    except Exception as e:
        print(f"Error fetching candles for {symbol}: {e}", file=sys.stderr)
        return None


def calculate_indicators(
    df: pd.DataFrame, bb_window: int = 20, bb_mult: float = 2.0, rsi_window: int = 14, atr_window: int = 14
) -> pd.DataFrame:
    """Calculate Bollinger Bands, RSI, Volume SMA, and ATR on the DataFrame."""
    # 1. Bollinger Bands (20, 2)
    df["mbb"] = df["close"].rolling(window=bb_window).mean()
    df["std"] = df["close"].rolling(window=bb_window).std()
    df["ubb"] = df["mbb"] + (bb_mult * df["std"])
    df["lbb"] = df["mbb"] - (bb_mult * df["std"])

    # 2. RSI (14) using Wilder's smoothing alpha = 1/N
    delta = df["close"].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    ema_gain = gain.ewm(alpha=1 / rsi_window, adjust=False).mean()
    ema_loss = loss.ewm(alpha=1 / rsi_window, adjust=False).mean()

    # Smooth first N-1 elements using simple SMA to match TA-Lib initial warming period
    # gain_sma = gain.rolling(window=rsi_window).mean()
    # loss_sma = loss.rolling(window=rsi_window).mean()
    # But standard ewm with adjust=False is highly consistent and robust

    rs = ema_gain / np.where(ema_loss == 0, 1e-10, ema_loss)
    df["rsi"] = 100 - (100 / (1 + rs))

    # 3. Volume SMA (20) & Volume Ratio
    df["volume_sma20"] = df["volume"].rolling(window=20).mean()
    df["volume_ratio"] = df["volume"] / np.where(df["volume_sma20"] == 0, 1e-10, df["volume_sma20"])

    # 4. ATR (14) using Wilder's smoothing alpha = 1/N
    high = df["high"]
    low = df["low"]
    prev_close = df["close"].shift(1)

    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()

    df["tr"] = np.maximum(tr1, np.maximum(tr2, tr3))
    df["atr"] = df["tr"].ewm(alpha=1 / atr_window, adjust=False).mean()

    return df


def get_live_indicators_dict(symbol: str, interval: str = "15m", use_closed: bool = False) -> dict | None:
    """Fetch and return calculated indicators for the current or last closed candle."""
    df = fetch_klines(symbol, interval, limit=100)
    if df is None or len(df) < 50:
        return None

    df = calculate_indicators(df)
    latest = df.iloc[-2] if use_closed and len(df) >= 2 else df.iloc[-1]

    # Check wick ratio for rejection
    close = latest["close"]
    open_p = latest["open"]
    high = latest["high"]
    low = latest["low"]
    candle_range = high - low

    bottom_wick = min(open_p, close) - low
    top_wick = high - max(open_p, close)

    bottom_wick_pct = bottom_wick / candle_range if candle_range > 0 else 0
    top_wick_pct = top_wick / candle_range if candle_range > 0 else 0

    return {
        "symbol": symbol.upper(),
        "interval": interval,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "open_time": latest["open_datetime"].isoformat(),
        "open": round(open_p, 4),
        "high": round(high, 4),
        "low": round(low, 4),
        "close": round(close, 4),
        "volume": round(latest["volume"], 2),
        "volume_sma20": round(latest["volume_sma20"], 2),
        "volume_ratio": round(latest["volume_ratio"], 3),
        "lbb": round(latest["lbb"], 4) if not np.isnan(latest["lbb"]) else None,
        "mbb": round(latest["mbb"], 4) if not np.isnan(latest["mbb"]) else None,
        "ubb": round(latest["ubb"], 4) if not np.isnan(latest["ubb"]) else None,
        "rsi": round(latest["rsi"], 2) if not np.isnan(latest["rsi"]) else None,
        "atr": round(latest["atr"], 4) if not np.isnan(latest["atr"]) else None,
        "bottom_wick_pct": round(bottom_wick_pct, 3),
        "top_wick_pct": round(top_wick_pct, 3),
    }


def main():
    parser = argparse.ArgumentParser(description="Test local 15m indicator calculations")
    parser.add_argument("--symbol", type=str, default="SOLUSDT", help="Trading pair to query")
    parser.add_argument("--interval", type=str, default="15m", help="Candle interval (e.g. 15m, 1h)")
    args = parser.parse_args()

    symbol = args.symbol.upper()
    print(f"🚀 Fetching {args.interval} data for {symbol} and calculating indicators locally...")

    res = get_live_indicators_dict(symbol, args.interval)
    if res is None:
        print("❌ FAILED: Could not calculate indicators.")
        sys.exit(1)

    print("\n" + "=" * 50)
    print(f"  LOCAL INDICATORS REPORT ({symbol} - {args.interval})")
    print(f"  Open Time: {res['open_time']}")
    print("=" * 50)
    print(f"  Price metrics:")
    print(f"    Open:   {res['open']}")
    print(f"    High:   {res['high']}")
    print(f"    Low:    {res['low']}")
    print(f"    Close:  {res['close']}")
    print("-" * 50)
    print(f"  Bollinger Bands (20, 2):")
    print(f"    Upper Band (UBB): {res['ubb']}")
    print(f"    Middle Band (MBB): {res['mbb']}")
    print(f"    Lower Band (LBB): {res['lbb']}")
    print(
        f"    Position in Band:  {round(((res['close'] - res['lbb']) / (res['ubb'] - res['lbb'])) * 100, 1)}% (0%=LBB, 100%=UBB)"
    )
    print("-" * 50)
    print(f"  Momentum & Volatility:")
    print(f"    RSI (14):         {res['rsi']}")
    print(f"    ATR (14):         {res['atr']}")
    print("-" * 50)
    print(f"  Volume Metrics:")
    print(f"    Current Volume:   {res['volume']}")
    print(f"    Volume SMA (20):  {res['volume_sma20']}")
    print(f"    Volume Ratio:     {res['volume_ratio']}x (Need >= 1.25x for climax)")
    print("-" * 50)
    print(f"  Candlestick Rejections:")
    print(f"    Bottom Wick Pct:  {round(res['bottom_wick_pct'] * 100, 1)}% (Need >= 30% for LONG)")
    print(f"    Top Wick Pct:     {round(res['top_wick_pct'] * 100, 1)}% (Need >= 30% for SHORT)")
    print("=" * 50 + "\n")

    # Output raw JSON representation as required
    print(json.dumps(res, indent=2))


if __name__ == "__main__":
    main()
