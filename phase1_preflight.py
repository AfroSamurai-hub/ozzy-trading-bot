#!/usr/bin/env python3
"""
Phase 1 Pre-Flight Verification
Checks if everything is configured correctly before starting monitor mode
"""

import os
import sys
import sqlite3
from pathlib import Path

def check_python_version():
    """Check Python version"""
    print("🐍 Checking Python version...")
    version = sys.version_info
    if version.major >= 3 and version.minor >= 8:
        print(f"   ✅ Python {version.major}.{version.minor}.{version.micro} (OK)")
        return True
    else:
        print(f"   ❌ Python {version.major}.{version.minor}.{version.micro} (Need 3.8+)")
        return False

def check_config():
    """Check config.py settings"""
    print("\n⚙️  Checking configuration...")
    
    try:
        import config
    except ImportError:
        print("   ❌ config.py not found")
        return False
    
    checks = {
        'MONITOR_ONLY_MODE': (True, "Must be True for Phase 1"),
        'PAPER_TRADING': (False, "Must be False to use live data"),
        'BYBIT_TESTNET': (False, "Must be False for live exchange"),
        'MIN_CONFIDENCE': ((30.0, 40.0), "Should be 30-40 for Phase 1"),
    }
    
    passed = 0
    total = len(checks)
    
    for setting, (expected, reason) in checks.items():
        if hasattr(config, setting):
            value = getattr(config, setting)
            
            # Check if value matches expected
            if isinstance(expected, tuple):
                # Range check
                is_ok = expected[0] <= value <= expected[1]
            else:
                # Exact match
                is_ok = value == expected
            
            if is_ok:
                print(f"   ✅ {setting} = {value}")
                passed += 1
            else:
                print(f"   ❌ {setting} = {value} (Expected: {expected})")
                print(f"      ℹ️  {reason}")
        else:
            print(f"   ⚠️  {setting} not found in config")
    
    # Check API keys exist (more lenient for monitor-only mode)
    has_api_key = False
    has_api_secret = False
    
    if hasattr(config, 'BYBIT_API_KEY') and config.BYBIT_API_KEY:
        if config.BYBIT_API_KEY != 'your_api_key_here':
            print(f"   ✅ BYBIT_API_KEY configured")
            has_api_key = True
            passed += 1
        else:
            print(f"   ⚠️  BYBIT_API_KEY placeholder (OK for monitor-only)")
    else:
        print(f"   ❌ BYBIT_API_KEY not found")
    
    if hasattr(config, 'BYBIT_API_SECRET') and config.BYBIT_API_SECRET:
        if config.BYBIT_API_SECRET != 'your_api_secret_here':
            print(f"   ✅ BYBIT_API_SECRET configured")
            has_api_secret = True
            passed += 1
        else:
            print(f"   ⚠️  BYBIT_API_SECRET placeholder (OK for monitor-only)")
    else:
        print(f"   ❌ BYBIT_API_SECRET not found")
    
    # For monitor-only mode, API keys are optional since we don't trade
    if getattr(config, 'MONITOR_ONLY_MODE', False):
        if not has_api_key:
            passed += 1  # Give credit for monitor mode
        if not has_api_secret:
            passed += 1  # Give credit for monitor mode
        print(f"   ℹ️  Monitor-only mode: API keys optional for market data")
    
    total += 2  # Add API key checks to total
    
    print(f"\n   Score: {passed}/{total} checks passed")
    
    return passed == total

def check_database():
    """Check database setup"""
    print("\n🗄️  Checking database...")
    
    db_path = 'ozzy_simple.db'
    
    if not os.path.exists(db_path):
        print(f"   ⚠️  Database not found at {db_path}")
        print(f"      Creating new database...")
        try:
            import db
            db.create_tables()
            print(f"   ✅ Database created successfully")
            return True
        except Exception as e:
            print(f"   ❌ Error creating database: {e}")
            return False
    else:
        print(f"   ✅ Database exists at {db_path}")
        
        # Check if signals table exists
        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='signals'")
            if cursor.fetchone():
                print(f"   ✅ signals table exists")
                
                # Check signal count
                cursor.execute("SELECT COUNT(*) FROM signals")
                count = cursor.fetchone()[0]
                print(f"   ℹ️  Current signal count: {count}")
            else:
                print(f"   ⚠️  signals table not found, creating...")
                try:
                    import db
                    db.create_tables()
                    print(f"   ✅ signals table created")
                except Exception as e:
                    print(f"   ❌ Error creating signals table: {e}")
                    return False
            
            conn.close()
            return True
        except Exception as e:
            print(f"   ❌ Database error: {e}")
            return False

def check_directories():
    """Check required directories exist"""
    print("\n📁 Checking directories...")
    
    dirs = ['logs']
    all_ok = True
    
    for dir_name in dirs:
        if os.path.exists(dir_name):
            print(f"   ✅ {dir_name}/ exists")
        else:
            print(f"   ⚠️  {dir_name}/ not found, creating...")
            try:
                os.makedirs(dir_name, exist_ok=True)
                print(f"   ✅ {dir_name}/ created")
            except Exception as e:
                print(f"   ❌ Error creating {dir_name}/: {e}")
                all_ok = False
    
    return all_ok

def check_dependencies():
    """Check required Python packages"""
    print("\n📦 Checking dependencies...")
    
    required = {
        'requests': 'requests',
        'loguru': 'loguru',
    }
    
    optional = {
        'numpy': 'numpy (for signal analysis)', 
        'pandas': 'pandas (for signal analysis)',
    }
    
    missing = []
    
    # Check required
    for module, package in required.items():
        try:
            __import__(module)
            print(f"   ✅ {package}")
        except ImportError:
            print(f"   ❌ {package} (REQUIRED)")
            missing.append(package)
    
    # Check optional
    for module, package in optional.items():
        try:
            __import__(module)
            print(f"   ✅ {package}")
        except ImportError:
            print(f"   ⚠️  {package} (optional for analysis)")
    
    if missing:
        print(f"\n   ⚠️  Missing required packages: {', '.join(missing)}")
        print(f"   Run: pip install {' '.join(missing)}")
        return False
    
    return True

def check_main_files():
    """Check essential files exist"""
    print("\n📄 Checking essential files...")
    
    files = {
        'main.py': 'Main bot script',
        'config.py': 'Configuration',
        'bybit_client.py': 'Exchange client',
        'signal_generator.py': 'Signal generation',
        'db.py': 'Database module',
    }
    
    all_ok = True
    
    for filename, description in files.items():
        if os.path.exists(filename):
            print(f"   ✅ {filename:20} ({description})")
        else:
            print(f"   ❌ {filename:20} ({description}) - MISSING")
            all_ok = False
    
    return all_ok

def test_api_connection():
    """Test API connection"""
    print("\n🔌 Testing API connection...")
    
    try:
        from bybit_client import BybitClient
        import config
        
        # Override to use live for testing
        client = BybitClient(
            paper_trading=False,
            testnet=False
        )
        
        # Try to get a price (no auth needed)
        price = client.get_current_price('BTCUSDT')
        print(f"   ✅ Market data accessible")
        print(f"   ℹ️  BTC price: ${price:,.2f}")
        
        # Try to get balance (requires auth)
        try:
            balance = client.get_balance()
            print(f"   ✅ API authentication successful")
            print(f"   ℹ️  Account balance: ${balance:,.2f}")
        except Exception as e:
            print(f"   ⚠️  Auth test failed (might be OK): {e}")
            print(f"   ℹ️  Market data works, auth may need paper trading")
        
        return True
        
    except Exception as e:
        print(f"   ❌ API connection failed: {e}")
        print(f"      Check your API keys in config.py")
        return False

def main():
    """Run all pre-flight checks"""
    print("\n" + "=" * 70)
    print("🚀 PHASE 1 PRE-FLIGHT VERIFICATION")
    print("=" * 70)
    print()
    
    checks = {
        'Python Version': check_python_version(),
        'Configuration': check_config(),
        'Database': check_database(),
        'Directories': check_directories(),
        'Dependencies': check_dependencies(),
        'Essential Files': check_main_files(),
        'API Connection': test_api_connection(),
    }
    
    print("\n" + "=" * 70)
    print("📊 VERIFICATION SUMMARY")
    print("=" * 70)
    print()
    
    for check_name, passed in checks.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status:10} | {check_name}")
    
    passed_count = sum(checks.values())
    total_count = len(checks)
    
    print()
    print("-" * 70)
    print(f"Result: {passed_count}/{total_count} checks passed")
    print("-" * 70)
    print()
    
    if passed_count == total_count:
        print("🎉 ALL CHECKS PASSED!")
        print()
        print("✅ System is ready for Phase 1")
        print()
        print("🚀 NEXT STEPS:")
        print("   1. Start the bot: python main.py")
        print("   2. Monitor for 48-72 hours")
        print("   3. Run analysis: python phase1_analysis.py")
        print()
        return 0
    else:
        print("⚠️  SOME CHECKS FAILED")
        print()
        print("📋 ACTIONS NEEDED:")
        print("   1. Fix the failed checks above")
        print("   2. Rerun this script: python phase1_preflight.py")
        print("   3. Don't start Phase 1 until all checks pass")
        print()
        return 1

if __name__ == "__main__":
    exit_code = main()
    print()
    sys.exit(exit_code)