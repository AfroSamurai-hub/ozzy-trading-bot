#!/usr/bin/env python3
"""Find per-symbol 1H strategy settings for Binance USD-M candidates.

This is research only. It fetches public futures candles and writes a report.
It does not touch live services or place orders.
"""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

from research_crypto_strategies import REPORT_DIR, StrategySpec, fetch_klines, run_strategy


def build_specs() -> list[StrategySpec]:
    """Build a focused 1H grid without exploding runtime."""
    specs: list[StrategySpec] = []
    modes = ["trend_pullback", "momentum", "pullback_reclaim"]
    side_modes = ["both", "long", "short"]
    st_settings = [(7, 2.2), (10, 3.0), (14, 3.5)]
    ema_lens = [100, 200]
    volume_mins = [0.75, 1.0, 1.2]
    atr_rr = [(1.2, 2.0), (1.5, 2.5), (2.0, 2.5), (2.5, 3.0)]
    rsi_bands = [(30, 70), (35, 75), (40, 65)]
    max_bars_options = [12, 18, 24, 36]

    for mode in modes:
        for side_mode in side_modes:
            for st_len, st_factor in st_settings:
                for ema_len in ema_lens:
                    for volume_min in volume_mins:
                        for atr_sl_mult, rr in atr_rr:
                            for rsi_min, rsi_max in rsi_bands:
                                for max_bars in max_bars_options:
                                    specs.append(
                                        StrategySpec(
                                            name=(
                                                f"{mode}_side-{side_mode}_st{st_len}x{st_factor}"
                                                f"_ema{ema_len}_vol{volume_min}_atr{atr_sl_mult}"
                                                f"_rr{rr}_rsi{rsi_min}-{rsi_max}_hold{max_bars}"
                                            ),
                                            timeframe="1h",
                                            days=180,
                                            st_len=st_len,
                                            st_factor=st_factor,
                                            ema_len=ema_len,
                                            rsi_min=rsi_min,
                                            rsi_max=rsi_max,
                                            volume_min=volume_min,
                                            atr_sl_mult=atr_sl_mult,
                                            rr=rr,
                                            max_bars=max_bars,
                                            mode=mode,
                                            side_mode=side_mode,
                                        )
                                    )
    return specs


def score(row: dict) -> tuple:
    """Rank robust candidates ahead of overfit small-sample outliers."""
    trade_penalty = 0 if row["trades"] >= 40 else -100
    dd_penalty = -1 if row["max_drawdown_pct"] > 25 else 0
    return (
        trade_penalty,
        dd_penalty,
        row["profit_factor"],
        row["return_pct"],
        row["trades"],
    )


def main() -> None:
    """Run per-symbol 1H optimization."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbols", default="ETHUSDT,LINKUSDT,SOLUSDT,SUIUSDT,HYPEUSDT")
    parser.add_argument("--top", type=int, default=8)
    args = parser.parse_args()

    symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    specs = build_specs()
    REPORT_DIR.mkdir(exist_ok=True)
    all_results = []
    top_by_symbol = {}

    for symbol in symbols:
        print(f"Fetching {symbol} 1h 180d")
        candles = fetch_klines(symbol, "1h", 180)
        symbol_results = []
        for idx, spec in enumerate(specs, 1):
            if idx % 250 == 0:
                print(f"  {symbol}: tested {idx}/{len(specs)}")
            result = run_strategy(symbol, candles, spec)
            symbol_results.append(result)
            all_results.append(result)
        ranked = sorted(symbol_results, key=score, reverse=True)
        top_by_symbol[symbol] = ranked[: args.top]

    path = REPORT_DIR / f"symbol_strategy_1h_optimization_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}.json"
    payload = {
        "generated_at": datetime.now(UTC).isoformat(),
        "symbols": symbols,
        "specs_tested_per_symbol": len(specs),
        "top_by_symbol": top_by_symbol,
    }
    path.write_text(json.dumps(payload, indent=2))

    print("\nBest 1H candidates by symbol")
    for symbol in symbols:
        print(f"\n{symbol}")
        print("pf return dd trades wr strategy")
        for row in top_by_symbol[symbol][: args.top]:
            print(
                row["profit_factor"],
                row["return_pct"],
                row["max_drawdown_pct"],
                row["trades"],
                row["win_rate"],
                row["strategy"],
            )
    print(f"\nReport: {path}")


if __name__ == "__main__":
    main()
