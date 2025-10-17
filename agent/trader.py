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
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from openai import OpenAI
from openai import APIConnectionError, OpenAIError

from agent.safety import SafetyRails
from agent.utils import safe_float, safe_int
from intelligence.pattern_library import PatternDefinition, describe_patterns, find_matching_patterns
from agent.improvements import (
    get_confidence_calculator,
    get_pattern_manager,
    get_spacing_manager
)

logger = logging.getLogger(__name__)

DECISIONS_LOG_FILE = Path(__file__).parent.parent / "logs/decisions.json"


class TradingAgent:
    """
    🧠 Self-Aware Trading Agent - Knows what it needs!
    
    This agent CHECKS its own dependencies and DEMANDS them if missing:
    - Pattern Intelligence (for win rates)
    - Dynamic Confidence Calculator (for smart confidence)
    - Improvement Managers (for pattern diversity, entry spacing)
    
    Philosophy: "I won't make decisions without the tools I need!"
    """

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

        # 🧬 SELF-AWARENESS: Check and initialize intelligence systems
        self._initialize_intelligence_systems()

        logger.info("🤖 AI Agent initialised with OpenAI")
        logger.info("   Model: %s", model)
        logger.info("   Capital: $%.2f", capital)
        self._ensure_log_file()
    
    def _initialize_intelligence_systems(self):
        """
        🧠 SELF-AWARENESS: Check if I have the intelligence I need!
        
        This agent KNOWS it needs:
        1. Pattern Intelligence (win rates, effectiveness)
        2. Dynamic Confidence Calculator (smart confidence)
        3. Improvement Managers (diversity, spacing)
        
        If missing, it DEMANDS initialization!
        """
        logger.info("🔍 Checking agent intelligence systems...")
        
        # Check 1: Pattern Intelligence
        try:
            from intelligence.pattern_intelligence import PatternIntelligence, check_intelligence_health
            
            if not PatternIntelligence.is_initialized():
                logger.warning("⚠️ Pattern Intelligence NOT initialized! Bootstrapping...")
                self.pattern_intelligence = PatternIntelligence.get_instance()
            else:
                self.pattern_intelligence = PatternIntelligence.get_instance()
                logger.info("✅ Pattern Intelligence ready")
            
            # Health check
            health = check_intelligence_health()
            if health.get('status') == '🔥 CRITICAL':
                logger.warning(f"⚠️ Pattern Intelligence health: {health.get('status')}")
                logger.warning(f"   Issues: {health.get('issues', [])}")
            else:
                logger.info(f"   Status: {health.get('status')}")
                logger.info(f"   Patterns with data: {health.get('patterns_with_trades', 0)}")
        
        except ImportError as e:
            logger.error(f"❌ CRITICAL: Pattern Intelligence module missing! {e}")
            logger.error("   Agent will work but won't learn from outcomes!")
            self.pattern_intelligence = None
        
        # Check 2: Dynamic Confidence Calculator
        try:
            from agent.improvements import get_confidence_calculator
            self.confidence_calculator = get_confidence_calculator()
            logger.info("✅ Dynamic Confidence Calculator ready")
        except ImportError as e:
            logger.error(f"❌ Dynamic Confidence Calculator missing! {e}")
            self.confidence_calculator = None
        
        # Check 3: Pattern Diversity Manager
        try:
            from agent.improvements import get_pattern_manager
            self.pattern_manager = get_pattern_manager()
            logger.info("✅ Pattern Diversity Manager ready")
        except ImportError as e:
            logger.warning(f"⚠️ Pattern Diversity Manager missing! {e}")
            self.pattern_manager = None
        
        # Check 4: Entry Spacing Manager
        try:
            from agent.improvements import get_spacing_manager
            self.spacing_manager = get_spacing_manager()
            logger.info("✅ Entry Spacing Manager ready")
        except ImportError as e:
            logger.warning(f"⚠️ Entry Spacing Manager missing! {e}")
            self.spacing_manager = None
        
        # Final status
        systems_ready = sum([
            self.pattern_intelligence is not None,
            self.confidence_calculator is not None,
            self.pattern_manager is not None,
            self.spacing_manager is not None
        ])
        
        if systems_ready == 4:
            logger.info("🧬 All intelligence systems operational! Agent is FULLY AWARE! 🚀")
        elif systems_ready >= 2:
            logger.warning(f"⚠️ Agent partially aware: {systems_ready}/4 systems ready")
        else:
            logger.error("🔥 CRITICAL: Agent is NOT SELF-AWARE! Missing critical systems!")
        
        self.systems_ready = systems_ready
    
    def check_readiness(self) -> Dict[str, Any]:
        """
        🔍 Self-diagnostic: Am I ready to trade?
        
        Returns health status and any warnings.
        """
        return {
            'pattern_intelligence': self.pattern_intelligence is not None,
            'confidence_calculator': self.confidence_calculator is not None,
            'pattern_manager': self.pattern_manager is not None,
            'spacing_manager': self.spacing_manager is not None,
            'systems_ready': self.systems_ready,
            'ready_to_trade': self.systems_ready >= 2,  # At least pattern intelligence + confidence
            'optimal': self.systems_ready == 4
        }

    def _ensure_log_file(self):
        """Ensure the decision log file and its directory exist."""
        DECISIONS_LOG_FILE.parent.mkdir(exist_ok=True)
        if not DECISIONS_LOG_FILE.exists():
            with open(DECISIONS_LOG_FILE, "w", encoding="utf-8") as f:
                json.dump({"decisions": [], "portfolio": {"starting_capital": self.capital, "current_capital": self.capital}}, f, indent=2)

    def _log_decision(self, decision: Dict[str, Any], market_state: Dict[str, Any]):
        """Logs the final decision to a JSON file."""
        # Extract pattern from reasoning if not explicitly provided
        pattern = decision.get("pattern")
        if not pattern:
            reasoning = decision.get("reasoning", "")
            if "whale accumulation" in reasoning.lower():
                pattern = "Whale Accumulation"
            elif "bullish divergence" in reasoning.lower():
                pattern = "Bullish Divergence"
            elif "bearish divergence" in reasoning.lower():
                pattern = "Bearish Divergence"
            elif "support bounce" in reasoning.lower():
                pattern = "Support Bounce"
            elif "resistance breakout" in reasoning.lower():
                pattern = "Resistance Breakout"
            else:
                pattern = "General Pattern"
        
        # Extract expected profit if not explicitly provided
        expected_profit_pct = decision.get("expected_profit_pct")
        if not expected_profit_pct:
            reasoning = decision.get("reasoning", "")
            import re
            profit_match = re.search(r"(\d+(\.\d+)?)%", reasoning)
            if profit_match:
                try:
                    expected_profit_pct = float(profit_match.group(1))
                except ValueError:
                    expected_profit_pct = None
        
        log_entry = {
            "timestamp": datetime.now().isoformat() + "Z",
            "action": decision.get("action"),
            "symbol": market_state.get("symbol"),
            "entry_price": market_state.get("price"),
            "position_size": decision.get("position_size"),
            "confidence": decision.get("confidence"),
            "pattern": pattern,
            "reasoning": decision.get("reasoning"),
            "expected_profit_pct": expected_profit_pct,
            "status": "OPEN" if decision.get("action") in ["BUY", "SELL"] else "SKIPPED",
            "current_price": market_state.get("price"),
            "current_pnl": 0.0,
            "current_pnl_pct": 0.0,
            "exit_price": None,
            "exit_time": None,
            "outcome": None,
            "actual_pnl": None,
            # Add market state indicators for dashboard analysis
            "rsi": market_state.get("rsi"),
            "ema_ratio": market_state.get("ema_ratio"),
            "volume_change": market_state.get("volume_change"),
            "price_change": market_state.get("price_change"),
        }

        # Ensure the log directory exists
        DECISIONS_LOG_FILE.parent.mkdir(exist_ok=True)

        try:
            with open(DECISIONS_LOG_FILE, "r+", encoding="utf-8") as f:
                data = json.load(f)
                data["decisions"].append(log_entry)
                
                # Update portfolio information
                if decision.get("action") in ["BUY", "SELL"]:
                    position_size = decision.get("position_size", 0)
                    data["portfolio"]["current_capital"] -= position_size
                
                f.seek(0)
                json.dump(data, f, indent=2)
                f.truncate()
        except (FileNotFoundError, json.JSONDecodeError):
            with open(DECISIONS_LOG_FILE, "w", encoding="utf-8") as f:
                json.dump({
                    "decisions": [log_entry], 
                    "portfolio": {
                        "starting_capital": self.capital, 
                        "current_capital": self.capital - (log_entry.get("position_size", 0) if log_entry.get("action") in ["BUY", "SELL"] else 0)
                    }
                }, f, indent=2)

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

        cheat_matches = find_matching_patterns(market_state)
        if cheat_matches:
            logger.info(
                "   Pattern cheatsheet matches: %s",
                ", ".join(pattern.name for pattern in cheat_matches),
            )
        else:
            logger.info("   Pattern cheatsheet matches: none")

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

        ai_decision = await self._call_openai(market_state, patterns, portfolio, cheat_matches)
        logger.info("\n🤖 AI Decision: %s", ai_decision)

        action = (ai_decision.get("action") or "").upper()
        
        # Extract pattern name from cheat matches (for improvements tracking)
        pattern_name = "mixed_signals"  # Default
        if cheat_matches:
            # Use the first matched pattern name
            pattern_name = cheat_matches[0].name
        
        # 🔧 DATA-DRIVEN IMPROVEMENTS (Oct 15, 2025 - Analysis Results)
        if action in {"BUY", "SELL"}:
            # Fix #1: Dynamic Confidence Calculation
            base_confidence = ai_decision.get("confidence", 0.75)
            
            confidence_calc = get_confidence_calculator()
            adjusted_confidence, confidence_explanation = confidence_calc.calculate_dynamic_confidence(
                base_confidence,
                market_state,
                pattern_name
            )
            
            # Update decision with dynamic confidence
            ai_decision["base_confidence"] = base_confidence
            ai_decision["confidence"] = adjusted_confidence
            ai_decision["confidence_explanation"] = confidence_explanation
            
            # Fix #2: Pattern Diversity Check
            pattern_mgr = get_pattern_manager()
            pattern_allowed, pattern_reason = pattern_mgr.should_use_pattern(pattern_name)
            
            if not pattern_allowed:
                logger.warning(f"⏭️  PATTERN DIVERSITY: {pattern_reason}")
                return {
                    "action": "SKIP",
                    "confidence": 0.0,
                    "reasoning": f"Pattern diversity check: {pattern_reason}",
                    "original_decision": ai_decision,
                }
            
            # Fix #3: Entry Spacing Check
            spacing_mgr = get_spacing_manager()
            spacing_allowed, spacing_reason = spacing_mgr.can_enter_position(pattern_name)
            
            if not spacing_allowed:
                logger.info(f"⏱️  ENTRY SPACING: {spacing_reason}")
                return {
                    "action": "SKIP",
                    "confidence": 0.0,
                    "reasoning": f"Entry spacing: {spacing_reason}",
                    "original_decision": ai_decision,
                }
            
            logger.info(f"   ✅ Improvements check passed: {pattern_reason}, {spacing_reason}")
        
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
        
        # Record pattern usage and entry timing (for improvements tracking)
        if action in {"BUY", "SELL"}:
            # pattern_name already extracted above from cheat_matches
            pattern_mgr = get_pattern_manager()
            spacing_mgr = get_spacing_manager()
            
            # Record this decision
            pattern_mgr.record_pattern_usage(pattern_name)
            spacing_mgr.record_entry(datetime.now(), pattern_name)
        
        self._log_decision(ai_decision, market_state)
        return ai_decision

    async def _call_openai(
        self,
        market_state: Dict[str, Any],
        patterns: Dict[str, Any],
        portfolio: Dict[str, Any],
        cheat_matches: List[PatternDefinition],
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
                    returns.append(safe_float(value))
            if returns:
                avg_return = sum(returns) / len(returns)

        available_capital = safe_float(
            portfolio.get("cash_balance", portfolio.get("capital")),
            default=self.capital,
        )
        max_new_position_size = min(self.max_position_size, (available_capital or self.capital) * 0.05)

        cheat_sheet_summary = describe_patterns(cheat_matches)

        # 🎓 PhD-LEVEL: Build market context (regime, session, volatility)
        market_context_str = ""
        current_regime = "unknown"
        current_session = "unknown"
        current_volatility = "unknown"
        
        try:
            from intelligence.market_context import get_session_detector
            session_detector = get_session_detector()
            current_session = session_detector.get_session()
            market_context_str += f"📊 MARKET CONTEXT:\n"
            market_context_str += f"- Trading Session: {current_session.upper()}"
            if session_detector.is_high_volume_period():
                market_context_str += " ⭐ HIGH VOLUME PERIOD\n"
            else:
                market_context_str += "\n"
        except Exception as e:
            logger.debug(f"Could not get market context: {e}")
            market_context_str = ""

        # 🧠 INTELLIGENCE INJECTION: Get pattern effectiveness data with context awareness
        pattern_effectiveness = ""
        if self.pattern_intelligence:
            top_patterns = self.pattern_intelligence.get_top_patterns(n=5, min_trades=3)
            if top_patterns:
                pattern_effectiveness = "🎓 TOP PERFORMING PATTERNS (Context-Aware Intelligence):\n\n"
                for i, p in enumerate(top_patterns, 1):
                    # Get pattern stats object for context-specific win rates
                    pattern_stats = self.pattern_intelligence.get_pattern_stats(p['pattern_id'])
                    
                    pattern_effectiveness += f"{i}. {p['pattern_type']}\n"
                    pattern_effectiveness += f"   Overall: {p['win_rate']:.1%} win rate ({p['wins']}W/{p['losses']}L) | "
                    pattern_effectiveness += f"Expectancy: {p['expectancy']:+.2f}% | Conf: {p['confidence_score']:.2f}\n"
                    
                    # Add context-specific performance if available
                    if pattern_stats:
                        context_added = False
                        
                        # Session-specific performance
                        if current_session != "unknown":
                            session_wr = pattern_stats.get_session_win_rate(current_session)
                            if session_wr is not None:
                                indicator = "✅ FAVORABLE" if session_wr > p['win_rate'] else "⚠️ UNFAVORABLE"
                                pattern_effectiveness += f"   During {current_session}: {session_wr:.1%} {indicator}\n"
                                context_added = True
                        
                        # Show best context if we have context data
                        best_context = pattern_stats.get_best_context()
                        if best_context:
                            if 'best_session' in best_context:
                                pattern_effectiveness += f"   Best session: {best_context['best_session']}\n"
                                context_added = True
                        
                        if not context_added:
                            pattern_effectiveness += f"   (No context data yet - building intelligence...)\n"
                    
                    pattern_effectiveness += "\n"
                
                pattern_effectiveness += (
                    "⚡ IMPORTANT: Use context-aware win rates to calibrate your confidence!\n"
                    "If pattern shows 75% in current session vs 65% overall, use the 75%!\n\n"
                )
            else:
                pattern_effectiveness = "⚠️ No patterns with sufficient trade history yet. Building intelligence...\n\n"
        else:
            pattern_effectiveness = "⚠️ Pattern Intelligence not available.\n\n"

        user_prompt = (
            f"CURRENT MARKET\n"
            f"- Symbol: {market_state.get('symbol', 'UNKNOWN')}\n"
            f"- RSI: {market_state.get('rsi', 'n/a')}\n"
            f"- EMA Ratio: {market_state.get('ema_ratio', 'n/a')} (>1.0 = uptrend)\n"
            f"- Volume Change: {market_state.get('volume_change', 'n/a')}\n"
            f"- Price Change: {market_state.get('price_change', 'n/a')}\n\n"
            f"{market_context_str}\n"
            f"PATTERN CHEATSHEET\n"
            f"- Matches: {cheat_sheet_summary}\n\n"
            f"{pattern_effectiveness}"
            f"HISTORICAL PATTERNS (Raw Data)\n"
            f"- Similar patterns in database: {patterns.get('count', 0)}\n"
            f"- Basic win rate: {win_rate if win_rate is not None else 'n/a'}\n"
            f"- Average price change: {avg_return if avg_return is not None else 'n/a'}\n\n"
            f"PORTFOLIO\n"
            f"- Capital: {portfolio.get('capital', self.capital)}\n"
            f"- Open positions: {portfolio.get('open_count')} / {portfolio.get('max_positions')}\n"
            f"- Daily P&L: {portfolio.get('daily_pnl', 0)}\n"
            f"- Available capital: {available_capital}\n\n"
            "Rules:\n"
            "- Return JSON only.\n"
            "- JSON schema: {\"action\": \"BUY|SELL|SKIP\", \"confidence\": float 0-1, \"position_size\": float, \"reasoning\": string}.\n"
            "- Require win rate >= 40 percent to trade (lowered for testing).\n"
            "- Avoid RSI above 70 or below 30.\n"
            f"- Limit new position size to <= {max_new_position_size:.2f}.\n"
            "- If unsure, respond with SKIP."
        )

        request_kwargs = {
            "model": self.model,
            "input": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.3,
            "max_output_tokens": 200,
        }

        try:
            try:
                response = self.client.responses.create(
                    **request_kwargs,
                    response_format={"type": "json_object"},
                )
            except TypeError:
                response = self.client.responses.create(**request_kwargs)
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
        if text:
            stripped = text.strip()
            if stripped.startswith("```"):
                stripped = stripped.strip("`").strip()
                if stripped.lower().startswith("json"):
                    stripped = stripped[4:].strip()
            if stripped.endswith("```"):
                stripped = stripped[:-3].strip()
            text = stripped
        try:
            decision = json.loads(text)
        except json.JSONDecodeError as err:
            logger.error("Failed to parse OpenAI response: %s", err)
            logger.warning("Raw OpenAI output: %s", text)
            recovered = _extract_json_blob(text)
            if recovered:
                try:
                    decision = json.loads(recovered)
                except json.JSONDecodeError:
                    decision = {
                        "action": "SKIP",
                        "confidence": 0.0,
                        "position_size": 0.0,
                        "reasoning": f"Invalid JSON from model: {err}",
                    }
                else:
                    logger.info("Recovered JSON fragment from OpenAI response")
            else:
                decision = {
                    "action": "SKIP",
                    "confidence": 0.0,
                    "position_size": 0.0,
                    "reasoning": f"Invalid JSON from model: {err}",
                }

        decision.setdefault("action", "SKIP")
        decision["confidence"] = safe_float(decision.get("confidence"), 0.0)
        decision["position_size"] = safe_float(decision.get("position_size"), 0.0)
        decision.setdefault("reasoning", "No reasoning provided")
        decision["action"] = (decision.get("action") or "SKIP").upper()

        # Enforce position guard here as well (belt-and-braces).
        max_size = max_new_position_size
        size_value = safe_float(decision.get("position_size"), default=max_size)
        if size_value and size_value > max_size:
            decision["position_size"] = max_size
        elif size_value is None:
            decision["position_size"] = 0.0 # Set a safe default
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


def _extract_json_blob(payload: str) -> str | None:
    """Extract a JSON blob from a string that might have other text."""
    start = payload.find("{")
    end = payload.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    return payload[start : end + 1]


def _fmt(value) -> str:
    """Format a numeric value to a string with 4 decimal places."""
    float_val = safe_float(value)
    if float_val is None:
        return "n/a"
    return f"{float_val:.4f}"


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
