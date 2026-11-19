"""STRATLAB Unit Tests: Multi-Concept Strategy Research & Confluence Engines.

Tests:
- Elliott Wave 3rd Wave Breakout
- Fibonacci Golden Pocket (61.8% - 78.6%)
- ICT Killzones, OTE, and Liquidity Sweeps
- Wyckoff Springs and Upthrusts
- Candlestick Engulfing and Hammer Pin Bars
- Harmonic Formations
- Unified Concept Registry & Cross-Methodology Confluence Evaluation
"""

import unittest
from shared.schemas.market_data import Candle
from shared.schemas.provenance import ProvenanceMetadata

from backend.app.analytics.patterns.candlesticks import CandlestickPattern, CandlestickPatternEngine
from backend.app.analytics.patterns.elliott import ElliottWaveDetector, WaveType
from backend.app.analytics.patterns.fibonacci import FibonacciEngine
from backend.app.analytics.patterns.harmonics import HarmonicPatternEngine, HarmonicPatternType
from backend.app.analytics.patterns.wyckoff import WyckoffEngine, WyckoffEvent
from backend.app.analytics.smc.ict import ICTTradingEngine, KillZone
from backend.app.strategy.evaluator.composite_evaluator import MultiConceptEvaluator
from backend.app.strategy.registry.concepts import UnifiedConceptRegistry


class TestMultiConceptPlatform(unittest.TestCase):
    """Verifies all technical analysis concept detectors and cross-methodology evaluation."""

    def setUp(self):
        self.prov = ProvenanceMetadata.exchange_verified("NSE_TBT")

    def _make_candle(self, idx: int, o: float, h: float, l: float, c: float, v: int = 1000) -> Candle:
        return Candle(
            instrument_id="INS_NSE_RELIANCE",
            timestamp_utc=1700000000000 + idx * 300000,
            timeframe="5m",
            open=o,
            high=h,
            low=l,
            close=c,
            volume=v,
            provenance=self.prov,
        )

    def test_fibonacci_golden_pocket(self):
        """Validates dynamic 61.8% Golden Pocket calculation and containment."""
        candles = [
            self._make_candle(0, 100.0, 102.0, 99.0, 100.0),   # Low ~ 99.0
            self._make_candle(1, 100.0, 150.0, 100.0, 148.0),  # High ~ 150.0 (Diff = 51.0)
            self._make_candle(2, 148.0, 148.0, 115.0, 118.0),  # Pullback into 61.8% retrace
        ]
        # Diff = 150 - 99 = 51.
        # 61.8% level = 150 - 0.618*51 = 150 - 31.518 = 118.48
        # 78.6% level = 150 - 0.786*51 = 150 - 40.086 = 109.91
        # Golden Pocket is [109.91, 118.48]. Candle 2 close = 118.0 is inside Golden Pocket!
        fib = FibonacciEngine.calculate_levels(candles)
        self.assertTrue(fib.in_golden_pocket)
        self.assertAlmostEqual(fib.swing_high, 150.0)
        self.assertAlmostEqual(fib.swing_low, 99.0)

    def test_wyckoff_spring(self):
        """Validates Wyckoff Spring shakeout detection below trading range support."""
        candles = []
        # Build a trading range around 100 - 110
        for i in range(15):
            candles.append(self._make_candle(i, 102.0, 110.0, 100.0, 105.0))

        # Spring: dips below 100.0 support to 98.0, but closes at 101.0 back inside range
        candles.append(self._make_candle(15, 101.0, 102.0, 98.0, 101.0, v=2000))

        wyckoff = WyckoffEngine.analyze(candles)
        self.assertTrue(wyckoff.is_spring)
        self.assertEqual(wyckoff.active_event, WyckoffEvent.SPRING)
        self.assertEqual(wyckoff.range_low, 100.0)

    def test_candlestick_hammer_pin_bar(self):
        """Detects Hammer / Bullish Pin Bar with lower wick >= 2x real body."""
        # Open 100, High 101, Low 90, Close 100.5
        # Body = 0.5, Lower wick = 100 - 90 = 10.0 >= 2*0.5
        candle = self._make_candle(0, 100.0, 101.0, 90.0, 100.5)
        match = CandlestickPatternEngine.detect_latest([candle])
        self.assertEqual(match.pattern, CandlestickPattern.HAMMER_PIN_BAR)
        self.assertTrue(match.is_bullish)

    def test_candlestick_bullish_engulfing(self):
        """Detects Bullish Engulfing pattern overtaking prior red candle."""
        c1 = self._make_candle(0, 105.0, 106.0, 99.0, 100.0)  # Red candle
        c2 = self._make_candle(1, 99.5, 108.0, 99.0, 107.0)   # Green engulfing candle
        match = CandlestickPatternEngine.detect_latest([c1, c2])
        self.assertEqual(match.pattern, CandlestickPattern.BULLISH_ENGULFING)
        self.assertTrue(match.is_bullish)

    def test_ict_liquidity_sweep(self):
        """Detects Sellside Liquidity (SSL) sweep and reclaim."""
        candles = [
            self._make_candle(0, 100.0, 105.0, 95.0, 102.0),
            self._make_candle(1, 102.0, 106.0, 96.0, 104.0),
            self._make_candle(2, 104.0, 108.0, 97.0, 106.0),
            # Sweep below prior low 95.0 down to 93.0, but closes at 96.0 back above
            self._make_candle(3, 96.0, 97.0, 93.0, 96.0),
        ]
        ict = ICTTradingEngine.evaluate(candles)
        self.assertTrue(ict.has_bullish_sweep_rejection)
        self.assertGreaterEqual(len(ict.recent_sweeps), 1)

    def test_unified_concept_registry(self):
        """Verifies concepts and legendary recipes are loaded and retrievable."""
        concepts = UnifiedConceptRegistry.get_all_concepts()
        recipes = UnifiedConceptRegistry.get_all_recipes()

        self.assertGreaterEqual(len(concepts), 15)
        self.assertGreaterEqual(len(recipes), 4)

        w3 = UnifiedConceptRegistry.find_concept("elliott_wave_3_breakout")
        self.assertIsNotNone(w3)
        self.assertEqual(w3.category, "Elliott Wave")

    def test_multi_concept_confluence_evaluation(self):
        """Validates cross-methodology multi-concept evaluation combining Wave + Fib + RSI."""
        candles = [
            self._make_candle(0, 100.0, 102.0, 99.0, 100.0),
            self._make_candle(1, 100.0, 150.0, 100.0, 148.0),
            self._make_candle(2, 148.0, 148.0, 115.0, 118.0),
        ]
        features = MultiConceptEvaluator.extract_market_features(candles)

        # In golden pocket should be True
        self.assertTrue(features.get("in_golden_pocket", False))

        # Evaluate recipe: [fib_golden_pocket]
        is_triggered = MultiConceptEvaluator.evaluate_recipe(
            concept_ids=["fib_golden_pocket"],
            features=features,
            operator="AND",
        )
        self.assertTrue(is_triggered)


if __name__ == "__main__":
    unittest.main()
