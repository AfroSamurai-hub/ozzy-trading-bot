"""
🔄 Intelligent Stream Manager - WebSocket with Auto-Retry & Fallback

Manages WebSocket connections with:
- Auto-reconnect on disconnect
- Exponential backoff (1s, 2s, 4s, 8s, max 60s)
- Automatic fallback to mock after failures
- Connection health monitoring
- Quality tracking
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Callable
from enum import Enum

logger = logging.getLogger(__name__)


class ConnectionState(Enum):
    """Connection states"""
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    RECONNECTING = "reconnecting"
    FAILED = "failed"
    USING_MOCK = "using_mock"


class IntelligentStreamManager:
    """
    🔄 Manages WebSocket with intelligence and resilience.
    
    Features:
    - Auto-reconnect with exponential backoff
    - Automatic fallback to mock feed
    - Health monitoring
    - Connection quality tracking
    - Graceful degradation
    """
    
    def __init__(
        self,
        ws_feed,
        mock_feed,
        max_retries: int = 5,
        max_backoff: int = 60,
        fallback_after_failures: int = 3
    ):
        """
        Initialize intelligent stream manager.
        
        Args:
            ws_feed: WebSocket feed instance
            mock_feed: Mock feed instance for fallback
            max_retries: Max reconnection attempts before giving up
            max_backoff: Maximum backoff time in seconds
            fallback_after_failures: Use mock after this many failures
        """
        self.ws_feed = ws_feed
        self.mock_feed = mock_feed
        self.max_retries = max_retries
        self.max_backoff = max_backoff
        self.fallback_after_failures = fallback_after_failures
        
        # State tracking
        self.state = ConnectionState.DISCONNECTED
        self.retry_count = 0
        self.failure_count = 0
        self.using_mock = False
        
        # Health metrics
        self.connection_attempts = 0
        self.successful_connections = 0
        self.total_disconnects = 0
        self.last_connect_time: Optional[datetime] = None
        self.last_disconnect_time: Optional[datetime] = None
        self.uptime_seconds = 0.0
        
        # Current feed (switches between ws and mock)
        self.current_feed = ws_feed
        
        logger.info("🔄 IntelligentStreamManager initialized")
        logger.info(f"   Max retries: {max_retries}")
        logger.info(f"   Max backoff: {max_backoff}s")
        logger.info(f"   Fallback after: {fallback_after_failures} failures")
    
    async def connect(self) -> bool:
        """
        Connect with auto-retry and intelligent fallback.
        
        Returns:
            True if connected successfully (ws or mock), False if failed completely
        """
        logger.info("🔌 Attempting connection...")
        self.state = ConnectionState.CONNECTING
        self.connection_attempts += 1
        
        # Try WebSocket first
        success = await self._connect_with_retry()
        
        if success:
            self.state = ConnectionState.CONNECTED
            self.successful_connections += 1
            self.last_connect_time = datetime.now(timezone.utc)
            self.retry_count = 0
            self.failure_count = 0
            self.using_mock = False
            self.current_feed = self.ws_feed
            logger.info("✅ Connected to WebSocket successfully!")
            return True
        
        # WebSocket failed - check if we should fallback
        if self.failure_count >= self.fallback_after_failures:
            logger.warning(f"⚠️ WebSocket failed {self.failure_count} times, falling back to mock")
            return await self._fallback_to_mock()
        
        # Not enough failures yet - fail this attempt
        self.state = ConnectionState.FAILED
        logger.error("❌ Connection failed!")
        return False
    
    async def _connect_with_retry(self) -> bool:
        """
        Try to connect with exponential backoff.
        
        Returns:
            True if connected, False if all retries exhausted
        """
        self.retry_count = 0
        
        while self.retry_count < self.max_retries:
            try:
                logger.info(f"🔄 Connection attempt {self.retry_count + 1}/{self.max_retries}")
                
                # Try to connect
                await self.ws_feed.connect()
                
                # Success!
                logger.info("✅ WebSocket connected!")
                return True
                
            except Exception as e:
                self.retry_count += 1
                self.failure_count += 1
                
                if self.retry_count < self.max_retries:
                    # Calculate backoff time (exponential: 1s, 2s, 4s, 8s, ...)
                    backoff = min(2 ** (self.retry_count - 1), self.max_backoff)
                    logger.warning(f"⚠️ Connection failed: {e}")
                    logger.info(f"⏳ Retrying in {backoff}s...")
                    
                    self.state = ConnectionState.RECONNECTING
                    await asyncio.sleep(backoff)
                else:
                    logger.error(f"❌ All {self.max_retries} connection attempts failed")
        
        return False
    
    async def _fallback_to_mock(self) -> bool:
        """
        Fallback to mock feed.
        
        Returns:
            True (mock always succeeds)
        """
        logger.warning("🎮 FALLBACK MODE: Switching to mock feed")
        self.state = ConnectionState.USING_MOCK
        self.using_mock = True
        self.current_feed = self.mock_feed
        self.last_connect_time = datetime.now(timezone.utc)
        
        logger.info("✅ Mock feed active")
        return True
    
    async def get_ticker(self) -> Dict:
        """
        Get ticker from current feed (ws or mock).
        
        Handles disconnections and automatic reconnection.
        
        Returns:
            Ticker data from active feed
        """
        try:
            # Get ticker from current feed
            ticker = await self.current_feed.get_ticker()
            
            # Update uptime if connected
            if self.state == ConnectionState.CONNECTED and self.last_connect_time:
                self.uptime_seconds = (
                    datetime.now(timezone.utc) - self.last_connect_time
                ).total_seconds()
            
            return ticker
            
        except Exception as e:
            logger.error(f"❌ Error getting ticker: {e}")
            
            # Only try to reconnect if we're using WebSocket
            if not self.using_mock:
                logger.warning("🔄 Attempting to reconnect...")
                self.total_disconnects += 1
                self.last_disconnect_time = datetime.now(timezone.utc)
                
                # Try to reconnect
                reconnected = await self.connect()
                
                if reconnected:
                    # Retry getting ticker
                    return await self.current_feed.get_ticker()
            
            # If we're here, we're in mock mode or reconnection failed
            raise
    
    def get_health_status(self) -> Dict:
        """
        Get connection health metrics.
        
        Returns:
            Health status dictionary
        """
        uptime_hours = self.uptime_seconds / 3600 if self.uptime_seconds > 0 else 0
        
        # Calculate success rate
        success_rate = 0.0
        if self.connection_attempts > 0:
            success_rate = (self.successful_connections / self.connection_attempts) * 100
        
        # Calculate stability (uptime vs disconnects)
        stability_score = 100.0
        if self.total_disconnects > 0:
            # Penalize frequent disconnects
            stability_score = max(0, 100 - (self.total_disconnects * 10))
        
        return {
            'state': self.state.value,
            'using_mock': self.using_mock,
            'retry_count': self.retry_count,
            'failure_count': self.failure_count,
            
            # Connection stats
            'connection_attempts': self.connection_attempts,
            'successful_connections': self.successful_connections,
            'success_rate': round(success_rate, 1),
            
            # Stability metrics
            'total_disconnects': self.total_disconnects,
            'uptime_hours': round(uptime_hours, 2),
            'stability_score': round(stability_score, 1),
            
            # Timestamps
            'last_connect_time': self.last_connect_time.isoformat() if self.last_connect_time else None,
            'last_disconnect_time': self.last_disconnect_time.isoformat() if self.last_disconnect_time else None,
            
            # Health assessment
            'healthy': self.state in [ConnectionState.CONNECTED, ConnectionState.USING_MOCK],
            'quality': 'excellent' if stability_score > 90 else 'good' if stability_score > 70 else 'degraded'
        }
    
    def log_health_report(self):
        """Log detailed health report"""
        health = self.get_health_status()
        
        logger.info("╔════════════════════════════════════════════════════════════╗")
        logger.info("║                                                            ║")
        logger.info("║               📊 CONNECTION HEALTH REPORT 📊              ║")
        logger.info("║                                                            ║")
        logger.info("╚════════════════════════════════════════════════════════════╝")
        logger.info(f"")
        logger.info(f"State: {health['state'].upper()}")
        logger.info(f"Feed Type: {'🎮 MOCK' if health['using_mock'] else '🌐 WEBSOCKET'}")
        logger.info(f"Health: {'✅ HEALTHY' if health['healthy'] else '❌ UNHEALTHY'}")
        logger.info(f"Quality: {health['quality'].upper()}")
        logger.info(f"")
        logger.info(f"📊 Connection Stats:")
        logger.info(f"   Attempts: {health['connection_attempts']}")
        logger.info(f"   Successful: {health['successful_connections']}")
        logger.info(f"   Success Rate: {health['success_rate']}%")
        logger.info(f"   Disconnects: {health['total_disconnects']}")
        logger.info(f"")
        logger.info(f"⏱️  Uptime: {health['uptime_hours']} hours")
        logger.info(f"📈 Stability Score: {health['stability_score']}/100")
        logger.info(f"")
    
    async def close(self):
        """Close current connection"""
        if hasattr(self.current_feed, 'close'):
            try:
                await self.current_feed.close()
                logger.info("🔌 Connection closed")
            except Exception as e:
                logger.warning(f"Error closing connection: {e}")


async def test_stream_manager():
    """Test the intelligent stream manager"""
    from intelligence.realistic_mock_feed import get_realistic_feed
    
    # Create a mock WebSocket feed that will fail
    class FailingWsFeed:
        async def connect(self):
            raise Exception("WebSocket connection failed (simulated)")
        
        async def get_ticker(self):
            raise Exception("WebSocket disconnected (simulated)")
    
    print("╔════════════════════════════════════════════════════════════╗")
    print("║                                                            ║")
    print("║        🔄 TESTING INTELLIGENT STREAM MANAGER 🔄           ║")
    print("║                                                            ║")
    print("╚════════════════════════════════════════════════════════════╝\n")
    
    # Create feeds
    ws_feed = FailingWsFeed()
    mock_feed = get_realistic_feed()
    
    # Create manager
    manager = IntelligentStreamManager(
        ws_feed=ws_feed,
        mock_feed=mock_feed,
        max_retries=3,
        fallback_after_failures=2
    )
    
    print("📝 Test 1: WebSocket failure → Mock fallback\n")
    
    # First attempt will try ws and fail
    await manager.connect()
    print()
    
    # Second attempt will trigger fallback
    await manager.connect()
    print()
    
    # Get some tickers from mock
    print("📊 Getting tickers from active feed...\n")
    for i in range(3):
        ticker = await manager.get_ticker()
        print(f"Tick {i+1}: ${float(ticker['last_price']):,.2f} | Scenario: {ticker.get('scenario', 'N/A')}")
    
    print()
    
    # Health report
    manager.log_health_report()
    
    print("\n✅ Stream manager test complete!")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(levelname)s - %(message)s')
    asyncio.run(test_stream_manager())
