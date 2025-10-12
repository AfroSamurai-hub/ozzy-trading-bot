#!/usr/bin/env python3
"""
TURBO MODE - Generate 200+ trades in 48 hours
Run multiple strategies in parallel to find what works
"""
from __future__ import annotations

import argparse
import os
import sqlite3
import sys
import time
from datetime import datetime, timezone
from typing import Dict, Iterable, List, Optional

# Ensure project root on path when script executed from nested directories
ROOT_DIR = os.path.abspath(os.path.dirname(__file__))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

import config
import db
from scripts.simulate_end_to_end import simulate_trades

STRATEGY_VARIANTS: List[Dict[str, int]] = [
    {"name": "Conservative", "min_conf": 60, "rsi_os": 25, "rsi_ob": 75},
    {"name": "Aggressive", "min_conf": 35, "rsi_os": 35, "rsi_ob": 65},
    {"name": "Balanced", "min_conf": 45, "rsi_os": 30, "rsi_ob": 70},
    {"name": "Momentum", "min_conf": 40, "rsi_os": 40, "rsi_ob": 60},
    {"name": "Contrarian", "min_conf": 50, "rsi_os": 20, "rsi_ob": 80},
]


def _set_variant_config(variant: Dict[str, int]) -> Dict[str, int]:
    saved = {
        "MIN_CONFIDENCE": getattr(config, "MIN_CONFIDENCE", 45),
        "RSI_OVERSOLD": getattr(config, "RSI_OVERSOLD", 30),
        "RSI_OVERBOUGHT": getattr(config, "RSI_OVERBOUGHT", 70),
    }

    config.MIN_CONFIDENCE = variant["min_conf"]
    config.RSI_OVERSOLD = variant["rsi_os"]
    config.RSI_OVERBOUGHT = variant["rsi_ob"]
    return saved


def _restore_config(saved: Dict[str, int]) -> None:
    for key, value in saved.items():
        setattr(config, key, value)


def _tag_trades(conn: sqlite3.Connection, trade_ids: Iterable[int], variant_name: str, run_label: str) -> None:
    cur = conn.cursor()
    for trade_id in trade_ids:
        cur.execute("SELECT entry_reason FROM trades WHERE id = ?", (trade_id,))
        row = cur.fetchone()
        entry_reason = row[0] if row else ""
        suffix = f"strategy: {variant_name} ({run_label})"
        if entry_reason:
            new_reason = f"{entry_reason} | {suffix}"
        else:
            new_reason = suffix
        cur.execute(
            "UPDATE trades SET entry_reason = ?, exit_reason = ? WHERE id = ?",
            (new_reason, f"TURBO:{variant_name}", trade_id),
        )
    conn.commit()


def _summarize_trades(conn: sqlite3.Connection, trade_ids: Iterable[int]) -> Dict[str, float]:
    trade_ids = list(trade_ids)
    if not trade_ids:
        return {"count": 0, "wins": 0, "losses": 0, "win_rate": 0.0, "total_pnl": 0.0, "avg_pnl": 0.0}

    placeholders = ",".join(["?"] * len(trade_ids))
    cur = conn.cursor()
    cur.execute(
        f"""
        SELECT
            COUNT(*) AS count,
            SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) AS wins,
            SUM(CASE WHEN pnl <= 0 THEN 1 ELSE 0 END) AS losses,
            SUM(pnl) AS total_pnl,
            AVG(pnl) AS avg_pnl
        FROM trades
        WHERE id IN ({placeholders})
        """,
        trade_ids,
    )
    row = cur.fetchone()
    count = row[0] or 0
    wins = row[1] or 0
    losses = row[2] or 0
    total_pnl = row[3] or 0.0
    avg_pnl = row[4] or 0.0
    win_rate = (wins / count * 100) if count else 0.0
    return {
        "count": int(count),
        "wins": int(wins),
        "losses": int(losses),
        "win_rate": float(win_rate),
        "total_pnl": float(total_pnl),
        "avg_pnl": float(avg_pnl),
    }


def run_variant(variant: Dict[str, int], per_symbol: int, rounds: int, cooldown: float = 1.0, force_short_bias: bool = False) -> Dict[str, object]:
    print("\n" + "=" * 70)
    print(f"🚀 Running TURBO variant: {variant['name']}")
    if force_short_bias:
        print("⚡ SHORT BIAS ENABLED - Prioritizing SHORT trades")
    print("=" * 70)

    saved = _set_variant_config(variant)
    db.create_tables()
    conn = sqlite3.connect(db.DB_PATH)
    
    # Check current balance
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM trades WHERE side='LONG'")
    long_count = cur.fetchone()[0] or 0
    cur.execute("SELECT COUNT(*) FROM trades WHERE side='SHORT'")
    short_count = cur.fetchone()[0] or 0
    
    if force_short_bias or (short_count < long_count * 0.6):
        # Apply SHORT bias to config
        print(f"  Current balance: {long_count} LONGs, {short_count} SHORTs")
        print(f"  Adjusting RSI thresholds to favor SHORTs...")
        config.RSI_OVERBOUGHT = min(60, variant["rsi_ob"] - 5)  # Easier to trigger SHORTs
        config.RSI_OVERSOLD = max(20, variant["rsi_os"] + 5)    # Harder to trigger LONGs

    collected_ids: List[int] = []
    try:
        for round_idx in range(rounds):
            print(f"\n▶️  Round {round_idx + 1}/{rounds} for {variant['name']}")
            run_label = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
            inserted = simulate_trades(per_symbol=per_symbol)
            trade_ids = [trade_id for trade_id, *_ in inserted]
            collected_ids.extend(trade_ids)
            _tag_trades(conn, trade_ids, variant["name"], run_label)

            summary = _summarize_trades(conn, trade_ids)
            print(
                f"  Trades this round: {summary['count']} | Win Rate: {summary['win_rate']:.1f}% | Total P&L: R{summary['total_pnl']:.2f}"
            )

            if round_idx < rounds - 1 and cooldown > 0:
                time.sleep(cooldown)
    finally:
        _restore_config(saved)
        conn.close()

    return {
        "variant": variant["name"],
        "trade_ids": collected_ids,
    }


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Turbo Mode data generator")
    parser.add_argument("--per-symbol", type=int, default=4, help="Trades simulated per symbol per round")
    parser.add_argument("--rounds", type=int, default=3, help="How many cycles to run per strategy variant")
    parser.add_argument("--cooldown", type=float, default=0.5, help="Seconds to sleep between rounds (default: 0.5)")
    parser.add_argument(
        "--variants",
        nargs="*",
        help="Optional list of variant names to run (default: all)",
    )
    parser.add_argument(
        "--short-bias",
        action="store_true",
        help="Force SHORT bias to balance LONG/SHORT ratio",
    )
    parser.add_argument(
        "--fast",
        action="store_true",
        help="Maximum speed mode (no cooldown, reduced logging)",
    )
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> None:
    args = parse_args(argv)
    
    # Fast mode optimizations
    cooldown = 0.0 if args.fast else args.cooldown

    selected = [v for v in STRATEGY_VARIANTS if not args.variants or v["name"] in args.variants]
    if not selected:
        print("No matching strategy variants; exiting.")
        return

    conn = sqlite3.connect(db.DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM trades")
    before_count = cur.fetchone()[0] or 0
    conn.close()

    print(f"\n🚀 TURBO MODE - Starting with {before_count} trades")
    if args.fast:
        print("⚡ FAST MODE ENABLED - Maximum speed!")
    if args.short_bias:
        print("🎯 SHORT BIAS ENABLED - Balancing LONG/SHORT ratio")

    overall_results: List[Dict[str, object]] = []

    for variant in selected:
        result = run_variant(
            variant, 
            per_symbol=args.per_symbol, 
            rounds=args.rounds, 
            cooldown=cooldown,
            force_short_bias=args.short_bias
        )
        overall_results.append(result)

    conn = sqlite3.connect(db.DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM trades")
    after_count = cur.fetchone()[0] or 0

    print("\n" + "=" * 70)
    print("📊 TURBO MODE SUMMARY")
    print("=" * 70)
    print(f"Total trades before: {before_count}")
    print(f"Total trades after:  {after_count}")
    print(f"Net new trades:     {after_count - before_count}")

    for result in overall_results:
        summary = _summarize_trades(conn, result["trade_ids"])
        print(
            f"\n{result['variant']}: {summary['count']} trades | Wins: {summary['wins']} | Losses: {summary['losses']} | "
            f"Win Rate: {summary['win_rate']:.1f}% | Total P&L: R{summary['total_pnl']:.2f} | Avg P&L: R{summary['avg_pnl']:.2f}"
        )

    conn.close()
    print("\n✅ Turbo mode complete!")


if __name__ == "__main__":
    main()
