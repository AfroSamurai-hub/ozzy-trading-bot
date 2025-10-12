#!/usr/bin/env python3
"""Simulate end-to-end trading: generate signals, insert open trades, then immediately close them with synthetic P&L.

This creates completed trades in the DB so the dashboard and analytics show realistic history.
"""
import random
import time
from datetime import datetime, timedelta
import os
import sqlite3

# Ensure we import project modules
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import config
import db
from bybit_client import BybitClient
from signal_generator import SignalGenerator


def simulate_trades(per_symbol=5):
    db.create_tables()
    client = BybitClient()
    sg = SignalGenerator(client)
    inserted = []

    symbols = config.TRADING_SYMBOLS
    now = datetime.utcnow()

    for i in range(per_symbol):
        for symbol in symbols:
            # fetch candles (1m) - generator needs >=30
            candles = client.get_candles(symbol, interval='1', limit=60)
            if not candles or len(candles) < 30:
                # fallback: skip if data unavailable
                continue

            signal = sg.generate_signal(candles, symbol=symbol)
            # log the raw signal to DB for ML completeness
            try:
                db.log_signal({
                    'timestamp': signal.get('timestamp'),
                    'symbol': symbol,
                    'signal': signal.get('signal'),
                    'confidence': signal.get('confidence'),
                    'quality': signal.get('quality'),
                    'rsi': signal['technical_data'].get('rsi'),
                    'ema_short': signal['technical_data'].get('ema_short'),
                    'ema_long': signal['technical_data'].get('ema_long'),
                    'volume_ratio': signal['technical_data'].get('volume_ratio'),
                    'momentum': signal['technical_data'].get('price_momentum'),
                    'hour': datetime.utcnow().hour,
                    'day_of_week': datetime.utcnow().weekday(),
                    'atr_pct': signal['technical_data'].get('atr_pct'),
                    'stddev_returns_pct': signal['technical_data'].get('stddev_returns_pct'),
                    'reason': signal.get('reason')
                })
            except Exception:
                pass

            # If HOLD, optionally force some trades based on confidence
            if signal['signal'] == 'HOLD' and signal.get('confidence', 0) < config.MIN_CONFIDENCE:
                # skip low-confidence holds
                continue

            # Create an open trade row in DB
            entry_ts = (now - timedelta(minutes=random.randint(0, 120))).strftime('%Y-%m-%d %H:%M:%S')
            entry_price = signal.get('entry_price') or client.get_current_price(symbol) or 0.0
            side = signal.get('signal') if signal.get('signal') in ('LONG','SHORT') else ('LONG' if random.random() < 0.5 else 'SHORT')
            # position size heuristics: target ~R1000 notional
            position_size = round((1000.0 / entry_price) if entry_price else 0.001, 6)
            position_value = round(position_size * entry_price, 2)

            trade_row = {
                'entry_timestamp': entry_ts,
                'symbol': symbol,
                'side': side,
                'entry_price': round(entry_price, 6),
                'position_size': position_size,
                'position_value': position_value,
                'quality': signal.get('quality', ''),
                'confidence': signal.get('confidence', 0.0),
                'entry_reason': signal.get('reason', 'simulated')
            }

            trade_id = db.log_trade_open(trade_row)

            # Simulate exit shortly after with P&L: 60% wins
            is_win = random.random() < 0.6
            if is_win:
                pnl_amount = round(random.uniform(30, 150), 2)
            else:
                pnl_amount = round(random.uniform(-80, -20), 2)

            # Derive exit price from pnl
            if position_size and entry_price:
                exit_price = round(entry_price + (pnl_amount / position_size), 6) if side == 'LONG' else round(entry_price - (pnl_amount / position_size), 6)
            else:
                exit_price = entry_price

            exit_ts = (now - timedelta(minutes=random.randint(0, 119))).strftime('%Y-%m-%d %H:%M:%S')

            # Persist close
            db.log_trade_close(trade_id, exit_ts, exit_price, pnl_amount, 'SIMULATED_CLOSE')

            inserted.append((trade_id, symbol, side, pnl_amount))

            # small pause to avoid hitting API rate limits
            time.sleep(0.2)

    print(f'Inserted {len(inserted)} simulated completed trades')
    return inserted


if __name__ == '__main__':
    # Stop any running bot to avoid races
    try:
        os.system("pkill -f main.py || true")
    except Exception:
        pass
    inserted = simulate_trades(per_symbol=5)
    # Show summary
    conn = sqlite3.connect(db.DB_PATH)
    cur = conn.cursor()
    cur.execute('SELECT COUNT(*) FROM trades')
    print('Total trades in DB:', cur.fetchone()[0])
    cur.execute('SELECT id, entry_timestamp, exit_timestamp, symbol, side, pnl FROM trades ORDER BY id DESC LIMIT 20')
    rows = cur.fetchall()
    for r in rows:
        print(r)
    conn.close()
