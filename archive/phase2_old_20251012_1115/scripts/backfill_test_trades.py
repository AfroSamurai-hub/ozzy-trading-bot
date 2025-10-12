#!/usr/bin/env python3
"""Backfill script: insert synthetic trades into ozzy_simple.db for dashboard testing."""
import random
import sqlite3
from datetime import datetime, timedelta

DB = 'ozzy_simple.db'
SYMBOLS = ['BTCUSDT', 'SOLUSDT', 'BNBUSDT', 'XRPUSDT']


def random_timestamp_within_last_24h():
    now = datetime.utcnow()
    start = now - timedelta(hours=24)
    rand = start + timedelta(seconds=random.randint(0, 24 * 3600))
    return rand.strftime('%Y-%m-%d %H:%M:%S')


def generate_trade():
    side = random.choice(['LONG', 'SHORT'])
    symbol = random.choice(SYMBOLS)
    # Duration between 15 minutes and 2 hours
    duration = random.randint(15 * 60, 2 * 60 * 60)
    entry_time = datetime.utcnow() - timedelta(seconds=random.randint(0, 24 * 3600))
    exit_time = entry_time + timedelta(seconds=duration)
    # Random base price range (synthetic prices)
    base_price = {
        'BTCUSDT': 60000,
        'SOLUSDT': 120,
        'BNBUSDT': 370,
        'XRPUSDT': 0.65,
    }[symbol]
    # small variation
    entry_price = round(base_price * (1 + random.uniform(-0.02, 0.02)), 2)
    # win 60% of time
    is_win = random.random() < 0.6
    if is_win:
        pnl = round(random.uniform(30, 150), 2)
        exit_price = round(entry_price * (1 + pnl / (entry_price * 100)), 6) if entry_price else entry_price
    else:
        pnl = round(random.uniform(-80, -20), 2)
        exit_price = round(entry_price * (1 + pnl / (entry_price * 100)), 6) if entry_price else entry_price

    size = round((1000 / entry_price) if entry_price else 0.01, 6)
    position_value = round(size * entry_price, 2)

    return dict(
        entry_timestamp=entry_time.strftime('%Y-%m-%d %H:%M:%S'),
        exit_timestamp=exit_time.strftime('%Y-%m-%d %H:%M:%S'),
        symbol=symbol,
        side=side,
        entry_price=entry_price,
        exit_price=exit_price,
        position_size=size,
        position_value=position_value,
        pnl=pnl,
        duration_seconds=duration,
        quality='synthetic',
        confidence=round(random.uniform(0.3, 0.99), 2),
        entry_reason='backfill',
        exit_reason='backfill',
    )


def main(n=20):
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    inserted = []
    for _ in range(n):
        t = generate_trade()
        cur.execute('''
        INSERT INTO trades (entry_timestamp, exit_timestamp, symbol, side, entry_price, exit_price,
                            position_size, position_value, pnl, duration_seconds, quality, confidence,
                            entry_reason, exit_reason)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        ''', (
            t['entry_timestamp'], t['exit_timestamp'], t['symbol'], t['side'], t['entry_price'], t['exit_price'],
            t['position_size'], t['position_value'], t['pnl'], t['duration_seconds'], t['quality'], t['confidence'],
            t['entry_reason'], t['exit_reason']
        ))
        inserted.append(t)

    conn.commit()
    conn.close()
    print(f'Inserted {len(inserted)} synthetic trades into {DB}')


if __name__ == '__main__':
    main(20)
