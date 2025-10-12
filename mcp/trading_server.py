"""Lightweight MCP trading server exposing core tools for the agent.

The server wraps access to the rolling-window pattern database and basic
portfolio state so the AI layer can make informed, safe decisions.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from intelligence.rolling_window_db import RollingWindowPatternDB

logger = logging.getLogger(__name__)


@dataclass
class PortfolioState:
    capital: float = 5000.0
    daily_pnl: float = 0.0
    max_positions: int = 3
    open_positions: List[Dict[str, Any]] = field(default_factory=list)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "capital": self.capital,
            "daily_pnl": self.daily_pnl,
            "max_positions": self.max_positions,
            "open_positions": self.open_positions,
            "open_count": len(self.open_positions),
            "timestamp": datetime.utcnow().isoformat(),
        }


class TradingMCPServer:
    """Expose minimal MCP-style tools for the streaming agent."""

    def __init__(self, pattern_db: RollingWindowPatternDB) -> None:
        self.pattern_db = pattern_db
        self.portfolio = PortfolioState()
        logger.info("🛠️ Trading MCP server initialised (patterns: %s)", pattern_db.count())

    async def get_market_state(self, symbol: str) -> Dict[str, Any]:
        # Placeholder; real implementation will read from live feed/shared cache
        mock = {
            "symbol": symbol,
            "price": 0.0,
            "rsi": 50.0,
            "ema_ratio": 1.0,
            "volume_change": 0.0,
            "price_change": 0.0,
            "timestamp": datetime.utcnow().isoformat(),
        }
        logger.debug("Market state requested for %s", symbol)
        return mock

    async def get_similar_patterns(self, current_state: Dict[str, float], top_k: int = 5) -> Dict[str, Any]:
        embedding = [
            float(current_state.get("rsi", 50.0)) / 100.0,
            float(current_state.get("ema_ratio", 1.0)),
            float(current_state.get("volume_change", 0.0)),
            float(current_state.get("price_change", 0.0)),
        ]

        results = self.pattern_db.query(embedding, k=top_k)
        patterns = []
        for metadata, distance in zip(results.get("metadatas", [[]])[0], results.get("distances", [[]])[0]):
            similarity = 1 - distance if distance is not None else None
            patterns.append({"metadata": metadata, "similarity": similarity})

        win_rate = None
        if patterns:
            wins = sum(1 for p in patterns if p["metadata"].get("label") == "WIN")
            win_rate = wins / len(patterns) * 100

        response = {
            "count": len(patterns),
            "win_rate": win_rate,
            "patterns": patterns,
        }
        logger.debug("Pattern query returned %s matches", response["count"])
        return response

    async def get_portfolio_state(self) -> Dict[str, Any]:
        return self.portfolio.as_dict()

    async def check_risk_limits(self, proposed_trade: Dict[str, Any]) -> Dict[str, Any]:
        reasons: List[str] = []
        approved = True

        if len(self.portfolio.open_positions) >= self.portfolio.max_positions:
            approved = False
            reasons.append("Max positions reached")

        size = float(proposed_trade.get("position_size", 0))
        if size > self.portfolio.capital * 0.05:
            approved = False
            reasons.append("Position size exceeds 5% cap")

        if self.portfolio.daily_pnl <= -self.portfolio.capital * 0.10:
            approved = False
            reasons.append("Daily loss limit hit")

        return {
            "approved": approved,
            "reasons": reasons if not approved else ["All checks passed"],
            "timestamp": datetime.utcnow().isoformat(),
        }

    async def call_tool(self, name: str, args: Dict[str, Any]) -> Dict[str, Any]:
        tools = {
            "get_market_state": self.get_market_state,
            "get_similar_patterns": self.get_similar_patterns,
            "get_portfolio_state": self.get_portfolio_state,
            "check_risk_limits": self.check_risk_limits,
        }
        if name not in tools:
            raise ValueError(f"Unknown tool: {name}")
        return await tools[name](**args)


async def _demo() -> None:
    db = RollingWindowPatternDB()
    server = TradingMCPServer(db)
    state = await server.get_market_state("BTCUSDT")
    patterns = await server.get_similar_patterns(state)
    portfolio = await server.get_portfolio_state()
    risk = await server.check_risk_limits({"position_size": 200})
    print("Market", state)
    print("Patterns", patterns)
    print("Portfolio", portfolio)
    print("Risk", risk)


if __name__ == "__main__":
    asyncio.run(_demo())
