"""Static library of known trading patterns for quick reference.

Provides a lightweight matching helper that compares the current
market state against pre-defined condition ranges. The goal is to
surface recognisable setups that can be passed into the AI prompt or
logged for human review.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Tuple

NumericRange = Tuple[Optional[float], Optional[float]]


@dataclass(frozen=True)
class PatternDefinition:
    name: str
    conditions: Dict[str, NumericRange]
    historical_win_rate: float
    avg_profit: float
    time_to_profit: str
    risk_level: str
    description: str

    def matches(self, market_state: Dict[str, float]) -> bool:
        for key, (lower, upper) in self.conditions.items():
            value = market_state.get(key)
            if value is None:
                return False
            if lower is not None and value < lower:
                return False
            if upper is not None and value > upper:
                return False
        return True


PATTERN_CHEATSHEET: Dict[str, PatternDefinition] = {
    "bullish_reversal": PatternDefinition(
        name="bullish_reversal",
        conditions={
            "rsi": (20.0, 35.0),
            "ema_ratio": (0.995, 1.01),
            "volume_change": (0.15, None),
        },
        historical_win_rate=0.68,
        avg_profit=0.023,
        time_to_profit="30-60 seconds",
        risk_level="medium",
        description="Oversold bounce combined with volume expansion.",
    ),
    "momentum_continuation": PatternDefinition(
        name="momentum_continuation",
        conditions={
            "rsi": (55.0, 70.0),
            "ema_ratio": (1.005, 1.02),
            "volume_change": (0.1, 0.35),
        },
        historical_win_rate=0.72,
        avg_profit=0.031,
        time_to_profit="60-120 seconds",
        risk_level="low",
        description="Sustained uptrend with supportive momentum.",
    ),
    "whale_accumulation": PatternDefinition(
        name="whale_accumulation",
        conditions={
            "rsi": (30.0, 55.0),
            "volume_change": (0.5, None),
            "price_change": (-0.01, 0.01),
        },
        historical_win_rate=0.75,
        avg_profit=0.045,
        time_to_profit="120-300 seconds",
        risk_level="low",
        description="Large players accumulate quietly before a breakout.",
    ),
    "bear_trap": PatternDefinition(
        name="bear_trap",
        conditions={
            "rsi": (15.0, 30.0),
            "ema_ratio": (0.99, 1.01),
            "price_change": (-0.05, -0.02),
        },
        historical_win_rate=0.65,
        avg_profit=0.052,
        time_to_profit="180-600 seconds",
        risk_level="high",
        description="Capitulation wick that quickly reverses higher.",
    ),
}


def find_matching_patterns(market_state: Dict[str, float]) -> List[PatternDefinition]:
    """Return patterns whose condition ranges include the market state."""

    matches = [pattern for pattern in PATTERN_CHEATSHEET.values() if pattern.matches(market_state)]
    matches.sort(key=lambda pattern: pattern.historical_win_rate, reverse=True)
    return matches


def describe_patterns(patterns: Iterable[PatternDefinition]) -> str:
    """Compact human-readable summary for prompt injection."""

    parts: List[str] = []
    for pattern in patterns:
        parts.append(
            f"{pattern.name} (win≈{pattern.historical_win_rate:.0%}, profit≈{pattern.avg_profit*100:.1f}%)"
        )
    return ", ".join(parts) if parts else "None"
