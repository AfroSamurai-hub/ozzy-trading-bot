#!/usr/bin/env python3
"""Run a single end-to-end AI trading decision pipeline."""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from agent.trader import TradingAgent
from intelligence.rolling_window_db import RollingWindowPatternDB
from mcp.trading_server import TradingMCPServer


def _load_env() -> None:
    env_path = PROJECT_ROOT / ".env"
    if not env_path.exists():
        return

    try:
        for line in env_path.read_text().splitlines():
            striped = line.strip()
            if not striped or striped.startswith("#") or "=" not in striped:
                continue
            key, value = striped.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            os.environ.setdefault(key, value)
    except Exception:
        # Non-fatal; script will fail later if OPENAI_API_KEY missing.
        pass


def _fmt_price(value: Any) -> str:
    try:
        return f"${float(value):,.2f}"
    except (TypeError, ValueError):
        return "n/a"


def _fmt_pct(value: Any) -> str:
    try:
        return f"{float(value):.2f}%"
    except (TypeError, ValueError):
        return "n/a"


def _fmt_number(value: Any) -> str:
    try:
        return f"{float(value):.4f}"
    except (TypeError, ValueError):
        return "n/a"


def _fmt_confidence(value: Any) -> str:
    try:
        return f"{float(value) * 100:.1f}%"
    except (TypeError, ValueError):
        return "n/a"


def _print_header(symbol: str) -> None:
    print("🔍 Testing End-to-End Decision Pipeline")
    print(f"   Symbol: {symbol}")
    print()


async def _run_cycle(symbol: str) -> Dict[str, Any]:
    start_time = time.perf_counter()

    db = RollingWindowPatternDB()
    mcp = TradingMCPServer(db)
    agent = TradingAgent(mcp, model="gpt-4o-mini")

    market_state = await mcp.get_market_state(symbol)
    patterns = await mcp.get_similar_patterns(market_state, top_k=10)
    portfolio = await mcp.get_portfolio_state()

    print("📊 Market Snapshot")
    print(f"   Price Change: {_fmt_pct(market_state.get('price_change'))}")
    print(f"   RSI: {_fmt_number(market_state.get('rsi'))}")
    print(f"   EMA Ratio: {_fmt_number(market_state.get('ema_ratio'))}")
    print(f"   Volume Change: {_fmt_pct(market_state.get('volume_change'))}")
    print()

    print("📈 Pattern Analysis")
    similar_count = patterns.get("count", 0)
    win_rate = patterns.get("win_rate")
    print(f"   Similar patterns: {similar_count}")
    print(f"   Win rate: {_fmt_pct(win_rate)}")
    print()

    print("💼 Portfolio State")
    print(f"   Capital: {_fmt_price(portfolio.get('capital'))}")
    print(f"   Open positions: {portfolio.get('open_count')} / {portfolio.get('max_positions')}")
    print(f"   Daily P&L: {_fmt_price(portfolio.get('daily_pnl'))}")
    print()

    decision = await agent._call_openai(market_state, patterns, portfolio)  # noqa: SLF001

    action = (decision.get("action") or "SKIP").upper()
    confidence = decision.get("confidence", 0.0)
    position_size = decision.get("position_size", 0.0)
    reasoning = decision.get("reasoning", "No reasoning provided")

    print("🤖 AI Decision (GPT-4o-mini)")
    print(f"   Action: {action}")
    print(f"   Confidence: {_fmt_confidence(confidence)}")
    print(f"   Position Size: {_fmt_price(position_size)}")
    print(f"   Reasoning: {reasoning}")
    print()

    safety_status = "SKIPPED"
    risk_status = "SKIPPED"
    final_action = action
    final_reason = reasoning

    if action in {"BUY", "SELL"}:
        approved, reason = agent.safety.validate_decision(decision, market_state, win_rate, portfolio)
        if approved:
            safety_status = "PASSED"
            risk_check = await mcp.check_risk_limits(decision)
            if risk_check.get("approved", False):
                risk_status = "PASSED"
            else:
                risk_status = "REJECTED: " + ", ".join(risk_check.get("reasons") or ["Unknown reason"])
                final_action = "SKIP"
                final_reason = f"Risk check failed: {', '.join(risk_check.get('reasons') or ['Unknown reason'])}"
        else:
            safety_status = f"REJECTED: {reason}"
            final_action = "SKIP"
            final_reason = f"Rejected by safety rails: {reason}"
    else:
        safety_status = "SKIPPED (action=SKIP)"
        risk_status = "SKIPPED"

    print("🛡️ Safety Check:", safety_status)
    if risk_status != "SKIPPED":
        print("⚠️ Risk Check:", risk_status)
    print()

    print("✅ Final Decision")
    print(f"   Action: {final_action}")
    print(f"   Reason: {final_reason}")
    print()

    elapsed = time.perf_counter() - start_time
    print("💰 Cost Tracking")
    print(f"   This call: ${agent.estimated_cost_today:.4f}")
    print(f"   API calls today: {agent.api_calls_today}")
    print()

    print(f"⏱️ Total runtime: {elapsed:.2f}s")

    return {
        "initial_decision": decision,
        "final_action": final_action,
        "final_reason": final_reason,
        "safety_status": safety_status,
        "risk_status": risk_status,
        "elapsed": elapsed,
        "cost": agent.estimated_cost_today,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a single AI trading decision pipeline test.")
    parser.add_argument("--symbol", default="BTCUSDT", help="Market symbol to analyse (default: BTCUSDT)")
    args = parser.parse_args()

    _load_env()

    if not os.getenv("OPENAI_API_KEY"):
        print("❌ OPENAI_API_KEY not set. Use environment variable or .env file.")
        return 1

    _print_header(args.symbol)

    try:
        asyncio.run(_run_cycle(args.symbol))
    except KeyboardInterrupt:
        print("Interrupted by user.")
        return 130
    except Exception as exc:  # pragma: no cover - top-level diagnostic
        print(f"❌ Pipeline run failed: {exc}")
        return 1

    print("\n✅ End-to-end test complete!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
