#!/usr/bin/env python3
"""
OZZYBOT — Weekly Parameter Optimizer & Alpha Recycle System
Queries trades database, compiles live performance vs fee-adjusted shadow benchmarks,
and auto-generates dynamic config tuning suggestions.
"""
import sys
import os
import sqlite3
import numpy as np
from datetime import datetime, timedelta

# Allow importing from project root
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import trade_db

# Terminal Colors
C_GREEN = "\033[92m"
C_RED = "\033[91m"
C_YELLOW = "\033[93m"
C_BLUE = "\033[94m"
C_BOLD = "\033[1m"
C_RESET = "\033[0m"

def get_stats(trades: list) -> dict:
    if not trades:
        return {"total": 0, "wins": 0, "losses": 0, "win_rate": 0.0, "net_pnl": 0.0, "profit_factor": 0.0, "avg_pnl": 0.0}
        
    pnl_list = [float(t["pnl"] or 0) for t in trades]
    total = len(trades)
    wins_list = [p for p in pnl_list if p > 0]
    losses_list = [p for p in pnl_list if p <= 0]
    
    wins = len(wins_list)
    losses = len(losses_list)
    win_rate = (wins / total) * 100.0 if total > 0 else 0.0
    net_pnl = sum(pnl_list)
    avg_pnl = net_pnl / total if total > 0 else 0.0
    
    sum_wins = sum(wins_list)
    sum_losses = abs(sum(losses_list))
    profit_factor = sum_wins / sum_losses if sum_losses > 0 else (sum_wins if sum_wins > 0 else 1.0)
    
    return {
        "total": total,
        "wins": wins,
        "losses": losses,
        "win_rate": win_rate,
        "net_pnl": net_pnl,
        "profit_factor": profit_factor,
        "avg_pnl": avg_pnl
    }

def print_metric_row(label: str, stats: dict, color_net: str):
    print(f"  {C_BOLD}{label}{C_RESET}")
    print(f"    ├─ Total Trades:  {stats['total']}")
    print(f"    ├─ Win Rate:      {C_BOLD}{stats['win_rate']:.1f}%{C_RESET} ({stats['wins']} W / {stats['losses']} L)")
    print(f"    ├─ Profit Factor: {C_BOLD}{stats['profit_factor']:.2f}{C_RESET}")
    print(f"    ├─ Avg PnL:       {color_net}${stats['avg_pnl']:.2f}{C_RESET}")
    print(f"    └─ Net Profit:    {color_net}${stats['net_pnl']:+.2f}{C_RESET}")

def main():
    db_path = sys.argv[1] if len(sys.argv) > 1 else "/home/rick/ozzy-bot/trades.db"
    if not os.path.exists(db_path):
        print(f"{C_RED}Error: trades.db not found at {db_path}{C_RESET}")
        return
        
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    
    # Query trades from last 30 days
    from datetime import UTC
    thirty_days_ago = (datetime.now(UTC) - timedelta(days=30)).strftime("%Y-%m-%d %H:%M:%S")
    
    # 1. Fetch Live/Paper standard trades
    cur = conn.execute(
        "SELECT * FROM trades WHERE ts >= ? AND execution_state IN ('closed', 'confirmed', 'entry_filled')",
        (thirty_days_ago,)
    )
    live_trades = [dict(r) for r in cur.fetchall()]
    
    # 2. Fetch Shadow (skipped) trades
    cur = conn.execute(
        "SELECT * FROM trades WHERE ts >= ? AND execution_state IN ('shadow_closed', 'shadow')",
        (thirty_days_ago,)
    )
    shadow_trades = [dict(r) for r in cur.fetchall()]
    
    conn.close()
    
    live_stats = get_stats(live_trades)
    shadow_stats = get_stats(shadow_trades)
    
    print("\n" + "="*58)
    print(f"⚡  {C_BOLD}OZZYBOT DYNAMIC ALPHA OPTIMIZATION REPORT{C_RESET}  ⚡")
    print("="*58)
    print(f"Analysis Period: Past 30 Days | Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("─"*58)
    
    live_color = C_GREEN if live_stats["net_pnl"] >= 0 else C_RED
    shadow_color = C_GREEN if shadow_stats["net_pnl"] >= 0 else C_RED
    
    print_metric_row("Standard Executed Trades (Live/Testnet)", live_stats, live_color)
    print()
    print_metric_row("Virtual Shadow Trades (Filtered/Skipped)", shadow_stats, shadow_color)
    print("─"*58)
    
    # 3. Formulate recommendations
    print(f"🎯 {C_BOLD}DECISION ENGINE RECOMMENDATION:{C_RESET}")
    
    if shadow_stats["total"] >= 3:
        if shadow_stats["win_rate"] >= 58.0 and shadow_stats["profit_factor"] >= 1.4:
            print(f"  {C_GREEN}🟢 OPPORTUNITY DETECTED — Loose Gating Rules!{C_RESET}")
            print("  Virtual shadow/Grade-C trades are highly profitable after fees & spread.")
            print(f"  {C_BOLD}Actionable suggestions for config/dynamic_config_testnet.json:{C_RESET}")
            print(f"    1. Set {C_BLUE}\"SETUP_GRADE_C_LIVE\": true{C_RESET} to harvest these setups.")
            print(f"    2. Loosen volume limits: decrease {C_BLUE}\"grade_a_volume_min\": 0.95{C_RESET}")
        elif live_stats["win_rate"] >= 50.0 and shadow_stats["win_rate"] < 40.0:
            print(f"  {C_BLUE}🔒 RISK FILTERS VALIDATED — Maintain strict rules!{C_RESET}")
            print("  Your live strategy is profitable, while shadow trades are heavily losing.")
            print("  The current dynamic filter system is doing its job perfectly to protect capital.")
            print(f"  {C_BOLD}Actionable suggestions:{C_RESET}")
            print(f"    • Keep live thresholds intact. Filters are currently in optimal state.")
        elif live_stats["win_rate"] < 45.0 and shadow_stats["win_rate"] < 45.0:
            print(f"  {C_RED}⚠️ WARNING — High Chop / Correlation Drawdown Regime!{C_RESET}")
            print("  Both live and shadow trades are experiencing high chop failure rates.")
            print(f"  {C_BOLD}Actionable suggestions for config/dynamic_config_testnet.json:{C_RESET}")
            print(f"    1. Tighten ADX trend strength: increase {C_BLUE}\"adx_threshold\": 30.0{C_RESET}")
            print(f"    2. Decrease risk allocation: set {C_BLUE}\"risk_multiplier_grade_b\": 0.35{C_RESET}")
        else:
            print(f"  {C_YELLOW}🟡 STABLE FLOW — No adjustments recommended.{C_RESET}")
            print("  Live and shadow distributions are aligned within normal variance bounds.")
            print("  Maintain current dynamic configurations and re-evaluate in 7 days.")
    else:
        print(f"  {C_YELLOW}🟡 INSUFFICIENT SHADOW DATA ({shadow_stats['total']}/3){C_RESET}")
        print("  System needs a larger sample size of virtual shadow trades to formulate an optimizer edge.")
        print("  Re-run this command once more shadow setups are captured and closed.")
        
    print("="*58 + "\n")

if __name__ == "__main__":
    main()
