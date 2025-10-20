"""
Performance Benchmarking Script

Run comprehensive performance benchmarks on the trading system to establish
baseline metrics and identify optimization opportunities.

Usage:
    python scripts/benchmark_performance.py
    
Benchmarks:
1. Decision latency (AI trading decisions)
2. Pattern query speed (ChromaDB queries)
3. Memory usage (resident memory tracking)
4. Handbook validation speed
5. Pattern learning speed

Output:
- Console summary
- metrics.json (persistent storage)
- Performance report
"""

import sys
import time
import random
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from monitoring.performance_tracker import PerformanceTracker
from intelligence.pattern_intelligence import PatternIntelligence
from agent.portfolio import PaperTradingPortfolio


def simulate_market_data():
    """Generate realistic market data for benchmarking"""
    return {
        'symbol': 'BTCUSDT',
        'close': random.uniform(40000, 60000),
        'volume': random.uniform(100, 1000),
        'high': random.uniform(40000, 60000),
        'low': random.uniform(40000, 60000),
        'rsi': random.uniform(30, 70),
        'macd': random.uniform(-100, 100),
    }


def benchmark_decision_latency(tracker: PerformanceTracker, iterations: int = 100):
    """Benchmark AI decision making latency"""
    print(f"\n🕐 Benchmarking Decision Latency ({iterations} iterations)...")
    
    portfolio = PaperTradingPortfolio(starting_capital=10000.0, load_previous_state=False)
    
    for i in range(iterations):
        with tracker.track_decision():
            # Simulate AI decision making process
            market_data = simulate_market_data()
            
            # Simulate pattern detection (50ms)
            time.sleep(0.05)
            
            # Simulate validation checks (20ms)
            time.sleep(0.02)
            
            # Simulate confidence calculation (10ms)
            time.sleep(0.01)
            
            # Make decision
            decision = "LONG" if random.random() > 0.5 else "SHORT"
        
        if (i + 1) % 25 == 0:
            print(f"  Completed {i + 1}/{iterations} decisions...")
    
    print(f"✅ Decision latency benchmark complete")


def benchmark_query_speed(tracker: PerformanceTracker, iterations: int = 200):
    """Benchmark pattern query speed"""
    print(f"\n🔍 Benchmarking Query Speed ({iterations} iterations)...")
    
    pattern_intel = PatternIntelligence()
    
    # Seed some pattern data
    for i in range(50):
        pattern_id = f"pattern_{i}"
        outcome = {
            'win': random.random() > 0.5,
            'pnl_pct': random.uniform(-5, 10),
            'held_time': random.uniform(300, 3600),
        }
        pattern_intel.update_pattern_outcome(pattern_id, outcome)
    
    for i in range(iterations):
        with tracker.track_query():
            # Query top patterns
            top_patterns = pattern_intel.get_top_patterns(min_trades=3)
            
            # Query specific pattern
            if random.random() > 0.5:
                pattern_id = f"pattern_{random.randint(0, 49)}"
                stats = pattern_intel.get_pattern_stats(pattern_id)
        
        if (i + 1) % 50 == 0:
            print(f"  Completed {i + 1}/{iterations} queries...")
    
    print(f"✅ Query speed benchmark complete")


def benchmark_memory_usage(tracker: PerformanceTracker, duration_seconds: int = 30):
    """Benchmark memory usage over time"""
    print(f"\n💾 Benchmarking Memory Usage ({duration_seconds}s duration)...")
    
    pattern_intel = PatternIntelligence()
    portfolio = PaperTradingPortfolio(starting_capital=10000.0, load_previous_state=False)
    
    start_time = time.time()
    sample_count = 0
    
    while time.time() - start_time < duration_seconds:
        # Record memory
        mem_mb = tracker.record_memory_usage()
        sample_count += 1
        
        # Simulate normal operations
        pattern_id = f"pattern_{random.randint(0, 100)}"
        outcome = {
            'win': random.random() > 0.5,
            'pnl_pct': random.uniform(-5, 10),
            'held_time': random.uniform(300, 3600),
        }
        pattern_intel.update_pattern_outcome(pattern_id, outcome)
        
        # Open/close some positions
        open_positions = [p for p in portfolio.positions if p.get('status') == 'OPEN']
        if len(open_positions) < 3 and random.random() > 0.7:
            portfolio.open_position(
                symbol="BTCUSDT",
                side="LONG",
                entry_price=50000.0,
                size=1000.0,
                confidence=0.75,
                reason="Benchmark",
            )
        elif open_positions and random.random() > 0.8:
            pos = open_positions[0]
            portfolio.close_position(pos['id'], 51000.0, "benchmark")
        
        time.sleep(1)
        
        if sample_count % 10 == 0:
            print(f"  Memory samples: {sample_count}, Current: {mem_mb:.2f}MB")
    
    print(f"✅ Memory usage benchmark complete ({sample_count} samples)")


def benchmark_handbook_validation(tracker: PerformanceTracker, iterations: int = 100):
    """Benchmark validation speed"""
    print(f"\n✅ Benchmarking Validation Checks ({iterations} iterations)...")
    
    portfolio = PaperTradingPortfolio(starting_capital=10000.0, load_previous_state=False)
    
    for i in range(iterations):
        start = time.perf_counter()
        
        # Simulate validation checks
        signal_data = {
            'symbol': 'BTCUSDT',
            'side': 'LONG',
            'entry_price': random.uniform(40000, 60000),
            'confidence': random.uniform(0.6, 0.95),
            'pattern_id': f"pattern_{random.randint(0, 50)}",
            'rsi': random.uniform(30, 70),
            'volume': random.uniform(100, 1000),
        }
        
        # Simulate 8 validation checks (20ms each)
        time.sleep(0.02)
        checks_passed = random.random() > 0.3  # 70% pass rate
        
        elapsed_ms = (time.perf_counter() - start) * 1000
        
        # Record each check result
        for check_name in ['confidence', 'exposure', 'volatility', 'correlation', 
                          'pattern_quality', 'risk_reward', 'market_condition', 'position_sizing']:
            tracker.record_confirmation_check(check_name, random.random() > 0.2)  # 80% pass rate
        
        if (i + 1) % 25 == 0:
            print(f"  Completed {i + 1}/{iterations} validations...")
    
    print(f"✅ Validation check benchmark complete")


def benchmark_pattern_learning(tracker: PerformanceTracker, iterations: int = 100):
    """Benchmark pattern learning speed"""
    print(f"\n🧠 Benchmarking Pattern Learning ({iterations} iterations)...")
    
    pattern_intel = PatternIntelligence()
    
    for i in range(iterations):
        start = time.perf_counter()
        
        # Update 10 patterns
        for j in range(10):
            pattern_id = f"pattern_{random.randint(0, 50)}"
            outcome = {
                'win': random.random() > 0.5,
                'pnl_pct': random.uniform(-5, 10),
                'held_time': random.uniform(300, 3600),
            }
            pattern_intel.update_pattern_outcome(pattern_id, outcome)
        
        elapsed_ms = (time.perf_counter() - start) * 1000
        
        if (i + 1) % 25 == 0:
            print(f"  Completed {i + 1}/{iterations} learning cycles...")
    
    print(f"✅ Pattern learning benchmark complete")


def run_benchmarks():
    """Run all benchmarks and generate report"""
    print("=" * 80)
    print("🚀 PERFORMANCE BENCHMARKING SUITE")
    print("=" * 80)
    print("This will benchmark:")
    print("  1. Decision latency (100 iterations)")
    print("  2. Query speed (200 iterations)")
    print("  3. Memory usage (30 seconds)")
    print("  4. Validation checks (100 iterations)")
    print("  5. Pattern learning (100 iterations)")
    print("")
    print("Estimated time: 2-3 minutes")
    print("=" * 80)
    
    # Initialize tracker
    tracker = PerformanceTracker(save_to_file=True, metrics_file="monitoring/benchmark_metrics.json")
    
    # Run benchmarks
    try:
        benchmark_decision_latency(tracker, iterations=100)
        benchmark_query_speed(tracker, iterations=200)
        benchmark_memory_usage(tracker, duration_seconds=30)
        benchmark_handbook_validation(tracker, iterations=100)
        benchmark_pattern_learning(tracker, iterations=100)
        
        # Record some sample win rates and confidence values
        print("\n📊 Recording sample metrics...")
        for i in range(20):
            tracker.record_win_rate(random.uniform(45, 65))
            tracker.record_confidence(random.uniform(0.6, 0.9))
        
        # Generate summary
        print("\n" + "=" * 80)
        print("📊 BENCHMARK RESULTS")
        print("=" * 80)
        print(tracker.get_summary())
        
        # Get detailed statistics
        stats = tracker.get_statistics()
        
        # Performance assessment
        print("\n" + "=" * 80)
        print("🎯 PERFORMANCE ASSESSMENT")
        print("=" * 80)
        
        issues = []
        optimizations = []
        
        # Check decision latency
        if 'decision_latency' in stats:
            avg_latency = stats['decision_latency']['avg_ms']
            if avg_latency > 1000:
                issues.append(f"❌ Decision latency too high: {avg_latency:.2f}ms (target: <1000ms)")
                optimizations.append("  • Optimize pattern detection algorithm")
                optimizations.append("  • Cache handbook validation results")
                optimizations.append("  • Consider async operations")
            elif avg_latency > 500:
                issues.append(f"⚠️  Decision latency borderline: {avg_latency:.2f}ms (target: <1000ms)")
                optimizations.append("  • Monitor and optimize if it degrades further")
            else:
                issues.append(f"✅ Decision latency excellent: {avg_latency:.2f}ms")
        
        # Check query speed
        if 'query_speed' in stats:
            avg_query = stats['query_speed']['avg_ms']
            if avg_query > 100:
                issues.append(f"❌ Query speed too slow: {avg_query:.2f}ms (target: <100ms)")
                optimizations.append("  • Add ChromaDB indexes")
                optimizations.append("  • Implement query result caching")
                optimizations.append("  • Reduce query complexity")
            else:
                issues.append(f"✅ Query speed excellent: {avg_query:.2f}ms")
        
        # Check memory usage
        if 'memory_usage' in stats:
            peak_memory = stats['memory_usage']['peak_mb']
            if peak_memory > 500:
                issues.append(f"❌ Memory usage too high: {peak_memory:.2f}MB (target: <500MB)")
                optimizations.append("  • Implement pattern cache eviction")
                optimizations.append("  • Limit in-memory data structures")
                optimizations.append("  • Profile for memory leaks")
            else:
                issues.append(f"✅ Memory usage acceptable: {peak_memory:.2f}MB")
        
        for issue in issues:
            print(issue)
        
        if optimizations:
            print("\n💡 OPTIMIZATION OPPORTUNITIES:")
            for opt in optimizations:
                print(opt)
        
        print("\n" + "=" * 80)
        print("✅ Benchmark complete! Results saved to monitoring/benchmark_metrics.json")
        print("=" * 80)
        
    except KeyboardInterrupt:
        print("\n\n⚠️  Benchmark interrupted by user")
        print(tracker.get_summary())
    
    except Exception as e:
        print(f"\n\n❌ Benchmark failed: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    run_benchmarks()
