"""Lightweight MCP trading server exposing core tools for the agent.

The server wraps access to the rolling-window pattern database and basic
portfolio state so the AI layer can make informed, safe decisions.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
import json
import sys
from typing import Any, Dict, List, Optional

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
              "timestamp": datetime.now(timezone.utc).isoformat(),
        }


class TradingMCPServer:
    """Expose minimal MCP-style tools for the streaming agent."""

    def __init__(
        self,
        pattern_db: RollingWindowPatternDB,
        portfolio=None,  # Accept actual portfolio instance
        positions_path: Path | str = Path("positions.json"),
        risk_state_path: Path | str = Path("state.json"),
    ) -> None:
        self.pattern_db = pattern_db
        # Use provided portfolio or create default PortfolioState
        self.portfolio = portfolio if portfolio is not None else PortfolioState()
        self.positions_path = Path(positions_path)
        self.risk_state_path = Path(risk_state_path)
        logger.info("🛠️ Trading MCP server initialised (patterns: %s)", pattern_db.count())

    async def get_market_state(self, symbol: str) -> Dict[str, Any]:
        latest = self._latest_pattern_for_symbol(symbol)
        if latest is None:
            logger.debug("Market state request found no patterns for %s", symbol)
            return {
                "symbol": symbol,
                "price": None,
                "rsi": None,
                "ema_ratio": None,
                "price_change": None,
                "volume_change": None,
                "label": None,
                "sample_age_seconds": None,
                "source": "pattern_db",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
            }

        metadata = latest["metadata"]
        ts = metadata.get("timestamp")
        age = None
        if ts is not None:
            age = max(0.0, datetime.now(timezone.utc).timestamp() - float(ts))

        response = {
            "symbol": symbol,
            "pattern_id": latest["id"],
            "price": metadata.get("price"),  # Add current price from pattern
            "rsi": metadata.get("rsi"),
            "ema_ratio": metadata.get("ema_ratio"),
            "price_change": metadata.get("price_change"),
            "volume_change": metadata.get("volume_change"),
            "label": metadata.get("label"),
            "hit_takeprofit": metadata.get("hit_takeprofit"),
            "hit_stoploss": metadata.get("hit_stoploss"),
            "sample_age_seconds": age,
            "source": "pattern_db",
              "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        logger.debug("Market state assembled for %s", symbol)
        return response

    async def get_similar_patterns(self, current_state: Dict[str, float], top_k: int = 5) -> Dict[str, Any]:
        patterns = self.pattern_db.find_similar(current_state, k=top_k)

        win_rate: Optional[float] = None
        if patterns:
            labeled = [p for p in patterns if p["metadata"].get("label") in {"WIN", "LOSS"}]
            if labeled:
                wins = sum(1 for p in labeled if p["metadata"].get("label") == "WIN")
                win_rate = wins / len(labeled) * 100

        response = {
            "count": len(patterns),
            "win_rate": win_rate,
            "patterns": patterns,
              "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        logger.debug("Pattern query returned %s matches", response["count"])
        return response

    async def get_portfolio_state(self) -> Dict[str, Any]:
        positions_snapshot = self._load_json(self.positions_path) or {}
        risk_snapshot = self._load_json(self.risk_state_path) or {}

        # Handle both PortfolioState and PaperTradingPortfolio
        if hasattr(self.portfolio, 'as_dict'):
            portfolio = self.portfolio.as_dict()
        else:
            # PaperTradingPortfolio - build dict manually
            portfolio = {
                "capital": getattr(self.portfolio, 'capital', 0),
                "open_count": len(getattr(self.portfolio, 'positions', [])),
                "max_positions": getattr(self.portfolio, 'MAX_POSITIONS', 20),  # Fixed: uppercase attribute
                "daily_pnl": sum(p.get('realized_pnl', 0) for p in getattr(self.portfolio, 'closed_trades', []) if p.get('exit_time', '').startswith(datetime.now().strftime('%Y-%m-%d'))),
                "open_positions": getattr(self.portfolio, 'positions', []),
            }
        
        if positions_snapshot:
            portfolio.update(
                {
                    "positions_snapshot": positions_snapshot.get("positions", {}),
                    "portfolio_value": positions_snapshot.get("portfolio_value"),
                    "cash_balance": positions_snapshot.get("cash_balance"),
                    "positions_timestamp": positions_snapshot.get("updated_at"),
                }
            )
        if risk_snapshot:
            portfolio.update({"risk": risk_snapshot.get("risk"), "risk_timestamp": risk_snapshot.get("timestamp")})

        return portfolio

    async def check_risk_limits(self, proposed_trade: Dict[str, Any]) -> Dict[str, Any]:
        reasons: List[str] = []
        approved = True

        risk_snapshot = self._load_json(self.risk_state_path) or {}
        risk_info = (risk_snapshot.get("risk") or {}) if isinstance(risk_snapshot, dict) else {}

        # Handle both PortfolioState and PaperTradingPortfolio
        if hasattr(self.portfolio, 'open_positions'):
            open_count = len(self.portfolio.open_positions)
        else:
            # PaperTradingPortfolio - count OPEN positions manually
            open_count = len([p for p in getattr(self.portfolio, 'positions', []) if p.get('status') == 'OPEN'])
        
        max_pos = getattr(self.portfolio, 'MAX_POSITIONS', getattr(self.portfolio, 'max_positions', 20))  # Fixed: handle both cases
        if open_count >= max_pos:
            approved = False
            reasons.append("Max positions reached")

        size = float(proposed_trade.get("position_size", 0))
        if size > self.portfolio.capital * 0.05:
            approved = False
            reasons.append("Position size exceeds 5% cap")

        # Calculate daily P&L - handle both PortfolioState and PaperTradingPortfolio
        if hasattr(self.portfolio, 'daily_pnl'):
            daily_pnl = risk_info.get("daily_pnl", self.portfolio.daily_pnl)
        else:
            # PaperTradingPortfolio - calculate from closed_trades
            today = datetime.now().strftime('%Y-%m-%d')
            daily_pnl = sum(
                p.get('realized_pnl', 0) 
                for p in getattr(self.portfolio, 'closed_trades', []) 
                if p.get('exit_time', '').startswith(today)
            )
            daily_pnl = risk_info.get("daily_pnl", daily_pnl)
        
        # Get starting capital
        if hasattr(self.portfolio, 'starting_capital'):
            starting_capital = risk_info.get("starting_capital", self.portfolio.starting_capital)
        else:
            starting_capital = risk_info.get("starting_capital", self.portfolio.capital)
        if daily_pnl <= -starting_capital * 0.10:
            approved = False
            reasons.append("Daily loss limit hit")

        max_daily_loss_remaining = risk_info.get("max_daily_loss_remaining")
        if max_daily_loss_remaining is not None and max_daily_loss_remaining <= 0:
            approved = False
            reasons.append("Max daily loss remaining exhausted")

        return {
            "approved": approved,
            "reasons": reasons if not approved else ["All checks passed"],
              "timestamp": datetime.now(timezone.utc).isoformat(),
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

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _load_json(self, path: Path) -> Optional[Dict[str, Any]]:
        try:
            if not path.exists():
                return None
            with path.open("r", encoding="utf-8") as handle:
                return json.load(handle)
        except Exception as err:  # pragma: no cover - defensive logging
            logger.warning("Failed to load JSON snapshot %s: %s", path, err)
            return None

    def _latest_pattern_for_symbol(self, symbol: str) -> Optional[Dict[str, Any]]:
        try:
            data = self.pattern_db.collection.get(where={"symbol": symbol}, limit=100)
        except Exception as err:  # pragma: no cover - defensive logging
            logger.warning("Pattern lookup failed for %s: %s", symbol, err)
            return None

        metadatas = data.get("metadatas") or []
        ids = data.get("ids") or []
        if not metadatas:
            return None

        best_idx = max(
            range(len(metadatas)),
            key=lambda idx: (metadatas[idx] or {}).get("timestamp", 0),
        )

        return {"id": ids[best_idx], "metadata": metadatas[best_idx]}


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
