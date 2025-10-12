import sqlite3
import logging

logger = logging.getLogger(__name__)


class DynamicAdaptivePositionManager:
    """
    Dynamic position sizing that adapts to performance
    with hard-coded safety rails to prevent going rogue!
    """

    def __init__(self, starting_capital=5000):
        self.capital = starting_capital

        # LEVEL 1: HARD-CODED SAFETY RAILS (CANNOT BE EXCEEDED!)
        self.ABSOLUTE_MIN_POSITION = 50  # R50 minimum (1%)
        self.ABSOLUTE_MAX_POSITION = 500  # R500 maximum (10%)
        self.ABSOLUTE_MAX_RISK_PCT = 0.10  # Never risk >10% per trade
        self.ABSOLUTE_MAX_DEPLOYED_PCT = 0.60  # Never deploy >60% total
        self.ABSOLUTE_DAILY_LOSS_LIMIT = 250  # R250 max daily loss

        # LEVEL 2: BASE POSITION SIZING (Starting point)
        self.base_position_pct = {
            'T1': 0.03,   # Start at 3% for Tier 1
            'T2': 0.015,  # Start at 1.5% for Tier 2
            'T3': 0.0075  # Start at 0.75% for Tier 3
        }

        # LEVEL 3: PERFORMANCE SCALING RULES
        self.performance_thresholds = {
            0.80: 2.0,   # 80%+ WR → 2x multiplier
            0.75: 1.75,  # 75%+ WR → 1.75x multiplier
            0.70: 1.5,   # 70%+ WR → 1.5x multiplier
            0.65: 1.25,  # 65%+ WR → 1.25x multiplier
            0.55: 1.0,   # 55-65% WR → 1x (base)
            0.50: 0.75,  # 50-55% WR → 0.75x (reduce)
            0.00: 0.5    # <50% WR → 0.5x (minimum)
        }

        # LEVEL 4: DAILY CONFIDENCE MULTIPLIER
        self.confidence_levels = {
            'extreme_profit': 1.3,   # >R150 profit today
            'high_profit': 1.2,      # >R100 profit today
            'moderate_profit': 1.1,  # >R50 profit today
            'neutral': 1.0,          # -R50 to +R50 today
            'moderate_loss': 0.9,    # -R50 to -R100 today
            'high_loss': 0.8,        # -R100 to -R150 today
            'extreme_loss': 0.7      # <-R150 today
        }

        # Optional: override defaults from config if present
        try:
            import config as _cfg  # local import to avoid hard dependency at module load
            self.base_position_pct['T1'] = float(getattr(_cfg, 'BASE_TIER_1_PCT', self.base_position_pct['T1']))
            self.base_position_pct['T2'] = float(getattr(_cfg, 'BASE_TIER_2_PCT', self.base_position_pct['T2']))
            self.base_position_pct['T3'] = float(getattr(_cfg, 'BASE_TIER_3_PCT', self.base_position_pct['T3']))
            self.ABSOLUTE_MIN_POSITION = float(getattr(_cfg, 'ABSOLUTE_MIN_POSITION', self.ABSOLUTE_MIN_POSITION))
            self.ABSOLUTE_MAX_POSITION = float(getattr(_cfg, 'ABSOLUTE_MAX_POSITION', self.ABSOLUTE_MAX_POSITION))
            self.ABSOLUTE_MAX_RISK_PCT = float(getattr(_cfg, 'ABSOLUTE_MAX_RISK_PCT', self.ABSOLUTE_MAX_RISK_PCT))
            self.ABSOLUTE_MAX_DEPLOYED_PCT = float(getattr(_cfg, 'ABSOLUTE_MAX_DEPLOYED_PCT', self.ABSOLUTE_MAX_DEPLOYED_PCT))
            self.ABSOLUTE_DAILY_LOSS_LIMIT = float(getattr(_cfg, 'ABSOLUTE_DAILY_LOSS_LIMIT', self.ABSOLUTE_DAILY_LOSS_LIMIT))
            lookback = int(getattr(_cfg, 'PERFORMANCE_LOOKBACK_TRADES', 20))
            self._override_lookback = max(1, lookback)
        except (ImportError, AttributeError, ValueError, TypeError):
            self._override_lookback = 20

        logger.info("🤖 Dynamic Adaptive Position Manager initialized")
        logger.info("   Capital: R%s", self.capital)
        logger.info("   Safety: R%s - R%s per trade", self.ABSOLUTE_MIN_POSITION, self.ABSOLUTE_MAX_POSITION)

    def get_recent_performance(self, lookback_trades=20):
        """
        Get win rate from last N trades
        """
        # honor configured lookback if provided
        n = max(int(getattr(self, '_override_lookback', lookback_trades)), 1)
        try:
            conn = sqlite3.connect('ozzy_simple.db')
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT 
                    COUNT(*) as total,
                    SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) as wins
                FROM (
                    SELECT pnl FROM trades 
                    ORDER BY entry_timestamp DESC 
                    LIMIT ?
                )
                """,
                (n,),
            )
            result = cursor.fetchone()
            total = int(result[0] or 0)
            wins = int(result[1] or 0)
            if total == 0:
                return 0.60  # Default assumption if no data
            win_rate = wins / total
            logger.info("📊 Recent performance: %s/%s = %.1f%% WR", wins, total, win_rate * 100)
            return win_rate
        except sqlite3.Error as e:
            logger.error("Error getting performance: %s", e)
            return 0.60
        finally:
            if 'conn' in locals():
                try:
                    conn.close()
                except sqlite3.Error:
                    pass

    def get_daily_pnl(self):
        """
        Get today's P&L for confidence multiplier
        """
        try:
            conn = sqlite3.connect('ozzy_simple.db')
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT COALESCE(SUM(pnl), 0) as daily_pnl
                FROM trades
                WHERE date(entry_timestamp) = date('now')
                """
            )
            daily_pnl = float(cursor.fetchone()[0] or 0.0)
            logger.info("💰 Today's P&L: R%.2f", daily_pnl)
            return daily_pnl
        except sqlite3.Error as e:
            logger.error("Error getting daily P&L: %s", e)
            return 0.0
        finally:
            if 'conn' in locals():
                try:
                    conn.close()
                except sqlite3.Error:
                    pass

    def get_performance_multiplier(self):
        """
        Calculate multiplier based on recent win rate
        """
        win_rate = self.get_recent_performance()

        # Find appropriate multiplier
        for threshold, multiplier in sorted(self.performance_thresholds.items(), reverse=True):
            if win_rate >= threshold:
                logger.info("📈 Performance multiplier: %sx (WR: %.1f%%)", multiplier, win_rate * 100)
                return multiplier

        return 0.5  # Minimum if below 50%

    def get_confidence_multiplier(self):
        """
        Calculate multiplier based on today's performance
        """
        daily_pnl = self.get_daily_pnl()

        if daily_pnl > 150:
            multiplier = self.confidence_levels['extreme_profit']
        elif daily_pnl > 100:
            multiplier = self.confidence_levels['high_profit']
        elif daily_pnl > 50:
            multiplier = self.confidence_levels['moderate_profit']
        elif daily_pnl > -50:
            multiplier = self.confidence_levels['neutral']
        elif daily_pnl > -100:
            multiplier = self.confidence_levels['moderate_loss']
        elif daily_pnl > -150:
            multiplier = self.confidence_levels['high_loss']
        else:
            multiplier = self.confidence_levels['extreme_loss']

        logger.info("🎯 Confidence multiplier: %sx (P&L: R%.2f)", multiplier, daily_pnl)
        return multiplier

    def calculate_position_size(self, tier_name, current_capital=None):
        """
        Calculate adaptive position size with all multipliers and safety checks

        Args:
            tier_name: 'T1', 'T2', or 'T3'
            current_capital: Current account capital (if None, uses starting capital)

        Returns:
            dict with position details
        """
        if current_capital is None:
            current_capital = self.capital

        # Step 1: Base position from capital
        base_pct = self.base_position_pct[tier_name]
        base_position = current_capital * base_pct

        # Step 2: Apply performance multiplier
        performance_mult = self.get_performance_multiplier()

        # Step 3: Apply confidence multiplier
        confidence_mult = self.get_confidence_multiplier()

        # Step 4: Calculate final position
        final_position = base_position * performance_mult * confidence_mult

        # Step 5: ENFORCE HARD LIMITS (SAFETY RAILS!)
        final_position = max(final_position, self.ABSOLUTE_MIN_POSITION)
        final_position = min(final_position, self.ABSOLUTE_MAX_POSITION)

        # Ensure doesn't exceed max risk percentage
        max_allowed_by_pct = current_capital * self.ABSOLUTE_MAX_RISK_PCT
        final_position = min(final_position, max_allowed_by_pct)

        # Round to nearest R1
        final_position = round(final_position, 0)

        # Calculate metrics
        actual_pct = (final_position / current_capital) * 100 if current_capital else 0.0

        logger.info(
            "\n        🎯 %s Position Calculated:\n"
            "           Base: R%.0f (%.2f%%)\n"
            "           × Performance: %sx\n"
            "           × Confidence: %sx\n"
            "           = Raw: R%.0f\n"
            "           → Final: R%.0f (%.2f%%)\n"
            "           [Limited by R%s-R%s safety rails]\n",
            tier_name,
            base_position,
            base_pct * 100,
            performance_mult,
            confidence_mult,
            base_position * performance_mult * confidence_mult,
            final_position,
            actual_pct,
            self.ABSOLUTE_MIN_POSITION,
            self.ABSOLUTE_MAX_POSITION,
        )

        return {
            'tier': tier_name,
            'position_size': final_position,  # Currency amount (R)
            'position_pct': actual_pct,
            'base_position': base_position,
            'performance_multiplier': performance_mult,
            'confidence_multiplier': confidence_mult,
            'capital': current_capital,
            'within_limits': True
        }

    def get_all_position_sizes(self, current_capital=None):
        """
        Get current adaptive position sizes for all tiers
        """
        return {
            'T1': self.calculate_position_size('T1', current_capital),
            'T2': self.calculate_position_size('T2', current_capital),
            'T3': self.calculate_position_size('T3', current_capital)
        }


if __name__ == '__main__':
    m = DynamicAdaptivePositionManager(starting_capital=5000)
    print("═" * 70)
    print("🤖 DYNAMIC ADAPTIVE POSITION SIZING")
    print("═" * 70)
    print()
    positions = m.get_all_position_sizes()
    for tier, details in positions.items():
        print(f"{tier}: R{details['position_size']:.0f} ({details['position_pct']:.2f}%)")
        print(f"   Performance mult: {details['performance_multiplier']}x")
        print(f"   Confidence mult: {details['confidence_multiplier']}x")
        print()
    print("Safety Rails:")
    print(f"  Min position: R{m.ABSOLUTE_MIN_POSITION}")
    print(f"  Max position: R{m.ABSOLUTE_MAX_POSITION}")
    print(f"  Daily loss limit: R{m.ABSOLUTE_DAILY_LOSS_LIMIT}")
    print()
