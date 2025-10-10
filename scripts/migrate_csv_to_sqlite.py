"""
Migrate existing signals.csv and trades.csv into SQLite (ozzy_simple.db)
"""
import csv
import os
import db


def migrate_signals(csv_path='signals.csv'):
    if not os.path.exists(csv_path):
        print('No signals.csv found, skipping')
        return
    with open(csv_path, newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                db.insert_signal({
                    'timestamp': row.get('timestamp'),
                    'symbol': row.get('symbol'),
                    'signal': row.get('signal'),
                    'confidence': float(row.get('confidence') or 0),
                    'quality': row.get('quality'),
                    'rsi': float(row.get('rsi') or 0),
                    'ema_short': float(row.get('ema_short') or 0),
                    'ema_long': float(row.get('ema_long') or 0),
                    'volume_ratio': float(row.get('volume_ratio') or 0),
                    'momentum': float(row.get('momentum') or 0),
                    'hour': int(row.get('hour') or 0),
                    'day_of_week': int(row.get('day_of_week') or 0),
                    'atr_pct': float(row.get('atr_pct') or 0),
                    'stddev_returns_pct': float(row.get('stddev_returns_pct') or 0),
                    'reason': row.get('reason')
                })
            except Exception as e:
                print('Failed inserting signal:', e)


def migrate_trades(csv_path='trades.csv'):
    if not os.path.exists(csv_path):
        print('No trades.csv found, skipping')
        return
    with open(csv_path, newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                db.insert_trade({
                    'entry_timestamp': row.get('entry_timestamp'),
                    'exit_timestamp': row.get('exit_timestamp'),
                    'symbol': row.get('symbol'),
                    'side': row.get('side'),
                    'entry_price': float(row.get('entry_price') or 0),
                    'exit_price': float(row.get('exit_price') or 0),
                    'position_size': float(row.get('position_size') or 0),
                    'position_value': float(row.get('position_value') or 0),
                    'pnl': float(row.get('pnl') or 0),
                    'duration_seconds': int(row.get('duration_seconds') or 0),
                    'quality': row.get('quality'),
                    'confidence': float(row.get('confidence') or 0),
                    'entry_reason': row.get('entry_reason'),
                    'exit_reason': row.get('exit_reason')
                })
            except Exception as e:
                print('Failed inserting trade:', e)


if __name__ == '__main__':
    db.init_db()
    print('Migrating signals...')
    migrate_signals()
    print('Migrating trades...')
    migrate_trades()
    print('Migration complete')
