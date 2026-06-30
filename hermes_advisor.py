"""Read-only Gemini advisor for Hermes evidence reports."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from config import (
    GEMINI_API_KEY,
    HERMES_GEMINI_ENABLED,
    HERMES_GEMINI_MAX_CONTEXT_ROWS,
    HERMES_GEMINI_MODEL,
    HERMES_GEMINI_TEMPERATURE,
)

try:
    from google import genai as _genai
    from google.genai import types as _genai_types
except ImportError:  # pragma: no cover - operator venv may omit optional SDK
    _genai = None
    _genai_types = None

ADVISOR_BOUNDARY = (
    "Hermes Advisor is read-only. It is the Profit-Driven Risk & Performance Auditor "
    "for OzzyBot and optimizes for portfolio R-expectancy while ruthlessly defending "
    "capital. It explains supplied Hermes evidence, separates signal quality from exit "
    "and protection quality, and proposes tests. It must not place, close, modify, or "
    "veto trades; change risk; fabricate DB facts; or treat thin samples as proof. It "
    "must say insufficient evidence when supplied evidence does not prove a claim and "
    "must never invent incident root causes."
)

MICRO_BOOTSTRAP_MANDATE = (
    "LIVE MICRO is an intentional small-account growth lane. The operator is trying "
    "to grow the micro account from a small balance, so fixed-dollar bootstrap risk "
    "can be a deliberate business decision rather than a configuration mistake. The "
    "advisor must still state the real percentage risk, label it high-risk bootstrap "
    "when appropriate, enforce daily loss and protection evidence, and must not "
    "recommend scaling or normalizing the risk as safe until clean forward evidence "
    "supports it."
)

ECONOMIC_AUDIT_PILLARS = (
    {
        "name": "THE MULTIPLIER CORE",
        "rule": (
            "Every strategy filter exists to capture clean, high-probability moves with "
            "minimum 2.5R target potential. Treat rejections as capital-preservation "
            "events unless evidence proves the gate repeatedly blocks positive-R setups."
        ),
    },
    {
        "name": "SLIPPAGE AND FRICTION DEFENSE",
        "rule": (
            "A strategy-perfect setup is economically invalid if adverse entry drift, "
            "toxic spread, fees, or protection latency destroys edge. Treat adverse drift "
            "above 0.15% and toxic order book spread as fail-closed loss threats."
        ),
    },
    {
        "name": "OPTIMAL PERSONALITY LEVERAGE",
        "rule": (
            "Assets express edge differently. Trend assets must not be starved with tight "
            "pullback rules, and mean-reverting assets must not be allowed to bleed as loose "
            "momentum runners. Optimize symbol-specific flourishing under hard account risk limits."
        ),
    },
    {
        "name": "EVIDENCE BEFORE EXPANSION",
        "rule": (
            "No asset profile graduates from shadow/testnet into live capital because it sounds "
            "right. Require clean sample evidence, rejection attribution, realized R, slippage "
            "behavior, and protection reliability before recommending live expansion."
        ),
    },
)

ADVISOR_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "observations": {"type": "array", "items": {"type": "string"}},
        "risks": {"type": "array", "items": {"type": "string"}},
        "hypotheses_to_test": {"type": "array", "items": {"type": "string"}},
        "evidence_refs": {"type": "array", "items": {"type": "string"}},
        "operator_questions": {"type": "array", "items": {"type": "string"}},
        "data_quality": {"type": "array", "items": {"type": "string"}},
        "insufficient_evidence": {"type": "array", "items": {"type": "string"}},
        "next_evidence_to_collect": {"type": "array", "items": {"type": "string"}},
        "confidence": {
            "type": "string",
            "enum": ["low", "medium", "high"],
        },
    },
    "required": [
        "summary",
        "observations",
        "risks",
        "hypotheses_to_test",
        "evidence_refs",
        "operator_questions",
        "data_quality",
        "insufficient_evidence",
        "next_evidence_to_collect",
        "confidence",
    ],
    "additionalProperties": False,
}


class AdvisorUnavailableError(RuntimeError):
    """Raised when Gemini advisory analysis is intentionally unavailable."""


def advisor_status() -> dict[str, Any]:
    """Return safe status fields for `/status` and operator checks."""
    return {
        "enabled": HERMES_GEMINI_ENABLED,
        "model": HERMES_GEMINI_MODEL,
        "key_configured": bool(GEMINI_API_KEY),
        "role": "read_only_evidence_advisor",
        "broker_actions_allowed": False,
    }


def _limit_rows(value: Any, max_rows: int) -> Any:
    if isinstance(value, list):
        return [_limit_rows(item, max_rows) for item in value[:max_rows]]
    if isinstance(value, dict):
        return {key: _limit_rows(item, max_rows) for key, item in value.items()}
    return value


def build_evidence_pack(memory_report: dict[str, Any], question: str | None = None) -> dict[str, Any]:
    """Build the bounded Hermes context sent to the model."""
    report_keys = (
        "event_counts",
        "rejected_winners",
        "approved_losers",
        "good_entry_bad_exit",
        "grade_health_by_r",
        "symbol_direction_heat",
        "protection_failures",
    )
    selected = {key: memory_report.get(key, []) for key in report_keys}
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "question": question or "What should the operator learn from current Hermes evidence?",
        "advisor_boundary": ADVISOR_BOUNDARY,
        "evidence_contract": {
            "truth_source": "Hermes deterministic memory/report rows supplied below",
            "math_owner": "Python reports, not the model",
            "economic_audit_pillars": list(ECONOMIC_AUDIT_PILLARS),
            "micro_bootstrap_mandate": MICRO_BOOTSTRAP_MANDATE,
            "forbidden_conclusions": [
                "automatic strategy blocks from thin samples",
                "direct broker/order/risk actions",
                "market facts not present in evidence unless explicitly researched outside this brief",
            ],
        },
        "ozzy_memory_report": _limit_rows(selected, HERMES_GEMINI_MAX_CONTEXT_ROWS),
    }


def build_prompt(evidence_pack: dict[str, Any]) -> str:
    """Return the plain prompt wrapped around bounded Hermes evidence."""
    payload = json.dumps(evidence_pack, indent=2, default=str, sort_keys=True)
    return (
        "You are Hermes Advisor inside OzzyBot: the Profit-Driven Risk & Performance Auditor. "
        "Your objective is maximizing portfolio R-expectancy while defending capital through "
        "institutional risk controls. Use only the supplied Hermes evidence for trade and "
        "system conclusions. Reference evidence sections, trade ids, event rows, modes, "
        "symbols, strategies, grades, realized R, slippage, spread, or metric names when "
        "available. If evidence does not prove a claim, say 'insufficient evidence'. "
        "Never invent a root cause for an execution or protection incident. Never treat "
        "correlation or event counts alone as expectancy proof. Never treat TESTNET dollar "
        "PnL as LIVE expectancy; compare R-multiples, rejection attribution, and execution "
        "quality instead. Milestone hits or favorable excursion prove observed movement only, "
        "not setup viability, edge, or expectancy by themselves. Separate setup quality, exit "
        "quality, protection/execution quality, data quality, and asset-profile fit. Treat "
        "LIVE MICRO as an intentional small-account bootstrap growth lane: fixed-dollar risk "
        "may be deliberate, but always state its actual percentage of equity and label it "
        "high-risk bootstrap when appropriate. Do not call micro risk normal or safe without "
        "clean forward evidence, and do not recommend scaling while execution, protection, or "
        "reconciliation quality is degraded. Treat "
        "rejections as capital-preservation events unless evidence proves they repeatedly block "
        "positive-R opportunities. Treat adverse drift above 0.15% and toxic spread as economic "
        "loss threats. Prefer symbol-specific hypotheses, but require clean evidence before "
        "recommending profile expansion or live capital. Return the requested JSON schema.\n\n"
        f"HERMES_EVIDENCE:\n{payload}"
    )


def _load_genai():
    if _genai is None or _genai_types is None:
        raise AdvisorUnavailableError("google-genai is not installed in this Hermes venv")
    return _genai, _genai_types


def _build_client():
    genai, _types = _load_genai()
    return genai.Client(api_key=GEMINI_API_KEY)


def _build_config() -> Any:
    _genai, types = _load_genai()
    return types.GenerateContentConfig(
        system_instruction=ADVISOR_BOUNDARY,
        response_mime_type="application/json",
        response_json_schema=ADVISOR_RESPONSE_SCHEMA,
        temperature=HERMES_GEMINI_TEMPERATURE,
    )


def _parse_response_text(response: Any) -> dict[str, Any]:
    text = getattr(response, "text", None)
    if not text:
        raise AdvisorUnavailableError("Gemini returned no text payload")
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        raise AdvisorUnavailableError("Gemini returned non-JSON advisor output") from exc
    if not isinstance(parsed, dict):
        raise AdvisorUnavailableError("Gemini advisor output must be a JSON object")
    return parsed


def generate_brief(evidence_pack: dict[str, Any], client: Any | None = None) -> dict[str, Any]:
    """Generate a structured Gemini brief from Hermes evidence only."""
    if not HERMES_GEMINI_ENABLED:
        raise AdvisorUnavailableError("Hermes Gemini advisor is disabled; set HERMES_GEMINI_ENABLED=true")
    if not GEMINI_API_KEY:
        raise AdvisorUnavailableError("GEMINI_API_KEY is missing")
    model_client = client or _build_client()
    config = _build_config()
    response = model_client.models.generate_content(
        model=HERMES_GEMINI_MODEL,
        contents=build_prompt(evidence_pack),
        config=config,
    )
    return _parse_response_text(response)
