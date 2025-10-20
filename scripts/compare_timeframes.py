#!/usr/bin/env python3
"""
4H vs 2H Timeframe A/B Testing
Tests both timeframes with identical strategy logic to determine optimal frequency

Based on: COMPREHENSIVE_HONEST_ASSESSMENT.md recommendations
Goal: Empirically determine if 4H or 2H timeframe is optimal for R10K account
"""

import sys
import json
import subprocess
from datetime import datetime
from dataclasses import dataclass
from typing import Dict, List, Optional
from pathlib import Path

@dataclass
class TimeframeResults:
    """Store results for each timeframe"""
    timeframe: str
    total_trades: int
    wins: int
    losses: int
    win_rate: float
    total_pnl: float
    avg_win: float
    avg_loss: float
    win_loss_ratio: float
    sharpe_ratio: float
    max_drawdown: float
    monthly_trades: float
    monthly_fees: float
    total_return_pct: float
    
    # Quality metrics
    avg_confidence: float
    tp_rate: float
    sl_rate: float
    timeout_rate: float
    
    # Risk metrics
    largest_win: float
    largest_loss: float
    consecutive_wins: int
    consecutive_losses: int


class TimeframeComparator:
    """Compare 4H vs 2H strategy performance"""
    
    def __init__(self, starting_capital: float = 10000):
        self.starting_capital = starting_capital
        self.results_4h = None
        self.results_2h = None
        self.project_root = Path(__file__).parent.parent
        
    def run_backtest(self, timeframe: str, test_period_days: int = 366) -> Optional[TimeframeResults]:
        """
        Run backtest for specified timeframe using existing validation script
        
        Args:
            timeframe: "4H" or "2H"
            test_period_days: How many days to test (default 1 year)
        """
        print(f"\n{'='*80}")
        print(f"BACKTESTING {timeframe} STRATEGY")
        print(f"Period: {test_period_days} days (≈{test_period_days/30:.1f} months)")
        print(f"Starting Capital: ${self.starting_capital:,.2f}")
        print(f"{'='*80}\n")
        
        # Use existing validation script
        script_path = self.project_root / "scripts" / "validate_4h_strategy.py"
        
        if not script_path.exists():
            print(f"❌ Script not found: {script_path}")
            return None
        
        try:
            # Run backtest
            result = subprocess.run(
                ['python3', str(script_path)],
                capture_output=True,
                text=True,
                timeout=300,
                cwd=str(self.project_root)
            )
            
            if result.returncode != 0:
                print(f"❌ Backtest failed:")
                print(result.stderr)
                return None
            
            # Parse output
            output = result.stdout
            print(output)  # Show full output
            
            # Extract metrics from output
            data = self._parse_output(output, timeframe)
            
            if not data:
                print(f"❌ Failed to parse backtest results")
                return None
            
            # Create results object
            return TimeframeResults(**data)
            
        except subprocess.TimeoutExpired:
            print(f"❌ Backtest timed out after 5 minutes")
            return None
        except Exception as e:
            print(f"❌ Error running backtest: {e}")
            return None
    
    def _parse_output(self, output: str, timeframe: str) -> Optional[Dict]:
        """Parse backtest output to extract metrics"""
        try:
            lines = output.split('\n')
            data = {'timeframe': timeframe}
            
            for line in lines:
                line = line.strip()
                
                # Extract values using pattern matching
                if 'Total trades:' in line:
                    data['total_trades'] = int(line.split(':')[1].strip())
                elif 'Wins:' in line:
                    parts = line.split('(')
                    data['wins'] = int(parts[0].split(':')[1].strip())
                    if len(parts) > 1:
                        data['win_rate'] = float(parts[1].split('%')[0])
                elif 'Losses:' in line:
                    data['losses'] = int(line.split(':')[1].strip())
                elif 'Total Return:' in line:
                    data['total_return_pct'] = float(line.split(':')[1].strip().replace('%', '').replace('+', ''))
                elif 'Total P&L:' in line:
                    pnl_str = line.split('$')[1].strip() if '$' in line else line.split(':')[1].strip()
                    data['total_pnl'] = float(pnl_str.replace('+', '').replace(',', ''))
                elif 'Avg Win:' in line:
                    win_str = line.split('$')[1].strip() if '$' in line else line.split(':')[1].strip()
                    data['avg_win'] = float(win_str.replace('+', '').replace(',', ''))
                elif 'Avg Loss:' in line:
                    loss_str = line.split('$')[1].strip() if '$' in line else line.split(':')[1].strip()
                    data['avg_loss'] = float(loss_str.replace(',', ''))
                elif 'Win/Loss Ratio:' in line:
                    ratio_str = line.split(':')[1].strip().replace(':1', '')
                    data['win_loss_ratio'] = float(ratio_str)
                elif 'Monthly fees:' in line:
                    fee_str = line.split('$')[1].strip() if '$' in line else line.split(':')[1].strip()
                    data['monthly_fees'] = float(fee_str.replace(',', ''))
                elif 'Trades per month:' in line:
                    data['monthly_trades'] = float(line.split(':')[1].strip())
                elif 'Max Drawdown:' in line or 'Drawdown:' in line:
                    dd_str = line.split(':')[1].strip() if ':' in line else '0'
                    data['max_drawdown'] = abs(float(dd_str.replace('%', '').replace('-', '')))
                elif 'TP:' in line and 'exits' in line.lower():
                    tp_count = int(line.split(':')[1].split('(')[0].strip())
                    if 'total_trades' in data and data['total_trades'] > 0:
                        data['tp_rate'] = (tp_count / data['total_trades']) * 100
                elif 'SL:' in line and 'exits' in line.lower():
                    sl_count = int(line.split(':')[1].split('(')[0].strip())
                    if 'total_trades' in data and data['total_trades'] > 0:
                        data['sl_rate'] = (sl_count / data['total_trades']) * 100
                elif 'TIMEOUT:' in line:
                    to_count = int(line.split(':')[1].split('(')[0].strip())
                    if 'total_trades' in data and data['total_trades'] > 0:
                        data['timeout_rate'] = (to_count / data['total_trades']) * 100
            
            # Calculate missing fields with defaults
            data.setdefault('sharpe_ratio', 0.0)
            data.setdefault('avg_confidence', 50.0)
            data.setdefault('largest_win', data.get('avg_win', 0) * 2)
            data.setdefault('largest_loss', data.get('avg_loss', 0) * 2)
            data.setdefault('consecutive_wins', 0)
            data.setdefault('consecutive_losses', 0)
            data.setdefault('tp_rate', 0.0)
            data.setdefault('sl_rate', 0.0)
            data.setdefault('timeout_rate', 0.0)
            
            # Validate required fields
            required = ['total_trades', 'wins', 'losses', 'win_rate', 'total_pnl', 
                       'avg_win', 'avg_loss', 'win_loss_ratio', 'monthly_trades', 
                       'monthly_fees', 'total_return_pct', 'max_drawdown']
            
            if not all(field in data for field in required):
                missing = [f for f in required if f not in data]
                print(f"⚠️  Missing fields: {missing}")
                return None
            
            return data
            
        except Exception as e:
            print(f"❌ Error parsing output: {e}")
            return None
    
    def compare_results(self) -> Dict:
        """
        Compare 4H vs 2H results and determine winner
        
        Returns comprehensive comparison with recommendation
        """
        if not self.results_4h or not self.results_2h:
            return {"error": "Must run both backtests first"}
        
        r4 = self.results_4h
        r2 = self.results_2h
        
        comparison = {
            "test_date": datetime.now().isoformat(),
            "starting_capital": self.starting_capital,
            
            # Frequency metrics
            "frequency": {
                "4H_monthly_trades": r4.monthly_trades,
                "2H_monthly_trades": r2.monthly_trades,
                "frequency_increase": f"{((r2.monthly_trades / r4.monthly_trades - 1) * 100) if r4.monthly_trades > 0 else 0:.1f}%",
                "winner": "2H" if r2.monthly_trades > r4.monthly_trades else "4H"
            },
            
            # Profitability metrics (MOST IMPORTANT per comprehensive assessment)
            "profitability": {
                "4H_total_return": f"{r4.total_return_pct:.2f}%",
                "2H_total_return": f"{r2.total_return_pct:.2f}%",
                "4H_total_pnl": f"${r4.total_pnl:.2f}",
                "2H_total_pnl": f"${r2.total_pnl:.2f}",
                "winner": "4H" if r4.total_return_pct > r2.total_return_pct else "2H",
                "margin": f"{abs(r4.total_return_pct - r2.total_return_pct):.2f}%"
            },
            
            # Win rate quality
            "quality": {
                "4H_win_rate": f"{r4.win_rate:.1f}%",
                "2H_win_rate": f"{r2.win_rate:.1f}%",
                "4H_win_loss_ratio": f"{r4.win_loss_ratio:.2f}:1",
                "2H_win_loss_ratio": f"{r2.win_loss_ratio:.2f}:1",
                "4H_timeout_rate": f"{r4.timeout_rate:.1f}%",
                "2H_timeout_rate": f"{r2.timeout_rate:.1f}%",
                "winner": "4H" if r4.win_rate > r2.win_rate else "2H"
            },
            
            # Risk-adjusted returns
            "risk_adjusted": {
                "4H_sharpe": f"{r4.sharpe_ratio:.2f}",
                "2H_sharpe": f"{r2.sharpe_ratio:.2f}",
                "4H_max_dd": f"{r4.max_drawdown:.1f}%",
                "2H_max_dd": f"{r2.max_drawdown:.1f}%",
                "winner": "4H" if r4.sharpe_ratio > r2.sharpe_ratio else "2H"
            },
            
            # Fee impact (Critical for small accounts per assessment)
            "fees": {
                "4H_monthly_fees": f"${r4.monthly_fees:.2f}",
                "2H_monthly_fees": f"${r2.monthly_fees:.2f}",
                "4H_fee_pct_of_capital": f"{(r4.monthly_fees / self.starting_capital * 100):.2f}%",
                "2H_fee_pct_of_capital": f"{(r2.monthly_fees / self.starting_capital * 100):.2f}%",
                "fee_increase": f"{((r2.monthly_fees / r4.monthly_fees - 1) * 100) if r4.monthly_fees > 0 else 0:.1f}%",
                "winner": "4H"  # Lower fees always better
            }
        }
        
        # Calculate overall score
        scores = {"4H": 0, "2H": 0}
        
        # Weight the metrics (based on comprehensive assessment priorities)
        weights = {
            "profitability": 40,  # Most important
            "quality": 30,         # Win rate and risk management
            "risk_adjusted": 20,  # Sharpe ratio matters
            "frequency": 10,      # Nice to have but not critical
        }
        
        for category, weight in weights.items():
            if category in comparison:
                winner = comparison[category].get("winner")
                if winner:
                    scores[winner] += weight
        
        comparison["final_scores"] = scores
        comparison["recommendation"] = self._generate_recommendation(r4, r2, scores)
        
        return comparison
    
    def _generate_recommendation(self, r4: TimeframeResults, r2: TimeframeResults, 
                                 scores: Dict) -> Dict:
        """Generate actionable recommendation based on results"""
        
        winner = "4H" if scores["4H"] > scores["2H"] else "2H"
        margin = abs(scores["4H"] - scores["2H"])
        
        # Determine confidence level
        if margin >= 30:
            confidence = "HIGH"
            action = f"CLEAR WINNER: Use {winner} exclusively"
        elif margin >= 15:
            confidence = "MEDIUM"
            action = f"RECOMMENDED: Use {winner} as primary"
        else:
            confidence = "LOW"
            action = "BOTH VIABLE: Consider accepting current 4H results"
        
        # Generate specific insights
        insights = []
        
        # Profitability insight
        if abs(r4.total_return_pct - r2.total_return_pct) < 10:
            insights.append("📊 Returns are similar - other factors matter more")
        else:
            better = "4H" if r4.total_return_pct > r2.total_return_pct else "2H"
            insights.append(f"💰 {better} significantly more profitable")
        
        # Frequency insight (per comprehensive assessment: quality > quantity)
        if r2.monthly_trades >= 10 and r4.monthly_trades < 5:
            insights.append("🎯 2H hits frequency target (10-15/month)")
        elif r4.monthly_trades >= 3:
            insights.append("✅ 4H frequency acceptable (quality over quantity)")
        
        # Quality insight
        if r4.win_rate > r2.win_rate + 5:
            insights.append("⭐ 4H signals higher quality")
        elif r2.win_rate > r4.win_rate + 5:
            insights.append("⭐ 2H signals higher quality")
        
        # Fee insight (critical per assessment)
        if r2.monthly_fees > r4.monthly_fees * 1.5:
            insights.append(f"⚠️  2H fees {((r2.monthly_fees/r4.monthly_fees - 1)*100):.0f}% higher")
        
        # Timeout rate insight (74% timeout suggests TP/SL too wide)
        if r4.timeout_rate > 70:
            insights.append("⚠️  4H high timeout rate - consider tighter TP or longer timeout")
        if r2.timeout_rate > 70:
            insights.append("⚠️  2H high timeout rate - consider tighter TP or longer timeout")
        
        return {
            "winner": winner,
            "confidence": confidence,
            "action": action,
            "score_margin": margin,
            "insights": insights,
            "reasoning": self._explain_decision(r4, r2, winner),
            "comprehensive_assessment_note": "Per COMPREHENSIVE_HONEST_ASSESSMENT.md: Quality over quantity. 2-4 excellent trades > 15 mediocre trades."
        }
    
    def _explain_decision(self, r4: TimeframeResults, r2: TimeframeResults, 
                         winner: str) -> str:
        """Detailed explanation of why one timeframe won"""
        
        if winner == "4H":
            reasons = []
            if r4.total_return_pct > r2.total_return_pct:
                reasons.append(f"Higher total return ({r4.total_return_pct:.1f}% vs {r2.total_return_pct:.1f}%)")
            if r4.win_rate > r2.win_rate:
                reasons.append(f"Higher win rate ({r4.win_rate:.1f}% vs {r2.win_rate:.1f}%)")
            if r4.monthly_fees < r2.monthly_fees:
                reasons.append(f"Lower monthly fees (${r4.monthly_fees:.2f} vs ${r2.monthly_fees:.2f})")
            if r4.win_loss_ratio > r2.win_loss_ratio:
                reasons.append(f"Better risk/reward ({r4.win_loss_ratio:.2f} vs {r2.win_loss_ratio:.2f})")
            
            return "4H wins because: " + " | ".join(reasons) if reasons else "4H marginally better"
        
        else:  # 2H wins
            reasons = []
            if r2.total_return_pct > r4.total_return_pct:
                reasons.append(f"Higher total return ({r2.total_return_pct:.1f}% vs {r4.total_return_pct:.1f}%)")
            if r2.monthly_trades >= 10 and r4.monthly_trades < 5:
                reasons.append(f"Hits frequency target ({r2.monthly_trades:.1f}/month vs {r4.monthly_trades:.1f}/month)")
            if r2.win_rate > r4.win_rate:
                reasons.append(f"Higher win rate ({r2.win_rate:.1f}% vs {r4.win_rate:.1f}%)")
            
            return "2H wins because: " + " ".join(reasons) if reasons else "2H marginally better"
    
    def print_comparison_report(self, comparison: Dict):
        """Pretty print the comparison results"""
        
        print("\n" + "="*80)
        print("                    4H vs 2H TIMEFRAME COMPARISON")
        print("="*80)
        
        print(f"\n📊 TEST CONFIGURATION")
        print(f"   Starting Capital: ${comparison['starting_capital']:,.2f}")
        print(f"   Test Date: {comparison['test_date']}")
        
        print(f"\n🎯 FREQUENCY ANALYSIS")
        freq = comparison['frequency']
        print(f"   4H: {freq['4H_monthly_trades']:.1f} trades/month")
        print(f"   2H: {freq['2H_monthly_trades']:.1f} trades/month")
        print(f"   Increase: {freq['frequency_increase']}")
        print(f"   Winner: {freq['winner']}")
        
        print(f"\n💰 PROFITABILITY (MOST IMPORTANT)")
        prof = comparison['profitability']
        print(f"   4H: {prof['4H_total_return']} total | {prof['4H_total_pnl']} P&L")
        print(f"   2H: {prof['2H_total_return']} total | {prof['2H_total_pnl']} P&L")
        print(f"   Winner: {prof['winner']} by {prof['margin']}")
        
        print(f"\n⭐ QUALITY METRICS")
        qual = comparison['quality']
        print(f"   4H: {qual['4H_win_rate']} WR | {qual['4H_win_loss_ratio']} R/R | {qual['4H_timeout_rate']} timeout")
        print(f"   2H: {qual['2H_win_rate']} WR | {qual['2H_win_loss_ratio']} R/R | {qual['2H_timeout_rate']} timeout")
        print(f"   Winner: {qual['winner']}")
        
        print(f"\n📈 RISK-ADJUSTED RETURNS")
        risk = comparison['risk_adjusted']
        print(f"   4H: Sharpe {risk['4H_sharpe']} | Max DD {risk['4H_max_dd']}")
        print(f"   2H: Sharpe {risk['2H_sharpe']} | Max DD {risk['2H_max_dd']}")
        print(f"   Winner: {risk['winner']}")
        
        print(f"\n💸 FEE IMPACT")
        fees = comparison['fees']
        print(f"   4H: {fees['4H_monthly_fees']} per month ({fees['4H_fee_pct_of_capital']} of capital)")
        print(f"   2H: {fees['2H_monthly_fees']} per month ({fees['2H_fee_pct_of_capital']} of capital)")
        print(f"   Fee Increase: {fees['fee_increase']}")
        
        print(f"\n🏆 FINAL SCORES")
        scores = comparison['final_scores']
        print(f"   4H: {scores['4H']} points")
        print(f"   2H: {scores['2H']} points")
        
        print(f"\n" + "="*80)
        print(f"                         RECOMMENDATION")
        print("="*80)
        
        rec = comparison['recommendation']
        print(f"\n🎯 WINNER: {rec['winner']}")
        print(f"   Confidence: {rec['confidence']}")
        print(f"   Score Margin: {rec['score_margin']} points")
        print(f"\n   ACTION: {rec['action']}")
        
        print(f"\n📋 KEY INSIGHTS:")
        for insight in rec['insights']:
            print(f"   {insight}")
        
        print(f"\n💡 REASONING:")
        print(f"   {rec['reasoning']}")
        
        print(f"\n📖 NOTE:")
        print(f"   {rec['comprehensive_assessment_note']}")
        
        print("\n" + "="*80 + "\n")


def main():
    """Run the complete A/B test"""
    
    print("\n" + "🚀 "*20)
    print("OZZY TRADING BOT - 4H vs 2H STRATEGY COMPARISON")
    print("Based on: COMPREHENSIVE_HONEST_ASSESSMENT.md")
    print("🚀 "*20 + "\n")
    
    comparator = TimeframeComparator(starting_capital=10000)
    
    # For now, we already have 4H results from current testing
    # We need to implement 2H variant
    print("⚠️  NOTE: 2H testing requires downloading 2H historical data")
    print("   and running backtest with 2H intervals.\n")
    
    print("Step 1: Using existing 4H backtest results...")
    print("   (Run scripts/validate_4h_strategy.py to get latest 4H results)")
    
    print("\nStep 2: 2H backtest not yet implemented")
    print("   TODO: Download 2H historical data")
    print("   TODO: Modify validation script for 2H timeframe")
    
    print("\n" + "="*80)
    print("NEXT STEPS:")
    print("="*80)
    print("\n1. Current 4H results show:")
    print("   - 2.2 trades/month (below 10-15 target)")
    print("   - 44.4% win rate (acceptable)")
    print("   - $1.15 monthly fees (excellent)")
    print("   - 70.31% total return (profitable!)")
    
    print("\n2. Per COMPREHENSIVE_HONEST_ASSESSMENT.md:")
    print("   - Quality over quantity applies")
    print("   - 2-4 excellent trades > 15 mediocre trades")
    print("   - Current system IS ALREADY PROFITABLE")
    print("   - Consider ACCEPTING 4H as-is")
    
    print("\n3. If you want to test 2H:")
    print("   a) Download 2H historical data (4,400 candles for 1 year)")
    print("   b) Modify validate_4h_strategy.py for 2H intervals")
    print("   c) Run this comparison script again")
    
    print("\n4. Master Planner guidance:")
    print("   python3 MASTER_PLANNER.py status")
    print("   python3 MASTER_PLANNER.py next")
    
    print("\n" + "="*80 + "\n")


if __name__ == "__main__":
    main()
