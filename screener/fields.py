"""Field registry: every column the screener knows, its type, format and group.

One source of truth for the filter parser (names, prev-day variants), the API
(/api/meta) and the UI column picker. Adding an indicator = add it in
indicators.live() and list it here.
"""

from .indicators import EMA_N, SMA_N

# name: (label, type, format, group, prev_field)
# format: price | pct | num | int | vol | money | ratio | text | bool | time | list
_F = [
    ("sym", "Symbol", "str", "text", "Info", None),
    ("name", "Name", "str", "text", "Info", None),
    ("exchange", "Exch", "str", "text", "Info", None),
    ("series", "Series", "str", "text", "Info", None),
    ("industry", "Industry", "str", "text", "Info", None),
    ("indices", "Indices", "list", "list", "Info", None),
    ("price", "Price", "num", "price", "Price", "prev_close"),
    ("change", "Chg", "num", "price", "Price", None),
    ("change_pct", "Chg %", "num", "pct", "Price", None),
    ("open", "Open", "num", "price", "Price", None),
    ("high", "High", "num", "price", "Price", None),
    ("low", "Low", "num", "price", "Price", None),
    ("prev_close", "Prev Close", "num", "price", "Price", None),
    ("gap_pct", "Gap %", "num", "pct", "Price", None),
    ("chg_from_open", "Chg from Open %", "num", "pct", "Price", None),
    ("range_pct", "Day Range %", "num", "pct", "Price", None),
    ("close_in_range", "Pos in Range", "num", "ratio", "Price", None),
    ("volume", "Volume", "num", "vol", "Volume", "prev_volume"),
    ("prev_volume", "Prev Volume", "num", "vol", "Volume", None),
    ("turnover", "Turnover", "num", "money", "Volume", None),
    ("avg_vol10", "Avg Vol 10D", "num", "vol", "Volume", None),
    ("avg_vol20", "Avg Vol 20D", "num", "vol", "Volume", None),
    ("avg_vol50", "Avg Vol 50D", "num", "vol", "Volume", None),
    ("rvol", "Rel Vol", "num", "ratio", "Volume", None),
    ("rvol_tod", "Rel Vol (time adj)", "num", "ratio", "Volume", None),
    ("rsi14", "RSI 14", "num", "num", "Oscillators", "rsi14_prev"),
    ("rsi14_prev", "RSI 14 (prev)", "num", "num", "Oscillators", None),
    ("macd", "MACD", "num", "num", "Oscillators", "macd_prev"),
    ("macd_signal", "MACD Signal", "num", "num", "Oscillators", "macd_signal_prev"),
    ("macd_hist", "MACD Hist", "num", "num", "Oscillators", None),
    ("macd_prev", "MACD (prev)", "num", "num", "Oscillators", None),
    ("macd_signal_prev", "MACD Signal (prev)", "num", "num", "Oscillators", None),
    ("adx14", "ADX 14", "num", "num", "Oscillators", None),
    ("plus_di", "+DI", "num", "num", "Oscillators", None),
    ("minus_di", "-DI", "num", "num", "Oscillators", None),
    ("atr14", "ATR 14", "num", "price", "Volatility", None),
    ("atr_pct", "ATR %", "num", "pct", "Volatility", None),
    ("bb_upper", "BB Upper", "num", "price", "Volatility", None),
    ("bb_lower", "BB Lower", "num", "price", "Volatility", None),
    ("bb_pctb", "BB %B", "num", "ratio", "Volatility", None),
    ("bb_width", "BB Width %", "num", "pct", "Volatility", None),
    ("high_52w", "52W High", "num", "price", "Performance", None),
    ("low_52w", "52W Low", "num", "price", "Performance", None),
    ("from_52w_high", "From 52W High %", "num", "pct", "Performance", None),
    ("from_52w_low", "From 52W Low %", "num", "pct", "Performance", None),
    ("high_20d", "20D High Close", "num", "price", "Performance", None),
    ("low_20d", "20D Low Close", "num", "price", "Performance", None),
    ("chg_1w", "Perf 1W %", "num", "pct", "Performance", None),
    ("chg_1m", "Perf 1M %", "num", "pct", "Performance", None),
    ("chg_3m", "Perf 3M %", "num", "pct", "Performance", None),
    ("chg_6m", "Perf 6M %", "num", "pct", "Performance", None),
    ("chg_1y", "Perf 1Y %", "num", "pct", "Performance", None),
    ("chg_ytd", "Perf YTD %", "num", "pct", "Performance", None),
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
    ("age", "Data Age (s)", "num", "int", "Data", None),
    ("hist_days", "History Bars", "num", "int", "Data", None),
    ("official_eod", "Official EOD", "bool", "bool", "Data", None),
]
for n in SMA_N:
    _F.append(("sma%d" % n, "SMA %d" % n, "num", "price", "Moving Averages", "sma%d_prev" % n))
    _F.append(("sma%d_prev" % n, "SMA %d (prev)" % n, "num", "price", "Moving Averages", None))
for n in EMA_N:
    _F.append(("ema%d" % n, "EMA %d" % n, "num", "price", "Moving Averages", "ema%d_prev" % n))
    _F.append(("ema%d_prev" % n, "EMA %d (prev)" % n, "num", "price", "Moving Averages", None))

PATTERNS = [
    ("breakout_20d", "20D closing-high breakout"), ("breakdown_20d", "20D closing-low breakdown"),
    ("new_52w_high", "New 52-week high"), ("new_52w_low", "New 52-week low"),
    ("reclaim_ma20", "Reclaimed SMA 20"), ("golden_cross", "Golden cross (50/200)"),
    ("death_cross", "Death cross (50/200)"), ("macd_bull_cross", "MACD bullish cross"),
    ("oversold", "RSI < 30"), ("overbought", "RSI > 70"), ("oversold_bounce", "Oversold bounce"),
    ("volume_shock", "Volume shocker (3x)"), ("gap_up", "Gap up > 2%"), ("gap_down", "Gap down > 2%"),
    ("nr7", "NR7 (narrowest range of 7)"), ("inside_day", "Inside day"),
    ("bull_flag", "Bull flag (in the box)"), ("bull_flag_breakout", "Bull flag breakout"),
    ("double_bottom", "Double bottom breakout (today, on volume)"),
    ("db_forming", "Double bottom forming (below neckline)"),
]
for p, label in PATTERNS:
    _F.append((p, label, "bool", "bool", "Patterns", None))

FIELDS = {name: {"label": lab, "type": typ, "fmt": fmt, "group": grp, "prev": prev}
          for name, lab, typ, fmt, grp, prev in _F}

DEFAULT_COLUMNS = ["sym", "price", "change_pct", "volume", "rvol_tod", "rsi14",
                   "turnover", "from_52w_high", "industry", "exchange"]

PRESETS = [
    {"name": "Top gainers", "filter": "change_pct > 0 and turnover > 5cr", "sort": "change_pct", "desc": True},
    {"name": "Top losers", "filter": "change_pct < 0 and turnover > 5cr", "sort": "change_pct", "desc": False},
    {"name": "Volume shockers", "filter": "rvol_tod > 3 and turnover > 2cr", "sort": "rvol_tod", "desc": True},
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
