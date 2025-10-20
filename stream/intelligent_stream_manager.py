"""
🔌 Intelligent Stream Manager - Never Die Architecture

This manager wraps any market data stream (Bybit WebSocket, Mock Feed, etc.)
and provides enterprise-grade reliability features:

1. Auto-reconnect with exponential backoff
2. Health monitoring (heartbeat checks)
3. Connection quality metrics
4. Graceful fallback to mock feed
5. Circuit breaker pattern
6. Event logging and metrics

Philosophy: "The system must NEVER die due to network issues."

Usage:
    manager = IntelligentStreamManager(
        primary_stream=BybitMarketStream("BTCUSDT"),
        fallback_stream=MockTickFeed("BTCUSDT"),
        health_check_interval=30.0
    )
    
    async with manager:
        async for tick in manager.ticks():
            # Process tick
            # Manager handles reconnection transparently
            pass
"""

import asyncio
import time
import logging
from dataclasses import dataclass, field
from typing import AsyncIterator, Optional, Callable, Any
from enum import Enum

logger = logging.getLogger(__name__)


class StreamState(Enum):
    """Stream connection states"""
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    RECONNECTING = "reconnecting"
    FALLBACK = "fallback"  # Using fallback feed
    CIRCUIT_OPEN = "circuit_open"  # Circuit breaker tripped


@dataclass
class ConnectionMetrics:
    """Track connection quality and reliability"""
    total_connections: int = 0
    total_disconnections: int = 0
    total_reconnections: int = 0
    successful_reconnections: int = 0
    failed_reconnections: int = 0
    fallback_activations: int = 0
    
    # Timing metrics
    connection_start_time: float = 0.0
    total_uptime_seconds: float = 0.0
    total_downtime_seconds: float = 0.0
    last_disconnect_time: float = 0.0
    
    # Quality metrics
    ticks_received: int = 0
    ticks_dropped: int = 0
    last_tick_time: float = 0.0
    average_tick_latency: float = 0.0
    
    def get_uptime_percentage(self) -> float:
        """Calculate uptime percentage"""
        total_time = self.total_uptime_seconds + self.total_downtime_seconds
        if total_time == 0:
            return 0.0
        return (self.total_uptime_seconds / total_time) * 100.0
    
    def get_current_uptime(self) -> float:
        """Get current uptime in seconds"""
        if self.connection_start_time == 0:
            return 0.0
        return time.time() - self.connection_start_time
    
    def record_connection(self):
        """Record successful connection"""
        self.total_connections += 1
        self.connection_start_time = time.time()
    
    def record_disconnection(self):
        """Record disconnection"""
        self.total_disconnections += 1
        if self.connection_start_time > 0:
            uptime = time.time() - self.connection_start_time
            self.total_uptime_seconds += uptime
        self.last_disconnect_time = time.time()
    
    def record_tick(self, latency_ms: float = 0.0):
        """Record received tick"""
        self.ticks_received += 1
        self.last_tick_time = time.time()
        
        # Update average latency (exponential moving average)
        alpha = 0.1  # Smoothing factor
        self.average_tick_latency = (alpha * latency_ms) + ((1 - alpha) * self.average_tick_latency)


@dataclass
class ExponentialBackoff:
    """Exponential backoff calculator for reconnection attempts"""
    base_delay: float = 1.0  # Start with 1 second
    max_delay: float = 60.0  # Cap at 60 seconds
    multiplier: float = 2.0  # Double each time
    current_attempt: int = 0
    
    def get_delay(self) -> float:
        """Get delay for current attempt"""
        delay = min(self.base_delay * (self.multiplier ** self.current_attempt), self.max_delay)
        return delay
    
    def next_attempt(self) -> float:
        """Increment attempt and return delay"""
        delay = self.get_delay()
        self.current_attempt += 1
        return delay
    
    def reset(self):
        """Reset after successful connection"""
        self.current_attempt = 0


@dataclass
class CircuitBreaker:
    """Circuit breaker to prevent infinite reconnection attempts"""
    max_failures: int = 5  # Trip after 5 consecutive failures
    reset_timeout: float = 300.0  # Reset after 5 minutes of success
    
    failures: int = 0
    is_open: bool = False
    last_success_time: float = 0.0
    opened_time: float = 0.0
    
    def record_failure(self) -> bool:
        """
        Record a failure and check if circuit should open.
        
        Returns:
            True if circuit breaker tripped (too many failures)
        """
        self.failures += 1
        
        if self.failures >= self.max_failures and not self.is_open:
            self.is_open = True
            self.opened_time = time.time()
            logger.error(
                f"🔴 CIRCUIT BREAKER TRIPPED after {self.failures} failures! "
                f"Switching to fallback mode."
            )
            return True
        
        return self.is_open
    
    def record_success(self):
        """Record successful connection"""
        self.failures = 0
        self.last_success_time = time.time()
        
        # Close circuit breaker if it was open
        if self.is_open:
            logger.info("🟢 Circuit breaker RESET after successful connection")
            self.is_open = False
    
    def should_attempt_reconnect(self) -> bool:
        """Check if we should try to reconnect from fallback"""
        if not self.is_open:
            return True
        
        # Try to reset circuit breaker after timeout
        time_since_opened = time.time() - self.opened_time
        if time_since_opened >= self.reset_timeout:
            logger.info(f"🔄 Circuit breaker timeout ({self.reset_timeout}s) expired, attempting reconnect...")
            self.is_open = False
            self.failures = 0
            return True
        
        return False


class IntelligentStreamManager:
    """
    🧠 Intelligent stream manager with auto-reconnect and fallback.
    
    Features:
    - Automatic reconnection with exponential backoff
    - Health monitoring with heartbeat checks
    - Circuit breaker to prevent infinite retries
    - Graceful fallback to backup stream
    - Connection quality metrics
    - Event callbacks for monitoring
    """
    
    def __init__(
        self,
        primary_stream: Any,
        fallback_stream: Optional[Any] = None,
        health_check_interval: float = 30.0,
        tick_timeout: float = 60.0,
        enable_fallback: bool = True,
    ):
        """
        Initialize intelligent stream manager.
        
        Args:
            primary_stream: Main stream (e.g., BybitMarketStream)
            fallback_stream: Backup stream (e.g., MockTickFeed)
            health_check_interval: How often to check connection health (seconds)
            tick_timeout: Max time without tick before considering connection dead (seconds)
            enable_fallback: Whether to use fallback stream on failures
        """
        self.primary_stream = primary_stream
        self.fallback_stream = fallback_stream
        self.health_check_interval = health_check_interval
        self.tick_timeout = tick_timeout
        self.enable_fallback = enable_fallback
        
        # State management
        self.state = StreamState.DISCONNECTED
        self.using_fallback = False
        self.stop_event = asyncio.Event()
        
        # Reliability components
        self.metrics = ConnectionMetrics()
        self.backoff = ExponentialBackoff()
        self.circuit_breaker = CircuitBreaker()
        
        # Health monitoring
        self._health_check_task: Optional[asyncio.Task] = None
        self._current_stream = None
        
        logger.info("🔌 IntelligentStreamManager initialized")
        logger.info(f"   Primary: {type(primary_stream).__name__}")
        logger.info(f"   Fallback: {type(fallback_stream).__name__ if fallback_stream else 'None'}")
        logger.info(f"   Health checks: every {health_check_interval}s")
    
    async def __aenter__(self):
        """Start the manager"""
        await self.start()
        return self
    
    async def __aexit__(self, exc_type, exc, tb):
        """Stop the manager"""
        await self.stop()
    
    async def start(self):
        """Start the stream manager"""
        logger.info("🚀 Starting IntelligentStreamManager...")
        
        # Try to connect to primary stream
        success = await self._connect_primary()
        
        # If initial connection fails, start background reconnection
        if not success:
            logger.info("🔄 Initial connection failed, will retry in background...")
            # Start reconnection in background (don't await)
            asyncio.create_task(self._reconnect())
        
        # Start health monitoring
        self._health_check_task = asyncio.create_task(self._health_monitor())
        
        logger.info("✅ IntelligentStreamManager started")
    
    async def stop(self):
        """Stop the stream manager"""
        logger.info("🛑 Stopping IntelligentStreamManager...")
        
        self.stop_event.set()
        
        # Stop health monitoring
        if self._health_check_task:
            self._health_check_task.cancel()
            try:
                await self._health_check_task
            except asyncio.CancelledError:
                pass
        
        # Close current stream
        if self._current_stream:
            if hasattr(self._current_stream, 'close'):
                await self._current_stream.close()
            elif hasattr(self._current_stream, 'stop'):
                self._current_stream.stop()
        
        logger.info("✅ IntelligentStreamManager stopped")
    
    async def _connect_primary(self) -> bool:
        """
        Attempt to connect to primary stream.
        
        Returns:
            True if successful, False otherwise
        """
        try:
            self.state = StreamState.CONNECTING
            logger.info("🔌 Connecting to primary stream...")
            
            # Connect primary stream
            if hasattr(self.primary_stream, 'connect'):
                await self.primary_stream.connect()
            
            self._current_stream = self.primary_stream
            self.using_fallback = False
            self.state = StreamState.CONNECTED
            
            # Update metrics and reliability components
            self.metrics.record_connection()
            self.backoff.reset()
            self.circuit_breaker.record_success()
            
            logger.info("✅ Connected to primary stream")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to connect to primary stream: {e}")
            self.metrics.record_disconnection()
            self.circuit_breaker.record_failure()
            return False
    
    async def _switch_to_fallback(self):
        """Switch to fallback stream"""
        if not self.enable_fallback or not self.fallback_stream:
            logger.error("❌ No fallback stream available!")
            return False
        
        try:
            logger.warning("⚠️  Switching to FALLBACK stream...")
            self.state = StreamState.FALLBACK
            self._current_stream = self.fallback_stream
            self.using_fallback = True
            self.metrics.fallback_activations += 1
            logger.info("✅ Switched to fallback stream")
            return True
        except Exception as e:
            logger.error(f"❌ Failed to switch to fallback: {e}")
            return False
    
    async def _reconnect(self):
        """Attempt to reconnect to primary stream"""
        self.state = StreamState.RECONNECTING
        self.metrics.total_reconnections += 1
        
        # Get backoff delay
        delay = self.backoff.next_attempt()
        logger.info(f"🔄 Reconnecting in {delay:.1f}s (attempt {self.backoff.current_attempt})...")
        await asyncio.sleep(delay)
        
        success = await self._connect_primary()
        
        if success:
            self.metrics.successful_reconnections += 1
            logger.info("✅ Reconnection successful!")
            return True
        else:
            self.metrics.failed_reconnections += 1
            
            # Check circuit breaker
            if self.circuit_breaker.record_failure():
                # Circuit breaker tripped, switch to fallback
                await self._switch_to_fallback()
            
            return False
    
    async def _health_monitor(self):
        """Background task to monitor connection health"""
        logger.info(f"💓 Health monitor started (checking every {self.health_check_interval}s)")
        
        while not self.stop_event.is_set():
            try:
                await asyncio.sleep(self.health_check_interval)
                
                # Check if we've received ticks recently
                if self.metrics.last_tick_time > 0:
                    time_since_last_tick = time.time() - self.metrics.last_tick_time
                    
                    if time_since_last_tick > self.tick_timeout:
                        logger.warning(
                            f"⚠️  No ticks received for {time_since_last_tick:.1f}s "
                            f"(timeout: {self.tick_timeout}s) - connection may be dead"
                        )
                        
                        # Try to reconnect if not using fallback
                        if not self.using_fallback:
                            logger.info("🔄 Triggering reconnection due to tick timeout...")
                            self.metrics.record_disconnection()
                            await self._reconnect()
                
                # Log health status
                uptime_pct = self.metrics.get_uptime_percentage()
                current_uptime = self.metrics.get_current_uptime()
                
                logger.debug(
                    f"💓 Health: State={self.state.value}, "
                    f"Uptime={current_uptime:.0f}s ({uptime_pct:.1f}%), "
                    f"Ticks={self.metrics.ticks_received}, "
                    f"Reconnects={self.metrics.total_reconnections}"
                )
                
                # Try to reconnect from fallback if circuit breaker allows
                if self.using_fallback and self.circuit_breaker.should_attempt_reconnect():
                    logger.info("🔄 Attempting to reconnect to primary from fallback...")
                    success = await self._connect_primary()
                    if success:
                        logger.info("✅ Successfully reconnected to primary!")
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"❌ Health monitor error: {e}")
    
    async def ticks(self) -> AsyncIterator:
        """
        Get tick iterator with automatic reconnection.
        
        Yields:
            Ticks from current stream (primary or fallback)
        """
        while not self.stop_event.is_set():
            try:
                # Get ticks from current stream
                if self._current_stream is None:
                    logger.warning("⚠️  No active stream, attempting connection...")
                    success = await self._connect_primary()
                    if not success:
                        await self._switch_to_fallback()
                    
                    if self._current_stream is None:
                        logger.error("❌ No stream available, waiting before retry...")
                        await asyncio.sleep(5.0)
                        continue
                
                # Stream ticks
                async for tick in self._current_stream.ticks():
                    self.metrics.record_tick()
                    yield tick
                
            except Exception as e:
                logger.error(f"❌ Stream error: {e}")
                self.metrics.record_disconnection()
                
                # Try to reconnect
                if not self.using_fallback:
                    await self._reconnect()
                else:
                    # Already on fallback, just wait and continue
                    logger.warning("⚠️  Error on fallback stream, waiting...")
                    await asyncio.sleep(5.0)
    
    def get_metrics(self) -> ConnectionMetrics:
        """Get current connection metrics"""
        return self.metrics
    
    def get_state(self) -> StreamState:
        """Get current stream state"""
        return self.state
    
    def is_healthy(self) -> bool:
        """Check if stream is healthy"""
        if self.state == StreamState.CONNECTED:
            # Check if we're receiving ticks
            if self.metrics.last_tick_time == 0:
                return False  # Never received ticks
            
            time_since_last_tick = time.time() - self.metrics.last_tick_time
            return time_since_last_tick < self.tick_timeout
        
        return False


# Example usage
if __name__ == "__main__":
    async def demo():
        from stream.market_feed import BybitMarketStream, MockTickFeed
        
        # Create streams
        primary = BybitMarketStream("BTCUSDT", testnet=True)
        fallback = MockTickFeed("BTCUSDT")
        
        # Create manager
        manager = IntelligentStreamManager(
            primary_stream=primary,
            fallback_stream=fallback,
            health_check_interval=30.0
        )
        
        # Use manager
        async with manager:
            tick_count = 0
            async for tick in manager.ticks():
                tick_count += 1
                print(f"Tick {tick_count}: {tick.symbol} @ ${tick.price:,.2f}")
                
                if tick_count >= 100:
                    break
            
            # Print metrics
            metrics = manager.get_metrics()
            print(f"\nMetrics:")
            print(f"  Uptime: {metrics.get_uptime_percentage():.1f}%")
            print(f"  Ticks: {metrics.ticks_received}")
            print(f"  Reconnections: {metrics.total_reconnections}")
    
    logging.basicConfig(level=logging.INFO)
    asyncio.run(demo())
