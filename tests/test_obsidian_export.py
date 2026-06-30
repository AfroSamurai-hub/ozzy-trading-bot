import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, "/home/rick/ozzy-bot")

from scripts.export_obsidian_journal import (
    _regime_markdown,
    summarize_trade_rows,
    render_active_blueprints_markdown,
    render_trade_card_markdown,
    render_daily_trade_links,
    export_derivatives_shadow_pages,
    export_navigation_pages,
    export_placeholder_pages,
    export_trade_strategy_pages,
)


class ObsidianExportTests(unittest.TestCase):
    def test_summarize_trade_rows_groups_pnl_and_win_rate(self):
        stats = summarize_trade_rows(
            [
                {"symbol": "SOLUSDT", "strategy_label": "BREAKOUT_RETEST", "pnl": 2.0},
                {"symbol": "SOLUSDT", "strategy_label": "BREAKOUT_RETEST", "pnl": -1.0},
                {"symbol": "ETHUSDT", "strategy_label": "1H_TREND_CONTINUATION", "pnl": 3.0},
            ],
            "symbol",
        )

        self.assertEqual(stats["SOLUSDT"]["count"], 2)
        self.assertEqual(stats["SOLUSDT"]["wins"], 1)
        self.assertEqual(stats["SOLUSDT"]["win_rate"], 50.0)
        self.assertEqual(stats["SOLUSDT"]["pnl"], 1.0)

    def test_regime_map_uses_links_and_lane_columns(self):
        content = _regime_markdown(
            {
                "SOLUSDT": {
                    "assigned_strategy": "4H_MACRO_BREAKOUT",
                    "signal_strategy": "momentum",
                    "configured_lane": "Macro",
                    "lane_timeframe": "4H/1H",
                    "directional_bias": "DOWN",
                    "metrics": {"adx": 25.88, "close": 67.0, "ema200": 77.0},
                }
            }
        )

        self.assertIn("| Symbol | Lane | Timeframe | Status | Strategy | Bias | ADX | EMA Distance |", content)
        self.assertIn("[[Symbols/SOLUSDT|SOLUSDT]]", content)
        self.assertIn("[[Strategies/momentum|momentum]]", content)
        self.assertIn("Macro", content)
        self.assertIn("4H/1H", content)

    def test_active_blueprints_render_lane_strategy_and_derivatives_context(self):
        content = render_active_blueprints_markdown(
            {
                "SOLUSDT": {
                    "symbol": "SOLUSDT",
                    "side": "SELL",
                    "entry_price": 66.94,
                    "status": "ARMED",
                    "configured_lane": "Macro",
                    "strategy_label": "BREAKOUT_RETEST",
                    "regime_label": "OPENCLAW_4H_MACRO_BREAKOUT",
                }
            },
            {
                "last_results": [
                    {
                        "symbol": "SOLUSDT",
                        "status": "WAIT",
                        "reasons": ["close_not_beyond_trigger"],
                        "derivatives_context": {"verdict": "mixed", "score": 1},
                    }
                ]
            },
        )

        self.assertIn("[[Symbols/SOLUSDT|SOLUSDT]]", content)
        self.assertIn("Lane: Macro", content)
        self.assertIn("[[Strategies/BREAKOUT_RETEST|BREAKOUT_RETEST]]", content)
        self.assertIn("[[Regimes/OPENCLAW_4H_MACRO_BREAKOUT|OPENCLAW_4H_MACRO_BREAKOUT]]", content)
        self.assertIn("Derivatives: mixed (score 1)", content)
        self.assertIn("testnet webhook :5001", content)

    def test_trade_card_links_symbol_strategy_and_regime(self):
        content = render_trade_card_markdown(
            {
                "id": 54,
                "symbol": "RENDERUSDT",
                "direction": "BUY",
                "execution_state": "closed",
                "exit_reason": "momentum_exit",
                "pnl": -23.35,
                "setup_grade": "A",
                "volume_ratio": 1.27,
                "strategy_label": "BREAKOUT_RETEST",
                "entry_setup_label": "OPENCLAW_BREAKOUT",
                "regime_label": "OPENCLAW_4H_MACRO_BREAKOUT",
                "source_service": "openclaw_breakout_executor",
                "context_json": json.dumps({"chart_quality_confirmations": ["volume_expansion:1.27"]}),
            }
        )

        self.assertIn("[[Symbols/RENDERUSDT|RENDERUSDT]]", content)
        self.assertIn("[[Strategies/BREAKOUT_RETEST|BREAKOUT_RETEST]]", content)
        self.assertIn("[[Setups/OPENCLAW_BREAKOUT|OPENCLAW_BREAKOUT]]", content)
        self.assertIn("[[Regimes/OPENCLAW_4H_MACRO_BREAKOUT|OPENCLAW_4H_MACRO_BREAKOUT]]", content)
        self.assertIn("**Source Service:** openclaw_breakout_executor", content)

    def test_trade_card_marks_pre_label_era_without_inventing_labels(self):
        content = render_trade_card_markdown(
            {
                "id": 1,
                "symbol": "ETHUSDT",
                "execution_state": "closed",
                "exit_reason": "opposite",
                "pnl": 0.07,
                "setup_grade": "B",
                "volume_ratio": 0.82,
                "strategy_label": "1H_TREND_CONTINUATION",
                "entry_setup_label": None,
                "regime_label": None,
                "source_service": None,
            }
        )

        self.assertIn("Pre-label era", content)
        self.assertIn("not backfilled", content)
        self.assertIn("[[Setups/UNKNOWN|UNKNOWN]]", content)
        self.assertIn("[[Regimes/UNKNOWN|UNKNOWN]]", content)

    def test_daily_trade_links_filter_report_date_and_link_cards(self):
        content = render_daily_trade_links(
            "2026-06-15",
            [
                {"id": 10, "symbol": "SOLUSDT", "ts": "2026-06-15T07:00:00+00:00", "duration_min": 15, "pnl": 2.91},
                {"id": 11, "symbol": "ETHUSDT", "ts": "2026-06-14T22:00:00+00:00", "duration_min": 30, "pnl": -1.0},
            ],
        )

        self.assertIn("## Trade Cards Closed This Date", content)
        self.assertIn("[[Trades/SOLUSDT-10|SOLUSDT #10]]", content)
        self.assertIn("$2.91", content)
        self.assertNotIn("ETHUSDT-11", content)

    def test_daily_trade_links_fallback_to_most_recent_closed_trade_date_when_report_date_empty(self):
        content = render_daily_trade_links(
            "2026-06-15",
            [
                {"id": 10, "symbol": "SOLUSDT", "ts": "2026-06-14T07:00:00+00:00", "duration_min": 15, "pnl": 2.91},
                {"id": 11, "symbol": "ETHUSDT", "ts": "2026-06-13T22:00:00+00:00", "duration_min": 30, "pnl": -1.0},
            ],
        )

        self.assertIn("_No closed trade cards matched this report date._", content)
        self.assertIn("## Most Recent Closed Trade Cards (2026-06-14)", content)
        self.assertIn("[[Trades/SOLUSDT-10|SOLUSDT #10]]", content)
        self.assertNotIn("ETHUSDT-11", content)

    def test_derivatives_shadow_pages_link_symbols_and_setups(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            export_derivatives_shadow_pages(
                root,
                events=[
                    {
                        "symbol": "SOLUSDT",
                        "entry_setup_label": "OPENCLAW_BREAKOUT",
                        "derivatives_verdict": "supportive",
                        "status": "FIRED",
                        "outcome": "win",
                        "score": 3,
                        "r_multiple": 2.5,
                    }
                ],
            )

            index = (root / "Derivatives_Shadow" / "Derivatives Shadow Evidence.md").read_text(encoding="utf-8")
            symbol = (root / "Derivatives_Shadow" / "Symbols" / "SOLUSDT.md").read_text(encoding="utf-8")
            setup = (root / "Derivatives_Shadow" / "Setups" / "OPENCLAW_BREAKOUT.md").read_text(encoding="utf-8")

        self.assertIn("[[Derivatives_Shadow/Symbols/SOLUSDT|SOLUSDT]]", index)
        self.assertIn("[[Derivatives_Shadow/Setups/OPENCLAW_BREAKOUT|OPENCLAW_BREAKOUT]]", index)
        self.assertIn("Rows: 1", symbol)
        self.assertIn("Win rate: 100.0%", symbol)
        self.assertIn("Avg R: 2.5", setup)

    def test_navigation_pages_create_profit_focused_indexes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            export_navigation_pages(
                root,
                regimes={
                    "SOLUSDT": {
                        "assigned_strategy": "4H_MACRO_BREAKOUT",
                        "signal_strategy": "momentum",
                        "configured_lane": "Macro",
                        "lane_timeframe": "4H/1H",
                        "directional_bias": "DOWN",
                    }
                },
                active_orders={
                    "SOLUSDT": {"symbol": "SOLUSDT", "side": "SELL", "entry_price": 66.94, "status": "ARMED"}
                },
                trade_rows=[
                    {"symbol": "SOLUSDT", "strategy_label": "BREAKOUT_RETEST", "pnl": 2.0},
                    {"symbol": "SOLUSDT", "strategy_label": "BREAKOUT_RETEST", "pnl": 0.91},
                    {"symbol": "ETHUSDT", "strategy_label": "1H_TREND_CONTINUATION", "pnl": -5.0},
                ],
            )

            home = (root / "00_Home.md").read_text(encoding="utf-8")
            symbol = (root / "Symbols" / "SOLUSDT.md").read_text(encoding="utf-8")
            strategy = (root / "Strategies" / "momentum.md").read_text(encoding="utf-8")

        self.assertIn("Profitability Control Room", home)
        self.assertIn("V2 Edge Spotlight", home)
        self.assertIn("BREAKOUT_RETEST", home)
        self.assertIn("$2.91", home)
        self.assertIn("[[Dashboards/OzzyBot Operating Dashboard|OzzyBot Operating Dashboard]]", home)
        self.assertIn("[[Alerts/Active OpenClaw Setups|Active OpenClaw Setups]]", home)
        self.assertIn("[[DangerBoard/Market Regime Map|Market Regime Map]]", home)
        self.assertIn("[[Derivatives_Shadow/Derivatives Shadow Evidence|Derivatives Shadow Evidence]]", home)
        self.assertIn("[[Symbols/SOLUSDT|SOLUSDT]]", home)
        self.assertIn("Current Lane", symbol)
        self.assertIn("Macro", symbol)
        self.assertIn("## Performance Summary", symbol)
        self.assertIn("Win rate: 100.0%", symbol)
        self.assertIn("Symbols using this strategy", strategy)

    def test_trade_strategy_pages_cover_trade_card_strategy_links(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            export_trade_strategy_pages(
                root,
                [
                    {
                        "symbol": "RENDERUSDT",
                        "strategy": "1H_TREND_CONTINUATION",
                        "strategy_label": None,
                        "entry_setup_label": "MOMENTUM_A",
                        "regime_label": "SMC_PRO_BEARISH_BOS",
                        "pnl": 2.5,
                    }
                ],
            )

            strategy = (root / "Strategies" / "1H_TREND_CONTINUATION.md").read_text(encoding="utf-8")
            entry = (root / "Setups" / "MOMENTUM_A.md").read_text(encoding="utf-8")
            regime = (root / "Regimes" / "SMC_PRO_BEARISH_BOS.md").read_text(encoding="utf-8")

        self.assertIn("Trade-derived label", strategy)
        self.assertIn("[[Symbols/RENDERUSDT|RENDERUSDT]]", strategy)
        self.assertIn("Trade count: 1", strategy)
        self.assertIn("Total PnL: $2.50", strategy)
        self.assertIn("Trade-derived label", entry)
        self.assertIn("Trade-derived label", regime)

    def test_trade_strategy_pages_overwrite_generated_nav_pages_and_redirect_legacy_setup(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "Setups").mkdir(parents=True)
            (root / "Strategies").mkdir(parents=True)
            (root / "Setups" / "MOMENTUM_A.md").write_text("---\nsource: ozzy-bot\n---\n# MOMENTUM_A\n\n## Role in profitability\n", encoding="utf-8")
            (root / "Strategies" / "MOMENTUM_A.md").write_text("---\nsource: ozzy-bot\n---\n# MOMENTUM_A\n\n## Trade-derived label\n", encoding="utf-8")

            export_trade_strategy_pages(
                root,
                [{"symbol": "SOLUSDT", "strategy": "1H_TREND_CONTINUATION", "entry_setup_label": "MOMENTUM_A", "pnl": 3.0}],
            )

            setup = (root / "Setups" / "MOMENTUM_A.md").read_text(encoding="utf-8")
            legacy = (root / "Strategies" / "MOMENTUM_A.md").read_text(encoding="utf-8")

        self.assertIn("Trade-derived label", setup)
        self.assertIn("Total PnL: $3.00", setup)
        self.assertIn("Moved generated label", legacy)
        self.assertIn("[[Setups/MOMENTUM_A|MOMENTUM_A]]", legacy)

    def test_placeholder_pages_resolve_legacy_unknown_links(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            written = export_placeholder_pages(root)

            setup = (root / "Setups" / "UNKNOWN.md").read_text(encoding="utf-8")
            regime = (root / "Regimes" / "UNKNOWN.md").read_text(encoding="utf-8")
            btc = (root / "Symbols" / "BTCUSD.md").read_text(encoding="utf-8")

        self.assertTrue(written)
        self.assertIn("Pre-label-era placeholder", setup)
        self.assertIn("Pre-label-era placeholder", regime)
        self.assertIn("Prefer [[Symbols/BTCUSDT|BTCUSDT]]", btc)


if __name__ == "__main__":
    unittest.main()
