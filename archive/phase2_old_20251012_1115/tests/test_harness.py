import os
import time
import db
from main import OzzyBot


def test_db_and_logs(tmp_path):
    # Initialize DB in tmp path to avoid clobbering repo DB
    orig_db = db.DB_PATH
    db.DB_PATH = str(tmp_path / 'test_ozzy.db')
    db.init_db()

    bot = OzzyBot()

    # Generate one fake signal write using the bot helper
    signal = {
        'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
        'technical_data': {'rsi': 50, 'ema_short': 1, 'ema_long': 2, 'atr_pct': 0.1, 'stddev_returns_pct': 0.2, 'volume_ratio': 1.0, 'price_momentum': 0.01},
        'signal': 'HOLD',
        'confidence': 10.0,
        'quality': 'LOW',
        'reason': 'test'
    }

    bot._log_signal('BTCUSDT', signal)

    # Check DB has a signals row
    conn = db._get_conn()
    c = conn.cursor()
    c.execute('SELECT COUNT(*) FROM signals')
    count = c.fetchone()[0]
    conn.close()

    assert count >= 1

    # Clean up
    db.DB_PATH = orig_db
    os.remove(str(tmp_path / 'test_ozzy.db'))
