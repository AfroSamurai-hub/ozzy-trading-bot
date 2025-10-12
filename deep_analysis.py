#!/usr/bin/env python3
"""
OZZY Deep Analysis - Extract EVERY pattern from your trades
Find out EXACTLY what works and what doesn't
"""
from __future__ import annotations

import sqlite3
from contextlib import redirect_stdout
from io import StringIO
from typing import Dict, List, Optional

import numpy as np
import pandas as pd


DEFAULT_DB_PATH = "ozzy_simple.db"


class OzzyAnalyzer:
    def __init__(self, db_path: str = DEFAULT_DB_PATH):
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row

        self.trades = self._load_dataframe("trades")
        self.signals = self._load_dataframe("signals")

        self._ensure_columns()
        print(f"📊 Loaded {len(self.trades)} trades and {len(self.signals)} signals for analysis")

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _load_dataframe(self, table: str) -> pd.DataFrame:
        try:
            df = pd.read_sql_query(f"SELECT * FROM {table}", self.conn)
        except Exception:
            df = pd.DataFrame()
        return df

    def _ensure_columns(self) -> None:
        trade_defaults: Dict[str, object] = {
            "pnl": 0.0,
            "confidence": 0.0,
            "rsi": 50.0,
            "timestamp": None,
            "quality": "",
            "volatility": np.nan,
        }
        signal_defaults: Dict[str, object] = {
            "signal": "",
            "quality": "",
        }

        if self.trades.empty:
            self.trades = pd.DataFrame([{k: v for k, v in trade_defaults.items()}])
            self.trades = self.trades.iloc[0:0]  # keep schema but no rows
        else:
            for col, default in trade_defaults.items():
                if col not in self.trades.columns:
                    self.trades[col] = default
            if "signal" not in self.trades.columns:
                if "side" in self.trades.columns:
                    self.trades["signal"] = self.trades["side"]
                else:
                    self.trades["signal"] = ""
            self.trades["pnl"] = pd.to_numeric(self.trades["pnl"], errors="coerce").fillna(0.0)
            self.trades["confidence"] = pd.to_numeric(self.trades["confidence"], errors="coerce").fillna(0.0)
            if "timestamp" in self.trades.columns:
                self.trades["timestamp"] = self.trades["timestamp"].fillna("1970-01-01 00:00:00")
            else:
                self.trades["timestamp"] = "1970-01-01 00:00:00"
            self.trades["signal"] = self.trades["signal"].fillna("").astype(str)

        if self.signals.empty:
            self.signals = pd.DataFrame([{k: v for k, v in signal_defaults.items()}])
            self.signals = self.signals.iloc[0:0]
        else:
            for col, default in signal_defaults.items():
                if col not in self.signals.columns:
                    self.signals[col] = default

    def close(self) -> None:
        try:
            if self.conn:
                self.conn.close()
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Analyses
    # ------------------------------------------------------------------
    def confidence_deep_dive(self) -> None:
        """What confidence levels ACTUALLY work?"""
        print("\n" + "=" * 60)
        print("🎯 CONFIDENCE ANALYSIS - Finding Your Sweet Spot")
        print("=" * 60)

        if self.trades.empty:
            print("No trades data available.")
            return

        for conf_min in range(30, 95, 5):
            conf_max = conf_min + 5
            bucket_trades = self.trades[
                (self.trades["confidence"] >= conf_min)
                & (self.trades["confidence"] < conf_max)
            ]

            if len(bucket_trades) == 0:
                continue

            wins = (bucket_trades["pnl"] > 0).sum()
            losses = (bucket_trades["pnl"] <= 0).sum()
            win_rate = (wins / len(bucket_trades)) * 100 if len(bucket_trades) else 0
            avg_win = (
                bucket_trades[bucket_trades["pnl"] > 0]["pnl"].mean()
                if wins > 0
                else 0
            )
            avg_loss = (
                abs(bucket_trades[bucket_trades["pnl"] <= 0]["pnl"].mean())
                if losses > 0
                else 0
            )
            if losses > 0 and avg_loss > 0:
                profit_factor = (avg_win * wins) / (avg_loss * losses) if avg_loss else float("inf")
            else:
                profit_factor = float("inf")
            total_pnl = bucket_trades["pnl"].sum()

            if win_rate > 60 and profit_factor > 1.5:
                status = "🔥 HOT ZONE"
            elif win_rate > 50:
                status = "✅ Profitable"
            else:
                status = "⚠️  Avoid"

            print(f"\nConfidence {conf_min}-{conf_max}%: {status}")
            print(f"  Trades: {len(bucket_trades):3d} | Wins: {wins:3d} | Losses: {losses:3d}")
            print(
                f"  Win Rate: {win_rate:.1f}% | Avg Win: R{avg_win:.2f} | Avg Loss: R{avg_loss:.2f}"
            )
            pf_display = profit_factor if profit_factor != float("inf") else float("nan")
            print(f"  Profit Factor: {pf_display:.2f} | Total P&L: R{total_pnl:.2f}")

        best_threshold: Optional[int] = None
        best_score = -np.inf

        for threshold in range(35, 80):
            above_threshold = self.trades[self.trades["confidence"] >= threshold]
            if len(above_threshold) < 10:
                continue

            win_rate = (above_threshold["pnl"] > 0).mean()
            avg_pnl = above_threshold["pnl"].mean()
            score = win_rate * avg_pnl * np.sqrt(len(above_threshold))

            if score > best_score:
                best_score = score
                best_threshold = threshold

        print(f"\n🎯 OPTIMAL MIN_CONFIDENCE: {best_threshold}%")

    def rsi_analysis(self) -> None:
        """What RSI levels actually predict wins?"""
        print("\n" + "=" * 60)
        print("📈 RSI ANALYSIS - Finding Real Oversold/Overbought")
        print("=" * 60)

        if self.trades.empty:
            print("No trades data available.")
            return

        long_trades = self.trades[self.trades["signal"].str.upper() == "LONG"]
        short_trades = self.trades[self.trades["signal"].str.upper() == "SHORT"]

        if len(long_trades) > 0:
            winning_longs = long_trades[long_trades["pnl"] > 0]
            losing_longs = long_trades[long_trades["pnl"] <= 0]

            print("\n🟢 LONG TRADES:")
            if len(winning_longs) > 0:
                print(
                    f"  Winning RSI range: {winning_longs['rsi'].min():.1f} - {winning_longs['rsi'].max():.1f}"
                )
                print(f"  Winning RSI average: {winning_longs['rsi'].mean():.1f}")
            if len(losing_longs) > 0:
                print(f"  Losing RSI average: {losing_longs['rsi'].mean():.1f}")

            best_rsi_long = 30
            best_long_score = -np.inf

            for rsi_threshold in range(20, 45):
                triggered = long_trades[long_trades["rsi"] <= rsi_threshold]
                if len(triggered) < 5:
                    continue
                win_rate = (triggered["pnl"] > 0).mean()
                avg_pnl = triggered["pnl"].mean()
                score = win_rate * avg_pnl
                if score > best_long_score:
                    best_long_score = score
                    best_rsi_long = rsi_threshold

            print(f"  🎯 Optimal RSI oversold trigger: {best_rsi_long}")

        if len(short_trades) > 0:
            winning_shorts = short_trades[short_trades["pnl"] > 0]
            losing_shorts = short_trades[short_trades["pnl"] <= 0]

            print("\n🔴 SHORT TRADES:")
            if len(winning_shorts) > 0:
                print(
                    f"  Winning RSI range: {winning_shorts['rsi'].min():.1f} - {winning_shorts['rsi'].max():.1f}"
                )
                print(f"  Winning RSI average: {winning_shorts['rsi'].mean():.1f}")
            if len(losing_shorts) > 0:
                print(f"  Losing RSI average: {losing_shorts['rsi'].mean():.1f}")

            best_rsi_short = 70
            best_short_score = -np.inf

            for rsi_threshold in range(55, 80):
                triggered = short_trades[short_trades["rsi"] >= rsi_threshold]
                if len(triggered) < 5:
                    continue
                win_rate = (triggered["pnl"] > 0).mean()
                avg_pnl = triggered["pnl"].mean()
                score = win_rate * avg_pnl
                if score > best_short_score:
                    best_short_score = score
                    best_rsi_short = rsi_threshold

            print(f"  🎯 Optimal RSI overbought trigger: {best_rsi_short}")

    def time_pattern_analysis(self) -> None:
        """When are you most profitable?"""
        print("\n" + "=" * 60)
        print("⏰ TIME ANALYSIS - When Should You Trade?")
        print("=" * 60)

        if self.trades.empty:
            print("No trades data available.")
            return

        self.trades["datetime"] = pd.to_datetime(self.trades["timestamp"], errors="coerce")
        self.trades["hour"] = self.trades["datetime"].dt.hour
        self.trades["day_of_week"] = self.trades["datetime"].dt.dayofweek
        self.trades["day_name"] = self.trades["datetime"].dt.day_name()

        print("\n📊 HOURLY PERFORMANCE:")
        hourly = self.trades.groupby("hour").agg(
            Trades=("pnl", "count"),
            Avg_PnL=("pnl", "mean"),
            Total_PnL=("pnl", "sum"),
            pct_longs=("signal", lambda x: (x.str.upper() == "LONG").mean() * 100),
        )
        hourly = hourly.round(2)
        hourly = hourly.sort_values("Avg_PnL", ascending=False)

        print("\n🔥 BEST HOURS TO TRADE:")
        print(hourly.head(5))

        print("\n❌ WORST HOURS TO AVOID:")
        print(hourly.tail(5))

        print("\n📅 DAILY PERFORMANCE:")
        daily = self.trades.groupby("day_name").agg(
            Trades=("pnl", "count"),
            Avg_PnL=("pnl", "mean"),
            Total_PnL=("pnl", "sum"),
        )
        daily = daily.round(2)
        print(daily.sort_values("Avg_PnL", ascending=False))

    def signal_quality_analysis(self) -> None:
        """How good are your signals really?"""
        print("\n" + "=" * 60)
        print("🎯 SIGNAL QUALITY - How Many Signals Convert to Profits?")
        print("=" * 60)

        if self.signals.empty:
            print("No signal data available.")
            return

        signal_dist = self.signals["signal"].value_counts()
        print(f"\n📊 Total Signals Generated: {len(self.signals)}")
        print(f"  LONGs: {signal_dist.get('LONG', 0)}")
        print(f"  SHORTs: {signal_dist.get('SHORT', 0)}")
        print(f"  HOLDs: {signal_dist.get('HOLD', 0)}")

        actionable_signals = self.signals[self.signals["signal"] != "HOLD"]
        if len(actionable_signals) > 0:
            execution_rate = (len(self.trades) / len(actionable_signals)) * 100
            print(f"\n📈 Signal Execution Rate: {execution_rate:.1f}%")

            for quality in ["PREMIUM", "GOOD", "MODERATE", "POOR"]:
                quality_signals = self.signals[self.signals["quality"] == quality]
                if len(quality_signals) == 0:
                    continue

                if "quality" in self.trades.columns:
                    quality_trades = self.trades[self.trades["quality"] == quality]
                else:
                    quality_trades = pd.DataFrame()

                print(f"\n{quality} Signals:")
                print(f"  Count: {len(quality_signals)} | Executed: {len(quality_trades)}")
                if len(quality_trades) > 0:
                    win_rate = (quality_trades["pnl"] > 0).mean() * 100
                    avg_pnl = quality_trades["pnl"].mean()
                    print(f"  Win Rate: {win_rate:.1f}% | Avg P&L: R{avg_pnl:.2f}")

    def drawdown_analysis(self) -> None:
        """What's your risk profile?"""
        print("\n" + "=" * 60)
        print("📉 DRAWDOWN ANALYSIS - Understanding Your Risk")
        print("=" * 60)

        if self.trades.empty:
            print("No trades data available.")
            return

        self.trades = self.trades.sort_values("timestamp")
        self.trades["cumulative_pnl"] = self.trades["pnl"].cumsum()
        self.trades["running_peak"] = self.trades["cumulative_pnl"].cummax()
        self.trades["drawdown"] = self.trades["cumulative_pnl"] - self.trades["running_peak"]
        self.trades["drawdown_pct"] = (self.trades["drawdown"] / 10000) * 100

        max_drawdown = self.trades["drawdown"].min()
        max_drawdown_pct = self.trades["drawdown_pct"].min()

        print(f"\n💀 Maximum Drawdown: R{abs(max_drawdown):.2f} ({abs(max_drawdown_pct):.1f}%)")

        self.trades["is_loss"] = self.trades["pnl"] < 0
        self.trades["loss_streak"] = (
            self.trades["is_loss"].groupby((~self.trades["is_loss"]).cumsum()).cumsum()
        )
        max_losing_streak = self.trades["loss_streak"].max()
        print(f"📊 Longest Losing Streak: {int(max_losing_streak)} trades")

        drawdown_periods: List[int] = []
        in_drawdown = False
        start_idx: Optional[int] = None

        for idx, row in self.trades.iterrows():
            if row["drawdown"] < 0 and not in_drawdown:
                in_drawdown = True
                start_idx = idx
            elif row["drawdown"] == 0 and in_drawdown:
                in_drawdown = False
                if start_idx is not None:
                    recovery_trades = idx - start_idx
                    drawdown_periods.append(recovery_trades)

        if drawdown_periods:
            avg_recovery = float(np.mean(drawdown_periods))
            print(f"⏱️  Average Recovery Time: {avg_recovery:.1f} trades")

    def generate_confidence_requirements(self) -> None:
        """What do you need to see before going live?"""
        print("\n" + "=" * 60)
        print("🎯 CONFIDENCE CHECKLIST - What You Need for Live Trading")
        print("=" * 60)

        requirements = {
            "trades_needed": 200,
            "min_win_rate": 55,
            "min_profit_factor": 1.5,
            "max_drawdown": 15,
            "min_sample_per_setup": 20,
        }

        current_trades = len(self.trades)
        current_win_rate = (
            (self.trades["pnl"] > 0).mean() * 100 if current_trades > 0 else 0
        )

        wins = self.trades[self.trades["pnl"] > 0]
        losses = self.trades[self.trades["pnl"] <= 0]

        if len(losses) > 0 and losses["pnl"].sum() != 0 and len(wins) > 0:
            profit_factor = wins["pnl"].sum() / abs(losses["pnl"].sum())
        else:
            profit_factor = 0

        if "drawdown_pct" in self.trades.columns and not self.trades.empty:
            max_dd_pct = abs(self.trades["drawdown_pct"].min())
        else:
            max_dd_pct = 0

        print("\n📊 CURRENT vs REQUIRED:")
        print(
            f"  Trades: {current_trades}/{requirements['trades_needed']} "
            f"{'✅' if current_trades >= requirements['trades_needed'] else '❌'}"
        )
        print(
            f"  Win Rate: {current_win_rate:.1f}%/{requirements['min_win_rate']}% "
            f"{'✅' if current_win_rate >= requirements['min_win_rate'] else '❌'}"
        )
        print(
            f"  Profit Factor: {profit_factor:.2f}/{requirements['min_profit_factor']} "
            f"{'✅' if profit_factor >= requirements['min_profit_factor'] else '❌'}"
        )
        print(
            f"  Max Drawdown: {max_dd_pct:.1f}%/{requirements['max_drawdown']}% "
            f"{'✅' if max_dd_pct <= requirements['max_drawdown'] else '⚠️'}"
        )

        print("\n🎯 DATA GAPS TO FILL:")

        long_count = len(self.trades[self.trades["signal"].str.upper() == "LONG"])
        short_count = len(self.trades[self.trades["signal"].str.upper() == "SHORT"])

        if long_count < 50:
            print(f"  ❌ Need {50 - long_count} more LONG trades (have {long_count})")
        if short_count < 50:
            print(f"  ❌ Need {50 - short_count} more SHORT trades (have {short_count})")

        if "volatility" in self.trades.columns:
            high_vol_trades = len(
                self.trades[self.trades["volatility"] > self.trades["volatility"].median()]
            )
            if high_vol_trades < 30:
                print(f"  ❌ Need {30 - high_vol_trades} more high volatility trades")

        trades_per_day = current_trades / 7 if current_trades > 0 else 10
        trades_needed = max(0, requirements["trades_needed"] - current_trades)
        days_needed = trades_needed / trades_per_day if trades_per_day else float("inf")

        print(f"\n⏰ ESTIMATED TIME TO CONFIDENCE: {days_needed:.1f} more days of trading")

    def export_optimal_config(self) -> Dict[str, object]:
        """Generate the perfect config based on data"""
        print("\n" + "=" * 60)
        print("🔧 OPTIMAL CONFIGURATION")
        print("=" * 60)

        if self.trades.empty:
            print("No trades available to compute optimal config.")
            return {}

        winning_trades = self.trades[self.trades["pnl"] > 0]

        config = {
            "MIN_CONFIDENCE": int(
                np.nan_to_num(
                    self.trades[self.trades["pnl"] > 0]["confidence"].quantile(0.3),
                    nan=40,
                )
            ),
            "RSI_OVERSOLD": int(
                winning_trades[winning_trades["signal"].str.upper() == "LONG"]["rsi"].mean()
            )
            if len(winning_trades[winning_trades["signal"].str.upper() == "LONG"]) > 0
            else 30,
            "RSI_OVERBOUGHT": int(
                winning_trades[winning_trades["signal"].str.upper() == "SHORT"]["rsi"].mean()
            )
            if len(winning_trades[winning_trades["signal"].str.upper() == "SHORT"]) > 0
            else 70,
            "VOLUME_MULTIPLIER": 1.5,
            "RISK_PER_TRADE": 0.02,
            "DAILY_LOSS_LIMIT": 0.05,
            "MAX_POSITIONS": 3,
        }

        print("\n# Add this to your config.py:")
        print("OPTIMAL_CONFIG = {")
        for key, value in config.items():
            print(f"    '{key}': {value},")
        print("}")

        return config

    def run_full_analysis(self) -> Dict[str, object]:
        self.confidence_deep_dive()
        self.rsi_analysis()
        self.time_pattern_analysis()
        self.signal_quality_analysis()
        self.drawdown_analysis()
        self.generate_confidence_requirements()
        optimal_config = self.export_optimal_config()

        print("\n" + "=" * 60)
        print("📊 EXECUTIVE SUMMARY")
        print("=" * 60)

        total_pnl = self.trades["pnl"].sum()
        win_rate = (self.trades["pnl"] > 0).mean() * 100 if len(self.trades) > 0 else 0
        avg_win = (
            self.trades[self.trades["pnl"] > 0]["pnl"].mean()
            if len(self.trades[self.trades["pnl"] > 0]) > 0
            else 0
        )
        avg_loss = (
            abs(self.trades[self.trades["pnl"] < 0]["pnl"].mean())
            if len(self.trades[self.trades["pnl"] < 0]) > 0
            else 0
        )

        print(f"\n💰 Total P&L: R{total_pnl:.2f}")
        print(f"📈 Win Rate: {win_rate:.1f}%")
        print(f"✅ Average Win: R{avg_win:.2f}")
        print(f"❌ Average Loss: R{avg_loss:.2f}")
        if avg_loss > 0:
            print(f"📊 Risk/Reward Ratio: {avg_win / avg_loss:.2f}")

        confidence_score = 0
        if len(self.trades) >= 100:
            confidence_score += 25
        if win_rate >= 60:
            confidence_score += 25
        if total_pnl > 2000:
            confidence_score += 25
        if avg_loss > 0 and (avg_win / avg_loss) > 1.5:
            confidence_score += 25

        print(f"\n🎯 CONFIDENCE SCORE: {confidence_score}/100")

        if confidence_score >= 75:
            print("✅ READY FOR LIVE TRADING with small capital")
        elif confidence_score >= 50:
            print("⚠️  ALMOST READY - Need more consistent results")
        else:
            print("❌ NOT READY - Keep paper trading and optimizing")

        return optimal_config


if __name__ == "__main__":
    analyzer = OzzyAnalyzer()
    buffer = StringIO()

    with redirect_stdout(buffer):
        analyzer.run_full_analysis()

    report = buffer.getvalue()
    print(report)

    with open("analysis_report.md", "w", encoding="utf-8") as f:
        f.write(report)

    analyzer.close()
    print("\n📄 Full analysis saved to analysis_report.md")
