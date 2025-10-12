#!/usr/bin/env python3
"""Quick check for closed trades"""
import sqlite3

conn = sqlite3.connect('/home/rick/ozzy-simple/ozzy_simple.db')
cursor = conn.cursor()

# Check for closed TEST trades
cursor.execute("SELECT COUNT(*) FROM trades WHERE entry_reason LIKE '%TEST_%' AND exit_timestamp IS NOT NULL")
closed = cursor.fetchone()[0]

cursor.execute("SELECT COUNT(*) FROM trades WHERE entry_reason LIKE '%TEST_%' AND exit_timestamp IS NULL")
open_trades = cursor.fetchone()[0]

print(f"\n📊 A/B TEST PROGRESS")
print(f"=" * 40)
print(f"Closed trades:  {closed}/100 ({'Ready!' if closed > 0 else 'Waiting...'})")
print(f"Open trades:    {open_trades}")
print()

if closed > 0:
    print(f"✅ Dashboard has data now!")
    print(f"   Run: ./watch.sh")
else:
    print(f"⏳ Waiting for trades to close...")
    print(f"   Check again in 10-15 minutes")

conn.close()
