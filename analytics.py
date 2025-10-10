"""
analytics.py

Compute live performance metrics from trades.csv and print a real-time report.

Metrics:
 - Sharpe ratio (annualized using trade frequency)
 - Maximum drawdown (based on cumulative equity from starting capital)
 - Win rate by confidence buckets
 - Best and worst performing hours
 - Average trade duration
 - Risk/Reward ratios

Usage:
    python analytics.py           # print a single report
    python analytics.py --watch 10  # refresh every 10 seconds
"""
from __future__ import annotations
import csv
import math
import time
from datetime import datetime
from statistics import mean, stdev
from typing import List, Dict, Any, Optional, Tuple
import config
import os

TRADES_CSV = "trades.csv"


def read_trades(csv_path: str = TRADES_CSV) -> List[Dict[str, Any]]:
    if not os.path.exists(csv_path):
        return []

    rows: List[Dict[str, Any]] = []
    with open(csv_path, newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for r in reader:
            # Normalize fields
            try:
                r['entry_timestamp'] = r.get('entry_timestamp') or r.get('timestamp')
                r['exit_timestamp'] = r.get('exit_timestamp')
                # numeric fields
                r['entry_price'] = float(r['entry_price']) if r.get('entry_price') not in (None, '', 'None') else None
                r['exit_price'] = float(r['exit_price']) if r.get('exit_price') not in (None, '', 'None') else None
                r['position_size'] = float(r['position_size']) if r.get('position_size') not in (None, '', 'None') else 0.0
                r['position_value'] = float(r['position_value']) if r.get('position_value') not in (None, '', 'None') else 0.0
                r['pnl'] = float(r['pnl']) if r.get('pnl') not in (None, '', 'None') else 0.0
                r['duration_seconds'] = int(r['duration_seconds']) if r.get('duration_seconds') not in (None, '', 'None') else None
                r['confidence'] = float(r['confidence']) if r.get('confidence') not in (None, '', 'None') else 0.0
            except Exception:
                # best-effort parsing
                pass

            # parse timestamps to datetime when possible
            try:
                if r.get('entry_timestamp'):
                    r['_entry_dt'] = datetime.fromisoformat(r['entry_timestamp']) if 'T' in r['entry_timestamp'] else datetime.strptime(r['entry_timestamp'], '%Y-%m-%d %H:%M:%S')
                else:
                    r['_entry_dt'] = None
            except Exception:
                r['_entry_dt'] = None

            try:
                if r.get('exit_timestamp'):
                    r['_exit_dt'] = datetime.fromisoformat(r['exit_timestamp']) if 'T' in r['exit_timestamp'] else datetime.strptime(r['exit_timestamp'], '%Y-%m-%d %H:%M:%S')
                else:
                    r['_exit_dt'] = None
            except Exception:
                r['_exit_dt'] = None

            rows.append(r)
    return rows


def sharpe_ratio(trades: List[Dict[str, Any]]) -> Optional[float]:
    # Use per-trade returns: pnl / position_value
    returns = []
    for t in trades:
        pv = t.get('position_value')
        pnl = t.get('pnl', 0.0)
        if pv and pv != 0:
            returns.append(pnl / pv)

    if not returns:
        return None

    mean_r = mean(returns)
    sd = stdev(returns) if len(returns) > 1 else 0.0

    # Estimate trades per year from timestamp span
    dates = [t.get('_exit_dt') or t.get('_entry_dt') for t in trades if (t.get('_exit_dt') or t.get('_entry_dt'))]
    if not dates:
        return None
    span_days = (max(dates) - min(dates)).days or 1
    trades_per_year = max(len(trades) / span_days * 252, 1)

    if sd == 0:
        return None

    sr = (mean_r / sd) * math.sqrt(trades_per_year)
    return sr


def max_drawdown(trades: List[Dict[str, Any]], starting_capital: float = None) -> Optional[Tuple[float, float]]:
    if starting_capital is None:
        starting_capital = getattr(config, 'STARTING_CAPITAL', 10000.0)

    # Build equity curve by sorting trades by exit time
    trades_sorted = sorted([t for t in trades if t.get('_exit_dt')], key=lambda x: x['_exit_dt'])
    equity = starting_capital
    peak = equity
    max_dd = 0.0
    max_dd_pct = 0.0

    for t in trades_sorted:
        pnl = t.get('pnl', 0.0) or 0.0
        equity += pnl
        if equity > peak:
            peak = equity
        dd = peak - equity
        dd_pct = dd / peak if peak != 0 else 0.0
        if dd > max_dd:
            max_dd = dd
            max_dd_pct = dd_pct

    return (round(max_dd, 6), round(max_dd_pct * 100, 4))


def win_rate_by_confidence(trades: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    # Buckets: 0-20,20-40,40-60,60-80,80-100
    buckets = [(0,20),(20,40),(40,60),(60,80),(80,100)]
    result = {}
    for low, high in buckets:
        key = f"{low}-{high}"
        subset = [t for t in trades if t.get('confidence') is not None and low <= t.get('confidence',0) < high]
        wins = [t for t in subset if t.get('pnl',0) > 0]
        result[key] = {
            'trades': len(subset),
            'wins': len(wins),
            'win_rate_pct': round((len(wins)/len(subset)*100) if subset else 0.0, 2)
        }
    return result


def best_worst_hours(trades: List[Dict[str, Any]]) -> Tuple[List[Tuple[int, float]], List[Tuple[int, float]]]:
    # Compute average pnl per exit hour
    hour_map: Dict[int, List[float]] = {}
    for t in trades:
        dt = t.get('_exit_dt') or t.get('_entry_dt')
        if not dt:
            continue
        hr = dt.hour
        hour_map.setdefault(hr, []).append(t.get('pnl', 0.0))

    avg_by_hour = [(hr, mean(vals)) for hr, vals in hour_map.items() if vals]
    if not avg_by_hour:
        return ([], [])

    sorted_by_perf = sorted(avg_by_hour, key=lambda x: x[1], reverse=True)
    best = sorted_by_perf[:3]
    worst = sorted_by_perf[-3:]
    return best, worst


def average_trade_duration(trades: List[Dict[str, Any]]) -> Optional[float]:
    durations = [t.get('duration_seconds') for t in trades if t.get('duration_seconds')]
    if not durations:
        return None
    avg_seconds = mean(durations)
    return avg_seconds


def risk_reward(trades: List[Dict[str, Any]]) -> Dict[str, Any]:
    winners = [t.get('pnl') for t in trades if t.get('pnl',0) > 0]
    losers = [t.get('pnl') for t in trades if t.get('pnl',0) < 0]
    avg_win = mean(winners) if winners else 0.0
    avg_loss = mean(losers) if losers else 0.0
    rr = (avg_win / abs(avg_loss)) if (avg_loss != 0) else None
    return {
        'avg_win': round(avg_win,6),
        'avg_loss': round(avg_loss,6),
        'risk_reward': round(rr,4) if rr is not None else None,
        'wins': len(winners),
        'losses': len(losers)
    }


def print_report(trades: List[Dict[str, Any]]):
    total = len(trades)
    print(f"\nPerformance Report — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*60)
    print(f"Total completed trades: {total}")

    sr = sharpe_ratio(trades)
    print(f"Sharpe Ratio (ann.): {sr:.4f}" if sr is not None else "Sharpe Ratio: N/A")

    dd, dd_pct = max_drawdown(trades)
    print(f"Max Drawdown: R{dd:.2f} ({dd_pct:.2f}%)")

    wr = win_rate_by_confidence(trades)
    print("\nWin rate by confidence buckets:")
    for k, v in wr.items():
        print(f"  {k}: trades={v['trades']} wins={v['wins']} win_rate={v['win_rate_pct']}%")

    best, worst = best_worst_hours(trades)
    print("\nBest hours (hour, avg pnl):", best)
    print("Worst hours (hour, avg pnl):", worst)

    avg_dur = average_trade_duration(trades)
    if avg_dur is not None:
        print(f"\nAverage trade duration: {avg_dur/60:.2f} minutes")
    else:
        print("Average trade duration: N/A")

    rr = risk_reward(trades)
    print(f"\nRisk/Reward: avg_win={rr['avg_win']}, avg_loss={rr['avg_loss']}, R:R={rr['risk_reward']}")

    # Equity curve basic summary
    starting = getattr(config, 'STARTING_CAPITAL', 10000.0)
    equity = starting
    eq_curve = []
    for t in sorted([x for x in trades if x.get('_exit_dt')], key=lambda x: x['_exit_dt']):
        equity += t.get('pnl', 0.0)
        eq_curve.append(equity)

    if eq_curve:
        print(f"\nFinal equity: R{eq_curve[-1]:,.2f} (start R{starting:,.2f})")
    print("="*60 + "\n")


def main(watch: Optional[int] = None):
    last_mtime = None
    while True:
        trades = read_trades()
        print_report(trades)
        if not watch:
            break
        try:
            time.sleep(watch)
        except KeyboardInterrupt:
            print("Stopping watch")
            break


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--watch', type=int, help='Refresh interval in seconds')
    args = parser.parse_args()
    main(watch=args.watch)
