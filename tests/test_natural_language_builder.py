"""Tests for Natural Language Strategy Builder & Prompt Parser."""

import unittest
from backend.app.strategy.registry.concepts import ConceptPromptParser
from fastapi.testclient import TestClient
from backend.app.api.main import app


class TestNaturalLanguageStrategyBuilder(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_parse_elliott_and_golden_pocket(self):
        prompt = "Buy when Elliott Wave 3 breaks out with Golden Pocket Fib"
        res = ConceptPromptParser.parse(prompt)
        self.assertIn("elliott_wave_3_breakout", res.matched_concept_ids)
        self.assertIn("fib_golden_pocket", res.matched_concept_ids)
        self.assertEqual(res.operator, "AND")
        self.assertEqual(res.side, "BUY")
        self.assertTrue(len(res.matched_concepts) >= 2)
        self.assertIn("Wave 3", res.plain_english_summary)

    def test_parse_ict_silver_bullet_and_liquidity_sweep(self):
        prompt = "ICT silver bullet killzone with liquidity sweep and footprint imbalance"
        res = ConceptPromptParser.parse(prompt)
        self.assertIn("ict_silver_bullet", res.matched_concept_ids)
        self.assertIn("ict_liquidity_sweep", res.matched_concept_ids)
        self.assertIn("footprint_buy_imbalance", res.matched_concept_ids)
        self.assertEqual(res.operator, "AND")

    def test_parse_wyckoff_with_or_operator(self):
        prompt = "Wyckoff spring shakeout or delta absorption divergence"
        res = ConceptPromptParser.parse(prompt)
        self.assertIn("wyckoff_spring", res.matched_concept_ids)
        self.assertIn("cvd_absorption_divergence", res.matched_concept_ids)
        self.assertEqual(res.operator, "OR")

    def test_parse_fallback_when_generic(self):
        prompt = "test something random"
        res = ConceptPromptParser.parse(prompt)
        # Should fall back to safe default
        self.assertTrue(len(res.matched_concept_ids) >= 1)

    def test_api_prompt_parse_endpoint(self):
        resp = self.client.post("/api/v1/strategies/prompt/parse", json={"prompt": "EMA cross with FVG and RSI oversold"})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("matched_concept_ids", data)
        self.assertIn("indicator_ema_crossover", data["matched_concept_ids"])
        self.assertIn("smc_fair_value_gap", data["matched_concept_ids"])
        self.assertIn("indicator_rsi_oversold", data["matched_concept_ids"])

    def test_api_prompt_parse_and_test_endpoint(self):
        resp = self.client.post(
            "/api/v1/strategies/prompt/parse-and-test",
            json={
                "prompt": "Elliott Wave 3 with Golden Pocket Fib and 3:1 Footprint Imbalance",
                "symbol": "RELIANCE",
                "initial_cash": 100000.0,
            },
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("parsed", data)
        self.assertIn("backtest", data)
        self.assertIn("metrics", data["backtest"])
        self.assertGreater(data["backtest"]["metrics"]["net_pnl"], 0)
        self.assertGreater(len(data["backtest"]["closed_trades"]), 0)


if __name__ == "__main__":
    unittest.main()
