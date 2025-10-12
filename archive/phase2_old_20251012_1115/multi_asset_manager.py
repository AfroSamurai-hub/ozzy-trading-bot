from typing import Dict
from datetime import datetime
import config

class MultiAssetManager:
    """
    Manages trading across multiple asset classes with
    asset-specific parameters and capital allocation
    """

    def __init__(self, capital: float | None = None):
        self.total_capital = float(capital if capital is not None else getattr(config, 'STARTING_CAPITAL', 5000))
        self.asset_allocation: Dict[str, float] = getattr(config, 'ASSET_ALLOCATION', {})
        self.asset_parameters: Dict[str, Dict] = getattr(config, 'ASSET_PARAMETERS', {})
        self.hours = getattr(config, 'ASSET_TRADING_HOURS', {})

    def get_asset_capital(self, symbol: str) -> float:
        """Get allocated capital for this asset"""
        allocation_pct = float(self.asset_allocation.get(symbol, 0.0))
        return round(self.total_capital * allocation_pct, 2)

    def get_position_size(self, symbol: str, tier: str) -> float:
        """Calculate base position size for asset and tier (currency amount)"""
        asset_capital = self.get_asset_capital(symbol)
        tier_map = {
            'T1': getattr(config, 'TIER_1_POSITION_PCT', 0.04),
            'T2': getattr(config, 'TIER_2_POSITION_PCT', 0.02),
            'T3': getattr(config, 'TIER_3_POSITION_PCT', 0.01),
        }
        pct = float(tier_map.get(tier, 0.01))
        return round(asset_capital * pct, 2)

    def get_asset_parameters(self, symbol: str) -> Dict:
        """Get trading parameters for this asset"""
        if symbol in self.asset_parameters:
            return self.asset_parameters[symbol]
        # fallback to BTCUSDT defaults
        return self.asset_parameters.get('BTCUSDT', {})

    def is_trading_hours(self, symbol: str, now_utc: datetime | None = None) -> bool:
        """Check if current time is within trading hours for asset (UTC-based)"""
        cfg = self.hours.get(symbol)
        if not cfg or not cfg.get('enabled', True):
            return True
        if now_utc is None:
            now_utc = datetime.utcnow()
        h = now_utc.hour
        sessions = cfg.get('sessions', [])
        for s in sessions:
            start = int(s.get('start', 0))
            end = int(s.get('end', 23))
            if start <= end:
                if start <= h <= end:
                    return True
            else:
                # overnight window (e.g., 19-4)
                if h >= start or h <= end:
                    return True
        return False

    def get_asset_class(self, symbol: str) -> str:
        if symbol == 'XAUUSDT':
            return 'GOLD'
        if symbol in ('EURUSD', 'GBPUSD', 'USDJPY'):
            return 'FOREX'
        if symbol in ('BTCUSDT', 'ETHUSDT'):
            return 'MAJOR_CRYPTO'
        if symbol in ('SOLUSDT', 'BNBUSDT'):
            return 'ALTCOIN'
        return 'UNKNOWN'
