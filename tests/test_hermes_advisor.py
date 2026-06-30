import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import hermes_advisor


class FakeModels:
    def __init__(self):
        self.calls = []

    def generate_content(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(text=json.dumps({
            "summary": "B trades have bounded evidence.",
            "observations": ["LIVE and TESTNET are separated."],
            "risks": ["Sample size is thin."],
            "hypotheses_to_test": ["Compare 0.5R partial outcomes."],
            "evidence_refs": ["grade_health_by_r[0]"],
            "operator_questions": ["Review exit quality?"],
            "data_quality": ["Thin sample."],
            "insufficient_evidence": ["No backfilled R rows."],
            "next_evidence_to_collect": ["Recent exit rows."],
            "confidence": "low",
        }))


class HermesAdvisorTests(unittest.TestCase):
    def test_evidence_pack_limits_memory_rows_and_keeps_boundary(self):
        report = {"event_counts": [{"count": idx} for idx in range(4)]}
        with patch.object(hermes_advisor, "HERMES_GEMINI_MAX_CONTEXT_ROWS", 2):
            pack = hermes_advisor.build_evidence_pack(report, "What changed?")

        self.assertEqual(pack["question"], "What changed?")
        self.assertEqual(len(pack["ozzy_memory_report"]["event_counts"]), 2)
        self.assertIn("read-only", pack["advisor_boundary"].lower())
        self.assertIn("direct broker/order/risk actions", pack["evidence_contract"]["forbidden_conclusions"])
        self.assertIn("small-account growth lane", pack["evidence_contract"]["micro_bootstrap_mandate"])
        pillar_names = [pillar["name"] for pillar in pack["evidence_contract"]["economic_audit_pillars"]]
        self.assertIn("EVIDENCE BEFORE EXPANSION", pillar_names)

    def test_generate_brief_is_disabled_by_default_boundary(self):
        with (
            patch.object(hermes_advisor, "HERMES_GEMINI_ENABLED", False),
            self.assertRaisesRegex(hermes_advisor.AdvisorUnavailableError, "disabled"),
        ):
            hermes_advisor.generate_brief({"evidence": []})

    def test_generate_brief_requires_key(self):
        with (
            patch.object(hermes_advisor, "HERMES_GEMINI_ENABLED", True),
            patch.object(hermes_advisor, "GEMINI_API_KEY", ""),
            self.assertRaisesRegex(hermes_advisor.AdvisorUnavailableError, "GEMINI_API_KEY"),
        ):
            hermes_advisor.generate_brief({"evidence": []})

    def test_generate_brief_uses_structured_model_request(self):
        fake_models = FakeModels()
        fake_client = SimpleNamespace(models=fake_models)
        with (
            patch.object(hermes_advisor, "HERMES_GEMINI_ENABLED", True),
            patch.object(hermes_advisor, "GEMINI_API_KEY", "test-key"),
            patch.object(hermes_advisor, "HERMES_GEMINI_MODEL", "gemini-test"),
            patch.object(hermes_advisor, "_build_config", return_value={"structured": True}),
        ):
            brief = hermes_advisor.generate_brief({"ozzy_memory_report": {}}, client=fake_client)

        self.assertEqual(brief["confidence"], "low")
        self.assertEqual(fake_models.calls[0]["model"], "gemini-test")
        self.assertEqual(fake_models.calls[0]["config"], {"structured": True})
        self.assertIn("Hermes Advisor", fake_models.calls[0]["contents"])

    def test_prompt_enforces_insufficient_evidence_rules(self):
        prompt = hermes_advisor.build_prompt({"runtime_context": {}})

        self.assertIn("insufficient evidence", prompt)
        self.assertIn("Never invent a root cause", prompt)
        self.assertIn("Never treat TESTNET dollar PnL as LIVE expectancy", prompt)
        self.assertIn("Milestone hits", prompt)
        self.assertIn("Profit-Driven Risk & Performance Auditor", prompt)
        self.assertIn("adverse drift above 0.15%", prompt)
        self.assertIn("asset-profile fit", prompt)
        self.assertIn("intentional small-account bootstrap growth lane", prompt)
        self.assertIn("actual percentage of equity", prompt)
        self.assertIn("Do not call micro risk normal or safe", prompt)

    def test_schema_requires_data_quality_fields(self):
        required = hermes_advisor.ADVISOR_RESPONSE_SCHEMA["required"]

        self.assertIn("data_quality", required)
        self.assertIn("insufficient_evidence", required)
        self.assertIn("next_evidence_to_collect", required)


if __name__ == "__main__":
    unittest.main()
