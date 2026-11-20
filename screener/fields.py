"""Field registry: every column the screener knows, its type, format and group.

One source of truth for the filter parser (names, prev-day variants), the API
(/api/meta) and the UI column picker. Adding an indicator = add it in
indicators.live() and list it here.
"""

import re
from .indicators import EMA_N, SMA_N

# Master field schema tuples: (name, label, type, format, group, prev_field)
# Rationale:
#   name: Identifier used in Python dicts and filter expressions (e.g., 'rsi14').
#   label: Clean human-readable display header for UI tables and charts.
#   type: 'num' | 'str' | 'bool' | 'list' - used by expr.py parser for type-checking.
#   format: 'price' | 'pct' | 'num' | 'int' | 'vol' | 'money' | 'ratio' | 'text' | 'bool' | 'time' | 'list'
#           determines localized display in UI (e.g., Lakh/Crore suffix, % sign, decimals).
#   group: Category for the visual column picker (Info, Price, Volume, Oscillators, etc.).
#   prev_field: The counterpart field name holding yesterday's value (e.g., 'prev_close' for 'price').
#               Required by expr.py for crosses_above() and crosses_below() to detect transitions.
_F = [
    # ---- Company & Symbol Metadata ----
    ("sym", "Symbol", "str", "text", "Info", None),
    ("name", "Name", "str", "text", "Info", None),
    ("exchange", "Exch", "str", "text", "Info", None),
    ("series", "Series", "str", "text", "Info", None),
    ("industry", "Industry", "str", "text", "Info", None),
    ("indices", "Indices", "list", "list", "Info", None),

    # ---- Live Price & Session Range ----
    ("price", "Price", "num", "price", "Price", "prev_close"),
    ("open", "Open", "num", "price", "Price", None),
    ("high", "High", "num", "price", "Price", None),
    ("low", "Low", "num", "price", "Price", None),
    ("prev_close", "Prev Close", "num", "price", "Price", None),
    ("change", "Change", "num", "price", "Price", None),
    ("change_pct", "Change %", "num", "pct", "Price", None),
    ("gap_pct", "Gap %", "num", "pct", "Price", None),

    # ---- Traded Volume & Liquidity ----
    ("volume", "Volume", "num", "vol", "Volume", "prev_volume"),
    ("prev_volume", "Prev Volume", "num", "vol", "Volume", None),
    ("turnover", "Turnover ₹", "num", "money", "Volume", None),
    ("avg_vol10", "Avg Vol 10D", "num", "vol", "Volume", None),
    ("avg_vol20", "Avg Vol 20D", "num", "vol", "Volume", None),
    ("avg_vol50", "Avg Vol 50D", "num", "vol", "Volume", None),
    ("rvol", "RVOL", "num", "ratio", "Volume", None),
    ("rvol_tod", "RVOL (time-of-day)", "num", "ratio", "Volume", None),
    ("vwap", "VWAP", "num", "price", "Volume", None),
    ("vwap_pct", "% from VWAP", "num", "pct", "Performance", None),

    # ---- Oscillators & Momentum ----
    ("rsi14", "RSI 14", "num", "num", "Oscillators", "rsi14_prev"),
    ("rsi14_prev", "RSI 14 (prev)", "num", "num", "Oscillators", None),
    ("macd", "MACD", "num", "price", "Oscillators", "macd_prev"),
    ("macd_prev", "MACD (prev)", "num", "price", "Oscillators", None),
    ("macd_signal", "MACD Signal", "num", "price", "Oscillators", "macd_signal_prev"),
    ("macd_signal_prev", "MACD Signal (prev)", "num", "price", "Oscillators", None),
    ("macd_hist", "MACD Hist", "num", "price", "Oscillators", None),
    ("adx14", "ADX 14", "num", "num", "Oscillators", None),
    ("plus_di", "+DI 14", "num", "num", "Oscillators", None),
    ("minus_di", "−DI 14", "num", "num", "Oscillators", None),
    ("stoch_k", "Stochastic %K (14)", "num", "num", "Oscillators", "stoch_k_prev"),
    ("stoch_k_prev", "Stochastic %K (prev)", "num", "num", "Oscillators", None),
    ("stoch_d", "Stochastic %D (3)", "num", "num", "Oscillators", "stoch_d_prev"),
    ("stoch_d_prev", "Stochastic %D (prev)", "num", "num", "Oscillators", None),

    # ---- Volatility & Bollinger Bands ----
    ("atr14", "ATR 14", "num", "price", "Volatility", None),
    ("atr_pct", "ATR %", "num", "pct", "Volatility", None),
    ("bb_upper", "BB Upper 20", "num", "price", "Volatility", None),
    ("bb_lower", "BB Lower 20", "num", "price", "Volatility", None),
    ("bb_pctb", "BB %B", "num", "num", "Volatility", None),
    ("bb_width", "BB Width %", "num", "pct", "Volatility", None),
    ("donchian_high", "Donchian Upper (20)", "num", "price", "Volatility", None),
    ("donchian_low", "Donchian Lower (20)", "num", "price", "Volatility", None),
    ("donchian_mid", "Donchian Middle (20)", "num", "price", "Volatility", None),

    # ---- Trend Following ----
    ("supertrend", "Supertrend (10, 3.0)", "num", "price", "Trend", "supertrend_prev"),
    ("supertrend_prev", "Supertrend (prev)", "num", "price", "Trend", None),
    ("supertrend_dir", "Supertrend Direction (+1/-1)", "num", "int", "Trend", "supertrend_dir_prev"),
    ("supertrend_dir_prev", "Supertrend Direction (prev)", "num", "int", "Trend", None),

    # ---- Key Price Levels & Historical Extremes ----
    ("high_20d", "20D High Close", "num", "price", "Levels", None),
    ("low_20d", "20D Low Close", "num", "price", "Levels", None),
    ("high_52w", "52W High", "num", "price", "Levels", None),
    ("low_52w", "52W Low", "num", "price", "Levels", None),
    ("from_52w_high", "% from 52W High", "num", "pct", "Levels", None),
    ("from_52w_low", "% from 52W Low", "num", "pct", "Levels", None),

    # ---- Multi-Period Trailing Performance ----
    ("chg_1w", "Perf 1W %", "num", "pct", "Performance", None),
    ("chg_1m", "Perf 1M %", "num", "pct", "Performance", None),
    ("chg_3m", "Perf 3M %", "num", "pct", "Performance", None),
    ("chg_6m", "Perf 6M %", "num", "pct", "Performance", None),
    ("chg_1y", "Perf 1Y %", "num", "pct", "Performance", None),
    ("chg_ytd", "Perf YTD %", "num", "pct", "Performance", None),

    # ---- Double Bottom (W Pattern) Scoring & Trade Plan Fields ----
    ("db_score", "Double Bottom Score", "num", "int", "Patterns", None),
    ("db_neckline", "DB Neckline", "num", "price", "Patterns", None),
    ("db_target", "DB Target", "num", "price", "Patterns", None),
    ("db_stop", "DB Stop", "num", "price", "Patterns", None),
    ("db_entry", "DB Entry", "num", "price", "Patterns", None),
    ("db_risk_pct", "DB Risk %", "num", "pct", "Patterns", None),
    ("db_target_1r", "DB Target 1R", "num", "price", "Patterns", None),
    ("db_target_2r", "DB Target 2R", "num", "price", "Patterns", None),
    ("db_days_since_breakout", "DB Days Since Breakout", "num", "int", "Patterns", None),
    ("db_l1_date", "DB Trough 1 Date", "str", "text", "Patterns", None),
    ("db_l2_date", "DB Trough 2 Date", "str", "text", "Patterns", None),

    # ---- Data Quality & Diagnostic Markers ----
    ("age", "Data Age (s)", "num", "int", "Data", None),
    ("hist_days", "History Bars", "num", "int", "Data", None),
    ("official_eod", "Official EOD", "bool", "bool", "Data", None),
]

# Programmatically generate SMA and EMA moving average fields and their previous-day counterparts.
# Rationale: Eliminates repetitive manual boilerplate while linking each average with its
# corresponding '_prev' variant so crosses_above(sma50, sma200) can automatically resolve prior values.
for n in SMA_N:
    _F.append(("sma%d" % n, "SMA %d" % n, "num", "price", "Moving Averages", "sma%d_prev" % n))
    _F.append(("sma%d_prev" % n, "SMA %d (prev)" % n, "num", "price", "Moving Averages", None))
for n in EMA_N:
    _F.append(("ema%d" % n, "EMA %d" % n, "num", "price", "Moving Averages", "ema%d_prev" % n))
    _F.append(("ema%d_prev" % n, "EMA %d (prev)" % n, "num", "price", "Moving Averages", None))

# Discrete Boolean pattern indicators
# Rationale: Pre-computed flags allowing users to write concise filter rules
# like 'breakout_20d and volume_shock' rather than complex multi-line math.
PATTERNS = [
    ("breakout_20d", "20D closing-high breakout"),
    ("breakdown_20d", "20D closing-low breakdown"),
    ("new_52w_high", "New 52-week high"),
    ("new_52w_low", "New 52-week low"),
    ("reclaim_ma20", "Reclaimed SMA 20"),
    ("golden_cross", "Golden cross (50/200)"),
    ("death_cross", "Death cross (50/200)"),
    ("macd_bull_cross", "MACD bullish cross"),
    ("oversold", "RSI < 30"),
    ("overbought", "RSI > 70"),
    ("oversold_bounce", "Oversold bounce"),
    ("volume_shock", "Volume shocker (3x)"),
    ("gap_up", "Gap up > 2%"),
    ("gap_down", "Gap down > 2%"),
    ("nr7", "NR7 (narrowest range of 7)"),
    ("inside_day", "Inside day"),
    ("bull_flag", "Bull flag (in the box)"),
    ("bull_flag_breakout", "Bull flag breakout"),
    ("double_bottom", "Double bottom breakout (today, on volume)"),
    ("db_forming", "Double bottom forming (below neckline)"),
    ("supertrend_buy", "Supertrend Buy Signal (bullish flip)"),
    ("supertrend_sell", "Supertrend Sell Signal (bearish flip)"),
    ("stoch_bull_cross", "Stochastic Bullish Cross (%K > %D)"),
    ("stoch_bear_cross", "Stochastic Bearish Cross (%K < %D)"),
    ("stoch_oversold", "Stochastic Oversold (%K < 20)"),
    ("stoch_overbought", "Stochastic Overbought (%K > 80)"),
]
for p, label in PATTERNS:
    _F.append((p, label, "bool", "bool", "Patterns", None))


def _dynamic_field_spec(name):
    """
    On-demand schema synthesizer for arbitrary indicator periods.

    Why this was written:
    TradingView allows traders to use ANY arbitrary period (e.g. EMA 17, SMA 42, RSI 21, ATR 10).
    This function recognizes any valid moving average, oscillator, or lookback period,
    and returns its field specification including linked previous-day (_prev) support for crossovers.
    """
    m = re.fullmatch(r"(ema|sma|rsi|atr)(\d+)(_prev)?", name, re.I)
    if m:
        kind, n, prev = m.group(1).upper(), int(m.group(2)), bool(m.group(3))
        if 2 <= n <= 400:
            base = "%s%d" % (kind.lower(), n)
            fmt = "num" if kind in ("RSI", "ATR") else "price"
            grp = "Moving Averages" if "MA" in kind else "Oscillators"
            return {
                "label": "%s %d%s" % (kind, n, " (prev)" if prev else ""),
                "type": "num",
                "fmt": fmt,
                "group": grp,
                "prev": None if prev else base + "_prev",
            }
    m = re.fullmatch(r"(high|low)_(\d+)d(_prev)?", name, re.I)
    if m:
        kind, n, prev = m.group(1).lower(), int(m.group(2)), bool(m.group(3))
        if 2 <= n <= 400:
            base = "%s_%dd" % (kind, n)
            return {
                "label": "%d-Day %sest Close%s" % (n, "High" if kind == "high" else "Low", " (prev)" if prev else ""),
                "type": "num",
                "fmt": "price",
                "group": "Levels",
                "prev": None if prev else base + "_prev",
            }
    return None


class DynamicFieldsDict(dict):
    """
    Dictionary of supported screener fields with on-demand dynamic field resolution.

    Why this was written:
    Allows user filter expressions like 'crosses_above(ema17, ema42) and rsi21 < 30' to compile
    seamlessly without throwing 'unknown field' errors.
    """
    def __contains__(self, k):
        if dict.__contains__(self, k):
            return True
        return _dynamic_field_spec(k) is not None

    def __getitem__(self, k):
        try:
            return dict.__getitem__(self, k)
        except KeyError:
            spec = _dynamic_field_spec(k)
            if spec is not None:
                self[k] = spec
                return spec
            raise

    def get(self, k, default=None):
        if k in self:
            return self[k]
        return default


# Dictionary lookup mapping field name -> metadata dict.
# Rationale: O(1) attribute lookup for the filter compiler and HTTP /api/meta endpoint.
FIELDS = {
    name: {"label": lab, "type": typ, "fmt": fmt, "group": grp, "prev": prev}
    for name, lab, typ, fmt, grp, prev in _F
}

# Default columns displayed when opening the web UI for the first time.
DEFAULT_COLUMNS = ["sym", "price", "change_pct", "volume", "rvol_tod", "rsi14",
                   "turnover", "from_52w_high", "industry", "exchange"]

# Pre-configured trading setups available in the UI dropdown and CLI.
PRESETS = [
    {"name": "Top gainers", "filter": "change_pct > 0 and turnover > 5cr", "sort": "change_pct", "desc": True},
    {"name": "Top losers", "filter": "change_pct < 0 and turnover > 5cr", "sort": "change_pct", "desc": False},
    {"name": "Volume shockers", "filter": "rvol_tod > 3 and turnover > 2cr", "sort": "rvol_tod", "desc": True},
    {"name": "Supertrend Buy Flips", "filter": "supertrend_buy and turnover > 2cr", "sort": "change_pct", "desc": True},
    {"name": "Stochastic Bullish Cross", "filter": "stoch_bull_cross and stoch_k < 30 and turnover > 2cr", "sort": "change_pct", "desc": True},
    {"name": "Above VWAP on volume", "filter": "price > vwap and rvol_tod > 1.5 and turnover > 2cr", "sort": "change_pct", "desc": True},
    {"name": "52W high breakouts", "filter": "new_52w_high and turnover > 2cr", "sort": "change_pct", "desc": True},
    {"name": "20D breakouts on volume", "filter": "breakout_20d and rvol_tod > 1.5 and turnover > 2cr", "sort": "rvol_tod", "desc": True},
    {"name": "Double bottom (W) breakout", "filter": "double_bottom and turnover > 1cr", "sort": "db_score", "desc": True},
    {"name": "W forming (within 3% of neckline)", "filter": "db_forming and price >= db_neckline * 0.97 and turnover > 1cr", "sort": "db_score", "desc": True},
    {"name": "W follow-through (broke out ≤5 days ago, below target)", "filter": "1 <= db_days_since_breakout <= 5 and db_neckline < price < db_target and turnover > 1cr", "sort": "db_days_since_breakout", "desc": False},
    {"name": "Bull flags", "filter": "bull_flag or bull_flag_breakout", "sort": "change_pct", "desc": True},
    {"name": "Oversold (RSI<30), liquid", "filter": "rsi14 < 30 and turnover > 2cr", "sort": "rsi14", "desc": False},
    {"name": "Oversold bounce", "filter": "oversold_bounce and turnover > 1cr", "sort": "change_pct", "desc": True},
    {"name": "Golden cross today", "filter": "golden_cross", "sort": "turnover", "desc": True},
    {"name": "EMA 9/21 bullish cross", "filter": "crosses_above(ema9, ema21) and turnover > 2cr", "sort": "change_pct", "desc": True},
    {"name": "Strong trend (ADX>25, above 50/200)", "filter": "adx14 > 25 and plus_di > minus_di and price > sma50 and sma50 > sma200", "sort": "adx14", "desc": True},
    {"name": "Gap up > 2%", "filter": "gap_up and turnover > 2cr", "sort": "gap_pct", "desc": True},
    {"name": "Recent listings at a new high", "filter": "hist_days < 250 and new_52w_high and turnover > 1cr", "sort": "change_pct", "desc": True},
    {"name": "NIFTY 50", "filter": "\"NIFTY50\" in indices", "sort": "change_pct", "desc": True},
    {"name": "NR7 squeeze", "filter": "nr7 and bb_width < 8 and turnover > 2cr", "sort": "bb_width", "desc": False},
]
