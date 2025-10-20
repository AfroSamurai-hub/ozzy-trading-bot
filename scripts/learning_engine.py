#!/usr/bin/env python3
"""
🧠 LEARNING ENGINE - Stage 5 of Learning Pipeline

AUTO-UPDATES pattern confidence based on real outcomes.
This closes the feedback loop: Trades → Outcomes → Learning → Better Decisions

Part of Milestone 1.2.5: Build Learning System (Day 6)

Integration Flow:
1. TradingAgent makes decisions with base confidence
2. Learning Engine monitors outcomes (via track_trade_outcomes.py)
3. Analyzers calculate pattern performance (analyze_pattern_performance.py)
4. Learning Engine adjusts confidence multipliers (NON-BREAKING)
5. PatternIntelligence applies multipliers to next decision

Usage:
    # Run learning updates
    python3 learning_engine.py --update
    
    # Show current multipliers
    python3 learning_engine.py --show
    
    # Test mode (no changes)
    python3 learning_engine.py --dry-run
"""

import sys
import json
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Tuple

sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.analyze_pattern_performance import PatternPerformanceAnalyzer
from scripts.analyze_volume_impact import VolumeImpactAnalyzer
from scripts.track_trade_outcomes import TradeOutcomeTracker


class LearningEngine:
    """
    🧠 Auto-updates pattern confidence based on real outcomes.
    
    NON-BREAKING Design:
    - Uses confidence multipliers (0.5× to 1.2×)
    - Stores in data/learning_multipliers.json
    - TradingAgent applies: final_confidence = base × multiplier
    - Can be disabled without breaking system
    
    Update Rules:
    1. Pattern <40% WR → DISABLE (multiplier = 0.0)
    2. Pattern 40-50% WR → REDUCE (multiplier = 0.8)
    3. Pattern 50-60% WR → KEEP (multiplier = 1.0)
    4. Pattern >60% WR → BOOST (multiplier = 1.2)
    
    Safety:
    - Requires 10+ trades before DISABLE
    - Requires 5+ trades before BOOST
    - Gradual updates (max 0.1 change per day)
    - Human review for DISABLE actions
    """
    
    def __init__(self, data_dir: str = "data"):
        self.data_dir = Path(data_dir)
        self.multipliers_file = self.data_dir / "learning_multipliers.json"
        
        # Initialize components
        self.tracker = TradeOutcomeTracker()
        self.pattern_analyzer = PatternPerformanceAnalyzer()
        self.volume_analyzer = VolumeImpactAnalyzer()
        
        # Load existing multipliers
        self.multipliers = self._load_multipliers()
        
        # Learning history
        self.history_file = self.data_dir / "learning_history.json"
        self.history = self._load_history()
    
    def _load_multipliers(self) -> Dict[str, float]:
        """Load confidence multipliers from disk"""
        if self.multipliers_file.exists():
            with open(self.multipliers_file) as f:
                return json.load(f)
        return {}
    
    def _save_multipliers(self):
        """Save multipliers to disk"""
        self.multipliers_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.multipliers_file, 'w') as f:
            json.dump(self.multipliers, f, indent=2)
    
    def _load_history(self) -> List[Dict]:
        """Load learning history"""
        if self.history_file.exists():
            with open(self.history_file) as f:
                return json.load(f)
        return []
    
    def _save_history(self):
        """Save learning history"""
        self.history_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.history_file, 'w') as f:
            json.dump(self.history, f, indent=2)
    
    def _record_update(self, pattern: str, old_mult: float, new_mult: float, 
                      reason: str, stats: Dict):
        """Record learning update in history"""
        update = {
            'timestamp': datetime.now().isoformat(),
            'pattern': pattern,
            'old_multiplier': old_mult,
            'new_multiplier': new_mult,
            'reason': reason,
            'stats': {
                'trades': stats.get('total_trades', 0),
                'win_rate': stats.get('win_rate', 0),
                'avg_pnl': stats.get('avg_pnl', 0)
            }
        }
        self.history.append(update)
        self._save_history()
    
    def calculate_updates(self, min_trades_disable: int = 10, 
                         min_trades_boost: int = 5) -> List[Dict]:
        """
        Calculate confidence multiplier updates based on pattern performance.
        
        Returns list of updates: [{'pattern': str, 'action': str, 'multiplier': float, ...}]
        """
        stats = self.pattern_analyzer.calculate_pattern_stats()
        
        if not stats:
            return []
        
        updates = []
        
        for pattern, pattern_stats in stats.items():
            count = pattern_stats['total_trades']
            win_rate = pattern_stats['win_rate']
            
            # 🚫 CRITICAL: Skip patterns that aren't real patterns
            # - "unknown_pattern": Failed pattern extraction (legacy)
            # - "indicator_based": No pattern detected, decision based on indicators only
            if pattern in ['unknown_pattern', 'indicator_based']:
                # Don't learn from these - they're not repeatable chart patterns
                continue
            
            current_mult = self.multipliers.get(pattern, 1.0)
            new_mult = current_mult
            action = 'KEEP'
            reason = ''
            
            # Rule 1: DISABLE (<40% WR, min 10 trades)
            if win_rate < 0.40 and count >= min_trades_disable:
                new_mult = 0.0
                action = 'DISABLE'
                reason = f"{win_rate*100:.0f}% WR < 40% (n={count})"
            
            # Rule 2: REDUCE (40-50% WR, min 5 trades)
            elif 0.40 <= win_rate < 0.50 and count >= 5:
                new_mult = 0.8
                action = 'REDUCE'
                reason = f"{win_rate*100:.0f}% WR below target (n={count})"
            
            # Rule 3: KEEP (50-60% WR)
            elif 0.50 <= win_rate < 0.60:
                new_mult = 1.0
                action = 'KEEP'
                reason = f"{win_rate*100:.0f}% WR acceptable (n={count})"
            
            # Rule 4: BOOST (>60% WR, min 5 trades)
            elif win_rate >= 0.60 and count >= min_trades_boost:
                new_mult = 1.2
                action = 'BOOST'
                reason = f"{win_rate*100:.0f}% WR excellent (n={count})"
            
            # Safety: Gradual updates (max 0.1 change)
            if abs(new_mult - current_mult) > 0.1:
                if new_mult > current_mult:
                    new_mult = current_mult + 0.1
                elif new_mult < current_mult and new_mult > 0:
                    new_mult = current_mult - 0.1
                # Exception: Allow immediate DISABLE (0.0)
            
            # Only record if changed
            if new_mult != current_mult:
                updates.append({
                    'pattern': pattern,
                    'action': action,
                    'old_multiplier': current_mult,
                    'new_multiplier': new_mult,
                    'reason': reason,
                    'stats': pattern_stats,
                    'requires_review': action == 'DISABLE'
                })
        
        return updates
    
    def apply_updates(self, updates: List[Dict], dry_run: bool = False) -> int:
        """
        Apply confidence multiplier updates.
        
        Returns number of updates applied.
        """
        applied = 0
        
        for update in updates:
            pattern = update['pattern']
            new_mult = update['new_multiplier']
            
            # Skip DISABLE if requires review
            if update['requires_review'] and not dry_run:
                print(f"⚠️  DISABLE {pattern} requires manual review - skipping")
                continue
            
            if not dry_run:
                old_mult = self.multipliers.get(pattern, 1.0)
                self.multipliers[pattern] = new_mult
                self._record_update(
                    pattern, old_mult, new_mult,
                    update['reason'], update['stats']
                )
                applied += 1
        
        if not dry_run and applied > 0:
            self._save_multipliers()
        
        return applied
    
    def generate_report(self, updates: List[Dict]) -> str:
        """Generate learning engine report"""
        report = []
        report.append("="*70)
        report.append("🧠 LEARNING ENGINE REPORT")
        report.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        report.append("="*70)
        
        if not updates:
            report.append("\n✅ No updates needed - all patterns performing as expected")
            return "\n".join(report)
        
        # Group by action
        disable = [u for u in updates if u['action'] == 'DISABLE']
        reduce = [u for u in updates if u['action'] == 'REDUCE']
        boost = [u for u in updates if u['action'] == 'BOOST']
        
        # DISABLE section
        if disable:
            report.append(f"\n❌ PATTERNS TO DISABLE ({len(disable)}):")
            report.append("-"*70)
            for u in disable:
                report.append(f"  {u['pattern']}")
                report.append(f"    Multiplier: {u['old_multiplier']:.2f} → {u['new_multiplier']:.2f}")
                report.append(f"    Reason: {u['reason']}")
                report.append(f"    ⚠️  Requires manual review before disabling")
        
        # REDUCE section
        if reduce:
            report.append(f"\n⬇️  PATTERNS TO REDUCE ({len(reduce)}):")
            report.append("-"*70)
            for u in reduce:
                report.append(f"  {u['pattern']}")
                report.append(f"    Multiplier: {u['old_multiplier']:.2f} → {u['new_multiplier']:.2f}")
                report.append(f"    Reason: {u['reason']}")
        
        # BOOST section
        if boost:
            report.append(f"\n⬆️  PATTERNS TO BOOST ({len(boost)}):")
            report.append("-"*70)
            for u in boost:
                report.append(f"  {u['pattern']}")
                report.append(f"    Multiplier: {u['old_multiplier']:.2f} → {u['new_multiplier']:.2f}")
                report.append(f"    Reason: {u['reason']}")
        
        # Summary
        report.append(f"\n📊 SUMMARY:")
        report.append("-"*70)
        report.append(f"  Total Updates: {len(updates)}")
        report.append(f"  Disable: {len(disable)} (manual review)")
        report.append(f"  Reduce: {len(reduce)}")
        report.append(f"  Boost: {len(boost)}")
        
        # Integration instructions
        report.append(f"\n🔗 INTEGRATION:")
        report.append("-"*70)
        report.append(f"  Multipliers saved to: {self.multipliers_file}")
        report.append(f"  TradingAgent applies: final_confidence = base × multiplier")
        report.append(f"  See: agent/trader.py (integrate with PatternIntelligence)")
        
        report.append("="*70)
        
        return "\n".join(report)
    
    def show_current_state(self) -> str:
        """Show current multipliers and recent history"""
        report = []
        report.append("="*70)
        report.append("🧠 LEARNING ENGINE STATE")
        report.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        report.append("="*70)
        
        # Current multipliers
        report.append(f"\n📊 ACTIVE MULTIPLIERS ({len(self.multipliers)}):")
        report.append("-"*70)
        
        if not self.multipliers:
            report.append("  (none - using defaults)")
        else:
            for pattern, mult in sorted(self.multipliers.items()):
                emoji = "❌" if mult == 0 else "⬇️" if mult < 1 else "✅" if mult == 1 else "⬆️"
                report.append(f"  {emoji} {pattern}: {mult:.2f}×")
        
        # Recent history
        report.append(f"\n📜 RECENT UPDATES ({len(self.history)}):")
        report.append("-"*70)
        
        if not self.history:
            report.append("  (no updates yet)")
        else:
            recent = self.history[-5:]  # Last 5
            for update in reversed(recent):
                timestamp = datetime.fromisoformat(update['timestamp'])
                report.append(f"  {timestamp.strftime('%Y-%m-%d %H:%M')} - {update['pattern']}")
                report.append(f"    {update['old_multiplier']:.2f} → {update['new_multiplier']:.2f}")
                report.append(f"    {update['reason']}")
        
        report.append("="*70)
        
        return "\n".join(report)


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Learning Engine")
    parser.add_argument('--update', action='store_true',
                       help='Calculate and apply updates')
    parser.add_argument('--dry-run', action='store_true',
                       help='Show updates without applying')
    parser.add_argument('--show', action='store_true',
                       help='Show current state and history')
    parser.add_argument('--min-trades-disable', type=int, default=10,
                       help='Minimum trades before disabling pattern')
    parser.add_argument('--min-trades-boost', type=int, default=5,
                       help='Minimum trades before boosting pattern')
    
    args = parser.parse_args()
    
    engine = LearningEngine()
    
    if args.show:
        print(engine.show_current_state())
    elif args.update or args.dry_run:
        updates = engine.calculate_updates(
            min_trades_disable=args.min_trades_disable,
            min_trades_boost=args.min_trades_boost
        )
        
        print(engine.generate_report(updates))
        
        if args.dry_run:
            print("\n💡 DRY RUN - No changes applied")
        elif updates:
            applied = engine.apply_updates(updates, dry_run=False)
            print(f"\n✅ Applied {applied}/{len(updates)} updates")
    else:
        parser.print_help()


if __name__ == '__main__':
    main()
