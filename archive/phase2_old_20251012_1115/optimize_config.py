"""
optimize_config.py

Run this hourly to adjust `config.py` based on recent performance.

Behavior:
  - Reads last 20 completed trades from trades.csv
  - Computes win rate
  - If win rate < 40%: increase MIN_CONFIDENCE by 5 (capped at 95)
  - If win rate > 70%: decrease MIN_CONFIDENCE by 5 (floored at 5)
  - Adjust RSI_OVERSOLD / RSI_OVERBOUGHT slightly based on performance
  - Writes changes to config.py (creates a backup config.py.bak.TIMESTAMP)

Usage: run from repository root. Add to crontab: 0 * * * * /path/to/venv/bin/python /path/to/optimize_config.py
"""
from __future__ import annotations
import csv
import pathlib
import shutil
from datetime import datetime
from statistics import mean
import re

ROOT = pathlib.Path(__file__).resolve().parent
TRADES_CSV = ROOT / 'trades.csv'
CONFIG_PY = ROOT / 'config.py'


def read_last_trades(n: int = 20):
    if not TRADES_CSV.exists():
        return []
    rows = []
    with open(TRADES_CSV, newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for r in reader:
            rows.append(r)
    return rows[-n:]


def compute_win_rate(trades):
    wins = 0
    total = 0
    for t in trades:
        try:
            pnl = float(t.get('pnl', 0) or 0)
        except Exception:
            pnl = 0
        total += 1
        if pnl > 0:
            wins += 1
    return (wins, total, (wins/total*100) if total else 0.0)


def backup_config():
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    bak = CONFIG_PY.with_suffix(f'.bak.{ts}')
    shutil.copy2(CONFIG_PY, bak)
    return bak


def write_config_updates(updates: dict):
    text = CONFIG_PY.read_text(encoding='utf-8')
    new_text = text
    # MIN_CONFIDENCE
    if 'MIN_CONFIDENCE' in updates:
        new_text = re.sub(r"MIN_CONFIDENCE\s*=\s*[0-9]+\.?[0-9]*",
                          f"MIN_CONFIDENCE = {updates['MIN_CONFIDENCE']}", new_text)
    # RSI_OVERSOLD / RSI_OVERBOUGHT (create if not present)
    if 'RSI_OVERSOLD' in updates:
        if 'RSI_OVERSOLD' in new_text:
            new_text = re.sub(r"RSI_OVERSOLD\s*=\s*[0-9]+", f"RSI_OVERSOLD = {updates['RSI_OVERSOLD']}", new_text)
        else:
            new_text = new_text.replace('# Trade parameters', '# Trade parameters\nRSI_OVERSOLD = %d' % updates['RSI_OVERSOLD'])
    if 'RSI_OVERBOUGHT' in updates:
        if 'RSI_OVERBOUGHT' in new_text:
            new_text = re.sub(r"RSI_OVERBOUGHT\s*=\s*[0-9]+", f"RSI_OVERBOUGHT = {updates['RSI_OVERBOUGHT']}", new_text)
        else:
            new_text = new_text.replace('# Trade parameters', '# Trade parameters\nRSI_OVERBOUGHT = %d' % updates['RSI_OVERBOUGHT'])

    CONFIG_PY.write_text(new_text, encoding='utf-8')


def main():
    trades = read_last_trades(20)
    wins, total, win_pct = compute_win_rate(trades)
    print(f"Last {total} trades: wins={wins} win_pct={win_pct:.2f}%")

    updates = {}
    # MIN_CONFIDENCE adjustment
    # Read current MIN_CONFIDENCE from config.py
    cfg_text = CONFIG_PY.read_text(encoding='utf-8')
    m = re.search(r"MIN_CONFIDENCE\s*=\s*([0-9]+\.?[0-9]*)", cfg_text)
    cur_min_conf = float(m.group(1)) if m else 25.0

    if win_pct < 40.0:
        new_conf = min(95.0, cur_min_conf + 5.0)
        updates['MIN_CONFIDENCE'] = new_conf
    elif win_pct > 70.0:
        new_conf = max(5.0, cur_min_conf - 5.0)
        updates['MIN_CONFIDENCE'] = new_conf

    # RSI adjustments: if win rate low, widen bands (make harder to trigger)
    # read existing or default
    m1 = re.search(r"RSI_OVERSOLD\s*=\s*([0-9]+)", cfg_text)
    m2 = re.search(r"RSI_OVERBOUGHT\s*=\s*([0-9]+)", cfg_text)
    rsi_oversold = int(m1.group(1)) if m1 else 45
    rsi_overbought = int(m2.group(1)) if m2 else 55

    if win_pct < 40.0:
        # widen gap: lower oversold by 2, raise overbought by 2
        rsi_oversold = max(20, rsi_oversold - 2)
        rsi_overbought = min(80, rsi_overbought + 2)
    elif win_pct > 70.0:
        # tighten gap: raise oversold, lower overbought
        rsi_oversold = min(50, rsi_oversold + 2)
        rsi_overbought = max(50, rsi_overbought - 2)

    updates['RSI_OVERSOLD'] = rsi_oversold
    updates['RSI_OVERBOUGHT'] = rsi_overbought

    if updates:
        bak = backup_config()
        print(f"Backed up config to {bak}")
        write_config_updates(updates)
        print(f"Applied updates: {updates}")
    else:
        print("No updates required")


if __name__ == '__main__':
    main()
