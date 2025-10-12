"""AI trading agent powered by OpenAI's GPT models.

The agent orchestrates data collection through the Trading MCP server,
asks OpenAI for a trading recommendation, and enforces deterministic
safety rails before a trade is allowed to proceed.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Any, Dict

from openai import OpenAI
from openai import APIConnectionError, OpenAIError

from agent.safety import SafetyRails

logger = logging.getLogger(__name__)


class TradingAgent:
    """High-level controller around the OpenAI trading workflow."""

    def __init__(
        self,
        mcp_server,
        api_key: str | None = None,
        capital: float = 5_000.0,
        model: str = "gpt-4o-mini",
        max_position_size: float | None = None,
    ) -> None:
        self.mcp = mcp_server
        self.safety = SafetyRails(capital)
        self.capital = capital
        self.model = model
        self.max_position_size = max_position_size or capital * 0.05

        key = api_key or os.getenv("OPENAI_API_KEY")
        if not key:
            raise ValueError("OpenAI API key missing. Set OPENAI_API_KEY or pass api_key explicitly.")

        self.client = OpenAI(api_key=key)

        # Cost tracking
        self.api_calls_today = 0
        self.tokens_used_today = 0
        self.estimated_cost_today = 0.0

        logger.info("🤖 AI Agent initialised with OpenAI")
        logger.info("   Model: %s", model)
        logger.info("   Capital: $%.2f", capital)

    async def analyze_and_decide(self, symbol: str = "BTCUSDT") -> Dict[str, Any]:
        """Core loop: gather state, query OpenAI, enforce safeguards."""

        logger.info("\n🔍 Analyzing %s...", symbol)

        market_state = await self.mcp.get_market_state(symbol)
        logger.info(
            "   RSI: %s | EMA ratio: %s | Price Δ: %s",
            _fmt(market_state.get("rsi")),
            _fmt(market_state.get("ema_ratio")),
            _fmt(market_state.get("price_change")),
        )

        patterns = await self.mcp.get_similar_patterns(market_state, top_k=10)
        win_rate = patterns.get("win_rate")
        logger.info(
            "   Patterns found: %s | Win rate: %s",
            patterns.get("count"),
            f"{win_rate:.1f}%" if win_rate is not None else "n/a",
        )

        portfolio = await self.mcp.get_portfolio_state()
        logger.info(
            "   Open positions: %s/%s | Available capital: $%s",
            portfolio.get("open_count"),
            portfolio.get("max_positions"),
            _fmt(portfolio.get("capital")),
        )

        ai_decision = await self._call_openai(market_state, patterns, portfolio)
        logger.info("\n🤖 AI Decision: %s", ai_decision)

        action = (ai_decision.get("action") or "").upper()
        if action in {"BUY", "SELL"}:
            approved, reason = self.safety.validate_decision(ai_decision, market_state, win_rate, portfolio)
            if not approved:
                logger.warning("🛡️ SAFETY RAILS REJECTED: %s", reason)
                return {
                    "action": "SKIP",
                    "confidence": 0.0,
                    "reasoning": f"Rejected by safety rails: {reason}",
                    "original_decision": ai_decision,
                }

            risk_check = await self.mcp.check_risk_limits(ai_decision)
            if not risk_check.get("approved", False):
                reasons = risk_check.get("reasons") or ["Unknown risk failure"]
                logger.warning("🛡️ RISK CHECK FAILED: %s", ", ".join(reasons))
                return {
                    "action": "SKIP",
                    "confidence": 0.0,
                    "reasoning": f"Risk check failed: {', '.join(reasons)}",
                    "original_decision": ai_decision,
                }

        return ai_decision

    async def _call_openai(
        self,
        market_state: Dict[str, Any],
        patterns: Dict[str, Any],
        portfolio: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Invoke OpenAI with structured prompt and parse response."""

        system_prompt = (
            "You are an expert cryptocurrency trading AI. "
            "Analyse market data and respond with a single JSON object only."
        )

        win_rate = patterns.get("win_rate")
        avg_return = None
        similar_patterns = patterns.get("patterns") or []
        if similar_patterns:
            returns: list[float] = []
            for pattern in similar_patterns:
                metadata = pattern.get("metadata") if isinstance(pattern, dict) else None
                value = metadata.get("price_change") if isinstance(metadata, dict) else None
                if isinstance(value, (int, float)):
                    returns.append(float(value))
            if returns:
                avg_return = sum(returns) / len(returns)

        available_capital = _safe_float(
            portfolio.get("cash_balance", portfolio.get("capital")),
            default=self.capital,
        )
        max_new_position_size = min(self.max_position_size, (available_capital or self.capital) * 0.05)

        user_prompt = (
            f"CURRENT MARKET\n"
            f"- Symbol: {market_state.get('symbol', 'UNKNOWN')}\n"
            f"- RSI: {market_state.get('rsi', 'n/a')}\n"
            f"- EMA Ratio: {market_state.get('ema_ratio', 'n/a')} (>1.0 = uptrend)\n"
            f"- Volume Change: {market_state.get('volume_change', 'n/a')}\n"
            f"- Price Change: {market_state.get('price_change', 'n/a')}\n\n"
            f"HISTORICAL PATTERNS\n"
            f"- Similar patterns: {patterns.get('count', 0)}\n"
            f"- Win rate: {win_rate if win_rate is not None else 'n/a'}\n"
            f"- Average price change: {avg_return if avg_return is not None else 'n/a'}\n\n"
            f"PORTFOLIO\n"
            f"- Capital: {portfolio.get('capital', self.capital)}\n"
            f"- Open positions: {portfolio.get('open_count')} / {portfolio.get('max_positions')}\n"
            f"- Daily P&L: {portfolio.get('daily_pnl', 0)}\n"
            f"- Available capital: {available_capital}\n\n"
            "Rules:\n"
            "- Return JSON only.\n"
            "- JSON schema: {\"action\": \"BUY|SELL|SKIP\", \"confidence\": float 0-1, \"position_size\": float, \"reasoning\": string}.\n"
            "- Require win rate >= 60 to trade.\n"
            "- Avoid RSI above 70 or below 30.\n"
            f"- Limit new position size to <= {max_new_position_size:.2f}.\n"
            "- If unsure, respond with SKIP."
        )

        try:
            response = self.client.responses.create(
                model=self.model,
                input=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.3,
                max_output_tokens=200,
                response_format={"type": "json_object"},
            )
        except (APIConnectionError, OpenAIError) as err:
            logger.error("❌ OpenAI API error: %s", err)
            return {
                "action": "SKIP",
                "confidence": 0.0,
                "position_size": 0.0,
                "reasoning": f"AI error: {err}",
            }

        self.api_calls_today += 1
        usage = getattr(response, "usage", None)
        if usage is not None:
            input_tokens = getattr(usage, "input_tokens", 0) or 0
            output_tokens = getattr(usage, "output_tokens", 0) or 0
            self.tokens_used_today += input_tokens + output_tokens
            cost = (input_tokens / 1_000_000 * 0.15) + (output_tokens / 1_000_000 * 0.60)
            self.estimated_cost_today += cost
            logger.info(
                "💰 API Call #%s: $%.4f (Total today: $%.4f)",
                self.api_calls_today,
                cost,
                self.estimated_cost_today,
            )
        text = getattr(response, "output_text", None) or _extract_response_text(response)
        try:
            decision = json.loads(text)
        except json.JSONDecodeError as err:
            logger.error("Failed to parse OpenAI response: %s", err)
            decision = {
                "action": "SKIP",
                "confidence": 0.0,
                "position_size": 0.0,
                "reasoning": f"Invalid JSON from model: {err}",
            }

        decision.setdefault("action", "SKIP")
        decision.setdefault("confidence", 0.0)
        decision.setdefault("position_size", 0.0)
        decision.setdefault("reasoning", "No reasoning provided")
        decision["action"] = (decision.get("action") or "SKIP").upper()

        # Enforce position guard here as well (belt-and-braces).
        max_size = max_new_position_size
        size_value = _safe_float(decision.get("position_size"), default=max_size)
        if size_value and size_value > max_size:
            decision["position_size"] = max_size
        elif size_value is None:
            decision["position_size"] = max_size
        else:
            decision["position_size"] = size_value

        return decision


def _extract_response_text(response) -> str:
    """Pull text content from the OpenAI responses API."""

    try:
        outputs = response.output or []
    except AttributeError:
        return "{}"

    for item in outputs:
        parts = getattr(item, "content", [])
        if not parts:
            continue
        text = getattr(parts[0], "text", None)
        if text:
            return text
    return "{}"


def _safe_float(value, default: float | None = None) -> float | None:
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _fmt(value) -> str:
    if value is None:
        return "n/a"
    try:
        return f"{float(value):.4f}"
    except (TypeError, ValueError):
        return str(value)


async def _smoke_test() -> None:
    from intelligence.rolling_window_db import RollingWindowPatternDB
    from mcp.trading_server import TradingMCPServer

    pattern_db = RollingWindowPatternDB()
    mcp = TradingMCPServer(pattern_db)

    agent = TradingAgent(mcp)
    decision = await agent.analyze_and_decide("BTCUSDT")
    logger.info("Decision: %s", decision)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    try:
        asyncio.run(_smoke_test())
    except ValueError as err:
        logger.error("%s", err)
        logger.info("Set OPENAI_API_KEY before running the smoke test.")
