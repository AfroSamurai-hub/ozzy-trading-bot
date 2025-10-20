#!/usr/bin/env python3
"""
📊 REGIME PERFORMANCE ANALYZER - Stage 3 of Learning Pipeline

Analyzes trade performance across different market regimes:
- Trending Up (bullish)
- Ranging (sideways)
- Trending Down (bearish)

Validates QuantStart hypothesis: Trend-following strategies should perform
+0.6 Sharpe better in trending markets with -50% drawdown reduction.

Part of Milestone 1.2.5: Build Learning System (Day 5)

Usage:
    # Generate regime impact report
    python3 analyze_regime_performance.py
    
    # Export to JSON
    python3 analyze_regime_performance.py --json
    
    # Detailed breakdown
    python3 analyze_regime_performance.py --detailed
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


class RegimePerformanceAnalyzer:
    """
    Analyzes trade performance across market regimes.
    
    Regimes:
    - trending_up: Strong upward momentum
    - trending_down: Strong downward momentum
    - ranging: Sideways/choppy market
    
    Research (QuantStart):
    - Trend-following in trending markets: +0.6 Sharpe, -50% max DD
    - Mean-reversion in ranging markets: Better win rate
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
                'profit_factor': 0.0,
                'sharpe_estimate': 0.0
            }
        
        wins = [t for t in trades if t['outcome'] in ['WIN', 'BIG_WIN']]
        losses = [t for t in trades if t['outcome'] in ['LOSS', 'BIG_LOSS']]
        
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
        
        # Sharpe estimate (simple: avg_pnl / std_dev)
        if len(pnls) > 1:
            import statistics
            std_dev = statistics.stdev(pnls)
            sharpe = (avg_pnl / std_dev) if std_dev > 0 else 0
        else:
            sharpe = 0
        
        return {
            'count': len(trades),
            'wins': win_count,
            'losses': loss_count,
            'breakevens': len([t for t in trades if t['outcome'] == 'BREAKEVEN']),
            'win_rate': win_rate,
            'avg_pnl': avg_pnl,
            'profit_factor': profit_factor,
            'sharpe_estimate': sharpe
        }
    
    def analyze_regime_performance(self) -> Dict:
        """
        Compare trades across different market regimes.
        
        Returns:
            {
                'trending_up': stats_dict,
                'ranging': stats_dict,
                'trending_down': stats_dict,
                'comparison': {...},
                'validation': {...}
            }
        """
        trades = self.get_all_trades()
        
        if not trades:
            return {
                'error': 'No trades available',
                'trending_up': {},
                'ranging': {},
                'trending_down': {},
                'comparison': {},
                'validation': {
                    'status': 'NO_DATA',
                    'message': 'No trades to analyze'
                }
            }
        
        # Split trades by regime
        trending_up = [t for t in trades if t.get('regime', 'unknown') == 'trending_up']
        ranging = [t for t in trades if t.get('regime', 'unknown') == 'ranging']
        trending_down = [t for t in trades if t.get('regime', 'unknown') == 'trending_down']
        unknown = [t for t in trades if t.get('regime', 'unknown') == 'unknown']
        
        # Calculate stats for each regime
        trending_up_stats = self.calculate_stats(trending_up)
        ranging_stats = self.calculate_stats(ranging)
        trending_down_stats = self.calculate_stats(trending_down)
        unknown_stats = self.calculate_stats(unknown)
        
        # Comparison: Trending vs Ranging (QuantStart hypothesis)
        comparison = {}
        
        if trending_up_stats['count'] > 0 and ranging_stats['count'] > 0:
            # Sharpe improvement
            sharpe_delta = trending_up_stats['sharpe_estimate'] - ranging_stats['sharpe_estimate']
            
            # Win rate comparison
            wr_delta = trending_up_stats['win_rate'] - ranging_stats['win_rate']
            
            comparison = {
                'sharpe_improvement': sharpe_delta,
                'win_rate_delta': wr_delta,
                'pnl_delta': trending_up_stats['avg_pnl'] - ranging_stats['avg_pnl']
            }
        
        # Validation vs QuantStart research
        expected_sharpe_improvement = 0.6
        
        if trending_up_stats['count'] < 5 or ranging_stats['count'] < 5:
            validation = {
                'status': 'INSUFFICIENT_DATA',
                'message': f"Need 5+ trades per regime (trending: {trending_up_stats['count']}, ranging: {ranging_stats['count']})"
            }
        elif comparison.get('sharpe_improvement', 0) >= expected_sharpe_improvement:
            validation = {
                'status': 'CONFIRMED',
                'message': f"Trending markets show +{comparison['sharpe_improvement']:.2f} Sharpe improvement! QuantStart validated."
            }
        elif comparison.get('sharpe_improvement', 0) > 0:
            validation = {
                'status': 'PROMISING',
                'message': f"Trending markets +{comparison['sharpe_improvement']:.2f} Sharpe (target: +{expected_sharpe_improvement}). Approaching target."
            }
        else:
            validation = {
                'status': 'UNEXPECTED',
                'message': f"Trending markets show {comparison.get('sharpe_improvement', 0):+.2f} Sharpe. May need strategy adjustment."
            }
        
        return {
            'trending_up': trending_up_stats,
            'ranging': ranging_stats,
            'trending_down': trending_down_stats,
            'unknown': unknown_stats,
            'comparison': comparison,
            'validation': validation
        }
    
    def generate_report(self) -> str:
        """Generate Regime Performance Analysis Report"""
        analysis = self.analyze_regime_performance()
        
        report = []
        report.append("="*70)
        report.append("📊 REGIME PERFORMANCE ANALYSIS")
        report.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        report.append("="*70)
        
        if 'error' in analysis:
            report.append(f"\n❌ {analysis['error']}")
            return "\n".join(report)
        
        trending_up = analysis['trending_up']
        ranging = analysis['ranging']
        trending_down = analysis['trending_down']
        unknown = analysis['unknown']
        comparison = analysis['comparison']
        validation = analysis['validation']
        
        # TRENDING UP stats
        report.append(f"\n📈 TRENDING UP (Bullish):")
        report.append("-"*70)
        report.append(f"  Trades: {trending_up['count']}")
        if trending_up['count'] > 0:
            report.append(f"  Win Rate: {trending_up['win_rate']*100:.1f}%")
            report.append(f"  Avg P&L: {trending_up['avg_pnl']:+.2f}%")
            report.append(f"  Profit Factor: {trending_up['profit_factor']:.2f}")
            report.append(f"  Sharpe (est): {trending_up['sharpe_estimate']:.2f}")
            report.append(f"  W/L/BE: {trending_up['wins']}/{trending_up['losses']}/{trending_up['breakevens']}")
        else:
            report.append("  (no trades yet)")
        
        # RANGING stats
        report.append(f"\n↔️  RANGING (Sideways):")
        report.append("-"*70)
        report.append(f"  Trades: {ranging['count']}")
        if ranging['count'] > 0:
            report.append(f"  Win Rate: {ranging['win_rate']*100:.1f}%")
            report.append(f"  Avg P&L: {ranging['avg_pnl']:+.2f}%")
            report.append(f"  Profit Factor: {ranging['profit_factor']:.2f}")
            report.append(f"  Sharpe (est): {ranging['sharpe_estimate']:.2f}")
            report.append(f"  W/L/BE: {ranging['wins']}/{ranging['losses']}/{ranging['breakevens']}")
        else:
            report.append("  (no trades yet)")
        
        # TRENDING DOWN stats
        report.append(f"\n📉 TRENDING DOWN (Bearish):")
        report.append("-"*70)
        report.append(f"  Trades: {trending_down['count']}")
        if trending_down['count'] > 0:
            report.append(f"  Win Rate: {trending_down['win_rate']*100:.1f}%")
            report.append(f"  Avg P&L: {trending_down['avg_pnl']:+.2f}%")
            report.append(f"  Profit Factor: {trending_down['profit_factor']:.2f}")
            report.append(f"  Sharpe (est): {trending_down['sharpe_estimate']:.2f}")
            report.append(f"  W/L/BE: {trending_down['wins']}/{trending_down['losses']}/{trending_down['breakevens']}")
        else:
            report.append("  (no trades yet)")
        
        # UNKNOWN regime
        if unknown['count'] > 0:
            report.append(f"\n❓ UNKNOWN REGIME:")
            report.append("-"*70)
            report.append(f"  Trades: {unknown['count']}")
            report.append(f"  ⚠️  Regime not captured - improve data collection")
        
        # COMPARISON
        if comparison:
            report.append(f"\n💡 REGIME COMPARISON:")
            report.append("-"*70)
            report.append(f"  Trending vs Ranging:")
            report.append(f"    Sharpe Improvement: {comparison.get('sharpe_improvement', 0):+.2f}")
            report.append(f"    Win Rate Delta: {comparison.get('win_rate_delta', 0)*100:+.1f} points")
            report.append(f"    P&L Delta: {comparison.get('pnl_delta', 0):+.2f}%")
        
        # RESEARCH VALIDATION
        report.append(f"\n📚 RESEARCH VALIDATION:")
        report.append("-"*70)
        
        status_emoji = {
            'CONFIRMED': '✅',
            'PROMISING': '🟡',
            'INSUFFICIENT_DATA': '❌',
            'UNEXPECTED': '⚠️',
            'NO_DATA': '❌'
        }
        
        emoji = status_emoji.get(validation['status'], '❓')
        report.append(f"{emoji} Status: {validation['status']}")
        report.append(f"   {validation['message']}")
        
        report.append(f"\n   Research Reference: QuantStart regime study")
        report.append(f"   Expected: +0.6 Sharpe in trending markets")
        if comparison:
            report.append(f"   Our Result: {comparison.get('sharpe_improvement', 0):+.2f} Sharpe improvement")
        
        # ACTIONABLE INSIGHTS
        report.append(f"\n🎯 ACTIONABLE INSIGHTS:")
        report.append("-"*70)
        
        if validation['status'] == 'CONFIRMED':
            report.append(f"  ✅ IMPLEMENT REGIME FILTER!")
            report.append(f"     - Trade ONLY in trending markets")
            report.append(f"     - Expected: +{comparison.get('sharpe_improvement', 0):.2f} Sharpe improvement")
            report.append(f"     - Milestone: 1.12 (Regime Detection)")
        elif validation['status'] == 'PROMISING':
            report.append(f"  🟡 Regime filtering shows promise")
            report.append(f"     - Continue collecting data")
            report.append(f"     - Target: 20+ trades per regime")
        elif validation['status'] == 'INSUFFICIENT_DATA':
            report.append(f"  📊 COLLECT MORE DATA")
            report.append(f"     - Need 5+ trades per regime")
            report.append(f"     - Currently: trending={trending_up['count']}, ranging={ranging['count']}")
        else:
            report.append(f"  ⚠️  Unexpected results")
            report.append(f"     - Review regime classification logic")
            report.append(f"     - May need strategy adjustment")
        
        report.append(f"\n" + "="*70)
        report.append("🔗 NEXT STEPS:")
        report.append(f"   1. Collect more trades (target: 20+ per regime)")
        report.append(f"   2. If Sharpe improvement >0.3: Implement regime filter")
        report.append(f"   3. Consider HMM regime detection (Milestone 1.12)")
        report.append("="*70)
        
        return "\n".join(report)
    
    def export_json(self) -> Dict:
        """Export analysis as JSON"""
        analysis = self.analyze_regime_performance()
        
        return {
            'generated_at': datetime.now().isoformat(),
            'analysis': analysis
        }


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Regime Performance Analyzer")
    parser.add_argument('--json', action='store_true',
                       help='Export as JSON')
    parser.add_argument('--detailed', action='store_true',
                       help='Show detailed breakdown')
    
    args = parser.parse_args()
    
    analyzer = RegimePerformanceAnalyzer()
    
    if args.json:
        data = analyzer.export_json()
        print(json.dumps(data, indent=2, default=str))
    else:
        report = analyzer.generate_report()
        print(report)


if __name__ == '__main__':
    main()
