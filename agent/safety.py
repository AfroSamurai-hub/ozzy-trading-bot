"""Safety rails for AI-driven trade decisions.

This module centralises guardrails that keep the AI trading agent within
pre-defined risk tolerances before escalating a proposed trade to the
execution layer.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Tuple

from agent.utils import safe_float


@dataclass
class SafetyRailsConfig:
    """Configuration thresholds for validating AI decisions."""

    capital: float = 5_000.0
    max_position_pct: float = 0.05  # 5% of capital per trade
    min_confidence: float = 0.55    # minimum AI confidence (0-1)
    min_pattern_win_rate: float = 40.0  # minimum historical win rate (percent) - lowered to 40% for testing
    rsi_bounds: Tuple[float, float] = (30.0, 70.0)  # avoid extreme RSI zones


class SafetyRails:
    """Lightweight rule engine that double-checks AI trading proposals."""

    def __init__(self, capital: float, config: SafetyRailsConfig | None = None) -> None:
        cfg = config or SafetyRailsConfig(capital=capital)
        self.config = cfg

    def validate_decision(
        self,
        decision: Dict,
        market_state: Dict,
        pattern_win_rate: float | None,
        portfolio: Dict,
    ) -> Tuple[bool, str]:
        """Validate the AI's decision against deterministic guardrails."""

        action = (decision.get("action") or "").upper()
        if action not in {"BUY", "SELL", "SKIP"}:
            return False, "Unsupported action requested"

        # Skip decisions are always safe to honour.
        if action == "SKIP":
            return True, "Decision set to SKIP"

        reasons: list[str] = []
        approved = True

        confidence = safe_float(decision.get("confidence"), default=0.0)
        if confidence < self.config.min_confidence:
            approved = False
            reasons.append(
                f"Confidence {confidence:.2f} below {self.config.min_confidence:.2f} threshold"
            )

        if pattern_win_rate is not None and pattern_win_rate < self.config.min_pattern_win_rate:
            approved = False
            reasons.append(
                f"Historical win rate {pattern_win_rate:.1f}% below {self.config.min_pattern_win_rate:.1f}%"
            )

        rsi = safe_float(market_state.get("rsi"))
        rsi_lower, rsi_upper = self.config.rsi_bounds
        if rsi is not None and (rsi <= rsi_lower or rsi >= rsi_upper):
            approved = False
            reasons.append(f"RSI {rsi:.1f} outside safe band {rsi_lower:.0f}-{rsi_upper:.0f}")

        portfolio_open = portfolio.get("open_count")
        if portfolio_open is None:
            portfolio_open = len(portfolio.get("open_positions") or [])
        max_positions = portfolio.get("max_positions", 3)
        if portfolio_open >= max_positions:
            approved = False
            reasons.append("Portfolio already at max positions")

        available_capital = safe_float(portfolio.get("capital"), default=self.config.capital)
        position_size = safe_float(decision.get("position_size"), default=0.0)
        if position_size > available_capital * self.config.max_position_pct:
            approved = False
            cap_pct = self.config.max_position_pct * 100
            reasons.append(
                f"Position size {position_size:.2f} exceeds {cap_pct:.1f}% of capital"
            )

        if approved:
            return True, "All safety checks passed"
        return False, "; ".join(reasons)
