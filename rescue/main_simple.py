"""
OZZY SIMPLE - Main Trading Bot
The simplest possible trading bot. No complexity, just works.
"""
from __future__ import annotations
import sys
import time
import logging
import numpy as np
from datetime import datetime
from pathlib import Path
from typing import Dict

# Add config to path
sys.path.append(str(Path(__file__).parent.parent))

from config import config
from config.config_validator import validate_config
from src.simple_signals import SimpleSignalGenerator
from src.simple_risk import SimpleRiskManager
from src.bybit_client import BybitClient

# Setup logging
logging.basicConfig(
    level=config.LOG_LEVEL,
    format='%(asctime)s | %(levelname)s | %(message)s',
    handlers=[
        logging.FileHandler(config.LOG_FILE),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class SimpleTradingBot:
    """
    The simplest possible trading bot.
    
    What it does:
    1. Gets candles from Bybit
    2. Runs simple RSI+EMA+Volume strategy
    3. Checks risk limits
    4. Places orders (if LIVE mode)
    5. Logs everything
    
    That's it. No ML, no agents, no complexity.
    """
    
    def __init__(self, config):
        self.config = config
        self.running = False
        self.decision_count = 0
        self.signal_stats = {'LONG': 0, 'SHORT': 0, 'SKIP': 0}
        self.confidence_sum = 0
        self.confidence_count = 0
        self.start_time = None
        
        # Initialize components
        self.client = BybitClient(
            api_key=config.BYBIT_API_KEY,
            api_secret=config.BYBIT_API_SECRET,
            testnet=config.BYBIT_TESTNET
        )
        self.signal_gen = SimpleSignalGenerator(config)
        self.risk_mgr = SimpleRiskManager(config)
    
    def run(self):
        """Main trading loop - runs continuously"""
        self.running = True
        self.start_time = datetime.now()
        
        logger.info(f"🎯 Starting main loop (checking every {self.config.CHECK_INTERVAL}s)")
        logger.info(f"📊 Timeframe: {self.config.TIMEFRAME}")
        logger.info(f"💰 Starting capital: R{self.config.STARTING_CAPITAL:,.2f}")
        logger.info(f"🎲 Mode: {self.config.TRADING_MODE}")
        
        while self.running:
            try:
                self.decision_count += 1
                
                logger.info("\n" + "="*60)
                logger.info(f"📈 DECISION #{self.decision_count}")
                logger.info(f"🕐 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
                logger.info("="*60)
                
                # Step 1: Get market data
                # Convert timeframe: "4h" → "240" (minutes)
                interval_minutes = str(int(self.config.TIMEFRAME.replace('h', '')) * 60)
                candles = self.client.get_candles(
                    symbol=self.config.SYMBOLS[0],
                    interval=interval_minutes,
                    limit=100
                )
                
                if not candles:
                    logger.warning("⚠️  No candle data received, skipping...")
                    time.sleep(60)  # Wait 1 minute and retry
                    continue
                
                logger.info(f"✅ Fetched {len(candles)} candles")
                logger.info(f"   Latest close: ${candles[-1]['close']:.2f}")
                
                # Step 2: Generate signal
                signal = self.signal_gen.generate_signal(candles)
                
                # Track stats
                self.signal_stats[signal['signal']] += 1
                if signal['confidence'] > 0:
                    self.confidence_sum += signal['confidence']
                    self.confidence_count += 1
                
                logger.info(f"\n🎯 SIGNAL: {signal['signal']}")
                logger.info(f"📊 Confidence: {signal['confidence']:.1f}%")
                
                # Show dashboard every 5 decisions
                if self.decision_count % 5 == 0:
                    self.print_status_dashboard()
                
                if signal['signal'] == 'SKIP':
                    logger.info(f"⏭️  Reason: {signal.get('reason', 'No clear opportunity')}")
                else:
                    # Got a tradeable signal!
                    logger.info(f"   Entry: ${signal['entry']:.2f}")
                    logger.info(f"   Stop Loss: ${signal['stop_loss']:.2f}")
                    logger.info(f"   Take Profit: ${signal['take_profit']:.2f}")
                    logger.info(f"   RSI: {signal['rsi']:.1f}")
                    logger.info(f"   EMA Short: ${signal['ema_short']:.2f}")
                    logger.info(f"   EMA Long: ${signal['ema_long']:.2f}")
                    logger.info(f"   Volume: {signal['volume_ratio']:.2f}x avg")
                    
                    # Step 3: Check risk limits
                    risk_check = self.risk_mgr.can_open_position(signal)
                    
                    if not risk_check['approved']:
                        logger.warning(f"🛑 REJECTED: {risk_check['reason']}")
                    else:
                        # Step 4: Calculate position size
                        position = self.risk_mgr.calculate_position_size(
                            entry=signal['entry'],
                            stop=signal['stop_loss'],
                            signal=signal['signal']
                        )
                        
                        if not position['approved']:
                            logger.warning(f"🛑 REJECTED: {position['reason']}")
                        else:
                            logger.info(f"\n✅ APPROVED TO TRADE")
                            logger.info(f"   Position Size: {position['size']:.6f} BTC")
                            logger.info(f"   Position Value: R{position['value']:.2f}")
                            logger.info(f"   Risk Amount: R{position['risk_amount']:.2f} ({position['risk_pct']:.1f}%)")
                            
                            # Step 5: Execute trade
                            if self.config.TRADING_MODE == "LIVE":
                                logger.info("\n🔥 EXECUTING LIVE TRADE...")
                                self._execute_trade(signal, position)
                            else:
                                logger.info("\n📝 PAPER MODE - Trade not executed (dry run only)")
                
                # Show risk stats
                stats = self.risk_mgr.get_stats()
                logger.info(f"\n💼 PORTFOLIO STATUS:")
                logger.info(f"   Capital: R{stats['capital']:,.2f}")
                logger.info(f"   Open Positions: {stats['open_positions']}/{self.config.MAX_POSITIONS}")
                logger.info(f"   Portfolio Heat: {stats['current_heat']:.1f}%")
                logger.info(f"   Daily P&L: R{stats['daily_pnl']:+,.2f} ({stats['daily_pnl_pct']:+.1f}%)")
                
                # Wait for next check
                logger.info(f"\n⏰ Next check in {self.config.CHECK_INTERVAL}s ({self.config.CHECK_INTERVAL//3600}h)...")
                logger.info("   Press Ctrl+C to stop")
                
                time.sleep(self.config.CHECK_INTERVAL)
                
            except KeyboardInterrupt:
                logger.info("\n\n🛑 Shutdown requested by user...")
                self.running = False
                break
                
            except Exception as e:
                logger.error(f"\n❌ ERROR in main loop: {e}", exc_info=True)
                logger.info("⏸️  Waiting 60 seconds before retry...")
                time.sleep(60)
        
        logger.info("\n" + "="*60)
        logger.info("👋 OZZY SIMPLE STOPPED")
        logger.info(f"📊 Total decisions: {self.decision_count}")
        logger.info("="*60)
    
    def _execute_trade(self, signal: Dict, position: Dict):
        """Execute the actual trade on Bybit"""
        try:
            logger.info(f"📤 Placing order with Bybit...")
            
            order = self.client.place_order(
                symbol=self.config.SYMBOLS[0],
                side=signal['signal'],
                size=position['size'],
                stop_loss=signal['stop_loss'],
                take_profit=signal['take_profit']
            )
            
            if order['success']:
                logger.info(f"✅ ORDER PLACED SUCCESSFULLY")
                logger.info(f"   Order ID: {order['order_id']}")
                
                # Track the position
                self.risk_mgr.add_position({
                    'id': order['order_id'],
                    'symbol': order['symbol'],
                    'signal': order['side'],
                    'entry': signal['entry'],
                    'size': order['size'],
                    'stop_loss': order['stop_loss'],
                    'take_profit': order['take_profit'],
                    'risk_pct': position['risk_pct'],
                    'timestamp': datetime.now()
                })
            else:
                logger.error(f"❌ ORDER FAILED: {order['error']}")
                
        except Exception as e:
            logger.error(f"❌ Failed to execute trade: {e}")

def main():
    """Entry point"""
    print("""
╔════════════════════════════════════════════════╗
║                                                ║
║            OZZY SIMPLE v1.0                    ║
║                                                ║
║   Dead simple crypto trading bot              ║
║   RSI + EMA + Volume strategy only            ║
║                                                ║
║   NO ML | NO Agents | NO Complexity           ║
║                                                ║
╚════════════════════════════════════════════════╝
    """)
    
    # Validate configuration
    if not validate_config():
        print("\n❌ Fix configuration errors before starting!")
        sys.exit(1)
    
    # Initialize and run bot
    bot = SimpleTradingBot(config)
    
    try:
        bot.run()
    except KeyboardInterrupt:
        logger.info("\n👋 Goodbye!")
    except Exception as e:
        logger.error(f"❌ Fatal error: {e}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    main()
