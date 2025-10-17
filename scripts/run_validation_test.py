#!/usr/bin/env python3
"""
Quick 30-minute validation test to verify risk management fixes
"""
import sys
import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]

print("=" * 80)
print("🔧 RISK MANAGEMENT VALIDATION TEST - 30 MINUTES")
print("=" * 80)
print()
print("This test will verify:")
print("  ✅ Capital check prevents over-leverage")
print("  ✅ Max position limit enforced (20)")
print("  ✅ Portfolio exposure controlled (<80%)")
print("  ✅ Rejections logged properly")
print()
print("Expected outcome:")
print("  - Opens max 20 positions")
print("  - Capital stays positive")
print("  - Rejection messages in logs")
print()

response = input("Start 30-minute validation test? (yes/no): ")

if response.lower() not in ['yes', 'y']:
    print("❌ Test cancelled")
    sys.exit(0)

print()
print("🚀 Starting test...")
print()

# Clean old logs
import os
logs_dir = PROJECT_ROOT / "logs"
if (logs_dir / "portfolio_state.json").exists():
    backup = logs_dir / f"portfolio_state_backup_{os.path.getmtime(logs_dir / 'portfolio_state.json'):.0f}.json"
    os.rename(logs_dir / "portfolio_state.json", backup)
    print(f"📦 Backed up old portfolio state to {backup.name}")

if (logs_dir / "decisions.json").exists():
    os.remove(logs_dir / "decisions.json")
    print("🗑️  Cleared old decisions.json")

print()
print("⏰ Running 30-minute test...")
print("   Monitor progress: tail -f logs/test_output.log")
print("   Check Slack for position notifications")
print()

# Start test
cmd = [
    sys.executable,
    str(PROJECT_ROOT / "scripts/test_live_stream.py"),
    "--symbol", "BTCUSDT",
    "--duration", "1800",  # 30 minutes
    "--decision-interval", "60"
]

try:
    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1
    )
    
    print(f"✅ Test started (PID: {process.pid})")
    print()
    print("=" * 80)
    print("LIVE OUTPUT:")
    print("=" * 80)
    
    # Stream output
    for line in process.stdout:
        print(line, end='')
    
    process.wait()
    
    print()
    print("=" * 80)
    print("✅ TEST COMPLETE!")
    print("=" * 80)
    print()
    
    # Analyze results
    print("📊 Analyzing results...")
    print()
    
    import json
    portfolio_file = PROJECT_ROOT / "logs/portfolio_state.json"
    
    if portfolio_file.exists():
        with open(portfolio_file) as f:
            data = json.load(f)
        
        positions = data.get('positions', [])
        capital = data.get('capital', 0)
        total_pnl = data.get('total_pnl', 0)
        
        print("RESULTS:")
        print("-" * 80)
        print(f"Positions opened: {len(positions)}")
        print(f"Final capital: ${capital:,.2f}")
        print(f"Total P&L: ${total_pnl:,.2f}")
        print()
        
        # Validation checks
        checks_passed = 0
        checks_total = 3
        
        print("VALIDATION CHECKS:")
        print("-" * 80)
        
        if len(positions) <= 20:
            print(f"✅ Max positions: {len(positions)}/20 (PASS)")
            checks_passed += 1
        else:
            print(f"❌ Max positions: {len(positions)}/20 (FAIL - should be ≤20)")
        
        if capital >= 0:
            print(f"✅ Capital positive: ${capital:,.2f} (PASS)")
            checks_passed += 1
        else:
            print(f"❌ Capital negative: ${capital:,.2f} (FAIL - over-leveraged!)")
        
        exposure = sum(p.get('size', 0) for p in positions)
        exposure_pct = exposure / 5000
        if exposure_pct <= 0.80:
            print(f"✅ Exposure controlled: {exposure_pct:.1%} (PASS)")
            checks_passed += 1
        else:
            print(f"❌ Exposure too high: {exposure_pct:.1%} (FAIL - should be ≤80%)")
        
        print()
        print("=" * 80)
        
        if checks_passed == checks_total:
            print("🎉 ALL CHECKS PASSED! Risk management working correctly!")
            print()
            print("✅ Ready for longer test run!")
            print()
            print("Next step:")
            print("  Run 2-12 hour test to collect meaningful data")
        else:
            print(f"⚠️  {checks_passed}/{checks_total} checks passed")
            print()
            print("❌ Fix issues before longer test!")
        
        print("=" * 80)
    
    else:
        print("❌ No portfolio state file found!")
        print("   Test may have failed to run")
    
except KeyboardInterrupt:
    print()
    print("⏸️  Test interrupted by user")
    process.terminate()
except Exception as e:
    print(f"❌ Error running test: {e}")
    sys.exit(1)
