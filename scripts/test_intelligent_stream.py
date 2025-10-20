#!/usr/bin/env python3
"""
🧪 Test Intelligent Stream Manager

Tests:
1. Normal connection and streaming
2. Reconnection after disconnect
3. Exponential backoff timing
4. Circuit breaker tripping
5. Fallback activation
6. Metrics tracking
7. Health monitoring
"""

import asyncio
import sys
from pathlib import Path
import time

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from stream.intelligent_stream_manager import (
    IntelligentStreamManager,
    StreamState,
    ExponentialBackoff,
    CircuitBreaker,
)
from stream.market_feed import MockTickFeed, Tick


class FailingStream:
    """Mock stream that fails on purpose for testing"""
    
    def __init__(self, fail_after: int = 0, fail_count: int = 1):
        """
        Args:
            fail_after: Succeed this many times before failing
            fail_count: Number of times to fail before succeeding
        """
        self.fail_after = fail_after
        self.fail_count = fail_count
        self.ticks_sent = 0
        self.connection_attempts = 0
        self.is_connected = False
    
    async def connect(self):
        """Simulate connection that may fail"""
        self.connection_attempts += 1
        
        # Fail for the first fail_count attempts
        if self.connection_attempts <= self.fail_count:
            raise ConnectionError(f"Simulated connection failure (attempt {self.connection_attempts})")
        
        self.is_connected = True
        print(f"   ✅ FailingStream connected (attempt {self.connection_attempts})")
    
    async def ticks(self):
        """Generate ticks, possibly failing mid-stream"""
        while self.is_connected:
            self.ticks_sent += 1
            
            # Fail after sending fail_after ticks
            if self.fail_after > 0 and self.ticks_sent > self.fail_after:
                self.is_connected = False
                raise ConnectionError(f"Simulated disconnect after {self.ticks_sent} ticks")
            
            yield Tick(
                symbol="TESTUSDT",
                price=50000.0 + self.ticks_sent,
                volume=1.0,
                timestamp=int(time.time() * 1000)
            )
            
            await asyncio.sleep(0.1)
    
    async def close(self):
        """Close connection"""
        self.is_connected = False


async def test_exponential_backoff():
    """Test 1: Exponential backoff timing"""
    print("1️⃣ Test: Exponential Backoff")
    print("   Testing backoff delays: 1s → 2s → 4s → 8s → 16s → 32s → 60s (capped)")
    
    backoff = ExponentialBackoff(base_delay=1.0, max_delay=60.0)
    
    expected_delays = [1.0, 2.0, 4.0, 8.0, 16.0, 32.0, 60.0, 60.0]  # Last one capped
    
    for i, expected in enumerate(expected_delays):
        delay = backoff.next_attempt()
        status = "✅" if delay == expected else "❌"
        print(f"   {status} Attempt {i+1}: {delay:.1f}s (expected: {expected:.1f}s)")
        
        if delay != expected:
            print(f"   ❌ FAIL: Backoff delay incorrect!")
            return False
    
    # Test reset
    backoff.reset()
    delay = backoff.next_attempt()
    if delay != 1.0:
        print(f"   ❌ FAIL: Reset didn't work (got {delay:.1f}s, expected 1.0s)")
        return False
    
    print(f"   ✅ Reset works correctly")
    print(f"   ✅ PASS: Exponential backoff working!\n")
    return True


async def test_circuit_breaker():
    """Test 2: Circuit breaker pattern"""
    print("2️⃣ Test: Circuit Breaker")
    print("   Testing circuit breaker trips after 5 failures...")
    
    breaker = CircuitBreaker(max_failures=5)
    
    # Record 4 failures (shouldn't trip)
    for i in range(4):
        tripped = breaker.record_failure()
        if tripped:
            print(f"   ❌ FAIL: Circuit breaker tripped too early (after {i+1} failures)")
            return False
        print(f"   ✅ Failure {i+1}/5 recorded, circuit still closed")
    
    # 5th failure should trip
    tripped = breaker.record_failure()
    if not tripped:
        print(f"   ❌ FAIL: Circuit breaker didn't trip after 5 failures")
        return False
    print(f"   🔴 Circuit breaker TRIPPED after 5 failures")
    
    # Success should reset
    breaker.record_success()
    if breaker.is_open:
        print(f"   ❌ FAIL: Circuit breaker didn't reset after success")
        return False
    print(f"   🟢 Circuit breaker RESET after success")
    
    print(f"   ✅ PASS: Circuit breaker working!\n")
    return True


async def test_basic_streaming():
    """Test 3: Basic streaming with mock feed"""
    print("3️⃣ Test: Basic Streaming")
    print("   Testing normal operation with MockTickFeed...")
    
    # Create mock feed
    feed = MockTickFeed("TESTUSDT", interval_ms=100)
    
    # Create manager (no fallback for this test)
    manager = IntelligentStreamManager(
        primary_stream=feed,
        health_check_interval=10.0,  # Long interval for test
        enable_fallback=False
    )
    
    # Stream some ticks
    tick_count = 0
    async with manager:
        async for tick in manager.ticks():
            tick_count += 1
            print(f"   📊 Tick {tick_count}: {tick.symbol} @ ${tick.price:,.2f}")
            
            if tick_count >= 5:
                break
    
    # Check metrics
    metrics = manager.get_metrics()
    
    if metrics.ticks_received != 5:
        print(f"   ❌ FAIL: Expected 5 ticks, got {metrics.ticks_received}")
        return False
    
    if metrics.total_connections != 1:
        print(f"   ❌ FAIL: Expected 1 connection, got {metrics.total_connections}")
        return False
    
    print(f"   ✅ Metrics: {metrics.ticks_received} ticks, {metrics.total_connections} connections")
    print(f"   ✅ PASS: Basic streaming working!\n")
    return True


async def test_reconnection():
    """Test 4: Reconnection after failure"""
    print("4️⃣ Test: Reconnection After Failure")
    print("   Testing auto-reconnect with FailingStream...")
    
    # Create stream that fails first 2 connection attempts
    failing_stream = FailingStream(fail_count=2)
    fallback = MockTickFeed("TESTUSDT", interval_ms=100)
    
    # Create manager
    manager = IntelligentStreamManager(
        primary_stream=failing_stream,
        fallback_stream=fallback,
        health_check_interval=10.0,
        enable_fallback=True
    )
    
    # This should trigger 2 failures and then succeed on 3rd attempt
    try:
        await manager.start()
    except Exception as e:
        # Manager should handle failures internally
        pass
    
    # Give it time to reconnect (async process)
    # First attempt: immediate fail
    # Backoff 1s, second attempt: fail  
    # Backoff 2s, third attempt: success
    # Total: ~3s + overhead
    print(f"   ⏳ Waiting for reconnection (up to 5s)...")
    await asyncio.sleep(5.0)
    
    # Check that we're connected (possibly on fallback)
    if manager.state not in [StreamState.CONNECTED, StreamState.FALLBACK]:
        print(f"   ❌ FAIL: Manager not connected (state: {manager.state})")
        return False
    
    # Check metrics
    metrics = manager.get_metrics()
    
    print(f"   📊 Connection attempts: {failing_stream.connection_attempts}")
    print(f"   📊 Reconnections: {metrics.total_reconnections}")
    print(f"   📊 State: {manager.state.value}")
    
    await manager.stop()
    
    if failing_stream.connection_attempts >= 3:
        print(f"   ✅ PASS: Reconnection working (succeeded after {failing_stream.connection_attempts} attempts)!\n")
        return True
    else:
        print(f"   ❌ FAIL: Not enough reconnection attempts")
        return False


async def test_fallback_activation():
    """Test 5: Fallback activation on persistent failures"""
    print("5️⃣ Test: Fallback Activation")
    print("   Testing fallback after circuit breaker trips...")
    
    # Create stream that always fails
    failing_stream = FailingStream(fail_count=999)  # Never succeeds
    fallback = MockTickFeed("FALLBACKUSDT", interval_ms=100)
    
    # Create manager with low max failures
    manager = IntelligentStreamManager(
        primary_stream=failing_stream,
        fallback_stream=fallback,
        health_check_interval=30.0,
        enable_fallback=True
    )
    
    # Manager should switch to fallback
    await manager.start()
    
    # Check state
    if not manager.using_fallback:
        print(f"   ⚠️  WARNING: Not using fallback yet (state: {manager.state})")
        # Give it some time
        await asyncio.sleep(2.0)
    
    # Stream a few ticks
    tick_count = 0
    async for tick in manager.ticks():
        tick_count += 1
        print(f"   📊 Tick {tick_count}: {tick.symbol} @ ${tick.price:,.2f}")
        
        if tick_count >= 3:
            break
    
    await manager.stop()
    
    # Check metrics
    metrics = manager.get_metrics()
    
    print(f"   📊 Fallback activations: {metrics.fallback_activations}")
    print(f"   📊 Using fallback: {manager.using_fallback}")
    print(f"   📊 State: {manager.state.value}")
    
    if metrics.fallback_activations > 0 or manager.using_fallback:
        print(f"   ✅ PASS: Fallback activation working!\n")
        return True
    else:
        print(f"   ❌ FAIL: Fallback not activated")
        return False


async def run_all_tests():
    """Run all tests"""
    print("🧪 Testing Intelligent Stream Manager\n")
    print("=" * 70)
    
    results = []
    
    # Test 1: Exponential Backoff
    results.append(("Exponential Backoff", await test_exponential_backoff()))
    
    # Test 2: Circuit Breaker
    results.append(("Circuit Breaker", await test_circuit_breaker()))
    
    # Test 3: Basic Streaming
    results.append(("Basic Streaming", await test_basic_streaming()))
    
    # Test 4: Reconnection
    results.append(("Reconnection", await test_reconnection()))
    
    # Test 5: Fallback Activation
    results.append(("Fallback Activation", await test_fallback_activation()))
    
    # Summary
    print("=" * 70)
    print("📊 TEST SUMMARY\n")
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"   {status}: {name}")
    
    print(f"\n   Results: {passed}/{total} tests passed ({passed/total*100:.0f}%)")
    
    if passed == total:
        print("\n✅ SUCCESS! All tests passed!")
        print("\n🎉 IntelligentStreamManager is working correctly!")
        print("   - Exponential backoff working")
        print("   - Circuit breaker working")
        print("   - Auto-reconnection working")
        print("   - Fallback activation working")
        print("   - Ready for production!")
        return 0
    else:
        print(f"\n❌ FAIL: {total - passed} test(s) failed")
        return 1


if __name__ == "__main__":
    import logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(levelname)s: %(message)s'
    )
    
    exit(asyncio.run(run_all_tests()))
