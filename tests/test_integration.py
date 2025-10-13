import asyncio
import json
import time
from dataclasses import dataclass
from typing import Any, Dict

import pytest

from agent.safety import SafetyRails
from intelligence.rolling_window_db import PatternEmbedding, RollingWindowPatternDB
from mcp.trading_server import TradingMCPServer


@pytest.fixture(scope="module")
def pattern_db() -> RollingWindowPatternDB:
    return RollingWindowPatternDB()


@pytest.fixture(scope="module")
def mcp_server(pattern_db: RollingWindowPatternDB) -> TradingMCPServer:
    return TradingMCPServer(pattern_db)


def _sample_state(db: RollingWindowPatternDB) -> Dict[str, Any]:
    labelled = db.collection.get(where={"label": {"$in": ["WIN", "LOSS", "NEUTRAL"]}}, limit=1)
    metadatas = labelled.get("metadatas") or []
    if not metadatas:
        data = db.collection.get(limit=1)
        metadatas = data.get("metadatas") or []
    if not metadatas:
        return {"rsi": 50.0, "ema_ratio": 1.0, "price_change": 0.0, "volume_change": 0.0}
    meta = metadatas[0] or {}
    return {
        "rsi": meta.get("rsi", 50.0),
        "ema_ratio": meta.get("ema_ratio", 1.0),
        "price_change": meta.get("price_change", 0.0),
        "volume_change": meta.get("volume_change", 0.0),
    }


def _ensure_labelled_sample(db: RollingWindowPatternDB) -> None:
    state = _sample_state(db)
    for attempt in range(3):
        results = db.find_similar(state, k=10)
        labels = {item.get("metadata", {}).get("label") for item in results}
        if labels.intersection({"WIN", "LOSS", "NEUTRAL"}):
            return

        base_ts = time.time()
        for offset, label in enumerate(["WIN", "LOSS", "NEUTRAL"]):
            metadata = {
                "timestamp": base_ts + offset + attempt * 10,
                "label": label,
                "symbol": "BTCUSDT",
                "rsi": state.get("rsi", 50.0),
                "ema_ratio": state.get("ema_ratio", 1.0),
                "price_change": state.get("price_change", 0.0) + (offset - 1) * 0.001,
                "volume_change": state.get("volume_change", 0.0) + (offset - 1) * 0.001,
            }
            embedding = [
                float(metadata["rsi"]) / 100.0,
                float(metadata["ema_ratio"]),
                float(metadata["volume_change"]),
                float(metadata["price_change"]),
            ]
            db.add_pattern(
                PatternEmbedding(
                    id=f"test_label_{label.lower()}_{int(metadata['timestamp'])}",
                    embedding=embedding,
                    metadata=metadata,
                ),
                prune=False,
            )


def test_vector_db(pattern_db: RollingWindowPatternDB) -> None:
    count = pattern_db.count()
    assert count >= 50, f"Expected at least 50 patterns in vector DB, found {count}"

    _ensure_labelled_sample(pattern_db)

    state = _sample_state(pattern_db)
    results = pattern_db.find_similar(state, k=5)

    assert isinstance(results, list)
    assert results, "Expected at least one similar pattern"

    labels = {item.get("metadata", {}).get("label") for item in results}
    if not labels.intersection({"WIN", "LOSS", "NEUTRAL"}):
        results = pattern_db.find_similar(state, k=50)
        labels = {item.get("metadata", {}).get("label") for item in results}
    assert labels.intersection({"WIN", "LOSS", "NEUTRAL"}), "No labelled patterns returned"

    for item in results:
        metadata = item.get("metadata", {}) or {}
        assert metadata.get("timestamp") is not None
        assert metadata.get("rsi") is not None


def test_mcp_server(mcp_server: TradingMCPServer, pattern_db: RollingWindowPatternDB) -> None:
    async def runner() -> None:
        symbol = "BTCUSDT"
        market_state = await mcp_server.get_market_state(symbol)
        assert market_state["symbol"] == symbol
        assert "timestamp" in market_state

        patterns = await mcp_server.get_similar_patterns(market_state, top_k=5)
        assert patterns["count"] >= 0
        assert "win_rate" in patterns
        assert "patterns" in patterns

        portfolio = await mcp_server.get_portfolio_state()
        assert portfolio["capital"] > 0
        assert "open_count" in portfolio

        risk = await mcp_server.check_risk_limits({"position_size": 10})
        assert isinstance(risk["approved"], bool)
        assert "timestamp" in risk

    asyncio.run(runner())


def test_safety_rails() -> None:
    rails = SafetyRails(capital=5000)

    base_decision = {"action": "BUY", "confidence": 0.8, "position_size": 150}
    market_state = {"rsi": 50}
    portfolio = {"capital": 5000, "open_count": 1, "max_positions": 3}

    approved, reason = rails.validate_decision(base_decision, market_state, 65.0, portfolio)
    assert approved, f"Expected decision to pass, but failed: {reason}"

    # RSI out of bounds should be blocked
    market_state_risky = {"rsi": 85}
    approved, reason = rails.validate_decision(base_decision, market_state_risky, 65.0, portfolio)
    assert not approved and "RSI" in reason

    # Low confidence should be blocked
    low_conf = base_decision | {"confidence": 0.3}
    approved, reason = rails.validate_decision(low_conf, market_state, 65.0, portfolio)
    assert not approved and "Confidence" in reason

    # Position size too large should be blocked
    big_position = base_decision | {"position_size": 1000}
    approved, reason = rails.validate_decision(big_position, market_state, 65.0, portfolio)
    assert not approved and "Position size" in reason

    # Portfolio max positions reached
    crowded_portfolio = {"capital": 5000, "open_count": 3, "max_positions": 3}
    approved, reason = rails.validate_decision(base_decision, market_state, 65.0, crowded_portfolio)
    assert not approved and "max positions" in reason.lower()


@dataclass
class _FakeUsage:
    input_tokens: int = 120
    output_tokens: int = 40


class _FakeResponse:
    def __init__(self) -> None:
        self.usage = _FakeUsage()
        self.output_text = json.dumps(
            {
                "action": "BUY",
                "confidence": 0.72,
                "position_size": 100.0,
                "reasoning": "Favourable pattern alignment",
            }
        )
        self.output = [{"content": [{"text": self.output_text}]}]


class _FakeOpenAI:
    def __init__(self, *args, **kwargs) -> None:
        self.responses = self

    def create(self, *args, **kwargs):
        return _FakeResponse()


def test_ai_agent_mock(monkeypatch, mcp_server: TradingMCPServer) -> None:
    async def runner() -> None:
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test-1234567890")

        from agent import trader as trader_module

        monkeypatch.setattr(trader_module, "OpenAI", _FakeOpenAI)

        agent = trader_module.TradingAgent(mcp_server, model="gpt-4o-mini")

        decision = await agent.analyze_and_decide("BTCUSDT")

        assert decision["action"] in {"BUY", "SELL", "SKIP"}
        assert 0.0 <= decision["confidence"] <= 1.0
        assert "reasoning" in decision
        assert agent.api_calls_today == 1
        assert agent.tokens_used_today > 0
        assert agent.estimated_cost_today > 0.0

    asyncio.run(runner())
