"""STRATLAB Strategy Evaluator: Multi-Concept Cross-Methodology Engine.

Unifies Elliott Wave, SMC, ICT, Wyckoff, Fibonacci, Volume Profile, Footprint,
Candlesticks, Harmonics, and Indicators into a single non-siloed evaluation pipeline.
"""

from typing import Any, Dict, List, Optional
from shared.schemas.market_data import Candle
from shared.schemas.order_flow import FootprintBar

from backend.app.analytics.indicators.technical import IndicatorEngine
from backend.app.analytics.patterns.candlesticks import CandlestickPattern, CandlestickPatternEngine
from backend.app.analytics.patterns.elliott import ElliottWaveDetector
from backend.app.analytics.patterns.fibonacci import FibonacciEngine
from backend.app.analytics.patterns.harmonics import HarmonicPatternEngine
from backend.app.analytics.patterns.wyckoff import WyckoffEngine
from backend.app.analytics.smc.ict import ICTTradingEngine
from backend.app.analytics.smc.structure import SMCDetectionEngine


class MultiConceptEvaluator:
    """
    Evaluates multi-concept confluent setups across all methodologies.
    """

    @classmethod
    def extract_market_features(
        cls,
        candles: List[Candle],
        footprint_bar: Optional[FootprintBar] = None,
    ) -> Dict[str, Any]:
        """
        Runs all concept analyzers on the candle history and returns a flat dictionary of signals.
        """
        if not candles:
            return {}

        features: Dict[str, Any] = {}

        # 1. Elliott Wave
        ew = ElliottWaveDetector.detect_waves(candles)
        features["is_wave_3_breakout"] = ew.is_wave_3_breakout
        features["is_wave_4_pullback"] = ew.is_wave_4_pullback
        features["current_wave"] = ew.current_wave.value

        # 2. Fibonacci
        fib = FibonacciEngine.calculate_levels(candles)
        features["in_golden_pocket"] = fib.in_golden_pocket
        features["is_at_50_percent"] = fib.is_at_50_percent
        features["is_at_618_level"] = fib.is_at_618_level

        # 3. ICT Trading Concepts
        ict = ICTTradingEngine.evaluate(candles)
        features["is_silver_bullet_window"] = ict.is_silver_bullet_window
        features["has_bullish_sweep_rejection"] = ict.has_bullish_sweep_rejection
        features["has_bearish_sweep_rejection"] = ict.has_bearish_sweep_rejection
        features["in_discount_zone"] = ict.in_discount_zone
        features["in_premium_zone"] = ict.in_premium_zone
        features["in_ote_zone"] = ict.in_ote_zone

        # 4. Smart Money Concepts (SMC)
        smc_engine = SMCDetectionEngine()
        smc_swings = smc_engine.find_swings(candles)
        fvgs = smc_engine.detect_fair_value_gaps(candles)
        last_px = candles[-1].close
        in_fvg = any(fvg.is_bullish and fvg.bottom_price <= last_px <= fvg.top_price for fvg in fvgs)
        features["in_bullish_fvg"] = in_fvg
        features["is_bos_bullish"] = len(smc_swings) >= 2 and candles[-1].close > smc_swings[-1].price if smc_swings else False
        features["is_choch_bullish"] = len(smc_swings) >= 3 and candles[-1].close > smc_swings[-2].price if smc_swings else False

        # 5. Wyckoff Methodology
        wyckoff = WyckoffEngine.analyze(candles)
        features["is_spring"] = wyckoff.is_spring
        features["is_upthrust"] = wyckoff.is_upthrust
        features["is_sign_of_strength"] = wyckoff.is_sign_of_strength
        features["is_sign_of_weakness"] = wyckoff.is_sign_of_weakness

        # 6. Candlestick Patterns
        candle_match = CandlestickPatternEngine.detect_latest(candles)
        features["is_hammer"] = candle_match.pattern == CandlestickPattern.HAMMER_PIN_BAR
        features["is_shooting_star"] = candle_match.pattern == CandlestickPattern.SHOOTING_STAR
        features["is_bullish_engulfing"] = candle_match.pattern == CandlestickPattern.BULLISH_ENGULFING

        # 7. Harmonics
        harmonic = HarmonicPatternEngine.detect(candles)
        features["is_gartley"] = harmonic.pattern.value == "GARTLEY"
        features["is_bat"] = harmonic.pattern.value == "BAT"
        features["is_butterfly"] = harmonic.pattern.value == "BUTTERFLY"

        # 8. Traditional Technical Indicators
        closes = [c.close for c in candles]
        if len(closes) >= 14:
            rsi = IndicatorEngine.rsi(closes, period=14)
            features["rsi"] = rsi[-1]
            features["rsi_oversold"] = rsi[-1] < 35.0 if rsi[-1] is not None else False
            features["rsi_overbought"] = rsi[-1] > 65.0 if rsi[-1] is not None else False
        else:
            features["rsi_oversold"] = False
            features["rsi_overbought"] = False

        if len(closes) >= 50:
            ema20 = IndicatorEngine.ema(closes, period=20)
            ema50 = IndicatorEngine.ema(closes, period=50)
            features["ema_cross_bullish"] = ema20[-1] > ema50[-1]
        else:
            features["ema_cross_bullish"] = True  # Neutral default

        # 9. Footprint & Order Flow (if present)
        if footprint_bar:
            has_buy_imb = any(
                getattr(c, "imbalance_buy", False) or getattr(c, "is_buy_imbalance", False)
                for c in (footprint_bar.clusters.values() if isinstance(footprint_bar.clusters, dict) else footprint_bar.clusters)
            )
            poc_px = footprint_bar.poc_price or 0.0
            val_px = footprint_bar.val or getattr(footprint_bar, "value_area_low", 0.0) or 0.0
            features["has_buy_imbalance"] = has_buy_imb
            features["at_poc_level"] = abs(last_px - poc_px) / max(last_px, 1) < 0.003
            features["at_val_level"] = abs(last_px - val_px) / max(last_px, 1) < 0.003
            features["is_absorption_divergence"] = footprint_bar.delta < 0 and candles[-1].close >= candles[-1].open
        else:
            features["has_buy_imbalance"] = False
            features["at_poc_level"] = False
            features["at_val_level"] = False
            features["is_absorption_divergence"] = False

        return features

    @classmethod
    def evaluate_recipe(
        cls,
        concept_ids: List[str],
        features: Dict[str, Any],
        operator: str = "AND",
    ) -> bool:
        """
        Evaluates whether the selected concept blocks are triggered.
        """
        if not concept_ids:
            return False

        # Map concept_id to feature key
        mapping = {
            "elliott_wave_3_breakout": "is_wave_3_breakout",
            "elliott_wave_4_pullback": "is_wave_4_pullback",
            "smc_fair_value_gap": "in_bullish_fvg",
            "smc_bos_breakout": "is_bos_bullish",
            "smc_choch_reversal": "is_choch_bullish",
            "ict_silver_bullet": "is_silver_bullet_window",
            "ict_liquidity_sweep": "has_bullish_sweep_rejection",
            "ict_discount_zone": "in_discount_zone",
            "ict_ote_entry": "in_ote_zone",
            "wyckoff_spring": "is_spring",
            "wyckoff_sign_of_strength": "is_sign_of_strength",
            "fib_golden_pocket": "in_golden_pocket",
            "fib_50_equilibrium": "is_at_50_percent",
            "footprint_buy_imbalance": "has_buy_imbalance",
            "volume_profile_poc_retest": "at_poc_level",
            "volume_profile_val_bounce": "at_val_level",
            "cvd_absorption_divergence": "is_absorption_divergence",
            "candlestick_hammer_pin_bar": "is_hammer",
            "candlestick_bullish_engulfing": "is_bullish_engulfing",
            "harmonic_gartley_bullish": "is_gartley",
            "indicator_rsi_oversold": "rsi_oversold",
            "indicator_ema_crossover": "ema_cross_bullish",
        }

        results: List[bool] = []
        for cid in concept_ids:
            feat_key = mapping.get(cid, cid)
            val = bool(features.get(feat_key, False))
            results.append(val)

        if operator.upper() == "AND":
            return all(results)
        elif operator.upper() == "OR":
            return any(results)
        return False
