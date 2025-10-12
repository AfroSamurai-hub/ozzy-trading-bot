#!/usr/bin/env python3
"""
TIME-OF-DAY FILTER A/B TEST
Test whether avoiding certain hours improves trading performance

Strategy:
- Control: No time filter (trade 24/7)
- Test: Avoid low-volatility hours (e.g., 22:00-02:00 UTC)

This runs as a wrapper that tags signals with test group and compares results.
"""

import sys
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Tuple, Optional
import random

# Color codes for terminal output
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
BLUE = "\033[94m"
RESET = "\033[0m"
BOLD = "\033[1m"


class TimeFilterABTest:
    """A/B test for time-of-day trading filters"""
    
    def __init__(self, 
                 test_name: str = "time_filter_night",
                 avoid_hours: List[Tuple[int, int]] = None,
                 trades_per_group: int = 50):
        """
        Initialize A/B test
        
        Args:
            test_name: Name for this test
            avoid_hours: List of (start_hour, end_hour) tuples to avoid (24h UTC)
                        e.g., [(22, 2)] means avoid 22:00-02:00 UTC
            trades_per_group: Number of trades to collect per group
        """
        self.test_name = test_name
        self.avoid_hours = avoid_hours or [(22, 2)]  # Default: avoid late night
        self.trades_per_group = trades_per_group
        
        # Database setup
        self.db_path = Path(__file__).parent.parent / "ozzy_simple.db"
        self.results_path = Path(__file__).parent.parent / "test_results.json"
        
        # Test state
        self.results = self._load_results()
        
    def _load_results(self) -> Dict:
        """Load existing test results from JSON"""
        if self.results_path.exists():
            with open(self.results_path, 'r') as f:
                return json.load(f)
        return {}
    
    def _save_results(self):
        """Save test results to JSON"""
        with open(self.results_path, 'w') as f:
            json.dump(self.results, f, indent=2)
    
    def is_in_avoid_window(self, hour: int) -> bool:
        """
        Check if hour is in any avoid window
        
        Args:
            hour: Hour in 24h format (0-23)
            
        Returns:
            True if hour should be avoided
        """
        for start, end in self.avoid_hours:
            if start < end:
                # Normal range (e.g., 10-14)
                if start <= hour < end:
                    return True
            else:
                # Wraps midnight (e.g., 22-2)
                if hour >= start or hour < end:
                    return True
        return False
    
    def format_hours_range(self) -> str:
        """Format avoid hours for display"""
        ranges = []
        for start, end in self.avoid_hours:
            ranges.append(f"{start:02d}:00-{end:02d}:00 UTC")
        return ", ".join(ranges)
    
    def should_skip_signal(self, test_group: str) -> Tuple[bool, str]:
        """
        Determine if current signal should be skipped based on time
        
        Args:
            test_group: "control" or "test"
            
        Returns:
            (should_skip, reason)
        """
        if test_group == "control":
            # Control group: never skip based on time
            return False, "Control group - no filter"
        
        # Test group: check if in avoid window
        current_hour = datetime.now(timezone.utc).hour
        if self.is_in_avoid_window(current_hour):
            return True, f"In avoid window ({self.format_hours_range()})"
        
        return False, "Outside avoid window - trade allowed"
    
    def assign_test_group(self) -> str:
        """Randomly assign to control or test group (50/50 split)"""
        return random.choice(["control", "test"])
    
    def get_test_stats(self) -> Dict:
        """Get current statistics from database"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        stats = {
            "control": {"trades": 0, "wins": 0, "losses": 0, "total_pnl": 0, "trades_list": []},
            "test": {"trades": 0, "wins": 0, "losses": 0, "total_pnl": 0, "trades_list": []}
        }
        
        # Get trades for this test
        cursor.execute("""
            SELECT id, pnl, entry_reason, exit_timestamp
            FROM trades
            WHERE entry_reason LIKE ?
            AND exit_timestamp IS NOT NULL
            ORDER BY id
        """, (f"%TEST_{self.test_name}_%",))
        
        for trade_id, pnl, entry_reason, exit_time in cursor.fetchall():
            # Parse test group from entry_reason
            # Format: "TEST_time_filter_night_control_..." or "TEST_time_filter_night_test_..."
            if "_control_" in entry_reason:
                group = "control"
            elif "_test_" in entry_reason:
                group = "test"
            else:
                continue
            
            stats[group]["trades"] += 1
            stats[group]["total_pnl"] += pnl
            stats[group]["trades_list"].append(pnl)
            
            if pnl > 0:
                stats[group]["wins"] += 1
            else:
                stats[group]["losses"] += 1
        
        # Calculate win rates
        for group in ["control", "test"]:
            total = stats[group]["trades"]
            if total > 0:
                stats[group]["win_rate"] = (stats[group]["wins"] / total) * 100
                stats[group]["avg_pnl"] = stats[group]["total_pnl"] / total
            else:
                stats[group]["win_rate"] = 0
                stats[group]["avg_pnl"] = 0
        
        conn.close()
        return stats
    
    def calculate_statistical_significance(self, control_pnls: List[float], test_pnls: List[float]) -> Dict:
        """
        Calculate statistical significance using t-test
        
        Args:
            control_pnls: List of P&Ls from control group
            test_pnls: List of P&Ls from test group
            
        Returns:
            Dict with statistical results
        """
        if len(control_pnls) < 30 or len(test_pnls) < 30:
            return {
                "significant": False,
                "p_value": None,
                "t_statistic": None,
                "note": "Need at least 30 trades per group for valid t-test"
            }
        
        try:
            from scipy import stats
            
            # Two-sample t-test
            t_stat, p_value = stats.ttest_ind(control_pnls, test_pnls)
            
            return {
                "significant": p_value < 0.05,
                "p_value": p_value,
                "t_statistic": t_stat,
                "confidence": 95 if p_value < 0.05 else 90 if p_value < 0.10 else 0
            }
        except ImportError:
            return {
                "significant": False,
                "p_value": None,
                "t_statistic": None,
                "note": "scipy not installed - install with: pip install scipy"
            }
    
    def generate_report(self) -> str:
        """Generate comprehensive test report"""
        stats = self.get_test_stats()
        
        control = stats["control"]
        test = stats["test"]
        
        # Header
        report = "\n" + "="*70 + "\n"
        report += f"{BOLD}╔══════════════════════════════════════════════════════════════════╗{RESET}\n"
        report += f"{BOLD}║  TIME-OF-DAY FILTER A/B TEST RESULTS                             ║{RESET}\n"
        report += f"{BOLD}╚══════════════════════════════════════════════════════════════════╝{RESET}\n"
        report += "="*70 + "\n\n"
        
        # Test Configuration
        report += f"{BLUE}📋 TEST CONFIGURATION{RESET}\n"
        report += "─"*70 + "\n"
        report += f"Test Name:           {self.test_name}\n"
        report += f"Avoid Hours (Test):  {self.format_hours_range()}\n"
        report += f"Target Trades:       {self.trades_per_group} per group\n"
        report += f"Status:              {self._get_test_status(control['trades'], test['trades'])}\n"
        report += "\n"
        
        # Progress
        report += f"{BLUE}📊 PROGRESS{RESET}\n"
        report += "─"*70 + "\n"
        report += f"Control Group:       {control['trades']}/{self.trades_per_group} trades "
        report += f"({control['trades']/self.trades_per_group*100:.0f}%)\n"
        report += f"Test Group:          {test['trades']}/{self.trades_per_group} trades "
        report += f"({test['trades']/self.trades_per_group*100:.0f}%)\n"
        report += "\n"
        
        # Results Comparison
        report += f"{BLUE}📈 RESULTS COMPARISON{RESET}\n"
        report += "─"*70 + "\n"
        report += f"{'Metric':<25} {'Control (24/7)':<20} {'Test (Filtered)':<20}\n"
        report += "─"*70 + "\n"
        
        # Trades
        report += f"{'Trades':<25} {control['trades']:<20} {test['trades']:<20}\n"
        
        # Win Rate
        ctrl_wr_color = GREEN if control['win_rate'] >= 55 else YELLOW if control['win_rate'] >= 50 else RED
        test_wr_color = GREEN if test['win_rate'] >= 55 else YELLOW if test['win_rate'] >= 50 else RED
        report += f"{'Win Rate':<25} {ctrl_wr_color}{control['win_rate']:.1f}%{RESET:<20} "
        report += f"{test_wr_color}{test['win_rate']:.1f}%{RESET:<20}\n"
        
        # Win/Loss
        report += f"{'Wins / Losses':<25} {control['wins']}/{control['losses']:<20} "
        report += f"{test['wins']}/{test['losses']:<20}\n"
        
        # Total P&L
        ctrl_pnl_color = GREEN if control['total_pnl'] > 0 else RED
        test_pnl_color = GREEN if test['total_pnl'] > 0 else RED
        report += f"{'Total P&L':<25} {ctrl_pnl_color}R{control['total_pnl']:,.2f}{RESET:<20} "
        report += f"{test_pnl_color}R{test['total_pnl']:,.2f}{RESET:<20}\n"
        
        # Average P&L
        ctrl_avg_color = GREEN if control['avg_pnl'] > 0 else RED
        test_avg_color = GREEN if test['avg_pnl'] > 0 else RED
        report += f"{'Avg P&L per Trade':<25} {ctrl_avg_color}R{control['avg_pnl']:,.2f}{RESET:<20} "
        report += f"{test_avg_color}R{test['avg_pnl']:,.2f}{RESET:<20}\n"
        
        report += "\n"
        
        # Statistical Analysis (if enough data)
        if control['trades'] >= 30 and test['trades'] >= 30:
            sig_results = self.calculate_statistical_significance(
                control['trades_list'], 
                test['trades_list']
            )
            
            report += f"{BLUE}📊 STATISTICAL ANALYSIS{RESET}\n"
            report += "─"*70 + "\n"
            
            if sig_results.get("p_value"):
                report += f"P-Value:             {sig_results['p_value']:.4f}\n"
                report += f"T-Statistic:         {sig_results['t_statistic']:.4f}\n"
                report += f"Significance:        "
                if sig_results['significant']:
                    report += f"{GREEN}YES - 95% confidence{RESET}\n"
                elif sig_results.get('confidence') == 90:
                    report += f"{YELLOW}MARGINAL - 90% confidence{RESET}\n"
                else:
                    report += f"{RED}NO - not statistically significant{RESET}\n"
            else:
                report += f"{YELLOW}{sig_results.get('note', 'Cannot calculate')}{RESET}\n"
            
            report += "\n"
        
        # Verdict
        report += f"{BLUE}🎯 VERDICT{RESET}\n"
        report += "─"*70 + "\n"
        
        if control['trades'] < self.trades_per_group or test['trades'] < self.trades_per_group:
            report += f"{YELLOW}⏳ INCOMPLETE - Need more trades{RESET}\n"
            needed_ctrl = max(0, self.trades_per_group - control['trades'])
            needed_test = max(0, self.trades_per_group - test['trades'])
            report += f"   Control needs: {needed_ctrl} more trades\n"
            report += f"   Test needs: {needed_test} more trades\n"
        else:
            # Compare performance
            wr_diff = test['win_rate'] - control['win_rate']
            pnl_diff = test['avg_pnl'] - control['avg_pnl']
            
            # Decision logic
            if wr_diff > 2 and pnl_diff > 5:
                report += f"{GREEN}✅ WINNER: Time Filter{RESET}\n"
                report += f"   Win rate improved by {wr_diff:+.1f}%\n"
                report += f"   Avg P&L improved by R{pnl_diff:+.2f}\n"
                report += f"   {BOLD}Recommendation: Apply time filter to baseline{RESET}\n"
            elif wr_diff < -2 or pnl_diff < -5:
                report += f"{RED}❌ LOSER: Time Filter Hurts Performance{RESET}\n"
                report += f"   Win rate changed by {wr_diff:+.1f}%\n"
                report += f"   Avg P&L changed by R{pnl_diff:+.2f}\n"
                report += f"   {BOLD}Recommendation: Keep 24/7 trading (no filter){RESET}\n"
            else:
                report += f"{YELLOW}⚖️  NO SIGNIFICANT DIFFERENCE{RESET}\n"
                report += f"   Win rate changed by {wr_diff:+.1f}% (negligible)\n"
                report += f"   Avg P&L changed by R{pnl_diff:+.2f} (negligible)\n"
                report += f"   {BOLD}Recommendation: Keep baseline (no filter){RESET}\n"
        
        report += "\n" + "="*70 + "\n"
        
        return report
    
    def _get_test_status(self, control_trades: int, test_trades: int) -> str:
        """Get colored status indicator"""
        if control_trades >= self.trades_per_group and test_trades >= self.trades_per_group:
            return f"{GREEN}Complete ✅{RESET}"
        else:
            pct = ((control_trades + test_trades) / (self.trades_per_group * 2)) * 100
            return f"{YELLOW}In Progress ({pct:.0f}%){RESET}"
    
    def run_test(self):
        """Main test execution"""
        print(f"\n{BOLD}TIME-OF-DAY FILTER A/B TEST{RESET}")
        print(f"Test: {self.test_name}")
        print(f"Avoid Hours: {self.format_hours_range()}")
        print("="*70)
        
        # Check current status
        stats = self.get_test_stats()
        control_trades = stats["control"]["trades"]
        test_trades = stats["test"]["trades"]
        
        print(f"\nCurrent Progress:")
        print(f"  Control: {control_trades}/{self.trades_per_group} trades")
        print(f"  Test:    {test_trades}/{self.trades_per_group} trades")
        
        if control_trades >= self.trades_per_group and test_trades >= self.trades_per_group:
            print(f"\n{GREEN}✅ Test Complete!{RESET}")
            print(self.generate_report())
            return
        
        print(f"\n{YELLOW}Test still running...{RESET}")
        print(f"\nTo integrate with your bot:")
        print(f"1. Bot assigns random test group to each signal")
        print(f"2. Test group checks time and skips if in avoid window")
        print(f"3. Tags trades with: TEST_{self.test_name}_control_... or TEST_{self.test_name}_test_...")
        print(f"4. Run this script again when enough trades collected")
        
        print(f"\nMonitor progress:")
        print(f"  ./venv/bin/python scripts/test_time_filter.py --status")


def main():
    """Main entry point"""
    import argparse
    
    parser = argparse.ArgumentParser(description="A/B test time-of-day filters")
    parser.add_argument("--test-name", default="time_filter_night", 
                       help="Name for this test (default: time_filter_night)")
    parser.add_argument("--avoid-start", type=int, default=22,
                       help="Start hour to avoid (0-23, default: 22)")
    parser.add_argument("--avoid-end", type=int, default=2,
                       help="End hour to avoid (0-23, default: 2)")
    parser.add_argument("--trades", type=int, default=50,
                       help="Trades per group (default: 50)")
    parser.add_argument("--status", action="store_true",
                       help="Show current test status")
    parser.add_argument("--report", action="store_true",
                       help="Generate full report")
    
    args = parser.parse_args()
    
    # Create test instance
    test = TimeFilterABTest(
        test_name=args.test_name,
        avoid_hours=[(args.avoid_start, args.avoid_end)],
        trades_per_group=args.trades
    )
    
    if args.status or args.report:
        # Just show report
        print(test.generate_report())
    else:
        # Run test
        test.run_test()


if __name__ == "__main__":
    main()
