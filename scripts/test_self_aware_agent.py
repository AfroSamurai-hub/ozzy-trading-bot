"""
🧪 Test Self-Aware Trading Agent

This script tests if the TradingAgent properly initializes
its intelligence systems and becomes SELF-AWARE!
"""

import sys
import asyncio
import logging
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from intelligence.rolling_window_db import RollingWindowPatternDB
from mcp.trading_server import TradingMCPServer
from agent.trader import TradingAgent

logging.basicConfig(
    level=logging.INFO,
    format='%(levelname)s:%(name)s: %(message)s'
)

async def test_self_aware_agent():
    """Test that agent initializes all intelligence systems."""
    
    print("╔════════════════════════════════════════════════════════════╗")
    print("║                                                            ║")
    print("║         🧠 TESTING SELF-AWARE TRADING AGENT 🧠            ║")
    print("║                                                            ║")
    print("╚════════════════════════════════════════════════════════════╝")
    print()
    
    # Step 1: Initialize pattern DB and MCP server
    print("1️⃣ Initializing pattern database...")
    pattern_db = RollingWindowPatternDB()
    print(f"   ✅ Pattern DB ready: {pattern_db.count()} patterns")
    print()
    
    print("2️⃣ Initializing MCP server...")
    mcp_server = TradingMCPServer(pattern_db)
    print("   ✅ MCP server ready")
    print()
    
    # Step 2: Create agent (should auto-initialize intelligence)
    print("3️⃣ Creating self-aware trading agent...")
    print("   (Watch for intelligence system checks...)")
    print()
    
    # Load environment variables
    from dotenv import load_dotenv
    import os
    load_dotenv()
    
    if not os.getenv("OPENAI_API_KEY"):
        print("   ⚠️ OPENAI_API_KEY not set, using dummy key for system check")
        os.environ["OPENAI_API_KEY"] = "sk-dummy-key-for-testing"
    
    agent = TradingAgent(
        mcp_server=mcp_server,
        capital=540.54,  # R10,000
        model="gpt-4o-mini"
    )
    
    print()
    
    # Step 3: Check agent readiness
    print("4️⃣ Checking agent readiness...")
    readiness = agent.check_readiness()
    
    print(f"   Pattern Intelligence: {'✅' if readiness['pattern_intelligence'] else '❌'}")
    print(f"   Confidence Calculator: {'✅' if readiness['confidence_calculator'] else '❌'}")
    print(f"   Pattern Manager: {'✅' if readiness['pattern_manager'] else '❌'}")
    print(f"   Entry Spacing Manager: {'✅' if readiness['spacing_manager'] else '❌'}")
    print()
    print(f"   Systems Ready: {readiness['systems_ready']}/4")
    print(f"   Ready to Trade: {'✅ YES' if readiness['ready_to_trade'] else '❌ NO'}")
    print(f"   Optimal Config: {'✅ YES' if readiness['optimal'] else '⚠️ PARTIAL'}")
    print()
    
    # Step 4: Test pattern intelligence
    if readiness['pattern_intelligence']:
        print("5️⃣ Testing Pattern Intelligence...")
        from intelligence.pattern_intelligence import check_intelligence_health
        
        health = check_intelligence_health()
        print(f"   Status: {health.get('status')}")
        print(f"   Total patterns in DB: {health.get('total_patterns', 0)}")
        print(f"   Patterns with stats: {health.get('patterns_with_stats', 0)}")
        print(f"   Patterns with trades: {health.get('patterns_with_trades', 0)}")
        
        if health.get('issues'):
            print("   Issues:")
            for issue in health.get('issues', []):
                print(f"     {issue}")
        print()
    
    # Step 5: Make a quick decision to test integration
    print("6️⃣ Testing AI decision with intelligence...")
    try:
        decision = await agent.analyze_and_decide("BTCUSDT")
        print(f"   Action: {decision.get('action')}")
        print(f"   Confidence: {decision.get('confidence', 0):.1%}")
        print(f"   Reasoning: {decision.get('reasoning', 'N/A')[:100]}...")
        print()
    except Exception as e:
        print(f"   ⚠️ Decision failed: {e}")
        print()
    
    # Final verdict
    print("╔════════════════════════════════════════════════════════════╗")
    print("║                                                            ║")
    if readiness['optimal']:
        print("║              ✅ AGENT IS FULLY SELF-AWARE! ✅             ║")
        print("║                                                            ║")
        print("║   All intelligence systems operational!                   ║")
        print("║   Agent knows what it needs and has it! 🧠                ║")
    elif readiness['ready_to_trade']:
        print("║           ⚠️ AGENT IS PARTIALLY SELF-AWARE ⚠️            ║")
        print("║                                                            ║")
        print(f"║   {readiness['systems_ready']}/4 systems ready                              ║")
        print("║   Agent can trade but not optimally                       ║")
    else:
        print("║              ❌ AGENT IS NOT SELF-AWARE! ❌               ║")
        print("║                                                            ║")
        print("║   Critical systems missing!                               ║")
        print("║   Agent cannot trade safely                               ║")
    print("║                                                            ║")
    print("╚════════════════════════════════════════════════════════════╝")

if __name__ == "__main__":
    asyncio.run(test_self_aware_agent())
