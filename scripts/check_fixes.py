#!/usr/bin/env python3
"""Quick status check - are the fixes in place?"""
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]

print("╔════════════════════════════════════════════════════════════════╗")
print("║           🔍 RISK MANAGEMENT FIX STATUS CHECK                 ║")
print("╚════════════════════════════════════════════════════════════════╝")
print()

checks_passed = 0
checks_total = 5

# Check 1: Portfolio has risk management
print("📋 Checking fixes...")
print("-" * 70)

portfolio_file = PROJECT_ROOT / "agent/portfolio.py"
content = portfolio_file.read_text()

if "MAX_POSITIONS" in content and "MAX_EXPOSURE_PCT" in content:
    print("✅ Fix 1: Risk limits added to PaperTradingPortfolio")
    checks_passed += 1
else:
    print("❌ Fix 1: Risk limits NOT FOUND in portfolio.py")

if "if self.capital < size:" in content and "return None" in content:
    print("✅ Fix 2: Capital check implemented")
    checks_passed += 1
else:
    print("❌ Fix 2: Capital check NOT FOUND")

# Check 2: Test script handles rejections
test_file = PROJECT_ROOT / "scripts/test_live_stream.py"
content = test_file.read_text()

if "if position is None:" in content:
    print("✅ Fix 3: Rejection handling added to test script")
    checks_passed += 1
else:
    print("❌ Fix 3: Rejection handling NOT FOUND")

if "decision_stats" in content:
    print("✅ Fix 4: Decision statistics tracking added")
    checks_passed += 1
else:
    print("❌ Fix 4: Decision statistics NOT FOUND")

# Check 3: Validation script exists
validation_script = PROJECT_ROOT / "scripts/run_validation_test.py"
if validation_script.exists():
    print("✅ Fix 5: Validation test script created")
    checks_passed += 1
else:
    print("❌ Fix 5: Validation script NOT FOUND")

print()
print("=" * 70)

if checks_passed == checks_total:
    print(f"🎉 ALL FIXES APPLIED! ({checks_passed}/{checks_total})")
    print()
    print("✅ System ready for validation testing!")
    print()
    print("Next step:")
    print("  cd ~/ozzy-simple")
    print("  source venv/bin/activate")
    print("  python scripts/run_validation_test.py")
else:
    print(f"⚠️  {checks_passed}/{checks_total} fixes found")
    print()
    print("Some fixes may be missing. Please review FIXES_APPLIED.txt")

print("=" * 70)
