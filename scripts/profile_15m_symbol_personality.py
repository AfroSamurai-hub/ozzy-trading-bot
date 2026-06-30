#!/usr/bin/env python3
"""Offline 15m symbol personality profiler.

This script is research-only. It fetches public Binance futures candles and
prints or writes aggregate metrics; it never posts webhooks or calls broker
order endpoints.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from binance_indicators import normalize_binance_symbol
from config import BINANCE_SYMBOLS

BINANCE_FUTURES_KLINES_URL = "https://fapi.binance.com/fapi/v1/klines"
MS_PER_15M = 15 * 60 * 1000


def fetch_futures_klines(symbol: str, days: int = 30, interval: str = "15m") -> pd.DataFrame:
    """Fetch public futures klines with pagination."""
    binance_symbol = normalize_binance_symbol(symbol)
    end_ms = int(time.time() * 1000)
    start_ms = end_ms - int(days * 24 * 60 * 60 * 1000)
    rows = []

    while start_ms < end_ms:
        params = {
            "symbol": binance_symbol,
            "interval": interval,
            "startTime": start_ms,
            "endTime": end_ms,
            "limit": 1500,
        }
        response = requests.get(BINANCE_FUTURES_KLINES_URL, params=params, timeout=15)
        response.raise_for_status()
        batch = response.json()
        if not batch:
            break
        rows.extend(batch)
        next_start = int(batch[-1][0]) + MS_PER_15M
        if next_start <= start_ms:
            break
        start_ms = next_start
        if len(batch) < 1500:
            break

    return klines_to_frame(rows)


def klines_to_frame(rows: list[list]) -> pd.DataFrame:
    df = pd.DataFrame(
        rows,
        columns=[
            "timestamp",
            "open",
            "high",
            "low",
            "close",
            "volume",
            "close_time",
            "quote_volume",
            "trades",
            "taker_buy_base",
            "taker_buy_quote",
            "ignore",
        ],
    )
    if df.empty:
        return df
    for col in ("open", "high", "low", "close", "volume"):
        df[col] = df[col].astype(float)
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
    return df.sort_values("timestamp").drop_duplicates("timestamp").reset_index(drop=True)


def enrich_indicators(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    previous_close = df["close"].shift(1)
    true_range = pd.concat(
        [
            df["high"] - df["low"],
            (df["high"] - previous_close).abs(),
            (df["low"] - previous_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    df["atr"] = true_range.rolling(14, min_periods=14).mean()
    df["atr_pct"] = (df["atr"] / df["close"]) * 100.0
    df["mid_bb"] = df["close"].rolling(20, min_periods=20).mean()
    bb_std = df["close"].rolling(20, min_periods=20).std()
    df["upper_bb"] = df["mid_bb"] + (bb_std * 2.0)
    df["lower_bb"] = df["mid_bb"] - (bb_std * 2.0)
    candle_range = (df["high"] - df["low"]).replace(0, pd.NA)
    upper_wick = df["high"] - df[["open", "close"]].max(axis=1)
    lower_wick = df[["open", "close"]].min(axis=1) - df["low"]
    df["upper_wick_ratio"] = upper_wick / candle_range
    df["lower_wick_ratio"] = lower_wick / candle_range
    df["return_pct"] = df["close"].pct_change() * 100.0
    return df


def mean_reversion_win_rate(df: pd.DataFrame, lookahead: int = 8) -> dict:
    wins = 0
    total = 0
    for idx in range(20, len(df) - lookahead):
        row = df.iloc[idx]
        if pd.isna(row["mid_bb"]) or pd.isna(row["lower_bb"]) or pd.isna(row["upper_bb"]):
            continue
        future = df.iloc[idx + 1 : idx + 1 + lookahead]
        buy_setup = row["low"] < row["lower_bb"] and row["close"] > row["lower_bb"]
        sell_setup = row["high"] > row["upper_bb"] and row["close"] < row["upper_bb"]
        if buy_setup:
            total += 1
            wins += int(float(future["high"].max()) >= float(row["mid_bb"]))
        if sell_setup:
            total += 1
            wins += int(float(future["low"].min()) <= float(row["mid_bb"]))
    return {"setups": total, "wins": wins, "win_rate": round(wins / total, 4) if total else None}


def breakout_stats(df: pd.DataFrame, lookback: int = 20, lookahead: int = 8) -> dict:
    follow = 0
    fakeout = 0
    total = 0
    for idx in range(lookback, len(df) - lookahead):
        prior = df.iloc[idx - lookback : idx]
        row = df.iloc[idx]
        atr = float(row.get("atr") or 0.0)
        if atr <= 0:
            continue
        prior_high = float(prior["high"].max())
        prior_low = float(prior["low"].min())
        future = df.iloc[idx + 1 : idx + 1 + lookahead]
        if row["close"] > prior_high:
            total += 1
            follow += int(float(future["high"].max()) >= float(row["close"] + atr))
            fakeout += int(float(future["close"].min()) < prior_high)
        elif row["close"] < prior_low:
            total += 1
            follow += int(float(future["low"].min()) <= float(row["close"] - atr))
            fakeout += int(float(future["close"].max()) > prior_low)
    return {
        "setups": total,
        "follow_through_rate": round(follow / total, 4) if total else None,
        "fakeout_rate": round(fakeout / total, 4) if total else None,
    }


def best_session_hour(df: pd.DataFrame, lookahead: int = 4) -> dict:
    work = df.copy()
    work["forward_abs_move_pct"] = ((work["close"].shift(-lookahead) - work["close"]).abs() / work["close"]) * 100.0
    hourly = work.groupby(work["timestamp"].dt.hour)["forward_abs_move_pct"].mean().dropna()
    if hourly.empty:
        return {"hour_utc": None, "avg_abs_move_pct": None}
    hour = int(hourly.idxmax())
    return {"hour_utc": hour, "avg_abs_move_pct": round(float(hourly.loc[hour]), 4)}


def mfe_mae_by_setup(df: pd.DataFrame, lookahead: int = 8) -> dict:
    buckets = {
        "mean_reversion_buy": [],
        "mean_reversion_sell": [],
        "breakout_up": [],
        "breakout_down": [],
    }
    for idx in range(20, len(df) - lookahead):
        row = df.iloc[idx]
        future = df.iloc[idx + 1 : idx + 1 + lookahead]
        if pd.isna(row["mid_bb"]) or pd.isna(row["lower_bb"]) or pd.isna(row["upper_bb"]):
            continue
        entry = float(row["close"])
        prior = df.iloc[idx - 20 : idx]
        setup = None
        direction = None
        if row["low"] < row["lower_bb"] and row["close"] > row["lower_bb"]:
            setup, direction = "mean_reversion_buy", "long"
        elif row["high"] > row["upper_bb"] and row["close"] < row["upper_bb"]:
            setup, direction = "mean_reversion_sell", "short"
        elif row["close"] > float(prior["high"].max()):
            setup, direction = "breakout_up", "long"
        elif row["close"] < float(prior["low"].min()):
            setup, direction = "breakout_down", "short"
        if not setup:
            continue
        if direction == "long":
            mfe = ((float(future["high"].max()) - entry) / entry) * 100.0
            mae = ((float(future["low"].min()) - entry) / entry) * 100.0
        else:
            mfe = ((entry - float(future["low"].min())) / entry) * 100.0
            mae = ((entry - float(future["high"].max())) / entry) * 100.0
        buckets[setup].append({"mfe_pct": mfe, "mae_pct": mae})

    summary = {}
    for setup, values in buckets.items():
        if not values:
            summary[setup] = {"count": 0, "avg_mfe_pct": None, "avg_mae_pct": None}
            continue
        summary[setup] = {
            "count": len(values),
            "avg_mfe_pct": round(sum(v["mfe_pct"] for v in values) / len(values), 4),
            "avg_mae_pct": round(sum(v["mae_pct"] for v in values) / len(values), 4),
        }
    return summary


def btc_correlation(df: pd.DataFrame, btc_df: pd.DataFrame | None) -> float | None:
    if btc_df is None or btc_df.empty or df.empty:
        return None
    left = df[["timestamp", "return_pct"]].rename(columns={"return_pct": "symbol_return"})
    right = btc_df[["timestamp", "return_pct"]].rename(columns={"return_pct": "btc_return"})
    merged = left.merge(right, on="timestamp", how="inner").dropna()
    if len(merged) < 20:
        return None
    return round(float(merged["symbol_return"].corr(merged["btc_return"])), 4)


def profile_symbol(symbol: str, df: pd.DataFrame, btc_df: pd.DataFrame | None = None) -> dict:
    enriched = enrich_indicators(df)
    mean_reversion = mean_reversion_win_rate(enriched)
    breakout = breakout_stats(enriched)
    return {
        "symbol": normalize_binance_symbol(symbol),
        "candles": len(enriched),
        "atr_pct": round(float(enriched["atr_pct"].dropna().mean()), 4) if not enriched["atr_pct"].dropna().empty else None,
        "wick_ratio": {
            "upper_avg": round(float(enriched["upper_wick_ratio"].dropna().mean()), 4)
            if not enriched["upper_wick_ratio"].dropna().empty
            else None,
            "lower_avg": round(float(enriched["lower_wick_ratio"].dropna().mean()), 4)
            if not enriched["lower_wick_ratio"].dropna().empty
            else None,
        },
        "mean_reversion_to_middle_bb": mean_reversion,
        "breakout_follow_through_rate": breakout["follow_through_rate"],
        "fakeout_rate": breakout["fakeout_rate"],
        "breakout_setups": breakout["setups"],
        "btc_correlation": btc_correlation(enriched, btc_df),
        "best_session_hour": best_session_hour(enriched),
        "mfe_mae_by_setup_type": mfe_mae_by_setup(enriched),
    }


def write_csv(path: Path, profiles: list[dict]) -> None:
    fields = [
        "symbol",
        "candles",
        "atr_pct",
        "upper_wick_avg",
        "lower_wick_avg",
        "mean_reversion_setups",
        "mean_reversion_win_rate",
        "breakout_follow_through_rate",
        "fakeout_rate",
        "btc_correlation",
        "best_hour_utc",
    ]
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for profile in profiles:
            writer.writerow(
                {
                    "symbol": profile["symbol"],
                    "candles": profile["candles"],
                    "atr_pct": profile["atr_pct"],
                    "upper_wick_avg": profile["wick_ratio"]["upper_avg"],
                    "lower_wick_avg": profile["wick_ratio"]["lower_avg"],
                    "mean_reversion_setups": profile["mean_reversion_to_middle_bb"]["setups"],
                    "mean_reversion_win_rate": profile["mean_reversion_to_middle_bb"]["win_rate"],
                    "breakout_follow_through_rate": profile["breakout_follow_through_rate"],
                    "fakeout_rate": profile["fakeout_rate"],
                    "btc_correlation": profile["btc_correlation"],
                    "best_hour_utc": profile["best_session_hour"]["hour_utc"],
                }
            )


def main() -> int:
    parser = argparse.ArgumentParser(description="Offline 15m personality profiler")
    parser.add_argument("--symbols", default=",".join(BINANCE_SYMBOLS), help="Comma-separated symbols")
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument("--json-out", type=Path)
    parser.add_argument("--csv-out", type=Path)
    args = parser.parse_args()

    symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    btc_df = enrich_indicators(fetch_futures_klines("BTCUSDT", days=args.days))
    profiles = []
    for symbol in symbols:
        df = fetch_futures_klines(symbol, days=args.days)
        if df.empty:
            profiles.append({"symbol": normalize_binance_symbol(symbol), "error": "no candles"})
            continue
        profiles.append(profile_symbol(symbol, df, btc_df=btc_df))

    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(profiles, indent=2, default=str) + "\n")
    if args.csv_out:
        args.csv_out.parent.mkdir(parents=True, exist_ok=True)
        write_csv(args.csv_out, [p for p in profiles if not p.get("error")])
    if not args.json_out and not args.csv_out:
        print(json.dumps(profiles, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
