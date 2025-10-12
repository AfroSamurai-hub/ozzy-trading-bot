#!/usr/bin/env python3
"""Demo trading script

Opens and immediately closes a few paper trades using the bot's code paths
so we can observe full lifecycle: signal -> pre-trade checks -> place_order -> DB writes -> close.
"""
import time
import random
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import config
import db
from main import OzzyBot


def force_signal_from_price(price, direction='LONG'):
    if direction == 'LONG':
        stop = price * (1 - config.STOP_LOSS_PERCENT / 100.0)
        tp = price * (1 + config.TAKE_PROFIT_PERCENT / 100.0)
    else:
        stop = price * (1 + config.STOP_LOSS_PERCENT / 100.0)
        tp = price * (1 - config.TAKE_PROFIT_PERCENT / 100.0)

    return {
        'signal': direction,
        'quality': 'DEMO',
        'confidence': 90.0,
        'reason': 'forced_demo_signal',
        'entry_price': round(price, 6),
        'stop_loss': round(stop, 6),
        'take_profit': round(tp, 6),
        'technical_data': {},
        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    }


def run_demo(trade_count=3):
    db.create_tables()
    bot = OzzyBot()

    symbols = config.TRADING_SYMBOLS[:trade_count]
    created = []

    for symbol in symbols:
        print(f"--- DEMO: attempting trade on {symbol} ---")
        # Try natural check_signal first
        sig = bot.check_signal(symbol)
        if not sig or sig.get('signal') == 'HOLD' or sig.get('confidence', 0) < config.MIN_CONFIDENCE:
            # Force a high-confidence signal so we exercise execution flow
            price = bot.client.get_current_price(symbol)
            if not price:
                print(f"Could not fetch price for {symbol}, skipping")
                continue
            direction = random.choice(['LONG', 'SHORT'])
            sig = force_signal_from_price(price, direction)
            print(f"Forcing {direction} @ {price:.6f}")

        ok = bot.execute_trade(symbol, sig)
        print('Execute result:', ok)
        if ok:
            # Wait briefly and then close the position with a small favorable move
            time.sleep(1)
            entry = bot.open_positions.get(symbol)
            if not entry:
                print('No open position found after execute (race?), skipping close')
                continue
            entry_price = sig.get('entry_price')
            # small move in favor
            if sig['signal'] == 'LONG':
                exit_price = round(entry_price * 1.002, 6)
            else:
                exit_price = round(entry_price * 0.998, 6)
            bot.close_position(symbol, exit_price, 'DEMO_CLOSE')
            created.append(symbol)
        print('---')

    # Print DB summary for last created trades
    import sqlite3
    conn = sqlite3.connect(db.DB_PATH)
    cur = conn.cursor()
    cur.execute('SELECT id, entry_timestamp, exit_timestamp, symbol, side, pnl FROM trades ORDER BY id DESC LIMIT 20')
    rows = cur.fetchall()
    print('\nLast trades (most recent first):')
    for r in rows:
        print(r)
    conn.close()
    print('\nDemo completed. Created trades for:', created)


if __name__ == '__main__':
    run_demo(trade_count=3)
