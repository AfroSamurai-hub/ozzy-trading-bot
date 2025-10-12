"""
Process historical OHLCV data into labeled trading patterns.

For each candle, calculate:
- RSI (14 period)
- EMA short (13 period) and long (23 period)
- Volume change
- Price change
- Look forward 6 candles (30 minutes)
- Label: WIN if price rallies 0.15%+ at any point within the window, LOSS otherwise

Output: data/historical/BTCUSDT_5m_bootstrap_patterns.csv
"""

from __future__ import annotations

import pandas as pd
import numpy as np
from ta.momentum import RSIIndicator
from ta.trend import EMAIndicator


def calculate_rsi(prices: pd.Series, period: int = 14) -> pd.Series:
    """Calculate RSI indicator."""
    indicator = RSIIndicator(close=prices, window=period)
    return indicator.rsi()


def calculate_ema(prices: pd.Series, period: int) -> pd.Series:
    """Calculate EMA indicator."""
    indicator = EMAIndicator(close=prices, window=period)
    return indicator.ema_indicator()


def process_patterns(
    input_file: str,
    lookforward: int = 6,
    win_threshold: float = 0.0015,
) -> pd.DataFrame:
    """
    Convert OHLCV data into labeled patterns for vector DB.

    Args:
        input_file: CSV file with OHLCV data
    lookforward: How many candles to look ahead (6 = 30 minutes for 5m)
    win_threshold: Minimum intrawindow rally to consider "WIN" (0.15%)

    Returns:
        DataFrame with patterns and labels
    """
    print(f"📊 Processing patterns from: {input_file}")

    # Load data
    df = pd.read_csv(input_file)
    df["timestamp"] = pd.to_datetime(df["timestamp"])

    print(f"   Loaded {len(df)} candles")

    # Calculate indicators
    print("🔢 Calculating indicators...")
    df["rsi"] = calculate_rsi(df["close"])
    df["ema_short"] = calculate_ema(df["close"], 13)
    df["ema_long"] = calculate_ema(df["close"], 23)

    # Derived features
    df["ema_ratio"] = df["ema_short"] / df["ema_long"]
    df["volume_change"] = df["volume"].pct_change()
    df["price_change"] = df["close"].pct_change()

    # Look forward for outcome
    print(f"🔮 Looking forward {lookforward} candles for labels...")
    df["future_close"] = df["close"].shift(-lookforward)

    future_high_candidates = [df["high"].shift(-i) for i in range(1, lookforward + 1)]
    df["future_high"] = pd.concat(future_high_candidates, axis=1).max(axis=1)

    df["price_change_forward"] = (df["future_high"] - df["close"]) / df["close"]
    df["price_change_forward_close"] = (
        df["future_close"] - df["close"]
    ) / df["close"]

    # Label patterns
    df["label"] = np.where(
        df["price_change_forward"] >= win_threshold, "WIN", "LOSS"
    )

    # Remove rows without enough future data
    df = df.iloc[:-lookforward].copy()

    # Drop NaNs from indicator warmups
    df = df.dropna()

    # Stats
    total = len(df)
    win_count = int((df["label"] == "WIN").sum())
    win_rate = (win_count / total * 100) if total else 0

    print(f"\n✅ Processed {total} patterns")
    print(f"   WIN: {win_count} ({win_rate:.1f}%)")
    print(f"   LOSS: {total - win_count} ({100 - win_rate:.1f}%)")

    output_file = input_file.replace(".csv", "_patterns.csv")
    columns = [
        "timestamp",
        "close",
        "rsi",
        "ema_short",
        "ema_long",
        "ema_ratio",
        "volume_change",
        "price_change",
        "future_close",
        "future_high",
        "price_change_forward_close",
        "price_change_forward",
        "label",
    ]
    df[columns].to_csv(output_file, index=False)

    print(f"📁 Saved to: {output_file}")

    return df


if __name__ == "__main__":
    SOURCE = "data/historical/BTCUSDT_5m_bootstrap.csv"
    patterns = process_patterns(
        input_file=SOURCE,
        lookforward=6,
        win_threshold=0.0015,
    )

    print("\n📋 Sample patterns:")
    print(
        patterns[
            [
                "timestamp",
                "rsi",
                "ema_ratio",
                "future_high",
                "price_change_forward",
                "label",
            ]
        ].head(10)
    )
