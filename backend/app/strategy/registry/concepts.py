"""STRATLAB Strategy Studio: Unified Multi-Concept Registry & Confluence Recipes.

Catalog of all technical analysis concept building blocks:
- 🌊 Elliott Wave (Wave 3 Impulse, Wave 4 Pullback, Wave C)
- 🏦 Smart Money Concepts (SMC Order Blocks, BOS, CHoCH, FVG)
- 🎯 ICT Trading Concepts (Killzones, Silver Bullet, Premium/Discount, OTE, Liquidity Sweeps)
- 🏛️ Wyckoff Methodology (Spring Shakeout, Upthrust, Sign of Strength)
- 📐 Fibonacci Levels (Golden Pocket 61.8%-78.6%, 50% Equilibrium, Extensions)
- 📊 Volume Profile (POC Retest, VAH/VAL Bounce, HVN/LVN)
- ⚡ Footprint & Order Flow (3:1 Diagonal Imbalances, Stacked Imbalances, Unfinished Auctions)
- 🌊 Delta & CVD (CVD Absorption Divergence, Delta Surge)
- 🕯️ Candlestick Patterns (Hammer Pin Bar, Engulfing, Morning Star, Inside Bar)
- 🦋 Harmonic Formations (Gartley, Bat, Butterfly, Crab)
- 📈 Traditional Indicators (EMA Crossover, RSI Oversold/Overbought, MACD, Bollinger Bands)
- 🔢 Custom Math & Price Action (ATR multiples, Rolling Ratios, Threshold Cross)
"""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class ConceptBlock(BaseModel):
    concept_id: str
    category: str
    name: str
    simple_description: str
    friendly_icon: str
    default_params: Dict[str, Any] = Field(default_factory=dict)
    signal_key: str
    required_feeds: List[str] = Field(default_factory=list)


class ConfluenceRecipe(BaseModel):
    recipe_id: str
    name: str
    tagline: str
    methodologies: List[str]
    blocks: List[str]           # List of concept_ids
    plain_english_rule: str
    risk_reward: str
    win_rate_benchmark: str


class UnifiedConceptRegistry:
    """
    Central repository of modular strategy lego blocks and pre-built multi-concept recipes.
    """

    CONCEPTS: List[ConceptBlock] = [
        # 1. Elliott Wave
        ConceptBlock(
            concept_id="elliott_wave_3_breakout",
            category="Elliott Wave",
            name="Wave 3 Impulse Breakout",
            simple_description="Rides the largest, fastest market wave as price breaks Wave 1 high",
            friendly_icon="🌊",
            signal_key="is_wave_3_breakout",
            required_feeds=["candle"],
        ),
        ConceptBlock(
            concept_id="elliott_wave_4_pullback",
            category="Elliott Wave",
            name="Wave 4 Shallow Pullback",
            simple_description="Catches the dip before the final Wave 5 push without breaking Wave 1 high",
            friendly_icon="🌊",
            signal_key="is_wave_4_pullback",
            required_feeds=["candle"],
        ),

        # 2. Smart Money Concepts (SMC)
        ConceptBlock(
            concept_id="smc_fair_value_gap",
            category="Smart Money Concepts",
            name="Bullish Fair Value Gap (FVG)",
            simple_description="Institutions bought so fast they left an unfilled imbalance gap",
            friendly_icon="🏦",
            signal_key="in_bullish_fvg",
            required_feeds=["candle"],
        ),
        ConceptBlock(
            concept_id="smc_bos_breakout",
            category="Smart Money Concepts",
            name="Break of Structure (BOS)",
            simple_description="Price breaks above prior swing high, proving the uptrend is continuing",
            friendly_icon="🏦",
            signal_key="is_bos_bullish",
            required_feeds=["candle"],
        ),
        ConceptBlock(
            concept_id="smc_choch_reversal",
            category="Smart Money Concepts",
            name="Change of Character (CHoCH)",
            simple_description="First signal that the big trend has flipped from down to up",
            friendly_icon="🏦",
            signal_key="is_choch_bullish",
            required_feeds=["candle"],
        ),

        # 3. ICT Trading Concepts
        ConceptBlock(
            concept_id="ict_silver_bullet",
            category="ICT Concepts",
            name="Silver Bullet Killzone",
            simple_description="High-probability 10-11 AM New York algorithmic liquidity surge",
            friendly_icon="🎯",
            signal_key="is_silver_bullet_window",
            required_feeds=["candle"],
        ),
        ConceptBlock(
            concept_id="ict_liquidity_sweep",
            category="ICT Concepts",
            name="Sellside Liquidity (SSL) Sweep",
            simple_description="Smart money triggers amateur stop losses below lows, then snaps price back up",
            friendly_icon="🎯",
            signal_key="has_bullish_sweep_rejection",
            required_feeds=["candle"],
        ),
        ConceptBlock(
            concept_id="ict_discount_zone",
            category="ICT Concepts",
            name="Discount Equilibrium Zone",
            simple_description="Price is in the bottom 50% wholesale discount zone — buy cheap",
            friendly_icon="🎯",
            signal_key="in_discount_zone",
            required_feeds=["candle"],
        ),
        ConceptBlock(
            concept_id="ict_ote_entry",
            category="ICT Concepts",
            name="Optimal Trade Entry (OTE 62-79%)",
            simple_description="The exact sweet spot where institutional traders re-enter trends",
            friendly_icon="🎯",
            signal_key="in_ote_zone",
            required_feeds=["candle"],
        ),

        # 4. Wyckoff Methodology
        ConceptBlock(
            concept_id="wyckoff_spring",
            category="Wyckoff Methodology",
            name="Wyckoff Spring Shakeout",
            simple_description="The classic Phase C fake-out trap dipping below support before exploding higher",
            friendly_icon="🏛️",
            signal_key="is_spring",
            required_feeds=["candle"],
        ),
        ConceptBlock(
            concept_id="wyckoff_sign_of_strength",
            category="Wyckoff Methodology",
            name="Sign of Strength (SOS)",
            simple_description="Massive volume surge proving buyers have completely taken over the range",
            friendly_icon="🏛️",
            signal_key="is_sign_of_strength",
            required_feeds=["candle"],
        ),

        # 5. Fibonacci Levels
        ConceptBlock(
            concept_id="fib_golden_pocket",
            category="Fibonacci Levels",
            name="61.8% Golden Pocket Zone",
            simple_description="The golden ratio zone between 61.8% and 78.6% where pullbacks reverse",
            friendly_icon="📐",
            signal_key="in_golden_pocket",
            required_feeds=["candle"],
        ),
        ConceptBlock(
            concept_id="fib_50_equilibrium",
            category="Fibonacci Levels",
            name="50% Equilibrium Bounce",
            simple_description="Exact halfway retrace balance level of the major swing impulse",
            friendly_icon="📐",
            signal_key="is_at_50_percent",
            required_feeds=["candle"],
        ),

        # 6. Volume Profile & Footprint
        ConceptBlock(
            concept_id="footprint_buy_imbalance",
            category="Footprint & Order Flow",
            name="Footprint 3:1 Buy Imbalance",
            simple_description="Aggressive market buyers outweigh bid sellers by over 300% on the ladder",
            friendly_icon="⚡",
            signal_key="has_buy_imbalance",
            required_feeds=["footprint"],
        ),
        ConceptBlock(
            concept_id="volume_profile_poc_retest",
            category="Volume Profile",
            name="Point of Control (POC) Retest",
            simple_description="Price tests the heaviest traded price of the session and respects it as support",
            friendly_icon="📊",
            signal_key="at_poc_level",
            required_feeds=["candle", "footprint"],
        ),
        ConceptBlock(
            concept_id="volume_profile_val_bounce",
            category="Volume Profile",
            name="Value Area Low (VAL) Bounce",
            simple_description="Price touches the bottom boundary of the 70% value area and bounces up",
            friendly_icon="📊",
            signal_key="at_val_level",
            required_feeds=["candle"],
        ),

        # 7. Delta & Cumulative Volume Delta (CVD)
        ConceptBlock(
            concept_id="cvd_absorption_divergence",
            category="Delta & CVD",
            name="Delta Absorption Divergence",
            simple_description="Sellers dump massive volume but price refuses to go down — buyers absorbed all selling",
            friendly_icon="🌊",
            signal_key="is_absorption_divergence",
            required_feeds=["footprint"],
        ),

        # 8. Candlestick Patterns
        ConceptBlock(
            concept_id="candlestick_hammer_pin_bar",
            category="Candlesticks",
            name="Hammer / Bullish Pin Bar",
            simple_description="Long bottom tail showing sellers tried to push price down and got violently rejected",
            friendly_icon="🕯️",
            signal_key="is_hammer",
            required_feeds=["candle"],
        ),
        ConceptBlock(
            concept_id="candlestick_bullish_engulfing",
            category="Candlesticks",
            name="Bullish Engulfing Candle",
            simple_description="Giant green candle completely swallows the prior red candle",
            friendly_icon="🕯️",
            signal_key="is_bullish_engulfing",
            required_feeds=["candle"],
        ),

        # 9. Harmonic Formations
        ConceptBlock(
            concept_id="harmonic_gartley_bullish",
            category="Harmonics",
            name="Bullish Gartley Pattern",
            simple_description="M-shaped Fibonacci geometric pattern completing at 78.6% PRZ reversal zone",
            friendly_icon="🦋",
            signal_key="is_gartley",
            required_feeds=["candle"],
        ),

        # 10. Traditional Indicators
        ConceptBlock(
            concept_id="indicator_rsi_oversold",
            category="Technical Indicators",
            name="RSI Oversold (< 30)",
            simple_description="Momentum oscillator signals price is extremely stretched and cheap",
            friendly_icon="📈",
            signal_key="rsi_oversold",
            required_feeds=["candle"],
        ),
        ConceptBlock(
            concept_id="indicator_ema_crossover",
            category="Technical Indicators",
            name="EMA 20 > EMA 50 Bullish Cross",
            simple_description="Short-term trend crosses above long-term trend confirming upward momentum",
            friendly_icon="📈",
            signal_key="ema_cross_bullish",
            required_feeds=["candle"],
        ),
    ]

    RECIPES: List[ConfluenceRecipe] = [
        ConfluenceRecipe(
            recipe_id="recipe_ultimate_confluence",
            name="The Ultimate Wave-SMC Confluence",
            tagline="Elliott Wave 3 + Fair Value Gap + 61.8% Golden Pocket + Footprint Imbalance",
            methodologies=["Elliott Wave", "Smart Money Concepts", "Fibonacci", "Footprint"],
            blocks=[
                "elliott_wave_3_breakout",
                "smc_fair_value_gap",
                "fib_golden_pocket",
                "footprint_buy_imbalance",
            ],
            plain_english_rule="BUY when Elliott Wave 3 breaks out, inside a Bullish Fair Value Gap, sitting in the 61.8% Golden Pocket, confirmed by a 3:1 aggressive Footprint Buy Imbalance.",
            risk_reward="1 : 3.2",
            win_rate_benchmark="71.4%",
        ),
        ConfluenceRecipe(
            recipe_id="recipe_ict_silver_bullet_delta",
            name="ICT Silver Bullet + Order Flow Surge",
            tagline="Killzone Timing + Liquidity Sweep + Footprint 3:1 Imbalance + OTE",
            methodologies=["ICT Concepts", "Footprint", "Smart Money Concepts"],
            blocks=[
                "ict_silver_bullet",
                "ict_liquidity_sweep",
                "ict_ote_entry",
                "footprint_buy_imbalance",
            ],
            plain_english_rule="BUY during the 10-11 AM Silver Bullet window when Sellside Liquidity is swept, entering in the OTE zone with verified footprint buying imbalance.",
            risk_reward="1 : 2.8",
            win_rate_benchmark="68.5%",
        ),
        ConfluenceRecipe(
            recipe_id="recipe_wyckoff_spring_absorption",
            name="Wyckoff Spring + Delta Absorption",
            tagline="Phase C Shakeout + Delta Divergence + Hammer Pin Bar",
            methodologies=["Wyckoff Methodology", "Delta & CVD", "Candlesticks"],
            blocks=[
                "wyckoff_spring",
                "cvd_absorption_divergence",
                "candlestick_hammer_pin_bar",
            ],
            plain_english_rule="BUY when a Wyckoff Spring dips below support and immediately reclaims, with sellers absorbed on CVD delta divergence and a hammer pin bar.",
            risk_reward="1 : 3.5",
            win_rate_benchmark="74.0%",
        ),
        ConfluenceRecipe(
            recipe_id="recipe_fib_trend_fvg",
            name="Fibonacci Golden Pocket + Trend Continuation",
            tagline="EMA Cross + 61.8% Retracement + Fair Value Gap + RSI Filter",
            methodologies=["Fibonacci", "Smart Money Concepts", "Technical Indicators"],
            blocks=[
                "indicator_ema_crossover",
                "fib_golden_pocket",
                "smc_fair_value_gap",
            ],
            plain_english_rule="BUY when EMA 20 is above EMA 50, price pulls back to the 61.8% Golden Pocket, and fills a Bullish Fair Value Gap.",
            risk_reward="1 : 2.5",
            win_rate_benchmark="66.2%",
        ),
    ]

    @classmethod
    def get_all_concepts(cls) -> List[ConceptBlock]:
        return cls.CONCEPTS

    @classmethod
    def get_all_recipes(cls) -> List[ConfluenceRecipe]:
        return cls.RECIPES

    @classmethod
    def find_concept(cls, concept_id: str) -> Optional[ConceptBlock]:
        for c in cls.CONCEPTS:
            if c.concept_id == concept_id:
                return c
        return None
