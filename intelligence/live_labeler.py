"""
A background service that monitors open trades and labels patterns in the vector
database with their outcomes (WIN, LOSS, NEUTRAL) in real-time.
"""

import asyncio
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List

from pybit.unified_trading import WebSocket  # V5 API (upgraded from V3 usdt_perpetual)

# Add project root to path to allow imports
import sys
sys.path.append(str(Path(__file__).parent.parent))

from intelligence.rolling_window_db import RollingWindowPatternDB

# --- Configuration ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

DB_PATH = str(Path(__file__).parent.parent / "data/vector_db")
API_KEY = os.getenv("BYBIT_API_KEY")
API_SECRET = os.getenv("BYBIT_API_SECRET")
SYMBOL = "BTCUSDT"

# How often to check for patterns to label
CHECK_INTERVAL_SECONDS = 5
# How long to track a pending pattern before giving up (in minutes)
MAX_PATTERN_AGE_MINUTES = 60

# Define Take Profit and Stop Loss percentages
TAKE_PROFIT_PCT = 1.0
STOP_LOSS_PCT = 0.5


class LiveLabeler:
    """
    A service that connects to a live price feed and our vector DB
    to label trading patterns as they resolve.
    """

    def __init__(self):
        self.db = RollingWindowPatternDB(persist_directory=DB_PATH)
        self.ws = None
        self.latest_price: float | None = None
        self.is_running = False
        logger.info("🏷️ Live Labeler initialized.")

    def _handle_message(self, msg: Dict):
        """Callback function to handle incoming WebSocket messages (V5 API format)."""
        # V5 API: trade data comes as a list under "data" key, each item has "p" for price
        if "data" in msg and isinstance(msg["data"], list) and len(msg["data"]) > 0:
            self.latest_price = float(msg["data"][0].get("p", self.latest_price or 0))

    async def _setup_websocket(self):
        """Initializes and connects the WebSocket client (V5 API)."""
        logger.info("🔌 Setting up WebSocket connection to Bybit V5...")
        self.ws = WebSocket(
            channel_type="linear",  # V5 API uses channel_type instead of test
            testnet=False,  # Use mainnet
        )
        # V5 API uses trade_stream instead of instrument_info_stream
        self.ws.trade_stream(symbol=SYMBOL, callback=self._handle_message)
        logger.info("✅ WebSocket connected (V5 API).")

    def _get_pending_patterns(self) -> List[Dict]:
        """Fetches all patterns from the DB with a 'PENDING' label."""
        try:
            cutoff_timestamp = time.time() - (MAX_PATTERN_AGE_MINUTES * 60)
            
            results = self.db.collection.get(
                where={"label": "PENDING"},
                include=["metadatas"]
            )
            
            pending_patterns = []
            for i, meta in enumerate(results['metadatas']):
                if meta.get('timestamp', 0) > cutoff_timestamp:
                    pattern = {
                        "id": results['ids'][i],
                        "metadata": meta
                    }
                    pending_patterns.append(pattern)

            if pending_patterns:
                logger.info(f"Found {len(pending_patterns)} pending patterns to track.")
            return pending_patterns

        except Exception as e:
            logger.error(f"❌ Error fetching pending patterns: {e}", exc_info=True)
            return []

    def _process_pending_patterns(self):
        """The core logic to check and label patterns."""
        if self.latest_price is None:
            logger.warning("⏳ No live price yet. Skipping processing.")
            return

        pending_patterns = self._get_pending_patterns()
        if not pending_patterns:
            return

        for pattern in pending_patterns:
            meta = pattern['metadata']
            entry_price = meta.get('price')

            if not entry_price:
                continue

            # Assuming a 'BUY' trade for now. A real system would check trade direction.
            tp_price = entry_price * (1 + TAKE_PROFIT_PCT / 100)
            sl_price = entry_price * (1 - STOP_LOSS_PCT / 100)

            new_label = None
            if self.latest_price >= tp_price:
                new_label = "WIN"
                logger.info(f"🎉 Pattern {pattern['id']} hit Take Profit! Price: {self.latest_price:.2f} >= {tp_price:.2f}")
            elif self.latest_price <= sl_price:
                new_label = "LOSS"
                logger.warning(f"💔 Pattern {pattern['id']} hit Stop Loss! Price: {self.latest_price:.2f} <= {sl_price:.2f}")

            if new_label:
                self._update_pattern_label(pattern['id'], new_label, self.latest_price)

    def _update_pattern_label(self, pattern_id: str, new_label: str, exit_price: float):
        """Updates a pattern's metadata in the database."""
        try:
            # ChromaDB's `update` replaces the entire metadata, so we must get the old one first.
            existing_pattern = self.db.collection.get(ids=[pattern_id], include=["metadatas"])
            if not existing_pattern['metadatas']:
                logger.error(f"Could not find pattern {pattern_id} to update.")
                return

            updated_meta = existing_pattern['metadatas'][0]
            updated_meta['label'] = new_label
            updated_meta['outcome'] = new_label.lower()
            updated_meta['exit_price'] = exit_price
            updated_meta['labeled_at'] = datetime.now(timezone.utc).isoformat()

            self.db.collection.update(
                ids=[pattern_id],
                metadatas=[updated_meta]
            )
            logger.info(f"✅ Labeled pattern {pattern_id} as {new_label}.")
        except Exception as e:
            logger.error(f"❌ Failed to update pattern {pattern_id}: {e}", exc_info=True)

    async def run(self):
        """Main execution loop for the service."""
        self.is_running = True
        await self._setup_websocket()
        
        logger.info("🚀 Live Labeler service started. Press Ctrl+C to stop.")
        
        while self.is_running:
            try:
                self._process_pending_patterns()
                await asyncio.sleep(CHECK_INTERVAL_SECONDS)
            except KeyboardInterrupt:
                self.is_running = False
                logger.info("🛑 Keyboard interrupt received. Shutting down...")
            except Exception as e:
                logger.critical(f"💥 An unexpected error occurred in the main loop: {e}", exc_info=True)
                self.is_running = False

        if self.ws:
            self.ws.exit()
        logger.info("👋 Live Labeler service stopped.")


if __name__ == "__main__":
    if not all([API_KEY, API_SECRET]):
        logger.error("BYBIT_API_KEY and BYBIT_API_SECRET environment variables must be set.")
    else:
        labeler = LiveLabeler()
        try:
            asyncio.run(labeler.run())
        except KeyboardInterrupt:
            logger.info("Program terminated by user.")
        except Exception as e:
            logger.error(f"Failed to run LiveLabeler: {e}")
