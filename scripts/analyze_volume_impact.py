#!/usr/bin/env python3
"""
📊 VOLUME CONFIRMATION ANALYZER - Stage 3 of Learning Pipeline

Validates the Mt.Gox volume hypothesis: Trades WITH volume confirmation
should significantly outperform trades WITHOUT.

Part of Milestone 1.2.5: Build Learning System (Day 3)

Research Expectation (Mt.Gox study): 83% WR WITH volume vs 60% WITHOUT = +23 points

Usage:
    # Generate volume impact report
    python3 analyze_volume_impact.py
    
    # Export to JSON
    python3 analyze_volume_impact.py --json
"""

import sys
import json
from pathlib import Path
from datetime import datetime
from typing import Dict, List

sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    import chromadb
    from chromadb.config import Settings
    CHROMADB_AVAILABLE = True
except ImportError:
    CHROMADB_AVAILABLE = False


class VolumeImpactAnalyzer:
    """
    Analyzes impact of volume confirmation on trade outcomes.
    
    Compares:
    - WITH volume (>1.5× 20-day average)
    - WITHOUT volume (≤1.5× average)
    
    Validates Mt.Gox hypothesis: +23 percentage points improvement
    """
    
    def __init__(self, db_path: str = "data/trade_labels", volume_threshold: float = 1.5):
        self.db_path = Path(db_path)
        self.volume_threshold = volume_threshold
        
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
        return results['metadatas']
    
    def calculate_stats(self, trades: List[Dict]) -> Dict:
        """Calculate statistics for a set of trades"""
        if not trades:
            return {
                'count': 0,
                'wins': 0,
                'losses': 0,
                'breakevens': 0,
                'win_rate': 0.0,
                'avg_pnl': 0.0,
                'profit_factor': 0.0
            }
        
        wins = [t for t in trades if t['outcome'] in ['WIN', 'BIG_WIN']]
        losses = [t for t in trades if t['outcome'] in ['LOSS', 'BIG_LOSS']]
        breakevens = [t for t in trades if t['outcome'] == 'BREAKEVEN']
        
        win_count = len(wins)
        loss_count = len(losses)
        
        win_rate = win_count / (win_count + loss_count) if (win_count + loss_count) > 0 else 0
        
        # P&L stats
        pnls = [t['pnl_pct'] for t in trades]
        avg_pnl = sum(pnls) / len(pnls) if pnls else 0
        
        # Profit factor
        win_pnls = [t['pnl_pct'] for t in wins]
        loss_pnls = [abs(t['pnl_pct']) for t in losses]
        
        total_wins = sum(win_pnls) if win_pnls else 0
        total_losses = sum(loss_pnls) if loss_pnls else 0
        profit_factor = total_wins / total_losses if total_losses > 0 else (float('inf') if total_wins > 0 else 0)
        
        return {
            'count': len(trades),
            'wins': win_count,
            'losses': loss_count,
            'breakevens': len(breakevens),
            'win_rate': win_rate,
            'avg_pnl': avg_pnl,
            'profit_factor': profit_factor
        }
    
    def analyze_volume_impact(self) -> Dict:
        """
        Compare trades WITH vs WITHOUT volume confirmation
        
        Returns:
            {
                'with_volume': stats_dict,
                'without_volume': stats_dict,
                'delta': {
                    'win_rate_improvement': float,
                    'pnl_improvement': float,
                    'expected_from_research': float
                },
                'validation': {
                    'status': str,
                    'message': str
                }
            }
        """
        trades = self.get_all_trades()
        
        if not trades:
            return {
                'error': 'No trades available',
                'with_volume': {},
                'without_volume': {},
                'delta': {},
                'validation': {
                    'status': 'NO_DATA',
                    'message': 'No trades to analyze'
                }
            }
        
        # Split trades by volume
        with_volume = [t for t in trades if t.get('volume_ratio', 1.0) > self.volume_threshold]
        without_volume = [t for t in trades if t.get('volume_ratio', 1.0) <= self.volume_threshold]
        
        # Calculate stats for each group
        with_stats = self.calculate_stats(with_volume)
        without_stats = self.calculate_stats(without_volume)
        
        # Calculate delta (improvement)
        if with_stats['count'] > 0 and without_stats['count'] > 0:
            win_rate_delta = with_stats['win_rate'] - without_stats['win_rate']
            pnl_delta = with_stats['avg_pnl'] - without_stats['avg_pnl']
        else:
            win_rate_delta = 0.0
            pnl_delta = 0.0
        
        # Research expectation: Mt.Gox study showed +23 percentage points
        expected_improvement = 0.23
        
        # Validation
        if with_stats['count'] == 0 or without_stats['count'] == 0:
            validation = {
                'status': 'INSUFFICIENT_DATA',
                'message': f"Need trades in both groups (WITH: {with_stats['count']}, WITHOUT: {without_stats['count']})"
            }
        elif with_stats['count'] < 10 or without_stats['count'] < 10:
            validation = {
                'status': 'PRELIMINARY',
                'message': f"Early results show {win_rate_delta*100:+.0f} points improvement (target: +{expected_improvement*100:.0f}). Need more data."
            }
        elif abs(win_rate_delta) >= expected_improvement:
            validation = {
                'status': 'CONFIRMED',
                'message': f"Volume confirmation adds {win_rate_delta*100:+.0f} points! Mt.Gox hypothesis CONFIRMED (+{expected_improvement*100:.0f} expected)"
            }
        elif win_rate_delta > 0:
            validation = {
                'status': 'PROMISING',
                'message': f"Volume adds {win_rate_delta*100:+.0f} points (target: +{expected_improvement*100:.0f}). Approaching research expectations."
            }
        else:
            validation = {
                'status': 'UNEXPECTED',
                'message': f"Volume shows {win_rate_delta*100:+.0f} points impact. May need strategy adjustment."
            }
        
        return {
            'with_volume': with_stats,
            'without_volume': without_stats,
            'delta': {
                'win_rate_improvement': win_rate_delta,
                'pnl_improvement': pnl_delta,
                'expected_from_research': expected_improvement
            },
            'validation': validation,
            'volume_threshold': self.volume_threshold
        }
    
    def generate_report(self) -> str:
        """Generate Volume Confirmation Analysis Report"""
        analysis = self.analyze_volume_impact()
        
        report = []
        report.append("="*70)
        report.append("📊 VOLUME CONFIRMATION ANALYSIS")
        report.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        report.append(f"Volume Threshold: >{self.volume_threshold}× average")
        report.append("="*70)
        
        if 'error' in analysis:
            report.append(f"\n❌ {analysis['error']}")
            return "\n".join(report)
        
        with_stats = analysis['with_volume']
        without_stats = analysis['without_volume']
        delta = analysis['delta']
        validation = analysis['validation']
        
        # WITH VOLUME stats
        report.append(f"\n✅ WITH VOLUME (>{self.volume_threshold}× average):")
        report.append("-"*70)
        report.append(f"  Trades: {with_stats['count']}")
        report.append(f"  Win Rate: {with_stats['win_rate']*100:.1f}%")
        report.append(f"  Avg P&L: {with_stats['avg_pnl']:+.2f}%")
        report.append(f"  Profit Factor: {with_stats['profit_factor']:.2f}")
        report.append(f"  W/L/BE: {with_stats['wins']}/{with_stats['losses']}/{with_stats['breakevens']}")
        
        # WITHOUT VOLUME stats
        report.append(f"\n❌ WITHOUT VOLUME (≤{self.volume_threshold}× average):")
        report.append("-"*70)
        report.append(f"  Trades: {without_stats['count']}")
        report.append(f"  Win Rate: {without_stats['win_rate']*100:.1f}%")
        report.append(f"  Avg P&L: {without_stats['avg_pnl']:+.2f}%")
        report.append(f"  Profit Factor: {without_stats['profit_factor']:.2f}")
        report.append(f"  W/L/BE: {without_stats['wins']}/{without_stats['losses']}/{without_stats['breakevens']}")
        
        # DELTA (Improvement)
        report.append(f"\n💡 IMPACT:")
        report.append("-"*70)
        report.append(f"  Win Rate Improvement: {delta['win_rate_improvement']*100:+.1f} percentage points")
        report.append(f"  P&L Improvement: {delta['pnl_improvement']:+.2f}%")
        
        if with_stats['profit_factor'] != float('inf') and without_stats['profit_factor'] != float('inf'):
            pf_improvement = with_stats['profit_factor'] - without_stats['profit_factor']
            report.append(f"  Profit Factor Improvement: {pf_improvement:+.2f}")
        
        # RESEARCH VALIDATION
        report.append(f"\n📚 RESEARCH VALIDATION:")
        report.append("-"*70)
        
        status_emoji = {
            'CONFIRMED': '✅',
            'PROMISING': '🟡',
            'PRELIMINARY': '⏸️',
            'UNEXPECTED': '⚠️',
            'INSUFFICIENT_DATA': '❌',
            'NO_DATA': '❌'
        }
        
        emoji = status_emoji.get(validation['status'], '❓')
        report.append(f"{emoji} Status: {validation['status']}")
        report.append(f"   {validation['message']}")
        
        report.append(f"\n   Research Reference: Mt.Gox study")
        report.append(f"   Expected Improvement: +{delta['expected_from_research']*100:.0f} percentage points")
        report.append(f"   Our Result: {delta['win_rate_improvement']*100:+.1f} percentage points")
        
        # ACTIONABLE INSIGHTS
        report.append(f"\n🎯 ACTIONABLE INSIGHTS:")
        report.append("-"*70)
        
        if delta['win_rate_improvement'] > 0.15:
            report.append(f"  ✅ IMPLEMENT VOLUME FILTER NOW!")
            report.append(f"     - Require >1.5× volume for all trades")
            report.append(f"     - Expected: +{delta['win_rate_improvement']*100:.0f} points win rate")
            report.append(f"     - Milestone: 1.10 (Volume Confirmation)")
        elif delta['win_rate_improvement'] > 0:
            report.append(f"  🟡 Volume shows promise (+{delta['win_rate_improvement']*100:.0f} points)")
            report.append(f"     - Collect more data (target: 20+ trades each group)")
            report.append(f"     - Continue monitoring")
        else:
            report.append(f"  ⚠️  Volume shows no improvement")
            report.append(f"     - May need strategy adjustment")
            report.append(f"     - Review volume calculation method")
        
        report.append(f"\n" + "="*70)
        report.append("🔗 NEXT STEPS:")
        report.append(f"   1. Collect more trades (target: 50+ total)")
        report.append(f"   2. If delta >15 points: Implement volume filter (Milestone 1.10)")
        report.append(f"   3. Revalidate with larger dataset")
        report.append("="*70)
        
        return "\n".join(report)
    
    def export_json(self) -> Dict:
        """Export analysis as JSON"""
        analysis = self.analyze_volume_impact()
        
        return {
            'generated_at': datetime.now().isoformat(),
            'volume_threshold': self.volume_threshold,
            'analysis': analysis
        }


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Volume Impact Analyzer")
    parser.add_argument('--json', action='store_true',
                       help='Export as JSON')
    parser.add_argument('--threshold', type=float, default=1.5,
                       help='Volume threshold multiplier (default: 1.5)')
    
    args = parser.parse_args()
    
    analyzer = VolumeImpactAnalyzer(volume_threshold=args.threshold)
    
    if args.json:
        data = analyzer.export_json()
        print(json.dumps(data, indent=2, default=str))
    else:
        report = analyzer.generate_report()
        print(report)


if __name__ == '__main__':
    main()
