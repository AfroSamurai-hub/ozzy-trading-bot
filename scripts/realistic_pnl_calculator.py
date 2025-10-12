import sqlite3
from dataclasses import dataclass


@dataclass
class TierConfig:
    position_size: float
    expected_wr: float
    take_profit: float
    stop_loss: float
    priority: int


class RealisticPnLCalculator:
    """Calculate realistic P&L projections for tiered trading"""

    def __init__(self, starting_capital=10000):
        self.starting_capital = starting_capital
        self.tiers = {
            'T1': TierConfig(position_size=200, expected_wr=0.70, take_profit=0.05, stop_loss=0.03, priority=1),
            'T2': TierConfig(position_size=100, expected_wr=0.60, take_profit=0.05, stop_loss=0.03, priority=2),
            'T3': TierConfig(position_size=50, expected_wr=0.52, take_profit=0.05, stop_loss=0.03, priority=3),
        }
        self.max_concurrent_positions = 5
        self.max_daily_loss = 500
        self.max_capital_deployed_pct = 0.30

    def calculate_tier_pnl(self, tier_name, signal_count):
        cfg = self.tiers[tier_name]
        expected_wins = int(signal_count * cfg.expected_wr)
        expected_losses = signal_count - expected_wins
        win_amount = cfg.position_size * cfg.take_profit
        loss_amount = cfg.position_size * cfg.stop_loss
        total_win_pnl = expected_wins * win_amount
        total_loss_pnl = expected_losses * loss_amount
        net_pnl = total_win_pnl - total_loss_pnl
        return {
            'tier': tier_name,
            'signal_count': signal_count,
            'expected_wins': expected_wins,
            'expected_losses': expected_losses,
            'win_rate': cfg.expected_wr * 100,
            'win_amount_per_trade': win_amount,
            'loss_amount_per_trade': loss_amount,
            'total_win_pnl': total_win_pnl,
            'total_loss_pnl': total_loss_pnl,
            'net_pnl': net_pnl,
            'roi_pct': (net_pnl / self.starting_capital) * 100,
        }

    def calculate_realistic_execution(self, tier_signals):
        prioritized = ['T1', 'T2', 'T3']
        max_capital = self.starting_capital * self.max_capital_deployed_pct
        executed = {'T1': 0, 'T2': 0, 'T3': 0}
        total_capital = 0
        total_positions = 0
        for tier in prioritized:
            available = int(tier_signals.get(tier, 0))
            pos_size = self.tiers[tier].position_size
            for _ in range(available):
                if total_positions >= self.max_concurrent_positions:
                    break
                if total_capital + pos_size > max_capital:
                    break
                executed[tier] += 1
                total_capital += pos_size
                total_positions += 1
        return {
            'executed': executed,
            'total_positions': total_positions,
            'capital_deployed': total_capital,
            'capital_deployed_pct': (total_capital / self.starting_capital) * 100,
        }

    def generate_report(self, tier_signals):
        print("═" * 70)
        print("💰 REALISTIC P&L PROJECTION")
        print("═" * 70)
        print()
        # Scenario 1: All signals executed
        print("📊 SCENARIO 1: All Signals Executed (Theoretical)")
        print("─" * 70)
        total_theoretical_pnl = 0
        for tier, count in tier_signals.items():
            res = self.calculate_tier_pnl(tier, count)
            emoji = {'T1': '🟢', 'T2': '🟡', 'T3': '🟠'}[tier]
            print(f"\n{emoji} {tier} ({count} signals @ {res['win_rate']:.0f}% WR):")
            print(f"  Position size: R{self.tiers[tier].position_size}")
            print(f"  Expected wins: {res['expected_wins']} × R{res['win_amount_per_trade']:.2f} = R{res['total_win_pnl']:.2f}")
            print(f"  Expected losses: {res['expected_losses']} × R{res['loss_amount_per_trade']:.2f} = -R{res['total_loss_pnl']:.2f}")
            print(f"  Net P&L: R{res['net_pnl']:.2f} ({res['roi_pct']:+.2f}%)")
            total_theoretical_pnl += res['net_pnl']
        print()
        print("-" * 70)
        print(f"💰 Total Theoretical P&L: R{total_theoretical_pnl:.2f}")
        print(f"📈 ROI: {(total_theoretical_pnl / self.starting_capital) * 100:+.2f}%")
        print()
        print("📊 SCENARIO 2: Realistic Execution (Constrained)")
        print("─" * 70)
        print(f"  • Max concurrent positions: {self.max_concurrent_positions}")
        print(f"  • Max capital deployed: {self.max_capital_deployed_pct * 100:.0f}% (R{self.starting_capital * self.max_capital_deployed_pct:.0f})")
        print(f"  • Max daily loss: R{self.max_daily_loss}")
        print()
        realistic = self.calculate_realistic_execution(tier_signals)
        print("Realistic execution plan:")
        print(f"  • T1: {realistic['executed']['T1']} trades (of {tier_signals.get('T1', 0)})")
        print(f"  • T2: {realistic['executed']['T2']} trades (of {tier_signals.get('T2', 0)})")
        print(f"  • T3: {realistic['executed']['T3']} trades (of {tier_signals.get('T3', 0)})")
        print(f"  • Total positions: {realistic['total_positions']}")
        print(f"  • Capital deployed: R{realistic['capital_deployed']:.2f} ({realistic['capital_deployed_pct']:.1f}%)")
        print()
        total_realistic_pnl = 0
        for tier, count in realistic['executed'].items():
            if count <= 0:
                continue
            res = self.calculate_tier_pnl(tier, count)
            emoji = {'T1': '🟢', 'T2': '🟡', 'T3': '🟠'}[tier]
            print(f"{emoji} {tier} ({count} trades): Net P&L: R{res['net_pnl']:.2f}")
            total_realistic_pnl += res['net_pnl']
        print()
        print("-" * 70)
        print(f"💰 REALISTIC DAILY P&L: R{total_realistic_pnl:.2f}")
        print(f"📈 Daily ROI: {(total_realistic_pnl / self.starting_capital) * 100:+.2f}%")
        print("═" * 70)
        return {
            'theoretical_pnl': total_theoretical_pnl,
            'realistic_pnl': total_realistic_pnl,
            'realistic_execution': realistic,
        }

if __name__ == '__main__':
    # Example usage placeholder
    calc = RealisticPnLCalculator(10000)
    # Replace with DB-derived numbers when used standalone
    calc.generate_report({'T1': 0, 'T2': 0, 'T3': 0})
