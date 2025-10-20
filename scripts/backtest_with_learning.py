#!/usr/bin/env python3
"""
Learning Backtest Time Machine

Simulates live trading through historical data, allowing the learning
system to train naturally without future knowledge.

This is NOT traditional backtesting - it's a learning simulator where
the bot experiences historical data as if it's real-time, makes blind
decisions, learns from outcomes, and gets progressively smarter.

Usage:
    python3 scripts/backtest_with_learning.py --symbol BTCUSDT --days 90
"""

import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional

# Import from root directory
import bybit_client
from agent import trader as trader_module
import scripts.track_trade_outcomes as track_module
import scripts.learning_engine as learning_module

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)


class LearningBacktest:
    """
    Time-machine backtest that lets the bot learn as it trades through history.
    
    Key features:
    - Feeds historical data sequentially (no future peeking)
    - Bot makes blind decisions based only on past data
    - Outcomes revealed after position closes
    - Learning system updates in real-time
    - Tracks system evolution and improvement
    """
    
    def __init__(self, symbol: str, start_date: str, end_date: str, interval: str = "240"):
        """
        Initialize learning backtest
        
        Args:
            symbol: Trading symbol (e.g., 'BTCUSDT')
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)
            interval: Candle interval in minutes ('240' = 4H, '60' = 1H, '15' = 15min, etc)
        """
        self.symbol = symbol
        self.start_date = start_date
        self.end_date = end_date
        self.interval = interval
        
        # Initialize components
        self.client = bybit_client.BybitClient()
        self.trader = trader_module.TradingAgent()
        self.tracker = track_module.TradeOutcomeTracker()
        self.engine = learning_module.LearningEngine()
        
        # State tracking
        self.data = []
        self.positions = {}  # Open positions
        self.closed_trades = []  # Completed trades
        self.timeline_snapshots = []  # System state over time
        self.learning_events = []  # Times when system learned
        
        # Performance tracking
        self.balance = 10000.0  # Starting capital
        self.peak_balance = 10000.0
        self.trades_count = 0
        self.wins = 0
        self.losses = 0
        
        logger.info(f"🎮 Initialized Learning Backtest")
        logger.info(f"   Symbol: {symbol}")
        logger.info(f"   Period: {start_date} to {end_date}")
        logger.info(f"   Interval: {interval}m candles")
    
    def load_historical_data(self):
        """Load all historical data for the period"""
        logger.info(f"📊 Loading historical data...")
        
        # Calculate number of days
        start = datetime.strptime(self.start_date, "%Y-%m-%d")
        end = datetime.strptime(self.end_date, "%Y-%m-%d")
        days = (end - start).days
        
        # Bybit limits to 200 candles per request
        # For 15m interval: 200 candles = 50 hours = ~2 days
        # For 5m interval: 200 candles = 16.67 hours = ~0.7 days
        
        all_candles = []
        current_end = end
        
        # Work backwards from end date to start date
        while current_end > start:
            # Fetch batch
            end_timestamp = int(current_end.timestamp() * 1000)
            
            candles = self._fetch_candles_with_retry(end_timestamp)
            if not candles:
                logger.warning(f"⚠️  Failed to fetch candles ending at {current_end}")
                break
            
            # Add to collection (reverse since we're going backwards)
            all_candles = candles + all_candles
            
            # Move to earlier time
            earliest_timestamp = int(candles[0]['timestamp'])
            current_end = datetime.fromtimestamp(earliest_timestamp / 1000)
            
            # Progress update
            days_loaded = (end - current_end).days
            logger.info(f"   Loaded: {days_loaded}/{days} days ({len(all_candles)} candles)")
            
            # Stop if we've gone before start date
            if current_end <= start:
                break
        
        # Filter to exact date range
        start_ts = int(start.timestamp() * 1000)
        end_ts = int(end.timestamp() * 1000)
        self.data = [c for c in all_candles if start_ts <= c['timestamp'] <= end_ts]
        
        logger.info(f"✅ Loaded {len(self.data)} candles for analysis")
        logger.info(f"   First: {self.data[0]['datetime']}")
        logger.info(f"   Last: {self.data[-1]['datetime']}")
        
        return len(self.data) > 0
    
    def _fetch_candles_with_retry(self, end_timestamp: int, max_retries: int = 3) -> Optional[List[Dict]]:
        """Fetch candles with retry logic"""
        import time
        
        for attempt in range(max_retries):
            try:
                # Bybit API endpoint for historical klines
                endpoint = "/v5/market/kline"
                params = {
                    "category": "spot",
                    "symbol": self.symbol,
                    "interval": self.interval,
                    "end": end_timestamp,
                    "limit": 200  # Max allowed
                }
                
                response = self.client._make_request("GET", endpoint, params, authenticated=False)
                
                if response.get("retCode") == 0:
                    candles_raw = response.get("result", {}).get("list", [])
                    
                    # Convert to standard format
                    candles = []
                    for candle in candles_raw:
                        candles.append({
                            "timestamp": int(candle[0]),
                            "open": float(candle[1]),
                            "high": float(candle[2]),
                            "low": float(candle[3]),
                            "close": float(candle[4]),
                            "volume": float(candle[5]),
                            "datetime": datetime.fromtimestamp(int(candle[0]) / 1000).strftime("%Y-%m-%d %H:%M:%S")
                        })
                    
                    # Reverse to chronological order
                    candles.reverse()
                    return candles
                
            except Exception as e:
                logger.warning(f"⚠️  Attempt {attempt + 1} failed: {e}")
                time.sleep(2 ** attempt)  # Exponential backoff
        
        return None
    
    def run(self):
        """Main simulation loop - THE TIME MACHINE!"""
        if not self.data:
            logger.error("❌ No data loaded. Call load_historical_data() first.")
            return
        
        logger.info("=" * 70)
        logger.info("🚀 STARTING LEARNING BACKTEST TIME MACHINE")
        logger.info("=" * 70)
        logger.info(f"📊 Processing {len(self.data)} candles...")
        logger.info(f"💰 Starting Balance: ${self.balance:,.2f}")
        logger.info("")
        
        # Take initial snapshot
        self._snapshot_state(0)
        
        # Process each candle as if it's live data
        total_candles = len(self.data)
        for i in range(total_candles):
            candle = self.data[i]
            
            # Progress indicator every 100 candles
            if i % 100 == 0 and i > 0:
                pct = (i / total_candles) * 100
                logger.info(f"   Progress: {i}/{total_candles} ({pct:.1f}%) | Trades: {self.trades_count} | Balance: ${self.balance:,.0f}")
            
            # 1. Check existing positions (close if hit SL/TP or timeout)
            self._check_positions(i, candle)
            
            # 2. Make new decision (bot thinks it's live!)
            if len(self.positions) < 3:  # Max 3 positions
                decision = self._make_decision(i, candle)
                
                # 3. Open position if signal
                if decision and decision['action'] != 'hold':
                    self._open_position(i, decision, candle)
            
            # 4. Snapshot system state periodically
            if i > 0 and i % 500 == 0:
                self._snapshot_state(i)
        
        # Close any remaining positions at end
        self._close_all_positions(len(self.data) - 1)
        
        # Generate final report
        self._generate_report()
    
    def _make_decision(self, candle_index: int, current_candle: Dict) -> Optional[Dict]:
        """
        Make trading decision with ONLY past data (no future peeking!)
        
        Args:
            candle_index: Current position in data
            current_candle: Current candle data
            
        Returns:
            Trading decision or None
        """
        # Build history (only past data!)
        lookback = 100
        start_idx = max(0, candle_index - lookback)
        history = self.data[start_idx:candle_index + 1]  # Include current candle
        
        if len(history) < 20:  # Need minimum data
            return None
        
        # Convert to format trader expects
        candles = history.copy()
        
        # Add current price as "ticker" data
        ticker = {
            'last_price': current_candle['close'],
            'bid': current_candle['low'],  # Approximate
            'ask': current_candle['high']  # Approximate
        }
        
        # Bot makes decision (thinks it's live!)
        try:
            decision = self.trader.make_decision(self.symbol, candles, ticker)
            return decision
        except Exception as e:
            logger.warning(f"⚠️  Decision error at candle {candle_index}: {e}")
            return None
    
    def _open_position(self, candle_index: int, decision: Dict, candle: Dict):
        """Open a new position"""
        position_id = f"pos_{candle_index}_{decision['action']}"
        
        # Calculate position size (2% risk per trade)
        risk_amount = self.balance * 0.02
        entry_price = candle['close']
        stop_distance = abs(entry_price - decision.get('stop_loss', entry_price * 0.98))
        
        if stop_distance > 0:
            position_size = risk_amount / stop_distance
        else:
            position_size = self.balance * 0.1 / entry_price  # 10% of balance
        
        position = {
            'id': position_id,
            'entry_candle': candle_index,
            'entry_time': candle['datetime'],
            'entry_price': entry_price,
            'size': position_size,
            'side': decision['action'],  # 'buy' or 'sell'
            'decision': decision,
            'stop_loss': decision.get('stop_loss'),
            'take_profit': decision.get('take_profit'),
            'max_hold_candles': 100  # Timeout after 100 candles
        }
        
        self.positions[position_id] = position
        
        logger.debug(f"📈 Position opened: {decision['action'].upper()} @ ${entry_price:,.2f} "
                    f"(Pattern: {decision.get('detected_pattern', 'unknown')})")
    
    def _check_positions(self, candle_index: int, candle: Dict):
        """Check if any positions should close"""
        for pos_id, position in list(self.positions.items()):
            outcome = self._should_close(position, candle_index, candle)
            
            if outcome:
                # LEARNING MOMENT! System learns from revealed outcome
                self._learn_from_outcome(candle_index, position, outcome)
                del self.positions[pos_id]
    
    def _should_close(self, position: Dict, candle_index: int, candle: Dict) -> Optional[Dict]:
        """
        Check if position should close
        
        Returns:
            Outcome dict if should close, None otherwise
        """
        entry_price = position['entry_price']
        current_price = candle['close']
        side = position['side']
        
        # Calculate P&L
        if side == 'buy':
            pnl_pct = ((current_price - entry_price) / entry_price) * 100
        else:  # sell/short
            pnl_pct = ((entry_price - current_price) / entry_price) * 100
        
        pnl_dollars = (pnl_pct / 100) * (position['size'] * entry_price)
        
        # Check exit conditions
        exit_reason = None
        
        # 1. Stop loss hit
        if position.get('stop_loss'):
            if side == 'buy' and current_price <= position['stop_loss']:
                exit_reason = 'stop_loss'
            elif side == 'sell' and current_price >= position['stop_loss']:
                exit_reason = 'stop_loss'
        
        # 2. Take profit hit
        if position.get('take_profit') and not exit_reason:
            if side == 'buy' and current_price >= position['take_profit']:
                exit_reason = 'take_profit'
            elif side == 'sell' and current_price <= position['take_profit']:
                exit_reason = 'take_profit'
        
        # 3. Timeout (held too long)
        candles_held = candle_index - position['entry_candle']
        if candles_held >= position['max_hold_candles'] and not exit_reason:
            exit_reason = 'timeout'
        
        if exit_reason:
            outcome = {
                'exit_candle': candle_index,
                'exit_time': candle['datetime'],
                'exit_price': current_price,
                'exit_reason': exit_reason,
                'pnl_pct': pnl_pct,
                'pnl_dollars': pnl_dollars,
                'candles_held': candles_held
            }
            return outcome
        
        return None
    
    def _learn_from_outcome(self, candle_index: int, position: Dict, outcome: Dict):
        """
        System learns from revealed outcome - THE MAGIC HAPPENS HERE!
        
        This is where the bot gets smarter in real-time.
        """
        decision = position['decision']
        pnl = outcome['pnl_dollars']
        
        # Update balance
        self.balance += pnl
        self.peak_balance = max(self.peak_balance, self.balance)
        self.trades_count += 1
        
        if pnl > 0:
            self.wins += 1
        else:
            self.losses += 1
        
        # Track closed trade
        self.closed_trades.append({
            'position': position,
            'outcome': outcome,
            'balance_after': self.balance
        })
        
        # Capture system state BEFORE learning
        before_multipliers = self.trader.learning_multipliers.copy()
        
        # FEED OUTCOME TO LEARNING SYSTEM
        try:
            self.tracker.track_outcome(
                decision=decision,
                actual_outcome=pnl,
                confidence=decision.get('confidence', 50.0)
            )
            
            # TRIGGER LEARNING ENGINE
            updated_multipliers = self.engine.update_multipliers()
            
            # APPLY TO TRADER IMMEDIATELY (bot just got smarter!)
            self.trader.load_learning_multipliers()
            
        except Exception as e:
            logger.warning(f"⚠️  Learning error: {e}")
            return
        
        # Capture system state AFTER learning
        after_multipliers = self.trader.learning_multipliers
        
        # Record learning event
        pattern = decision.get('detected_pattern', 'unknown')
        before_mult = before_multipliers.get(pattern, 1.0)
        after_mult = after_multipliers.get(pattern, 1.0)
        change = after_mult - before_mult
        
        if abs(change) > 0.01:  # Significant change
            self.learning_events.append({
                'candle_index': candle_index,
                'time': outcome['exit_time'],
                'pattern': pattern,
                'outcome_pnl': pnl,
                'before': before_mult,
                'after': after_mult,
                'change': change,
                'balance': self.balance
            })
            
            logger.info(f"   📚 LEARNING! {pattern}: {before_mult:.3f} → {after_mult:.3f} "
                       f"(Δ{change:+.3f}) | Balance: ${self.balance:,.0f}")
        
        # Log trade result
        win_loss = "WIN" if pnl > 0 else "LOSS"
        logger.debug(f"   {'✅' if pnl > 0 else '❌'} {win_loss}: {outcome['exit_reason']} | "
                    f"P&L: ${pnl:+,.2f} ({outcome['pnl_pct']:+.2f}%) | "
                    f"Balance: ${self.balance:,.2f}")
    
    def _close_all_positions(self, final_candle_index: int):
        """Close all remaining positions at end of backtest"""
        if not self.positions:
            return
        
        logger.info(f"🔚 Closing {len(self.positions)} remaining positions at end of period...")
        
        final_candle = self.data[final_candle_index]
        
        for pos_id, position in list(self.positions.items()):
            outcome = {
                'exit_candle': final_candle_index,
                'exit_time': final_candle['datetime'],
                'exit_price': final_candle['close'],
                'exit_reason': 'end_of_period',
                'pnl_pct': ((final_candle['close'] - position['entry_price']) / position['entry_price']) * 100
                           if position['side'] == 'buy'
                           else ((position['entry_price'] - final_candle['close']) / position['entry_price']) * 100,
                'pnl_dollars': 0,  # Simplified
                'candles_held': final_candle_index - position['entry_candle']
            }
            
            self._learn_from_outcome(final_candle_index, position, outcome)
            del self.positions[pos_id]
    
    def _snapshot_state(self, candle_index: int):
        """Take snapshot of system state for tracking evolution"""
        if candle_index < len(self.data):
            timestamp = self.data[candle_index]['datetime']
        else:
            timestamp = "end"
        
        # Get current learning multipliers
        multipliers = self.trader.learning_multipliers.copy()
        
        # Calculate current win rate
        win_rate = (self.wins / self.trades_count * 100) if self.trades_count > 0 else 0
        
        snapshot = {
            'candle_index': candle_index,
            'timestamp': timestamp,
            'balance': self.balance,
            'trades_count': self.trades_count,
            'wins': self.wins,
            'losses': self.losses,
            'win_rate': win_rate,
            'multipliers': multipliers.copy(),
            'learning_events_so_far': len(self.learning_events)
        }
        
        self.timeline_snapshots.append(snapshot)
    
    def _generate_report(self):
        """Generate comprehensive learning progression report"""
        logger.info("")
        logger.info("=" * 70)
        logger.info("✅ BACKTEST COMPLETE!")
        logger.info("=" * 70)
        
        # Overall Performance
        total_return = ((self.balance - 10000) / 10000) * 100
        max_drawdown = ((self.peak_balance - self.balance) / self.peak_balance) * 100 if self.peak_balance > 0 else 0
        win_rate = (self.wins / self.trades_count * 100) if self.trades_count > 0 else 0
        
        logger.info("")
        logger.info("📊 OVERALL PERFORMANCE:")
        logger.info(f"   Starting Balance: $10,000.00")
        logger.info(f"   Final Balance: ${self.balance:,.2f}")
        logger.info(f"   Total Return: {total_return:+.2f}%")
        logger.info(f"   Peak Balance: ${self.peak_balance:,.2f}")
        logger.info(f"   Max Drawdown: {max_drawdown:.2f}%")
        logger.info(f"")
        logger.info(f"   Total Trades: {self.trades_count}")
        logger.info(f"   Wins: {self.wins}")
        logger.info(f"   Losses: {self.losses}")
        logger.info(f"   Win Rate: {win_rate:.1f}%")
        
        # Learning Progression
        if self.learning_events:
            logger.info("")
            logger.info("📚 LEARNING PROGRESSION:")
            logger.info(f"   Total Learning Events: {len(self.learning_events)}")
            logger.info(f"")
            logger.info("   Top Pattern Changes:")
            
            # Aggregate changes by pattern
            pattern_changes = {}
            for event in self.learning_events:
                pattern = event['pattern']
                if pattern not in pattern_changes:
                    pattern_changes[pattern] = {
                        'initial': event['before'] - event['change'],
                        'final': event['after'],
                        'total_change': 0,
                        'events': 0
                    }
                pattern_changes[pattern]['total_change'] += event['change']
                pattern_changes[pattern]['events'] += 1
                pattern_changes[pattern]['final'] = event['after']
            
            # Sort by absolute change
            sorted_patterns = sorted(pattern_changes.items(), 
                                   key=lambda x: abs(x[1]['total_change']), 
                                   reverse=True)
            
            for pattern, data in sorted_patterns[:10]:
                logger.info(f"   • {pattern:20} | {data['initial']:.3f} → {data['final']:.3f} "
                          f"(Δ{data['total_change']:+.3f}) | {data['events']} adjustments")
        
        # Save detailed report
        self._save_report()
        
        logger.info("")
        logger.info("=" * 70)
    
    def _save_report(self):
        """Save detailed report to JSON"""
        report = {
            'backtest_config': {
                'symbol': self.symbol,
                'start_date': self.start_date,
                'end_date': self.end_date,
                'interval': self.interval,
                'candles_processed': len(self.data)
            },
            'performance': {
                'starting_balance': 10000.0,
                'final_balance': self.balance,
                'total_return_pct': ((self.balance - 10000) / 10000) * 100,
                'peak_balance': self.peak_balance,
                'total_trades': self.trades_count,
                'wins': self.wins,
                'losses': self.losses,
                'win_rate': (self.wins / self.trades_count * 100) if self.trades_count > 0 else 0
            },
            'learning_events': self.learning_events,
            'timeline_snapshots': self.timeline_snapshots,
            'closed_trades': [
                {
                    'entry_time': t['position']['entry_time'],
                    'exit_time': t['outcome']['exit_time'],
                    'pattern': t['position']['decision'].get('detected_pattern'),
                    'side': t['position']['side'],
                    'pnl': t['outcome']['pnl_dollars'],
                    'pnl_pct': t['outcome']['pnl_pct'],
                    'exit_reason': t['outcome']['exit_reason']
                }
                for t in self.closed_trades
            ]
        }
        
        output_file = f"data/backtest_learning_{self.symbol}_{self.start_date}_{self.end_date}.json"
        os.makedirs(os.path.dirname(output_file), exist_ok=True)
        
        with open(output_file, 'w') as f:
            json.dump(report, f, indent=2)
        
        logger.info(f"📄 Detailed report saved: {output_file}")


def main():
    """Main entry point"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Learning Backtest Time Machine')
    parser.add_argument('--symbol', type=str, default='BTCUSDT', help='Trading symbol')
    parser.add_argument('--days', type=int, default=90, help='Number of days to backtest')
    parser.add_argument('--interval', type=str, default='240', help='Candle interval in minutes (240=4H, 60=1H, 15=15min, etc)')
    
    args = parser.parse_args()
    
    # Calculate date range
    end_date = datetime.now()
    start_date = end_date - timedelta(days=args.days)
    
    # Create backtest
    backtest = LearningBacktest(
        symbol=args.symbol,
        start_date=start_date.strftime("%Y-%m-%d"),
        end_date=end_date.strftime("%Y-%m-%d"),
        interval=args.interval
    )
    
    # Load data and run
    if backtest.load_historical_data():
        backtest.run()
    else:
        logger.error("❌ Failed to load historical data")


if __name__ == "__main__":
    main()
