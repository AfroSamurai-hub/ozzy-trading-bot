#!/usr/bin/env python3
"""
📊 PATTERN PERFORMANCE ANALYZER - Stage 3 of Learning Pipeline

Analyzes pattern performance and generates Daily Pattern Performance Card.
Part of Milestone 1.2.5: Build Learning System (Day 3)

Features:
- Calculate win rates per pattern
- Identify top/worst performers
- Generate actionable recommendations
- Validate against research expectations (altFINS: 70-84% for top patterns)
- Map to research milestones

Usage:
    # Generate daily report
    python3 analyze_pattern_performance.py
    
    # Show detailed stats
    python3 analyze_pattern_performance.py --detailed
    
    # Export to JSON
    python3 analyze_pattern_performance.py --json > report.json
"""

import sys
import json
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Tuple
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    import chromadb
    from chromadb.config import Settings
    CHROMADB_AVAILABLE = True
except ImportError:
    CHROMADB_AVAILABLE = False


class PatternPerformanceAnalyzer:
    """
    Analyzes pattern performance from labeled trades.
    
    Generates actionable insights:
    - Which patterns are winning (>60% WR) → BOOST
    - Which patterns are failing (<40% WR) → DISABLE
    - Research validation (compare vs altFINS study)
    """
    
    def __init__(self, db_path: str = "data/trade_labels"):
        self.db_path = Path(db_path)
        
        if not CHROMADB_AVAILABLE:
            print("❌ ChromaDB not available")
            sys.exit(1)
        
        try:
            self.client = chromadb.PersistentClient(
                path=str(self.db_path),
                settings=Settings(anonymized_telemetry=False)
            )
            self.db = self.client.get_collection(name="trade_outcomes")
            print(f"✅ Loaded {self.db.count()} labeled trades")
        except Exception as e:
            print(f"❌ Failed to load ChromaDB: {e}")
            sys.exit(1)
    
    def get_all_trades(self) -> List[Dict]:
        """Load all labeled trades"""
        if self.db.count() == 0:
            return []
        
        results = self.db.get(include=['metadatas'])
        
        # Convert to list of dicts
        trades = []
        for i, metadata in enumerate(results['metadatas']):
            trades.append(metadata)
        
        return trades
    
    def calculate_pattern_stats(self) -> Dict[str, Dict]:
        """
        Calculate statistics for each pattern.
        
        Returns:
            Dict mapping pattern_name → stats_dict
        """
        trades = self.get_all_trades()
        
        if not trades:
            return {}
        
        # Group by pattern
        pattern_groups = {}
        for trade in trades:
            pattern = trade.get('pattern', 'unknown_pattern')
            
            # 🚫 Skip non-patterns (not learnable)
            # - "unknown_pattern": Failed extraction (legacy)
            # - "indicator_based": No chart pattern, indicators only
            if pattern in ['unknown_pattern', 'indicator_based']:
                continue
            
            if pattern not in pattern_groups:
                pattern_groups[pattern] = []
            pattern_groups[pattern].append(trade)
        
        # Calculate stats per pattern
        stats = {}
        for pattern, trades in pattern_groups.items():
            wins = [t for t in trades if t['outcome'] in ['WIN', 'BIG_WIN']]
            losses = [t for t in trades if t['outcome'] in ['LOSS', 'BIG_LOSS']]
            breakevens = [t for t in trades if t['outcome'] == 'BREAKEVEN']
            
            total_trades = len(trades)
            win_count = len(wins)
            loss_count = len(losses)
            
            win_rate = win_count / (win_count + loss_count) if (win_count + loss_count) > 0 else 0
            
            # P&L stats
            pnls = [t['pnl_pct'] for t in trades]
            avg_pnl = sum(pnls) / len(pnls) if pnls else 0
            
            # Profit factor (sum of wins / sum of losses)
            win_pnls = [t['pnl_pct'] for t in wins]
            loss_pnls = [abs(t['pnl_pct']) for t in losses]
            
            total_wins = sum(win_pnls) if win_pnls else 0
            total_losses = sum(loss_pnls) if loss_pnls else 0
            profit_factor = total_wins / total_losses if total_losses > 0 else (float('inf') if total_wins > 0 else 0)
            
            stats[pattern] = {
                'total_trades': total_trades,
                'wins': win_count,
                'losses': loss_count,
                'breakevens': len(breakevens),
                'win_rate': win_rate,
                'avg_pnl': avg_pnl,
                'profit_factor': profit_factor,
                'best_pnl': max(pnls) if pnls else 0,
                'worst_pnl': min(pnls) if pnls else 0,
                'avg_confidence': sum(t['confidence'] for t in trades) / len(trades)
            }
        
        return stats
    
    def rank_patterns(self, stats: Dict, top: bool = True, n: int = 5) -> List[Tuple[str, Dict]]:
        """
        Rank patterns by win rate
        
        Args:
            stats: Pattern statistics
            top: True for best, False for worst
            n: Number to return
        """
        if not stats:
            return []
        
        # Filter patterns with at least 3 trades for reliability
        reliable = [(p, s) for p, s in stats.items() if s['total_trades'] >= 3]
        
        if not reliable:
            # If no reliable patterns, show all
            reliable = list(stats.items())
        
        # Sort by win rate
        sorted_patterns = sorted(reliable, key=lambda x: x[1]['win_rate'], reverse=top)
        
        return sorted_patterns[:n]
    
    def generate_actions(self, stats: Dict) -> List[Dict]:
        """
        Generate actionable recommendations based on stats
        
        Returns list of actions:
        - DISABLE: Win rate <40%
        - REDUCE: Win rate 40-50%
        - KEEP: Win rate 50-60%
        - BOOST: Win rate >60%
        """
        actions = []
        
        for pattern, stat in stats.items():
            # Need at least 5 trades for confident action
            if stat['total_trades'] < 5:
                actions.append({
                    'pattern': pattern,
                    'action': 'MONITOR',
                    'reason': f"Need more data ({stat['total_trades']} trades)",
                    'milestone_ref': None,
                    'priority': 'LOW'
                })
                continue
            
            wr = stat['win_rate']
            
            if wr < 0.40:
                actions.append({
                    'pattern': pattern,
                    'action': 'DISABLE',
                    'reason': f"Win rate {wr*100:.0f}% below 40% threshold",
                    'milestone_ref': '1.9 - Pattern Filtering',
                    'priority': 'HIGH'
                })
            elif wr < 0.50:
                actions.append({
                    'pattern': pattern,
                    'action': 'REDUCE',
                    'reason': f"Win rate {wr*100:.0f}% below target (50%)",
                    'milestone_ref': '1.9 - Pattern Filtering',
                    'priority': 'MEDIUM'
                })
            elif wr < 0.60:
                actions.append({
                    'pattern': pattern,
                    'action': 'KEEP',
                    'reason': f"Win rate {wr*100:.0f}% acceptable",
                    'milestone_ref': None,
                    'priority': 'LOW'
                })
            else:
                actions.append({
                    'pattern': pattern,
                    'action': 'BOOST',
                    'reason': f"Win rate {wr*100:.0f}% above target (60%)",
                    'milestone_ref': '1.9 - Pattern Filtering',
                    'priority': 'HIGH'
                })
        
        return actions
    
    def validate_against_research(self, stats: Dict) -> Dict:
        """
        Compare our results vs research expectations
        
        Research (altFINS): Top-5 patterns should have 70-84% win rate
        """
        if not stats:
            return {
                'status': 'NO_DATA',
                'message': 'No patterns to validate yet'
            }
        
        # Get top patterns
        top_patterns = self.rank_patterns(stats, top=True, n=5)
        
        if not top_patterns:
            return {
                'status': 'INSUFFICIENT_DATA',
                'message': 'Need more trades to validate'
            }
        
        # Calculate average win rate of top patterns
        top_win_rates = [p[1]['win_rate'] for p in top_patterns]
        avg_top_wr = sum(top_win_rates) / len(top_win_rates)
        
        # Research expectation: 70-84%
        expected_min = 0.70
        expected_max = 0.84
        
        if avg_top_wr >= expected_min:
            status = 'ON_TRACK'
            message = f"Top patterns {avg_top_wr*100:.0f}% WR ≥ {expected_min*100:.0f}% expected (altFINS)"
        elif avg_top_wr >= 0.60:
            status = 'PROMISING'
            message = f"Top patterns {avg_top_wr*100:.0f}% WR approaching target ({expected_min*100:.0f}%)"
        else:
            status = 'NEEDS_IMPROVEMENT'
            message = f"Top patterns {avg_top_wr*100:.0f}% WR below {expected_min*100:.0f}% target"
        
        return {
            'status': status,
            'message': message,
            'avg_top_win_rate': avg_top_wr,
            'expected_range': f"{expected_min*100:.0f}-{expected_max*100:.0f}%",
            'top_patterns': [(p[0], f"{p[1]['win_rate']*100:.0f}%") for p in top_patterns]
        }
    
    def generate_report(self, detailed: bool = False) -> str:
        """Generate Daily Pattern Performance Card"""
        stats = self.calculate_pattern_stats()
        
        if not stats:
            return "❌ No pattern data available yet. Start trading!"
        
        report = []
        report.append("="*70)
        report.append("🎯 DAILY PATTERN PERFORMANCE CARD")
        report.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        report.append("="*70)
        
        # Summary stats
        total_trades = sum(s['total_trades'] for s in stats.values())
        total_patterns = len(stats)
        report.append(f"\n📊 SUMMARY:")
        report.append(f"  Total Trades: {total_trades}")
        report.append(f"  Unique Patterns: {total_patterns}")
        
        # Top performers
        report.append(f"\n🏆 TOP PERFORMERS:")
        report.append("-"*70)
        top = self.rank_patterns(stats, top=True, n=3)
        
        if top:
            for i, (pattern, stat) in enumerate(top, 1):
                report.append(f"\n{i}. {pattern.replace('_', ' ').title()}")
                report.append(f"   Trades: {stat['total_trades']} | "
                            f"Win Rate: {stat['win_rate']*100:.0f}% | "
                            f"Avg P&L: {stat['avg_pnl']:+.2f}%")
                report.append(f"   Profit Factor: {stat['profit_factor']:.2f} | "
                            f"Confidence: {stat['avg_confidence']*100:.0f}%")
                
                # Action
                if stat['win_rate'] > 0.60:
                    report.append(f"   ✅ Action: BOOST - Increase confidence to {min(stat['avg_confidence']*1.2, 1.0)*100:.0f}%")
                elif stat['win_rate'] > 0.50:
                    report.append(f"   ✅ Action: KEEP - Pattern working well")
                else:
                    report.append(f"   ⚠️  Action: MONITOR - Need more data")
        else:
            report.append("   No reliable patterns yet (need 3+ trades)")
        
        # Worst performers
        report.append(f"\n🚫 WORST PERFORMERS:")
        report.append("-"*70)
        worst = self.rank_patterns(stats, top=False, n=3)
        
        if worst:
            for i, (pattern, stat) in enumerate(worst, 1):
                report.append(f"\n{i}. {pattern.replace('_', ' ').title()}")
                report.append(f"   Trades: {stat['total_trades']} | "
                            f"Win Rate: {stat['win_rate']*100:.0f}% | "
                            f"Avg P&L: {stat['avg_pnl']:+.2f}%")
                
                # Action
                if stat['total_trades'] < 5:
                    report.append(f"   ⏸️  Action: MONITOR - Need more data ({stat['total_trades']} trades)")
                elif stat['win_rate'] < 0.40:
                    report.append(f"   ❌ Action: DISABLE - Win rate below 40% threshold")
                    report.append(f"   📋 Milestone: 1.9 (Pattern Filtering)")
                else:
                    report.append(f"   ⚠️  Action: REDUCE - Use only in high-confidence scenarios")
        
        # Research validation
        report.append(f"\n📚 RESEARCH VALIDATION:")
        report.append("-"*70)
        validation = self.validate_against_research(stats)
        
        status_emoji = {
            'ON_TRACK': '✅',
            'PROMISING': '🟡',
            'NEEDS_IMPROVEMENT': '⚠️',
            'INSUFFICIENT_DATA': '⏸️',
            'NO_DATA': '❌'
        }
        
        emoji = status_emoji.get(validation['status'], '❓')
        report.append(f"{emoji} Status: {validation['status']}")
        report.append(f"   {validation['message']}")
        
        if 'top_patterns' in validation:
            report.append(f"\n   Top Patterns:")
            for pattern, wr in validation['top_patterns']:
                report.append(f"   - {pattern.replace('_', ' ').title()}: {wr}")
        
        report.append(f"\n   Reference: altFINS study (top patterns 70-84% WR)")
        report.append(f"   Expected Range: {validation.get('expected_range', 'N/A')}")
        
        # Detailed stats (optional)
        if detailed:
            report.append(f"\n📋 DETAILED STATISTICS:")
            report.append("-"*70)
            for pattern, stat in sorted(stats.items(), key=lambda x: x[1]['win_rate'], reverse=True):
                report.append(f"\n{pattern.replace('_', ' ').title()}:")
                report.append(f"  Total: {stat['total_trades']} | "
                            f"W/L/BE: {stat['wins']}/{stat['losses']}/{stat['breakevens']}")
                report.append(f"  Win Rate: {stat['win_rate']*100:.1f}% | "
                            f"Avg P&L: {stat['avg_pnl']:+.2f}%")
                report.append(f"  Best: {stat['best_pnl']:+.2f}% | "
                            f"Worst: {stat['worst_pnl']:+.2f}%")
                report.append(f"  Profit Factor: {stat['profit_factor']:.2f} | "
                            f"Avg Conf: {stat['avg_confidence']*100:.0f}%")
        
        report.append("\n" + "="*70)
        report.append("🔗 NEXT STEPS:")
        report.append(f"   1. Implement pattern filtering (Milestone 1.9)")
        report.append(f"   2. Disable patterns <40% WR")
        report.append(f"   3. Boost patterns >60% WR")
        report.append(f"   4. Collect more data (target: 50+ trades)")
        report.append("="*70)
        
        return "\n".join(report)
    
    def export_json(self) -> Dict:
        """Export statistics as JSON"""
        stats = self.calculate_pattern_stats()
        actions = self.generate_actions(stats)
        validation = self.validate_against_research(stats)
        
        return {
            'generated_at': datetime.now().isoformat(),
            'pattern_statistics': stats,
            'actions': actions,
            'research_validation': validation,
            'summary': {
                'total_trades': sum(s['total_trades'] for s in stats.values()),
                'unique_patterns': len(stats),
                'avg_win_rate': sum(s['win_rate'] for s in stats.values()) / len(stats) if stats else 0
            }
        }


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Pattern Performance Analyzer")
    parser.add_argument('--detailed', action='store_true',
                       help='Show detailed statistics')
    parser.add_argument('--json', action='store_true',
                       help='Export as JSON')
    
    args = parser.parse_args()
    
    analyzer = PatternPerformanceAnalyzer()
    
    if args.json:
        data = analyzer.export_json()
        print(json.dumps(data, indent=2, default=str))
    else:
        report = analyzer.generate_report(detailed=args.detailed)
        print(report)


if __name__ == '__main__':
    main()
