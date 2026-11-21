"""STRATLAB strategy format (Strategy IR) and its compiler.

The visual builder and the chart builder both produce the same JSON - the
Strategy IR - and only this module turns it into something executable. It
compiles the IR to a backtest spec whose rules are in the screener's filter
language (parsed by expr.py: no eval, NULL-safe), so a strategy runs on
exactly the engine, fills, costs and bias rules of backtest.py.

    IR (JSON)  --validate-->  errors with a path ("entry.items[1].right")
               --compile--->  {"entry": "crosses_above(ema9, ema21) and ...",
                               "stop": "pct:1", "target": "pct:2", ...}

Shape
    {
      "version": 1, "name": "EMA momentum",
      "instrument": {"mode": "symbol", "symbols": ["RELIANCE.NS"]}
                  | {"mode": "universe", "exchanges": ["NSE"], "min_turnover": 1e7},
      "timeframe": "1d",
      "entry": <group>, "action": "BUY",
      "exit": <group> | null,                 # rule checked at each close -> exit next open
      "execution": {"entry_mode": "next_open" | "signal_close" | "buy_stop",
                    "entry_level": <operand>, "entry_valid_days": 1},
      "risk": {"stop":   {"type": "none|pct|atr|level", "value": 1, "level": <operand>},
               "target": {"type": "none|pct|atr|r|level", "value": 2, "level": <operand>},
               "trail":  {"type": "none|pct|atr", "value": 3},
               "max_hold": 20},
      "portfolio": {"capital": 100000, "sizing": "risk|equal", "risk_pct": 1,
                    "max_positions": 1, "max_alloc_pct": 100},
      "costs": {"profile": "india_delivery" | "flat", "fee_pct": 0.1, "slippage_pct": 0.05},
      "period": {"start": "2016-01-01", "end": null}
    }
    group     = {"type": "group", "op": "and"|"or", "negate": false, "items": [cond|group, ...]}
    condition = {"type": "cond", "left": <operand>, "op": <OPS>, "right": <operand>, "right2": <operand>}
              | {"type": "pattern", "pattern": "double_bottom", "negate": false}
    operand   = {"kind": "ind", "ind": "ema", "params": {"period": 9}, "mult": 1}
              | {"kind": "value", "value": 50}
"""

import datetime
import json
import os
import re

from . import backtest, expr, net
from .fields import FIELDS, PATTERNS

# ---------------------------------------------------------------- catalog
# Catalog of indicators available in the visual strategy builder.
# Format: (id, label, category_group, field_template, parameter_schema, chart_overlay)
# - field_template: formatting string such as "ema{period}" that produces the exact indicator column.
# - parameter_schema: list of (param_name, default, min, max).
# - chart_overlay: "price" draws on the main candle chart; "pane" creates an oscillator subpane;
#   None denotes purely tabular metrics that are not plotted as a time-series line.
_P = [("period", 14, 2, backtest.CUSTOM_MAX)]
INDICATORS = [
    ("close", "Close", "Price", "price", [], "price"),
    ("open", "Open", "Price", "open", [], "price"),
    ("high", "High", "Price", "high", [], "price"),
    ("low", "Low", "Price", "low", [], "price"),
    ("prev_close", "Previous close", "Price", "prev_close", [], "price"),
    ("volume", "Volume", "Volume", "volume", [], "pane"),
    ("avg_vol20", "Avg volume 20", "Volume", "avg_vol20", [], "pane"),
    ("rvol", "Relative volume", "Volume", "rvol", [], "pane"),
    ("turnover", "Turnover ₹", "Volume", "turnover", [], None),
    ("ema", "EMA", "Moving averages", "ema{period}", [("period", 9, 2, backtest.CUSTOM_MAX)], "price"),
    ("sma", "SMA", "Moving averages", "sma{period}", [("period", 20, 2, backtest.CUSTOM_MAX)], "price"),
    ("rsi", "RSI", "Oscillators", "rsi{period}", _P, "pane"),
    ("macd", "MACD line (12,26)", "Oscillators", "macd", [], "pane"),
    ("macd_signal", "MACD signal (9)", "Oscillators", "macd_signal", [], "pane"),
    ("macd_hist", "MACD histogram", "Oscillators", "macd_hist", [], "pane"),
    ("adx14", "ADX 14", "Oscillators", "adx14", [], "pane"),
    ("plus_di", "+DI 14", "Oscillators", "plus_di", [], "pane"),
    ("minus_di", "−DI 14", "Oscillators", "minus_di", [], "pane"),
    ("atr14", "ATR 14", "Volatility", "atr14", [], "pane"),
    ("atr", "ATR", "Volatility", "atr{period}", [("period", 14, 2, backtest.CUSTOM_MAX)], "pane"),
    ("atr_pct", "ATR % of price", "Volatility", "atr_pct", [], "pane"),
    ("supertrend", "Supertrend (10,3)", "Trends", "supertrend", [], "price"),
    ("supertrend_dir", "Supertrend Direction (+1/-1)", "Trends", "supertrend_dir", [], "pane"),
    ("vwap", "VWAP", "Price", "vwap", [], "price"),
    ("vwap_pct", "Price % from VWAP", "Performance", "vwap_pct", [], None),
    ("stoch_k", "Stochastic %K (14,3)", "Oscillators", "stoch_k", [], "pane"),
    ("stoch_d", "Stochastic %D (3)", "Oscillators", "stoch_d", [], "pane"),
    ("donchian_high", "Donchian Upper (20)", "Levels", "donchian_high", [], "price"),
    ("donchian_low", "Donchian Lower (20)", "Levels", "donchian_low", [], "price"),
    ("donchian_mid", "Donchian Mid (20)", "Levels", "donchian_mid", [], "price"),
    ("bb_upper", "Bollinger upper (20,2)", "Volatility", "bb_upper", [], "price"),
    ("bb_lower", "Bollinger lower (20,2)", "Volatility", "bb_lower", [], "price"),
    ("bb_pctb", "Bollinger %B", "Volatility", "bb_pctb", [], "pane"),
    ("bb_width", "Bollinger width %", "Volatility", "bb_width", [], "pane"),
    ("high_20d", "20-day highest close", "Levels", "high_20d", [], "price"),
    ("low_20d", "20-day lowest close", "Levels", "low_20d", [], "price"),
    ("high_nd", "N-day High", "Levels", "high_{period}d", [("period", 20, 2, backtest.CUSTOM_MAX)], "price"),
    ("low_nd", "N-day Low", "Levels", "low_{period}d", [("period", 20, 2, backtest.CUSTOM_MAX)], "price"),
    ("high_52w", "52-week high", "Levels", "high_52w", [], "price"),
    ("low_52w", "52-week low", "Levels", "low_52w", [], "price"),
    ("change_pct", "Day change %", "Performance", "change_pct", [], None),
    ("gap_pct", "Gap %", "Performance", "gap_pct", [], None),
    ("chg_1m", "1-month change %", "Performance", "chg_1m", [], None),
    ("chg_3m", "3-month change %", "Performance", "chg_3m", [], None),
    ("from_52w_high", "% from 52-week high", "Performance", "from_52w_high", [], None),
    ("db_neckline", "Double-bottom neckline", "Patterns", "db_neckline", [], "price"),
    ("db_stop", "Double-bottom stop", "Patterns", "db_stop", [], "price"),
    ("db_target", "Double-bottom target", "Patterns", "db_target", [], "price"),
]
IND = {i[0]: i for i in INDICATORS}

# Supported comparison and crossover operators in conditions.
OPS = {
    "crosses_above": "crosses above", "crosses_below": "crosses below",
    ">": "is above", "<": "is below", ">=": "is at or above", "<=": "is at or below",
    "between": "is between", "rising": "is rising", "falling": "is falling",
}
# Operators that require only a left operand and compare it to its own previous-day value.
UNARY = {"rising", "falling"}

STOP_TYPES = ("none", "pct", "atr", "level")
TARGET_TYPES = ("none", "pct", "atr", "r", "level")
TRAIL_TYPES = ("none", "pct", "atr")
TIMEFRAMES = {"1d": "Daily"}

# Safety limits on recursion and condition count to prevent denial-of-service via huge ASTs.
MAX_DEPTH = 6
MAX_CONDS = 40

# Predefined commission, statutory tax, and slippage cost profiles.
COST_PROFILES = {
    "india_delivery": "India equity delivery: STT, stamp, exchange, SEBI, GST, DP + slippage",
    "flat": "Flat % per side + slippage (crypto, forex, US, indices)",
}

ROOT = "strategies"


class StrategyError(ValueError):
    """Raised when Strategy IR validation or compilation encounters an error."""
    pass


def catalog():
    """
    Export indicator catalog and grammar metadata for builder UI dropdowns.

    Why this was written:
    Provides the frontend single-page app with full knowledge of allowed indicators,
    their parameter ranges, visual overlay types, and whether they can participate
    in crossover rules, keeping frontend and backend synchronized.
    """
    return {
        "indicators": [{"id": i, "label": lab, "group": grp, "params": [
            {"name": n, "default": d, "min": lo, "max": hi} for n, d, lo, hi in ps],
            "overlay": ov, "crossable": _has_prev(tpl, ps)} for i, lab, grp, tpl, ps, ov in INDICATORS],
        "ops": [{"id": k, "label": v, "unary": k in UNARY} for k, v in OPS.items()],
        "patterns": [{"id": p, "label": lab} for p, lab in PATTERNS],
        "timeframes": [{"id": k, "label": v} for k, v in TIMEFRAMES.items()],
        "cost_profiles": [{"id": k, "label": v} for k, v in COST_PROFILES.items()],
        "default": default_strategy(),
    }


def _has_prev(tpl, params):
    """
    Determine whether an indicator series tracks yesterday's value for crossover detection.

    Why this was written:
    Crossover logic (crosses_above / crosses_below) and trend checks (rising / falling)
    mathematically require evaluating day t and day t-1. Indicators with custom periods
    (EMA, SMA, RSI) and primary price series have previous-day values available. Static
    or non-temporal fields do not, and must be disallowed from crossover operations.
    """
    if params:          # ema/sma/rsi: built-in and custom periods all compute previous-day values
        return True
    if tpl == "price":
        return True
    return bool((FIELDS.get(tpl) or {}).get("prev"))


def default_strategy(symbol="RELIANCE.NS"):
    """
    Starter strategy template for the visual builder.

    Why this was written:
    Gives new users an immediate, fully valid, working trend-following template
    (EMA 9 crossing above EMA 21 with a 50-day EMA trend filter) so the studio
    never opens in a blank or broken state.
    """
    ind = lambda i, p=None: {"kind": "ind", "ind": i, "params": p or {}}
    return {
        "version": 1, "name": "EMA 9/21 crossover",
        "instrument": {"mode": "symbol", "symbols": [symbol]},
        "timeframe": "1d",
        "entry": {"type": "group", "op": "and", "negate": False, "items": [
            {"type": "cond", "left": ind("ema", {"period": 9}), "op": "crosses_above",
             "right": ind("ema", {"period": 21})},
            {"type": "cond", "left": ind("close"), "op": ">", "right": ind("ema", {"period": 50})},
        ]},
        "action": "BUY",
        "exit": {"type": "group", "op": "and", "negate": False, "items": [
            {"type": "cond", "left": ind("ema", {"period": 9}), "op": "crosses_below",
             "right": ind("ema", {"period": 21})},
        ]},
        "execution": {"entry_mode": "next_open", "entry_valid_days": 1},
        "risk": {"stop": {"type": "pct", "value": 3}, "target": {"type": "pct", "value": 6},
                 "trail": {"type": "none"}, "max_hold": 0},
        "portfolio": {"capital": 100000, "sizing": "equal", "risk_pct": 1, "max_positions": 1,
                      "max_alloc_pct": 100},
        "costs": {"profile": "india_delivery", "fee_pct": 0.1, "slippage_pct": 0.05},
        "period": {"start": None, "end": None},
    }


# ---------------------------------------------------------------- compile
def _num(v, path, lo=None, hi=None, integer=False):
    """
    Strict numeric validator with detailed JSON error pointer.

    Why this was written:
    Protects backtest execution from NaNs, infinities, booleans masquerading as ints,
    or out-of-bounds parameters. Reports errors with precise JSON path notation
    (e.g., 'portfolio.capital') so the frontend can highlight the exact offending input.
    """
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        try:
            v = float(v)
        except (TypeError, ValueError):
            raise StrategyError("%s: needs a number" % path) from None
    if v != v or v in (float("inf"), float("-inf")):
        raise StrategyError("%s: needs a finite number" % path)
    if lo is not None and v < lo or hi is not None and v > hi:
        raise StrategyError("%s: must be between %s and %s" % (path, lo, hi))
    if integer:
        if int(v) != v:
            raise StrategyError("%s: must be a whole number" % path)
        return int(v)
    return v


def _fmt(x):
    """Format numeric values cleanly without trailing zero artifacts."""
    return ("%.10g" % x) if isinstance(x, float) else str(x)


def operand(o, path):
    """
    Convert a visual builder operand into an executable expression string.

    Why this was written:
    Operands in the Strategy IR can be either static numeric literals or parameterized
    technical indicators (with optional multipliers like 'ema50 * 1.02').
    This function parses the parameters, validates parameter ranges against the indicator
    catalog, applies multipliers, and checks if the operand supports previous-day lookups.
    Returns: (expression_text, indicator_field_name, is_crossable).
    """
    if not isinstance(o, dict):
        raise StrategyError("%s: missing" % path)
    kind = o.get("kind")
    if kind == "value":
        return _fmt(_num(o.get("value"), path + ".value")), None, False
    if kind != "ind":
        raise StrategyError("%s: kind must be ind or value" % path)
    spec = IND.get(o.get("ind"))
    if spec is None:
        raise StrategyError("%s: unknown indicator %r" % (path, o.get("ind")))
    _, label, _, tpl, ps, _ = spec
    params = o.get("params") or {}
    vals = {}
    for name, default, lo, hi in ps:
        vals[name] = _num(params.get(name, default), "%s.params.%s" % (path, name), lo, hi, integer=True)
    field = tpl.format(**vals)
    text = field
    mult = o.get("mult")
    if mult not in (None, "", 1, 1.0):
        m = _num(mult, path + ".mult", 0.0001, 10000)
        text = "%s * %s" % (field, _fmt(m))
    return text, field, _has_prev(tpl, ps)


def _cond(c, path):
    """
    Compile a single condition node into a filter DSL expression.

    Why this was written:
    Translates condition primitives (patterns, unary rising/falling trends, binary comparisons,
    range checks, and crossovers) into valid filter language text for expr.py.
    Validates that:
    - Rising/falling operations target indicators that have a previous-day series.
    - Crossover operations (crosses_above/below) involve at least one valid indicator with historical continuity.
    - Negations ('not') are properly wrapped in parentheses to maintain operator precedence.
    """
    if c.get("type") == "pattern":
        p = c.get("pattern")
        if p not in dict(PATTERNS):
            raise StrategyError("%s: unknown pattern %r" % (path, p))
        return ("not %s" % p) if c.get("negate") else p
    op = c.get("op")
    if op not in OPS:
        raise StrategyError("%s.op: unknown comparison %r" % (path, op))
    left, lf, lcross = operand(c.get("left"), path + ".left")
    if op in UNARY:
        if lf is None or not lcross:
            raise StrategyError("%s: %s needs an indicator with a previous-day value" % (path, OPS[op]))
        prev = "%s_prev" % lf if lf != "price" else "prev_close"
        prev = (FIELDS.get(lf) or {}).get("prev") or prev
        out = "%s %s %s" % (lf, ">" if op == "rising" else "<", prev)
    else:
        right, rf, rcross = operand(c.get("right"), path + ".right")
        if op in ("crosses_above", "crosses_below"):
            for txt, f, ok, side in ((left, lf, lcross, "left"), (right, rf, rcross, "right")):
                if f is not None and not ok:
                    raise StrategyError("%s.%s: %s has no previous-day value, so it cannot cross"
                                        % (path, side, f))
            if lf is None and rf is None:
                raise StrategyError("%s: a crossing needs at least one indicator" % path)
            out = "%s(%s, %s)" % (op, left, right)
        elif op == "between":
            right2, _, _ = operand(c.get("right2"), path + ".right2")
            out = "%s <= %s <= %s" % (right, left, right2)
        else:
            out = "%s %s %s" % (left, op, right)
    return ("not (%s)" % out) if c.get("negate") else out


def rule(g, path="entry", depth=0, count=None):
    """
    Compile a recursive boolean group into an expression string.

    Why this was written:
    Users can build arbitrarily nested condition trees (e.g. A and (B or C)).
    This function walks the tree, enforces nesting depth limits (MAX_DEPTH=6) to prevent
    stack overflows, ignores disabled rules, respects group negation, and inserts
    parentheses when mixing AND and OR logic to ensure standard mathematical evaluation.
    """
    count = count if count is not None else [0]
    if not isinstance(g, dict) or g.get("type") != "group":
        raise StrategyError("%s: must be a condition group" % path)
    if depth > MAX_DEPTH:
        raise StrategyError("%s: groups nested deeper than %d" % (path, MAX_DEPTH))
    op = (g.get("op") or "and").lower()
    if op not in ("and", "or"):
        raise StrategyError("%s.op: must be and/or" % path)
    parts = []
    for i, it in enumerate(g.get("items") or []):
        p = "%s.items[%d]" % (path, i)
        if not isinstance(it, dict):
            raise StrategyError("%s: not a condition" % p)
        if it.get("disabled"):
            continue
        if it.get("type") == "group":
            txt = rule(it, p, depth + 1, count)
            if txt:
                parts.append("(%s)" % txt)
        else:
            count[0] += 1
            if count[0] > MAX_CONDS:
                raise StrategyError("more than %d conditions" % MAX_CONDS)
            txt = _cond(it, p)
            parts.append(("(%s)" % txt) if op == "and" and " or " in txt else txt)
    if not parts:
        return ""
    txt = (" %s " % op).join(parts)
    return ("not (%s)" % txt) if g.get("negate") else txt


def _level(lv, path, types):
    """
    Translate risk stop/target objects into backtest DSL strings.

    Why this was written:
    Normalizes diverse exit level representations ('none', 'pct:N', 'atr:N', 'r:N', or 'expr:...')
    into the concise string format consumed by backtest.py.
    """
    lv = lv or {"type": "none"}
    t = lv.get("type") or "none"
    if t not in types:
        raise StrategyError("%s.type: must be one of %s" % (path, ", ".join(types)))
    if t == "none":
        return "none"
    if t == "level":
        txt, _, _ = operand(lv.get("level"), path + ".level")
        return "expr:" + txt
    return "%s:%s" % (t, _fmt(_num(lv.get("value"), path + ".value", 0.01, 1000)))


def _date(v, path):
    """Validate ISO-8601 date string (YYYY-MM-DD)."""
    if not v:
        return None
    try:
        return datetime.date.fromisoformat(str(v)).isoformat()
    except ValueError:
        raise StrategyError("%s: must be a date like 2019-01-01" % path) from None


def compile_strategy(ir):
    """
    Compile a complete Strategy IR document into an executable backtest specification.

    Why this was written:
    Acts as the single gatekeeper between strategy definitions and backtest execution.
    Responsibilities:
    1. Validates supported action types (BUY long only) and timeframes (1d daily only).
    2. Compiles entry and exit rule groups to filter expressions.
    3. Normalizes execution models (next session open vs signal close vs buy stop).
    4. Handles instrument selection: single-stock benchmark mode vs universe scanning.
    5. Configures portfolio risk sizing and Indian delivery statutory tax models.
    6. Performs pre-flight dry-run compilation via `backtest.prepare(spec)` to catch syntax errors
       before allocating process pools.
    """
    if not isinstance(ir, dict):
        raise StrategyError("strategy must be a JSON object")
    action = (ir.get("action") or "BUY").upper()
    if action not in ("BUY", "SHORT", "BOTH"):
        raise StrategyError("action: must be BUY, SHORT or BOTH")
    if (ir.get("timeframe") or "1d") not in TIMEFRAMES:
        raise StrategyError("timeframe: only daily (1d) bars are supported so far")
    entry_src = ir.get("entry") if action in ("BUY", "BOTH") else (ir.get("entry_short") or ir.get("entry"))
    entry = rule(entry_src, "entry")
    if not entry:
        raise StrategyError("entry: add at least one condition")
    exit_ = rule(ir["exit"], "exit") if ir.get("exit") else ""
    entry_short = rule(ir["entry_short"], "entry_short") if ir.get("entry_short") else ""
    exit_short = rule(ir["exit_short"], "exit_short") if ir.get("exit_short") else ""
    ins = ir.get("instrument") or {}
    risk = ir.get("risk") or {}
    ex = ir.get("execution") or {}
    pf = dict(ir.get("portfolio") or {})
    co = ir.get("costs") or {}
    per = ir.get("period") or {}
    spec = {
        "action": action,
        "entry": entry, "exit": exit_,
        "entry_short": entry_short, "exit_short": exit_short,
        "stop": _level(risk.get("stop"), "risk.stop", STOP_TYPES),
        "target": _level(risk.get("target"), "risk.target", TARGET_TYPES),
        "trail": _level(risk.get("trail"), "risk.trail", TRAIL_TYPES),
        "max_hold": _num(risk.get("max_hold") or 0, "risk.max_hold", 0, 5000, integer=True),
        "entry_mode": ex.get("entry_mode") or "next_open",
        "entry_valid_days": _num(ex.get("entry_valid_days") or 1, "execution.entry_valid_days", 1, 60,
                                 integer=True),
        "start": _date(per.get("start"), "period.start"), "end": _date(per.get("end"), "period.end"),
    }
    if spec["entry_mode"] == "buy_stop":
        spec["entry_level"] = operand(ex.get("entry_level") or {"kind": "ind", "ind": "high"},
                                      "execution.entry_level")[0]
    mode = ins.get("mode") or "symbol"
    if mode == "symbol":
        syms = [s.strip() for s in ins.get("symbols") or [] if isinstance(s, str) and s.strip()]
        if not syms:
            raise StrategyError("instrument: pick a symbol")
        if len(syms) > 50:
            raise StrategyError("instrument: at most 50 symbols in symbol mode")
        for s in syms:
            if not re.fullmatch(r"[A-Za-z0-9.^=&_-]{1,30}", s):
                raise StrategyError("instrument: bad symbol %r" % s)
        spec["symbols"] = syms
        spec["exchanges"] = ["NSE", "BSE"]
        spec["min_turnover"] = 0
        if len(syms) == 1:
            spec["benchmark"] = syms[0]          # Benchmark against buy & hold of the instrument itself
    elif mode == "universe":
        ex_ = [e for e in ins.get("exchanges") or ["NSE"] if e in ("NSE", "BSE")]
        if not ex_:
            raise StrategyError("instrument.exchanges: NSE and/or BSE")
        spec["exchanges"] = ex_
        spec["min_turnover"] = _num(ins.get("min_turnover", 1e7), "instrument.min_turnover", 0)
    else:
        raise StrategyError("instrument.mode: symbol or universe")
    pf.setdefault("max_positions", 1 if mode == "symbol" and len(spec.get("symbols", [])) == 1 else 10)
    pf.setdefault("max_alloc_pct", 100 if pf["max_positions"] == 1 else 20)
    spec["portfolio"] = {
        "capital": _num(pf.get("capital", 100000), "portfolio.capital", 1000),
        "sizing": pf.get("sizing") or "equal",
        "risk_pct": _num(pf.get("risk_pct", 1), "portfolio.risk_pct", 0.01, 100),
        "max_positions": _num(pf["max_positions"], "portfolio.max_positions", 1, 500, integer=True),
        "max_alloc_pct": _num(pf["max_alloc_pct"], "portfolio.max_alloc_pct", 0.1, 100),
        "rank": "turnover", "rank_desc": True,
    }
    prof = co.get("profile") or "india_delivery"
    if prof == "india_delivery":
        spec["costs"] = dict(backtest.COSTS, slippage_pct=_num(co.get("slippage_pct", 0.05),
                                                               "costs.slippage_pct", 0, 5))
    elif prof == "flat":
        spec["costs"] = {k: 0.0 for k in backtest.COSTS}
        spec["costs"].update(brokerage_pct=_num(co.get("fee_pct", 0.1), "costs.fee_pct", 0, 5),
                             slippage_pct=_num(co.get("slippage_pct", 0.05), "costs.slippage_pct", 0, 5),
                             gst_pct=0.0, dp_flat=0.0)
    else:
        raise StrategyError("costs.profile: %s" % " or ".join(COST_PROFILES))
    spec["strategy"] = ir
    spec["name"] = str(ir.get("name") or "Untitled strategy")[:80]
    try:
        prep, warnings = backtest.prepare(spec)
    except (backtest.SpecError, expr.ExprError) as e:
        raise StrategyError(str(e)) from None
    return prep, warnings


def describe(spec):
    """
    Format a concise, human-readable English summary of the compiled strategy.

    Why this was written:
    Provides immediate visual feedback in the UI showing exactly how the strategy's
    entry trigger, execution timing, stop loss, profit target, and exit rules will behave.
    """
    lines = ["WHEN   " + spec["entry"], "THEN   BUY at " + {
        "next_open": "the next session's open", "signal_close": "the signal day's close (optimistic)",
        "buy_stop": "a buy stop at %s" % spec.get("entry_level")}[spec.get("entry_mode", "next_open")]]
    for k, lab in (("stop", "STOP"), ("target", "TARGET"), ("trail", "TRAIL")):
        if spec.get(k) and spec[k] != "none":
            lines.append("%-7s%s" % (lab, spec[k]))
    if spec.get("exit"):
        lines.append("EXIT   next open after: " + spec["exit"])
    if spec.get("max_hold"):
        lines.append("TIME   exit after %d sessions" % spec["max_hold"])
    return "\n".join(lines)


def chart_fields(ir):
    """
    Extract all indicator fields referenced by entry and exit rules.

    Why this was written:
    The STRATLAB interactive chart builder needs to know which indicators to compute
    and display on top of the candlestick chart. This function walks the AST and discovers
    all referenced indicators (e.g. EMA 9, EMA 21, Bollinger Bands), along with their display
    layer (main chart overlay vs separate oscillator pane).
    """
    out, seen = [], set()

    def walk(node):
        if not isinstance(node, dict):
            return
        if node.get("type") == "group":
            for it in node.get("items") or []:
                walk(it)
            return
        for side in ("left", "right", "right2"):
            o = node.get(side)
            if isinstance(o, dict) and o.get("kind") == "ind" and o.get("ind") in IND:
                try:
                    _, f, _ = operand(o, side)
                except StrategyError:
                    continue
                ov = IND[o["ind"]][5]
                if f and f not in seen and ov and f not in ("price", "open", "high", "low", "volume"):
                    seen.add(f)
                    out.append({"field": f, "label": _label(o), "overlay": ov})
    walk(ir.get("entry"))
    walk(ir.get("exit"))
    return out


def _label(o):
    """Generate display label for indicator with parameter values."""
    spec = IND[o["ind"]]
    ps = spec[4]
    if not ps:
        return spec[1]
    return "%s %s" % (spec[1], ",".join(str((o.get("params") or {}).get(n, d)) for n, d, _, _ in ps))


# ---------------------------------------------------------------- library
def _slug(name):
    """Convert human-readable strategy name to safe filesystem filename."""
    s = re.sub(r"[^a-z0-9]+", "-", (name or "").lower()).strip("-")[:60]
    return s or "strategy"


def save(ir, root=ROOT):
    """
    Atomically save Strategy IR document to local disk.

    Why this was written:
    Compiles the strategy first to guarantee that unrunnable or corrupted strategies
    are never persisted to disk. Uses atomic write (temp file + rename) to protect
    against partial writes during crash or power loss.
    """
    compile_strategy(ir)                     # Never save something that cannot run
    sid = ir.get("id") or _slug(ir.get("name"))
    if not re.fullmatch(r"[a-z0-9-]{1,60}", sid):
        sid = _slug(sid)
    ir = dict(ir, id=sid, saved=datetime.datetime.now().isoformat(timespec="seconds"))
    os.makedirs(root, exist_ok=True)
    net.write_atomic(os.path.join(root, sid + ".json"),
                     json.dumps(ir, indent=2, ensure_ascii=False).encode())
    return ir


def load(sid, root=ROOT):
    """Load saved Strategy IR document by sanitized identifier."""
    if not sid or not re.fullmatch(r"[a-z0-9-]{1,60}", sid):
        return None
    try:
        with open(os.path.join(root, sid + ".json"), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def delete(sid, root=ROOT):
    """Safely delete saved Strategy IR file."""
    if not sid or not re.fullmatch(r"[a-z0-9-]{1,60}", sid):
        return False
    try:
        os.remove(os.path.join(root, sid + ".json"))
        return True
    except OSError:
        return False


def list_saved(root=ROOT):
    """List all saved strategies with metadata for library drawer."""
    try:
        names = sorted(f for f in os.listdir(root) if f.endswith(".json"))
    except OSError:
        return []
    out = []
    for n in names:
        ir = load(n[:-5], root)
        if ir:
            out.append({"id": ir.get("id") or n[:-5], "name": ir.get("name"), "saved": ir.get("saved"),
                        "instrument": ir.get("instrument")})
    return out
