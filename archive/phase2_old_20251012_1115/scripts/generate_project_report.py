#!/usr/bin/env python3
"""
PROJECT REPORT GENERATOR

Builds a comprehensive, research-ready Markdown report using:
- SQLite trades (ozzy_simple.db)
- Current config (config.py)
- AI optimizer config (config_ai_optimized.py if present)
- Recent performance snapshots (today, last N trades)

Output: PROJECT_REPORT.md in repo root.
"""
from __future__ import annotations
import os
import sys
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, Tuple

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(ROOT, 'ozzy_simple.db')
REPORT_PATH = os.path.join(ROOT, 'PROJECT_REPORT.md')
CONFIG_PATH = os.path.join(ROOT, 'config.py')
AI_CONFIG_PATH = os.path.join(ROOT, 'config_ai_optimized.py')

# Attempt to import config dynamically from ROOT
sys.path.insert(0, ROOT)
try:
    import config  # type: ignore
except Exception:
    config = None


def load_trades() -> pd.DataFrame:
    if not os.path.exists(DB_PATH):
        return pd.DataFrame()
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query(
        '''
        SELECT id, entry_timestamp, exit_timestamp, symbol, side, entry_price, exit_price,
               position_size, position_value, pnl, duration_seconds, confidence
        FROM trades
        WHERE entry_timestamp IS NOT NULL
        ORDER BY entry_timestamp ASC
        ''',
        conn
    )
    conn.close()
    # Parse timestamps
    for col in ['entry_timestamp', 'exit_timestamp']:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors='coerce')
    # Add helpers
    if not df.empty:
        df['date'] = df['entry_timestamp'].dt.date
        df['hour'] = df['entry_timestamp'].dt.hour
        df['dow'] = df['entry_timestamp'].dt.day_name()
        df['is_win'] = (df['pnl'] > 0).astype(int)
        df['side_norm'] = df['side'].str.upper().str.replace('LONG','LONG').str.replace('SHORT','SHORT')
    return df


def stat_basic(df: pd.DataFrame) -> Dict[str, Any]:
    if df.empty:
        return {k: 0 for k in ['trades','wins','losses','win_rate','total_pnl','avg_pnl','avg_win','avg_loss','profit_factor']}
    trades = len(df)
    wins = int((df['pnl'] > 0).sum())
    losses = trades - wins
    win_rate = round(wins / trades * 100, 2) if trades else 0.0
    total_pnl = round(df['pnl'].sum(), 2)
    avg_pnl = round(df['pnl'].mean(), 2)
    avg_win = round(df.loc[df['pnl'] > 0, 'pnl'].mean(), 2) if (df['pnl'] > 0).any() else 0.0
    avg_loss = round(df.loc[df['pnl'] < 0, 'pnl'].mean(), 2) if (df['pnl'] < 0).any() else 0.0
    gross_profit = df.loc[df['pnl'] > 0, 'pnl'].sum()
    gross_loss = -df.loc[df['pnl'] < 0, 'pnl'].sum()
    profit_factor = round((gross_profit / gross_loss), 2) if gross_loss > 0 else None
    return {
        'trades': trades,
        'wins': wins,
        'losses': losses,
        'win_rate': win_rate,
        'total_pnl': total_pnl,
        'avg_pnl': avg_pnl,
        'avg_win': avg_win,
        'avg_loss': avg_loss,
        'profit_factor': profit_factor
    }


def max_drawdown(df: pd.DataFrame, starting_capital: float = 10000.0) -> Tuple[float, float]:
    if df.empty:
        return (0.0, 0.0)
    curve = [starting_capital]
    for v in df['pnl'].fillna(0):
        curve.append(curve[-1] + v)
    import numpy as np
    equity = np.array(curve[1:])
    peaks = np.maximum.accumulate(equity)
    drawdowns = peaks - equity
    max_dd = float(drawdowns.max() if drawdowns.size else 0.0)
    max_dd_pct = float((max_dd / peaks.max()) * 100) if peaks.max() > 0 else 0.0
    return (round(max_dd,2), round(max_dd_pct,2))


def streaks(df: pd.DataFrame) -> Tuple[int, int]:
    if df.empty:
        return (0, 0)
    max_win, max_loss = 0, 0
    cur_win, cur_loss = 0, 0
    for won in (df['pnl'] > 0).tolist():
        if won:
            cur_win += 1
            cur_loss = 0
        else:
            cur_loss += 1
            cur_win = 0
        max_win = max(max_win, cur_win)
        max_loss = max(max_loss, cur_loss)
    return (max_win, max_loss)


def conf_buckets(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty or 'confidence' not in df.columns:
        return pd.DataFrame()
    bins = [0,20,30,35,40,45,50,60,70,80,90,100]
    labels = ["0-20","20-30","30-35","35-40","40-45","45-50","50-60","60-70","70-80","80-90","90-100"]
    binned = pd.cut(df['confidence'].fillna(-1), bins=bins, labels=labels, include_lowest=True)
    tmp = df.copy()
    tmp['bucket'] = binned
    res = tmp.groupby('bucket', dropna=False).apply(lambda x: pd.Series({
        'trades': len(x),
        'wins': int((x['pnl']>0).sum()),
        'win_rate_pct': round(((x['pnl']>0).mean()*100) if len(x) else 0.0, 2),
        'avg_win': round(x.loc[x['pnl']>0,'pnl'].mean(),2) if (x['pnl']>0).any() else 0.0,
        'avg_loss': round(x.loc[x['pnl']<0,'pnl'].mean(),2) if (x['pnl']<0).any() else 0.0,
        'profit_factor': round((x.loc[x['pnl']>0,'pnl'].sum() / -x.loc[x['pnl']<0,'pnl'].sum()),2) if (x['pnl']<0).any() else None,
        'total_pnl': round(x['pnl'].sum(),2)
    })).reset_index()
    # Ensure numeric columns are clean; don't touch the categorical 'bucket' column
    for c in ['trades','wins']:
        if c in res.columns:
            res[c] = pd.to_numeric(res[c], errors='coerce').fillna(0).astype(int)
    for c in ['win_rate_pct','avg_win','avg_loss','profit_factor','total_pnl']:
        if c in res.columns:
            res[c] = pd.to_numeric(res[c], errors='coerce')
    return res


def current_config_snapshot() -> Dict[str, Any]:
    snap: Dict[str, Any] = {}
    if config:
        for k in [
            'PAPER_TRADING','RSI_OVERSOLD','RSI_OVERBOUGHT',
            'EMA_SHORT','EMA_LONG','MIN_CONFIDENCE','TRADING_HOURS',
            'LEVERAGE','POSITION_SIZE_PERCENTAGE','STOP_LOSS_PERCENTAGE','TAKE_PROFIT_PERCENTAGE',
            'INITIAL_BALANCE','SYMBOLS'
        ]:
            if hasattr(config, k):
                snap[k] = getattr(config, k)
    # file timestamps
    try:
        snap['config_mtime'] = datetime.fromtimestamp(os.path.getmtime(CONFIG_PATH)).strftime('%Y-%m-%d %H:%M:%S')
    except Exception:
        pass
    if os.path.exists(AI_CONFIG_PATH):
        try:
            snap['ai_config_mtime'] = datetime.fromtimestamp(os.path.getmtime(AI_CONFIG_PATH)).strftime('%Y-%m-%d %H:%M:%S')
        except Exception:
            pass
    return snap


def ai_cutover_time() -> Optional[datetime]:
    # Prefer ai config mtime; otherwise config mtime as proxy
    path = AI_CONFIG_PATH if os.path.exists(AI_CONFIG_PATH) else CONFIG_PATH
    try:
        return datetime.fromtimestamp(os.path.getmtime(path))
    except Exception:
        return None


def build_report() -> str:
    df = load_trades()
    cfg = current_config_snapshot()

    lines: list[str] = []
    lines.append("# 📚 Ozzy Project — Comprehensive Analysis Report")
    lines.append("")
    lines.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("")

    # Executive summary
    lines.append("## Executive summary")
    if df.empty:
        lines.append("No trades found in ozzy_simple.db — run the bot or import historicals.")
        return "\n".join(lines)

    overall = stat_basic(df)
    max_dd, max_dd_pct = max_drawdown(df, starting_capital=(cfg.get('INITIAL_BALANCE') or 10000))
    wstreak, lstreak = streaks(df)

    lines.append(f"- Total trades: {overall['trades']} | Wins: {overall['wins']} | Win rate: {overall['win_rate']}%")
    lines.append(f"- Total P&L: R{overall['total_pnl']:.2f} | Avg/trade: R{overall['avg_pnl']:.2f} | Profit factor: {overall['profit_factor']}")
    lines.append(f"- Max drawdown: R{max_dd} ({max_dd_pct}%) | Longest win streak: {wstreak} | Longest loss streak: {lstreak}")
    lines.append("")

    # Config snapshot
    lines.append("## Current configuration snapshot")
    for k, v in cfg.items():
        lines.append(f"- {k}: {v}")
    lines.append("")

    # Recent performance
    lines.append("## Recent performance")
    today = df[df['entry_timestamp'].dt.date == datetime.now().date()]
    last_15 = df.tail(15)
    last_100 = df.tail(100)
    for title, subset in [("Today", today), ("Last 15 trades", last_15), ("Last 100 trades", last_100)]:
        s = stat_basic(subset)
        lines.append(f"### {title}")
        lines.append(f"- Trades: {s['trades']} | Win rate: {s['win_rate']}% | Total P&L: R{s['total_pnl']:.2f} | Avg: R{s['avg_pnl']:.2f}")
    lines.append("")

    # Hourly and daily
    lines.append("## Time-of-day performance")
    by_hour = df.groupby('hour').agg(trades=('pnl','count'), avg_pnl=('pnl','mean'), total_pnl=('pnl','sum')).reset_index()
    if not by_hour.empty:
        lines.append("Hour | Trades | Avg PnL | Total PnL")
        lines.append("---|---:|---:|---:")
        for _, r in by_hour.sort_values('avg_pnl', ascending=False).iterrows():
            lines.append(f"{int(r['hour'])} | {int(r['trades'])} | R{r['avg_pnl']:.2f} | R{r['total_pnl']:.2f}")
    lines.append("")

    lines.append("## Day-of-week performance")
    by_dow = df.groupby('dow').agg(trades=('pnl','count'), avg_pnl=('pnl','mean'), total_pnl=('pnl','sum')).reset_index()
    if not by_dow.empty:
        lines.append("Day | Trades | Avg PnL | Total PnL")
        lines.append("---|---:|---:|---:")
        for _, r in by_dow.sort_values('avg_pnl', ascending=False).iterrows():
            lines.append(f"{r['dow']} | {int(r['trades'])} | R{r['avg_pnl']:.2f} | R{r['total_pnl']:.2f}")
    lines.append("")

    # Symbol and side
    lines.append("## Symbol performance")
    tmp = df.groupby('symbol').apply(lambda x: pd.Series({
        'trades': len(x),
        'win_rate': round(((x['pnl']>0).mean()*100) if len(x) else 0.0, 2),
        'avg_pnl': round(x['pnl'].mean(),2),
        'total_pnl': round(x['pnl'].sum(),2)
    })).reset_index()
    if not tmp.empty:
        lines.append("Symbol | Trades | Win% | Avg PnL | Total PnL")
        lines.append("---|---:|---:|---:|---:")
        for _, r in tmp.sort_values('total_pnl', ascending=False).iterrows():
            lines.append(f"{r['symbol']} | {int(r['trades'])} | {r['win_rate']:.1f}% | R{r['avg_pnl']:.2f} | R{r['total_pnl']:.2f}")
    lines.append("")

    lines.append("## Side performance (LONG vs SHORT)")
    if 'side_norm' in df.columns:
        tmp2 = df.groupby('side_norm').apply(lambda x: pd.Series({
            'trades': len(x),
            'win_rate': round(((x['pnl']>0).mean()*100) if len(x) else 0.0, 2),
            'avg_pnl': round(x['pnl'].mean(),2),
            'total_pnl': round(x['pnl'].sum(),2)
        })).reset_index()
        if not tmp2.empty:
            lines.append("Side | Trades | Win% | Avg PnL | Total PnL")
            lines.append("---|---:|---:|---:|---:")
            for _, r in tmp2.sort_values('total_pnl', ascending=False).iterrows():
                lines.append(f"{r['side_norm']} | {int(r['trades'])} | {r['win_rate']:.1f}% | R{r['avg_pnl']:.2f} | R{r['total_pnl']:.2f}")
    lines.append("")

    # Confidence buckets
    lines.append("## Confidence buckets")
    cb = conf_buckets(df)
    if not cb.empty:
        lines.append("Bucket | Trades | Win% | Avg Win | Avg Loss | PF | Total PnL")
        lines.append("---|---:|---:|---:|---:|---:|---:")
        for _, r in cb.iterrows():
            lines.append(f"{r['bucket']} | {int(r['trades'])} | {r['win_rate_pct']:.1f}% | R{r['avg_win']:.2f} | R{r['avg_loss']:.2f} | {'' if pd.isna(r['profit_factor']) else r['profit_factor'] } | R{r['total_pnl']:.2f}")
    lines.append("")

    # AI cutover and post-AI stats
    lines.append("## AI optimization — cutover analysis")
    cut = ai_cutover_time()
    if cut is not None:
        post_ai = df[df['entry_timestamp'] >= cut]
        pre_ai = df[df['entry_timestamp'] < cut].tail(200)  # recent baseline for fair compare
        s_pre = stat_basic(pre_ai)
        s_post = stat_basic(post_ai)
        lines.append(f"Cutover time (file timestamp): {cut.strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append("")
        lines.append("Metric | Pre-AI (recent 200) | Post-AI (since cutover)")
        lines.append("---|---:|---:")
        lines.append(f"Trades | {s_pre['trades']} | {s_post['trades']}")
        lines.append(f"Win rate | {s_pre['win_rate']:.1f}% | {s_post['win_rate']:.1f}%")
        lines.append(f"Total PnL | R{s_pre['total_pnl']:.2f} | R{s_post['total_pnl']:.2f}")
        lines.append(f"Avg/trade | R{s_pre['avg_pnl']:.2f} | R{s_post['avg_pnl']:.2f}")
    else:
        lines.append("AI cutover not detected (no config files found).")
    lines.append("")

    # Research questions & next steps
    lines.append("## Research questions (to investigate)")
    lines.append("- Which hours in 10:00–21:00 window yield highest PF by symbol?")
    lines.append("- Does raising MIN_CONFIDENCE from current level increase PF without killing volume?")
    lines.append("- Are SHORT trades underperforming versus LONGs in current market regime?")
    lines.append("- What is the average slippage per symbol and does it correlate with time of day?")
    lines.append("- Should we exclude first 30 minutes after 10:00 due to volatility spikes?")
    lines.append("")

    lines.append("## Recommendations")
    lines.append("- Keep trading within 10:00–21:00; iterate narrow sub-windows (e.g., 10–12, 14–17).")
    lines.append("- Tune confidence bands around current threshold and re-evaluate PF.")
    lines.append("- Cap simultaneous positions to reduce clustered losses on same symbol.")
    lines.append("- Add unit tests for signal validity when confidence just above threshold.")

    return "\n".join(lines)


def main():
    md = build_report()
    with open(REPORT_PATH, 'w', encoding='utf-8') as f:
        f.write(md)
    print(f"✅ Report written to {REPORT_PATH}")

if __name__ == '__main__':
    main()
