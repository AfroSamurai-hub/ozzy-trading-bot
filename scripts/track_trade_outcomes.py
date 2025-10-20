#!/usr/bin/env python3
"""
🧠 TRADE OUTCOME TRACKER - Stage 1 & 2 of Learning Pipeline

Captures trades at entry (Stage 1) and monitors/labels outcomes (Stage 2).
Part of Milestone 1.2.5: Build Learning System

Features:
- 5-tier outcome classification (BIG_WIN/WIN/BREAKEVEN/LOSS/BIG_LOSS)
- Captures quality metrics (pattern, confidence, volume, regime, etc.)
- Stores in ChromaDB for pattern intelligence integration
- Non-breaking: Runs alongside existing system

Usage:
    # As a service (monitors continuously)
    python3 track_trade_outcomes.py --monitor
    
    # One-time check
    python3 track_trade_outcomes.py --check
    
    # View statistics
    python3 track_trade_outcomes.py --stats
"""

import json
import sys
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
import time

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    import chromadb
    from chromadb.config import Settings
    CHROMADB_AVAILABLE = True
except ImportError:
    CHROMADB_AVAILABLE = False
    print("⚠️  ChromaDB not available. Install with: pip install chromadb")


class TradeOutcomeTracker:
    """
    Tracks trade outcomes and labels them with quality metrics.
    
    Stage 1: Capture trade at entry
    Stage 2: Monitor position and label outcome
    """
    
    def __init__(self, db_path: str = "data/trade_labels"):
        self.db_path = Path(db_path)
        self.db_path.mkdir(parents=True, exist_ok=True)
        
        # Pending trades (captured but not yet labeled)
        self.pending_file = self.db_path / "pending_trades.json"
        self.pending_trades = self._load_pending()
        
        # Initialize ChromaDB if available
        self.db = None
        if CHROMADB_AVAILABLE:
            try:
                self.client = chromadb.PersistentClient(
                    path=str(self.db_path),
                    settings=Settings(anonymized_telemetry=False)
                )
                self.db = self.client.get_or_create_collection(
                    name="trade_outcomes",
                    metadata={"description": "Labeled trade outcomes with quality metrics"}
                )
                print(f"✅ ChromaDB initialized: {self.db.count()} labeled trades")
            except Exception as e:
                print(f"⚠️  ChromaDB init failed: {e}")
                self.db = None
        
    def _load_pending(self) -> List[Dict]:
        """Load pending trades from file"""
        if self.pending_file.exists():
            try:
                with open(self.pending_file) as f:
                    return json.load(f)
            except:
                return []
        return []
    
    def _save_pending(self):
        """Save pending trades to file"""
        with open(self.pending_file, 'w') as f:
            json.dump(self.pending_trades, f, indent=2, default=str)
    
    def capture_trade(self, decision: Dict) -> str:
        """
        Stage 1: Capture trade at entry
        
        Args:
            decision: Trading decision dict with:
                - action: BUY/SELL/SKIP
                - confidence: 0-1
                - price: Entry price
                - pattern: Pattern used
                - reasoning: Decision reasoning
                - timestamp: When decision made
                
        Returns:
            trade_id: Unique ID for this trade
        """
        if decision.get('action') == 'SKIP':
            return None  # Don't track skips
        
        trade_id = f"trade_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{decision.get('index', 0)}"
        
        # 🎯 PRIORITY: Use detected_pattern from PatternIntelligence first!
        # This fixes the "unknown_pattern" bug by using actual pattern detection
        pattern = None
        if 'detected_pattern' in decision and decision['detected_pattern']:
            # Use PatternIntelligence detected pattern (most reliable!)
            pattern = decision['detected_pattern']
            print(f"🎯 Using detected pattern from PatternIntelligence: {pattern}")
        else:
            # Fallback: Try extracting from reasoning
            pattern = self._extract_pattern(decision.get('reasoning', ''))
            if pattern == 'unknown_pattern':
                # More accurate label for indicator-based decisions
                print(f"⚠️  No pattern detected - indicator-based decision")
                pattern = 'indicator_based'
            else:
                print(f"📝 Extracted pattern from reasoning: {pattern}")
        
        # Extract metrics from decision
        trade_data = {
            'id': trade_id,
            'timestamp': decision.get('timestamp', datetime.now().isoformat()),
            'action': decision['action'],
            'pattern': pattern,
            'confidence': decision.get('confidence', 0.0),
            'entry_price': decision.get('price', 0.0),
            'volume_ratio': decision.get('volume_ratio', 1.0),  # Will implement
            'regime': self._detect_regime(decision),
            'rsi': decision.get('rsi', 50.0),
            'ema_ratio': decision.get('ema_ratio', 1.0),
            'portfolio_heat': self._calculate_heat(decision),  # Will implement
            'reasoning': decision.get('reasoning', ''),
            'status': 'PENDING'
        }
        
        self.pending_trades.append(trade_data)
        self._save_pending()
        
        print(f"📸 CAPTURED: {trade_id} | {decision['action']} @ {decision.get('confidence', 0)*100:.0f}%")
        return trade_id
    
    def monitor_outcomes(self) -> int:
        """
        Stage 2: Check pending trades and label outcomes
        
        Returns:
            Number of trades labeled
        """
        if not self.pending_trades:
            return 0
        
        labeled_count = 0
        remaining_trades = []
        
        for trade in self.pending_trades:
            outcome = self._check_outcome(trade)
            
            if outcome:
                # Trade completed - label and store
                self._label_and_store(trade, outcome)
                labeled_count += 1
                print(f"✅ LABELED: {trade['id']} → {outcome['outcome']} ({outcome['pnl_pct']:+.2f}%)")
            else:
                # Still open - keep monitoring
                remaining_trades.append(trade)
        
        self.pending_trades = remaining_trades
        self._save_pending()
        
        return labeled_count
    
    def _check_outcome(self, trade: Dict) -> Optional[Dict]:
        """
        Check if trade is complete and determine outcome
        
        For now, uses simple time-based simulation.
        TODO: Integrate with actual position tracking
        """
        # Check if trade is old enough to have an outcome
        # For testing: assume 15min trades close after 1 hour
        entry_time = datetime.fromisoformat(trade['timestamp'])
        age = datetime.now() - entry_time
        
        if age < timedelta(hours=1):
            return None  # Still open
        
        # SIMULATION: Generate outcome based on confidence
        # TODO: Replace with actual position tracking
        confidence = trade['confidence']
        
        # Simulate outcome (higher confidence = higher win probability)
        import random
        win_prob = confidence * 0.8  # 70% conf → 56% win rate (realistic)
        
        if random.random() < win_prob:
            # Win
            pnl_pct = random.uniform(0.5, 3.5)
            peak_profit = pnl_pct * random.uniform(1.0, 1.3)
            peak_loss = -random.uniform(0.1, 0.3)
        else:
            # Loss
            pnl_pct = -random.uniform(0.5, 2.5)
            peak_profit = random.uniform(0.1, 0.5)
            peak_loss = pnl_pct * random.uniform(1.0, 1.2)
        
        return {
            'outcome': self._classify_outcome(pnl_pct),
            'pnl_pct': pnl_pct,
            'exit_price': trade['entry_price'] * (1 + pnl_pct/100),
            'exit_time': datetime.now().isoformat(),
            'hold_duration': age.total_seconds() / 60,  # minutes
            'peak_profit': peak_profit,
            'peak_loss': peak_loss,
            'r_multiple': pnl_pct / 2.0  # Assuming 2% risk
        }
    
    def _classify_outcome(self, pnl_pct: float) -> str:
        """
        5-tier outcome classification
        
        BIG_WIN: >3% gain (A+ trade)
        WIN: 1-3% gain (Good trade)
        BREAKEVEN: -1% to +1% (Neutral)
        LOSS: -3% to -1% (Bad trade)
        BIG_LOSS: <-3% (Terrible trade)
        """
        if pnl_pct > 3:
            return 'BIG_WIN'
        elif pnl_pct > 1:
            return 'WIN'
        elif pnl_pct > -1:
            return 'BREAKEVEN'
        elif pnl_pct > -3:
            return 'LOSS'
        else:
            return 'BIG_LOSS'
    
    def _label_and_store(self, trade: Dict, outcome: Dict):
        """Store labeled trade in ChromaDB"""
        if not self.db:
            print("⚠️  ChromaDB not available - outcome not stored")
            return
        
        # Merge trade data with outcome
        labeled_trade = {**trade, **outcome}
        labeled_trade['status'] = 'LABELED'
        
        # Store in ChromaDB
        try:
            self.db.add(
                ids=[trade['id']],
                documents=[trade.get('reasoning', '')],  # For semantic search
                metadatas=[{
                    'outcome': outcome['outcome'],
                    'pnl_pct': outcome['pnl_pct'],
                    'pattern': trade['pattern'],
                    'confidence': trade['confidence'],
                    'entry_price': trade['entry_price'],
                    'exit_price': outcome['exit_price'],
                    'hold_duration': outcome['hold_duration'],
                    'peak_profit': outcome['peak_profit'],
                    'peak_loss': outcome['peak_loss'],
                    'r_multiple': outcome['r_multiple'],
                    'timestamp': trade['timestamp'],
                    'action': trade['action'],
                    'volume_ratio': trade.get('volume_ratio', 1.0),
                    'regime': trade.get('regime', 'unknown'),
                    'rsi': trade.get('rsi', 50.0),
                    'ema_ratio': trade.get('ema_ratio', 1.0),
                    'reasoning': trade.get('reasoning', '')  # Add to metadata for easy access
                }]
            )
        except Exception as e:
            print(f"❌ Failed to store trade: {e}")
    
    def _extract_pattern(self, reasoning: str) -> str:
        """Extract pattern name from reasoning text"""
        # Common patterns to look for
        patterns = [
            'whale_accumulation', 'whale accumulation',
            'inverse_head_shoulders', 'inverse head',
            'bullish_engulfing', 'bullish engulfing',
            'hammer', 'morning_star', 'three_white_soldiers',
            'pennant', 'flag', 'triangle', 'wedge',
            'double_bottom', 'cup_handle',
            'mixed_signals', 'mixed signals'
        ]
        
        reasoning_lower = reasoning.lower()
        for pattern in patterns:
            if pattern in reasoning_lower:
                return pattern.replace(' ', '_')
        
        return 'unknown_pattern'
    
    def _detect_regime(self, decision: Dict) -> str:
        """Detect market regime (trending/ranging/volatile)"""
        ema_ratio = decision.get('ema_ratio', 1.0)
        
        if ema_ratio > 1.02:
            return 'trending_up'
        elif ema_ratio < 0.98:
            return 'trending_down'
        else:
            return 'ranging'
    
    def _calculate_heat(self, decision: Dict) -> float:
        """Calculate portfolio heat (total risk exposure)"""
        # TODO: Integrate with actual portfolio tracking
        return 0.0
    
    def get_stats(self) -> Dict:
        """Get statistics on tracked trades"""
        if not self.db:
            return {
                'error': 'ChromaDB not available',
                'pending_trades': len(self.pending_trades)
            }
        
        total = self.db.count()
        
        if total == 0:
            return {
                'total_labeled': 0,
                'pending_trades': len(self.pending_trades),
                'message': 'No labeled trades yet'
            }
        
        # Get all trades
        results = self.db.get(include=['metadatas'])
        metadatas = results['metadatas']
        
        # Calculate statistics
        outcomes = [m['outcome'] for m in metadatas]
        pnls = [m['pnl_pct'] for m in metadatas]
        
        wins = sum(1 for o in outcomes if o in ['BIG_WIN', 'WIN'])
        losses = sum(1 for o in outcomes if o in ['LOSS', 'BIG_LOSS'])
        breakevens = sum(1 for o in outcomes if o == 'BREAKEVEN')
        
        win_rate = wins / (wins + losses) if (wins + losses) > 0 else 0
        avg_pnl = sum(pnls) / len(pnls) if pnls else 0
        
        return {
            'total_labeled': total,
            'pending_trades': len(self.pending_trades),
            'wins': wins,
            'losses': losses,
            'breakevens': breakevens,
            'win_rate': f"{win_rate*100:.1f}%",
            'avg_pnl': f"{avg_pnl:+.2f}%",
            'outcome_breakdown': {
                'BIG_WIN': sum(1 for o in outcomes if o == 'BIG_WIN'),
                'WIN': sum(1 for o in outcomes if o == 'WIN'),
                'BREAKEVEN': breakevens,
                'LOSS': sum(1 for o in outcomes if o == 'LOSS'),
                'BIG_LOSS': sum(1 for o in outcomes if o == 'BIG_LOSS')
            }
        }
    
    def monitor_loop(self, interval: int = 60):
        """
        Continuous monitoring loop
        
        Args:
            interval: Check interval in seconds (default 60)
        """
        print(f"🔄 Starting monitoring loop (checking every {interval}s)")
        print(f"📊 Pending trades: {len(self.pending_trades)}")
        print("Press Ctrl+C to stop\n")
        
        try:
            while True:
                labeled = self.monitor_outcomes()
                if labeled > 0:
                    print(f"\n✅ Labeled {labeled} trade(s)")
                    stats = self.get_stats()
                    print(f"📊 Total labeled: {stats.get('total_labeled', 0)} | "
                          f"Win rate: {stats.get('win_rate', 'N/A')}")
                
                time.sleep(interval)
        except KeyboardInterrupt:
            print("\n\n⏸️  Monitoring stopped")
            print(f"📊 Final stats:")
            stats = self.get_stats()
            for key, value in stats.items():
                if key != 'outcome_breakdown':
                    print(f"   {key}: {value}")


def main():
    """CLI interface"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Trade Outcome Tracker")
    parser.add_argument('--monitor', action='store_true', 
                       help='Start monitoring loop')
    parser.add_argument('--check', action='store_true',
                       help='Check pending trades once')
    parser.add_argument('--stats', action='store_true',
                       help='Show statistics')
    parser.add_argument('--interval', type=int, default=60,
                       help='Monitoring interval in seconds (default: 60)')
    
    args = parser.parse_args()
    
    tracker = TradeOutcomeTracker()
    
    if args.stats or (not args.monitor and not args.check):
        # Show stats by default
        print("\n📊 TRADE OUTCOME STATISTICS")
        print("=" * 60)
        stats = tracker.get_stats()
        for key, value in stats.items():
            if key == 'outcome_breakdown':
                print(f"\n{key}:")
                for outcome, count in value.items():
                    print(f"  {outcome}: {count}")
            else:
                print(f"{key}: {value}")
        print("=" * 60)
    
    if args.check:
        print("\n🔍 Checking pending trades...")
        labeled = tracker.monitor_outcomes()
        print(f"✅ Labeled {labeled} trade(s)")
    
    if args.monitor:
        tracker.monitor_loop(interval=args.interval)


if __name__ == '__main__':
    main()
