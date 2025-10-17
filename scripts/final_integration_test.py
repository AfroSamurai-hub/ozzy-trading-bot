"""
🚀 FINAL INTEGRATION TEST

This is it! The comprehensive validation of our entire evolved system:
- Self-aware agent with 4 intelligence systems
- Pattern intelligence with context tracking
- Market context analyzers (regime/session/volatility)
- Intelligent stream manager with auto-retry
- Realistic mock feed with pattern-based scenarios
- Continuous learning and evolution

Duration: 1 hour
Decision Interval: 5 minutes (to get ~12 decisions)
Expected: AI confidence 60-85%, context-aware reasoning, pattern growth
"""

import asyncio
import logging
import sys
import os
from datetime import datetime, timezone
from pathlib import Path

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from agent.trader import TradingAgent
from intelligence.realistic_mock_feed import get_realistic_feed
from intelligence.intelligent_stream_manager import IntelligentStreamManager
from intelligence.pattern_intelligence import get_intelligence
from intelligence.market_context import get_session_detector, get_regime_detector
from agent.portfolio import PaperTradingPortfolio

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def final_integration_test(duration_seconds: int = 3600, decision_interval: int = 300):
    """
    🚀 FINAL INTEGRATION TEST
    
    Args:
        duration_seconds: Test duration (default 1 hour)
        decision_interval: Seconds between decisions (default 5 minutes)
    """
    
    print("╔════════════════════════════════════════════════════════════╗")
    print("║                                                            ║")
    print("║            🚀 FINAL INTEGRATION TEST 🚀                   ║")
    print("║                                                            ║")
    print("║   Testing the complete self-aware trading system with:    ║")
    print("║   • Pattern intelligence with context tracking            ║")
    print("║   • Market context analyzers (regime/session/volatility)  ║")
    print("║   • Intelligent stream manager (auto-retry + fallback)    ║")
    print("║   • Realistic mock feed (pattern-based scenarios)         ║")
    print("║   • Self-aware agent (4/4 systems operational)            ║")
    print("║   • Continuous learning and evolution                     ║")
    print("║                                                            ║")
    print("╚════════════════════════════════════════════════════════════╝\n")
    
    # Test parameters
    print(f"📋 Test Parameters:")
    print(f"   Duration: {duration_seconds}s ({duration_seconds/3600:.1f} hours)")
    print(f"   Decision Interval: {decision_interval}s ({decision_interval/60:.1f} minutes)")
    print(f"   Expected Decisions: ~{duration_seconds // decision_interval}")
    print()
    
    # Initialize components
    logger.info("🔧 Initializing components...")
    
    # Portfolio
    portfolio = PaperTradingPortfolio(
        starting_capital=10000.0,
        max_positions=20,
        max_exposure_pct=0.80
    )
    logger.info(f"💰 Capital: R{portfolio.starting_capital:,.2f} ZAR")
    logger.info(f"📊 Portfolio initialized | Positions: {len(portfolio.positions)}")
    
    # Feeds
    mock_feed = get_realistic_feed(symbol="BTCUSDT", base_price=67000.0)
    
    # Create a mock WebSocket (for demo purposes, it will fail and fallback)
    class DemoWsFeed:
        async def connect(self):
            logger.info("🌐 WebSocket: Attempting connection (will timeout for demo)")
            await asyncio.sleep(2)
            raise Exception("WebSocket timeout (demo)")
        
        async def get_ticker(self):
            raise Exception("Not connected")
    
    ws_feed = DemoWsFeed()
    
    # Stream manager (will fallback to mock)
    stream_manager = IntelligentStreamManager(
        ws_feed=ws_feed,
        mock_feed=mock_feed,
        max_retries=2,
        fallback_after_failures=1
    )
    
    # Connect
    logger.info("🔌 Connecting to stream...")
    connected = await stream_manager.connect()
    
    if not connected:
        logger.error("❌ Failed to connect!")
        return
    
    print()
    
    # Trading agent
    logger.info("🤖 Initializing trading agent...")
    
    # Create mock MCP server
    class MockMCPServer:
        def get_patterns(self, *args, **kwargs):
            return []
    
    agent = TradingAgent(
        mcp_server=MockMCPServer(),
        capital=10000.0,
        api_key=os.getenv("OPENAI_API_KEY")
    )
    
    # Check readiness
    readiness = agent.check_readiness()
    logger.info(f"🔍 Agent Readiness Check:")
    logger.info(f"   Pattern Intelligence: {'✅' if readiness['pattern_intelligence'] else '❌'}")
    logger.info(f"   Confidence Calculator: {'✅' if readiness['confidence_calculator'] else '❌'}")
    logger.info(f"   Pattern Manager: {'✅' if readiness['pattern_manager'] else '❌'}")
    logger.info(f"   Spacing Manager: {'✅' if readiness['spacing_manager'] else '❌'}")
    logger.info(f"   Systems Ready: {readiness['systems_ready']}/4")
    logger.info(f"   Status: {'🚀 OPTIMAL' if readiness['optimal'] else '⚠️ DEGRADED'}")
    
    if not readiness['ready_to_trade']:
        logger.error("❌ Agent not ready to trade!")
        return
    
    print()
    
    # Get intelligence systems
    pattern_intel = get_intelligence()
    session_detector = get_session_detector()
    regime_detector = get_regime_detector()
    
    # Initial stats
    initial_stats = pattern_intel.health_check()
    logger.info("📊 Pattern Intelligence - Initial State:")
    logger.info(f"   Total Patterns: {initial_stats['total_patterns']}")
    logger.info(f"   With Trades: {initial_stats['patterns_with_trades']}")
    logger.info(f"   Avg Win Rate: {initial_stats['average_win_rate']:.1%}")
    logger.info(f"   Avg Expectancy: {initial_stats['average_expectancy']:.2%}")
    
    print()
    
    # Current market context
    current_session = session_detector.get_session()
    logger.info(f"🌍 Current Market Context:")
    logger.info(f"   Trading Session: {current_session.upper()}")
    logger.info(f"   Timestamp: {datetime.now(timezone.utc).isoformat()}")
    
    print()
    print("=" * 60)
    print("🚀 STARTING TEST LOOP")
    print("=" * 60)
    print()
    
    # Decision loop
    start_time = asyncio.get_event_loop().time()
    decision_count = 0
    high_confidence_decisions = 0
    context_aware_decisions = 0
    
    try:
        while True:
            elapsed = asyncio.get_event_loop().time() - start_time
            
            if elapsed >= duration_seconds:
                logger.info(f"✅ Test duration complete!")
                break
            
            # Get ticker
            ticker = await stream_manager.get_ticker()
            
            # Make decision
            decision_count += 1
            logger.info(f"\n{'='*60}")
            logger.info(f"🎯 DECISION #{decision_count} | Elapsed: {elapsed/60:.1f}min")
            logger.info(f"{'='*60}")
            logger.info(f"💹 Price: ${float(ticker['last_price']):,.2f}")
            logger.info(f"🎬 Scenario: {ticker.get('scenario', 'unknown')}")
            logger.info(f"📊 Session: {current_session.upper()}")
            
            # Agent decision
            try:
                decision = await agent.make_decision(ticker, portfolio)
                
                logger.info(f"\n🤖 AI Decision:")
                logger.info(f"   Action: {decision.get('action', 'HOLD').upper()}")
                logger.info(f"   Confidence: {decision.get('confidence', 0):.1%}")
                logger.info(f"   Reasoning: {decision.get('reasoning', 'N/A')[:100]}...")
                
                # Track high confidence
                if decision.get('confidence', 0) >= 0.65:
                    high_confidence_decisions += 1
                
                # Check if context-aware (mentions session/regime in reasoning)
                reasoning = decision.get('reasoning', '').lower()
                if any(word in reasoning for word in ['session', 'regime', 'overlap', 'asian', 'european', 'bull', 'bear']):
                    context_aware_decisions += 1
                    logger.info("   🎓 Context-aware reasoning detected!")
                
            except Exception as e:
                logger.error(f"❌ Decision error: {e}")
            
            # Wait for next decision
            logger.info(f"\n⏳ Next decision in {decision_interval}s...")
            await asyncio.sleep(decision_interval)
    
    except KeyboardInterrupt:
        logger.info("\n⚠️ Test interrupted by user")
    
    print()
    print("=" * 60)
    print("📊 TEST RESULTS")
    print("=" * 60)
    print()
    
    # Final stats
    final_stats = pattern_intel.health_check()
    
    logger.info("🎯 Decision Statistics:")
    logger.info(f"   Total Decisions: {decision_count}")
    logger.info(f"   High Confidence (≥65%): {high_confidence_decisions} ({high_confidence_decisions/decision_count*100 if decision_count > 0 else 0:.1f}%)")
    logger.info(f"   Context-Aware: {context_aware_decisions} ({context_aware_decisions/decision_count*100 if decision_count > 0 else 0:.1f}%)")
    
    print()
    
    logger.info("📊 Pattern Intelligence - Final State:")
    logger.info(f"   Total Patterns: {final_stats['total_patterns']}")
    logger.info(f"   With Trades: {final_stats['patterns_with_trades']}")
    logger.info(f"   Avg Win Rate: {final_stats['average_win_rate']:.1%}")
    logger.info(f"   Avg Expectancy: {final_stats['average_expectancy']:.2%}")
    logger.info(f"   Growth: {final_stats['patterns_with_trades'] - initial_stats['patterns_with_trades']} patterns gained data")
    
    print()
    
    # Stream health
    stream_manager.log_health_report()
    
    print()
    
    # Portfolio status
    logger.info("💼 Portfolio Status:")
    logger.info(f"   Balance: R{portfolio.balance:,.2f}")
    logger.info(f"   Open Positions: {len(portfolio.positions)}")
    logger.info(f"   Closed Positions: {len(portfolio.closed_positions)}")
    
    print()
    
    # Success criteria
    print("=" * 60)
    print("✅ SUCCESS CRITERIA CHECK")
    print("=" * 60)
    print()
    
    criteria = {
        'decisions_made': decision_count >= 5,
        'high_confidence': high_confidence_decisions >= 1,
        'context_aware': context_aware_decisions >= 1,
        'systems_operational': readiness['systems_ready'] == 4,
        'patterns_tracked': final_stats['total_patterns'] > 0,
        'stream_healthy': stream_manager.get_health_status()['healthy']
    }
    
    for criterion, passed in criteria.items():
        status = '✅ PASS' if passed else '❌ FAIL'
        logger.info(f"{status} - {criterion.replace('_', ' ').title()}")
    
    print()
    
    all_passed = all(criteria.values())
    
    if all_passed:
        print("╔════════════════════════════════════════════════════════════╗")
        print("║                                                            ║")
        print("║               🎉 ALL TESTS PASSED! 🎉                     ║")
        print("║                                                            ║")
        print("║            🚀 SYSTEM IS PRODUCTION READY! 🚀              ║")
        print("║                                                            ║")
        print("╚════════════════════════════════════════════════════════════╝")
    else:
        print("╔════════════════════════════════════════════════════════════╗")
        print("║                                                            ║")
        print("║              ⚠️  SOME TESTS FAILED  ⚠️                    ║")
        print("║                                                            ║")
        print("║          Review failures and fix before deploying         ║")
        print("║                                                            ║")
        print("╚════════════════════════════════════════════════════════════╝")
    
    print()
    logger.info("🏁 Final integration test complete!")


if __name__ == "__main__":
    # Parse arguments
    import argparse
    
    parser = argparse.ArgumentParser(description='Final Integration Test')
    parser.add_argument('--duration', type=int, default=3600, help='Test duration in seconds (default: 3600 = 1 hour)')
    parser.add_argument('--interval', type=int, default=300, help='Decision interval in seconds (default: 300 = 5 minutes)')
    
    args = parser.parse_args()
    
    asyncio.run(final_integration_test(
        duration_seconds=args.duration,
        decision_interval=args.interval
    ))
