#!/usr/bin/env python3
import sqlite3

DB = 'ozzy_simple.db'

def analyze_performance_by_asset_class():
    conn = sqlite3.connect(DB)
    cur = conn.cursor()

    print("═" * 70)
    print("📊 PERFORMANCE BY ASSET CLASS")
    print("═" * 70)
    print()

    queries = {
        'GOLD': "SELECT COUNT(*), ROUND(100.0*SUM(CASE WHEN pnl>0 THEN 1 ELSE 0 END)/COUNT(*),1), ROUND(SUM(pnl),2) FROM trades WHERE symbol='XAUUSDT'",
        'FOREX': "SELECT COUNT(*), ROUND(100.0*SUM(CASE WHEN pnl>0 THEN 1 ELSE 0 END)/COUNT(*),1), ROUND(SUM(pnl),2) FROM trades WHERE symbol IN ('EURUSD','GBPUSD','USDJPY')",
        'MAJOR CRYPTO': "SELECT COUNT(*), ROUND(100.0*SUM(CASE WHEN pnl>0 THEN 1 ELSE 0 END)/COUNT(*),1), ROUND(SUM(pnl),2) FROM trades WHERE symbol IN ('BTCUSDT','ETHUSDT')",
        'ALTCOINS': "SELECT COUNT(*), ROUND(100.0*SUM(CASE WHEN pnl>0 THEN 1 ELSE 0 END)/COUNT(*),1), ROUND(SUM(pnl),2) FROM trades WHERE symbol IN ('SOLUSDT','BNBUSDT')",
    }

    for name, q in queries.items():
        cur.execute(q)
        total, wr, pnl = cur.fetchone()
        total = total or 0
        wr = wr or 0.0
        pnl = pnl or 0.0
        print(f"{name:15s} | {total:3d} trades | {wr:5.1f}% WR | R{pnl:8.2f}")

    print()

    # Simple correlation proxy: direction agreement between classes by day
    print("🔗 Direction Agreement (by day, simple proxy)")
    print("(Percent of days classes ended with same P&L sign)")

    # Fetch daily P&L per class
    def daily_class_pnl(where_clause: str):
        cur.execute(f"""
            SELECT date(entry_timestamp), SUM(pnl)
            FROM trades
            WHERE {where_clause}
            GROUP BY date(entry_timestamp)
        """)
        return dict(cur.fetchall())

    gold = daily_class_pnl("symbol='XAUUSDT'")
    forex = daily_class_pnl("symbol IN ('EURUSD','GBPUSD','USDJPY')")
    major = daily_class_pnl("symbol IN ('BTCUSDT','ETHUSDT')")
    alt = daily_class_pnl("symbol IN ('SOLUSDT','BNBUSDT')")

    pairs = [
        ("GOLD","FOREX", gold, forex),
        ("GOLD","MAJOR", gold, major),
        ("GOLD","ALT", gold, alt),
        ("FOREX","MAJOR", forex, major),
        ("FOREX","ALT", forex, alt),
        ("MAJOR","ALT", major, alt),
    ]
    for a,b,da,db in pairs:
        days = set(da.keys()) & set(db.keys())
        if not days:
            print(f"{a:6s}-{b:6s}: n/a")
            continue
        agree = 0
        for d in days:
            sa = 1 if da[d] > 0 else (-1 if da[d] < 0 else 0)
            sb = 1 if db[d] > 0 else (-1 if db[d] < 0 else 0)
            agree += 1 if sa == sb else 0
        pct = 100.0 * agree / len(days)
        print(f"{a:6s}-{b:6s}: {pct:5.1f}% (n={len(days)})")

    conn.close()

if __name__ == '__main__':
    analyze_performance_by_asset_class()
