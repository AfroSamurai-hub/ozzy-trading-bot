"""Generate a synthetic historical dataset for bootstrapping the pattern DB.

This script creates a CSV file with labelled pattern data, simulating
different market conditions (uptrends, downtrends, volatility) and the
resulting outcomes. This allows the AI agent to have a baseline of
historical context even without a real trading history.
"""

import numpy as np
import pandas as pd
from ta.momentum import RSIIndicator
from ta.trend import EMAIndicator

# Configuration
N_SAMPLES = 2500
SYMBOL = "BTCUSDT"
INITIAL_PRICE = 60000
VOLATILITY = 0.02
DRIFT = 0.0001
OUTPUT_PATH = "data/historical/BTCUSDT_5m_bootstrap.csv"


def generate_price_series(n_samples, initial_price, drift, volatility):
    """Generate a synthetic price series using a geometric Brownian motion."""
    dt = 1 / n_samples
    shocks = np.random.normal(loc=drift * dt, scale=volatility * np.sqrt(dt), size=n_samples)
    prices = initial_price * np.exp(np.cumsum(shocks))
    return prices


def generate_historical_data(n_samples, symbol):
    """Create a DataFrame with synthetic OHLCV data."""
    prices = generate_price_series(n_samples, INITIAL_PRICE, DRIFT, VOLATILITY)
    volume = np.random.poisson(lam=10, size=n_samples) + np.random.rand(n_samples)

    df = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(np.arange(n_samples), unit="m", origin="2024-01-01"),
            "symbol": symbol,
            "open": prices,
            "high": prices * (1 + np.random.uniform(0, 0.01, size=n_samples)),
            "low": prices * (1 - np.random.uniform(0, 0.01, size=n_samples)),
            "close": np.roll(prices, -1),
            "volume": volume,
        }
    )
    df.iloc[-1, df.columns.get_loc("close")] = prices[-1]  # Fix last close
    return df


def add_indicators(df):
    """Add technical indicators to the DataFrame."""
    df["price_change"] = df["close"].pct_change().fillna(0.0)
    df["volume_change"] = df["volume"].pct_change().fillna(0.0)
    df["rsi"] = RSIIndicator(close=df["close"], window=14).rsi().bfill().fillna(50.0)
    df["ema_short"] = EMAIndicator(close=df["close"], window=13).ema_indicator().bfill()
    df["ema_long"] = EMAIndicator(close=df["close"], window=23).ema_indicator().bfill()
    df["ema_ratio"] = df["ema_short"] / df["ema_long"]
    return df


def add_forward_labels(df, forward_window=6, takeprofit=0.03, stoploss=0.02):
    """Add forward-looking labels for training."""
    df["future_high"] = df["high"].rolling(window=forward_window).max().shift(-forward_window)
    df["future_low"] = df["low"].rolling(window=forward_window).min().shift(-forward_window)

    df["max_profit_pct"] = (df["future_high"] / df["close"]) - 1
    df["max_drawdown_pct"] = (df["future_low"] / df["close"]) - 1

    df["hit_takeprofit"] = df["max_profit_pct"] >= takeprofit
    df["hit_stoploss"] = df["max_drawdown_pct"] <= -stoploss

    # Labeling logic
    df["label"] = "NEUTRAL"
    df.loc[df["hit_takeprofit"] & ~df["hit_stoploss"], "label"] = "WIN"
    df.loc[~df["hit_takeprofit"] & df["hit_stoploss"], "label"] = "LOSS"
    df.loc[df["hit_takeprofit"] & df["hit_stoploss"], "label"] = "NEUTRAL"  # Volatile period

    return df


def main():
    """Main function to generate and save the data."""
    print(f"Generating {N_SAMPLES} synthetic historical data points...")
    df = generate_historical_data(N_SAMPLES, SYMBOL)
    print("Adding technical indicators...")
    df = add_indicators(df)
    print("Adding forward-looking labels...")
    df = add_forward_labels(df)

    # Select relevant columns for export
    export_cols = [
        "timestamp",
        "label",
        "symbol",
        "rsi",
        "ema_ratio",
        "price_change",
        "volume_change",
        "max_profit_pct",
        "max_drawdown_pct",
        "hit_takeprofit",
        "hit_stoploss",
    ]
    final_df = df[export_cols].dropna()

    print(f"Saving {len(final_df)} labelled patterns to {OUTPUT_PATH}...")
    final_df.to_csv(OUTPUT_PATH, index=False)
    print("✅ Done.")
    print("\nDistribution of labels:")
    print(final_df["label"].value_counts(normalize=True))


if __name__ == "__main__":
    main()
