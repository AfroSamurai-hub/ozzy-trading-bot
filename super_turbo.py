#!/usr/bin/env python3
"""
SUPER TURBO - Generate 100+ trades in minutes
Maximum speed, SHORT-focused data generation
"""
import subprocess
import time
from datetime import datetime

print("🔥 SUPER TURBO MODE")
print("="*60)
print("Target: Generate 70+ trades to reach 200 total")
print("Focus: SHORT bias to balance dataset")
print("="*60)

# Show before
print("\n📊 BEFORE:")
subprocess.run(["./venv/bin/python", "quick_stats.py"])

start_time = time.time()

print("\n🚀 Running 3 rapid-fire turbo rounds...")
print("="*60)

# Round 1: Conservative + Aggressive with SHORT bias
print("\n⚡ Round 1/3: Conservative + Aggressive")
subprocess.run([
    "./venv/bin/python", "turbo_mode.py",
    "--per-symbol", "10",
    "--rounds", "3",
    "--variants", "Conservative", "Aggressive",
    "--short-bias",
    "--fast"
])

print("\n⏸️  5 second cooldown...")
time.sleep(5)

# Round 2: Balanced + Momentum with SHORT bias
print("\n⚡ Round 2/3: Balanced + Momentum")
subprocess.run([
    "./venv/bin/python", "turbo_mode.py",
    "--per-symbol", "10",
    "--rounds", "3",
    "--variants", "Balanced", "Momentum",
    "--short-bias",
    "--fast"
])

print("\n⏸️  5 second cooldown...")
time.sleep(5)

# Round 3: Contrarian with extreme SHORT bias
print("\n⚡ Round 3/3: Contrarian (EXTREME SHORT BIAS)")
subprocess.run([
    "./venv/bin/python", "turbo_mode.py",
    "--per-symbol", "15",
    "--rounds", "2",
    "--variants", "Contrarian",
    "--short-bias",
    "--fast"
])

elapsed = time.time() - start_time

print("\n"+"="*60)
print("✅ SUPER TURBO COMPLETE!")
print(f"⏱️  Total time: {elapsed/60:.1f} minutes")
print("="*60)

# Show after
print("\n📊 AFTER:")
subprocess.run(["./venv/bin/python", "quick_stats.py"])

print("\n💡 NEXT STEPS:")
print("   1. Check if you have 200+ trades")
print("   2. If yes: ./venv/bin/python deep_analysis.py")
print("   3. If no:  Run ./super_turbo.py again!")
print("")
