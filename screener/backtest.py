"""Backtester: replay a screener rule over years of daily history.

The entry rule is the same filter language the live screener uses, evaluated
with the same indicator code (indicators.Base walked one closed bar at a time,
then indicators.live() for the day). A rule that screens a stock today is the
rule that is tested.

Timeline of one trade (daily bars only)
    day t      close: the rule is evaluated on day t's completed bar
    day t+1    entry: at the open ("next_open", default), or when the price
               reaches a level ("buy_stop", e.g. the neckline), or at day t's
               close ("signal_close" - optimistic, you rarely get the close)
    each day   stop / target / trailing stop checked against the bar
    exit       at the stop, the target, the open after an exit rule fires, or
               the close of the last allowed day (max_hold)

Bias and realism rules, and why each one exists
  * No look-ahead: a signal on day t can only trade from day t+1 (or at t's
    close). Stop/target levels come from day t's fields.
  * Gaps: a day that opens through the stop exits at the OPEN, not the stop
    (Indian stocks gap; the stop price is not a guaranteed fill).
  * Stop and target touched on the same day: daily bars cannot say which came
    first, so the stop is assumed (conservative); counted in `ambiguous`.
  * Untradable days: no fills on zero-volume days (Yahoo fills holidays and
    no-trade days with flat volume-0 bars) or single-price days (o=h=l=c,
    typically locked at a circuit limit - you could not have bought).
  * Costs: STT, stamp duty, exchange, SEBI and GST from `costs`, plus
    slippage on every fill, plus a flat DP charge per sell in the portfolio.
  * Bad data: a trade whose path contains a >45 % one-day move is marked
    `suspect` (an unadjusted split / bad Yahoo bar) and excluded by default.
  * One position per symbol at a time; signals while in a trade are ignored.

Known biases that remain (reported in every result's warnings)
  * Survivorship: the universe is TODAY's list. Companies delisted, merged or
    suspended in the period are missing, which flatters results.
  * Index membership (`indices`) is today's - using it in a rule is look-ahead.
  * Muhurat sessions are absent from Yahoo's history (one hour a year).
"""

import concurrent.futures as cf
import datetime
import math
import os
import random
import re
import statistics
import time

from . import expr, indicators, net, patterns
from .fields import FIELDS, PATTERNS
from .history import _fname

BT_ROOT = "data/history_bt"
BT_RANGE = "10y"
BT_MAX_BARS = 2600
BENCH = "^NSEI"
SUSPECT_MOVE = 0.45
STATIC_WINDOW = 200          # bars handed to patterns.static (double bottom needs ~110)

# Fields computed from structure over closed bars (patterns.static): only
# built when the rule needs them - they cost more than the indicators.
STATIC_FIELDS = {"nr7", "inside_day", "bull_flag", "bull_flag_breakout", "double_bottom", "db_forming",
                 "db_score", "db_neckline", "db_target", "db_stop", "db_entry", "db_risk_pct",
                 "db_target_1r", "db_target_2r", "db_days_since_breakout", "db_l1_date", "db_l2_date"}
FLAG_FIELDS = STATIC_FIELDS | {p for p, _ in PATTERNS}
NOT_HISTORICAL = {"age": "data age only exists live", "official_eod": "live-only flag",
                  "hist_ok": "live-only flag", "note": "live-only text"}
LOOKAHEAD = {"indices": "index membership is today's list - using it in a backtest is look-ahead "
                        "(stocks are in the NIFTY 50 because they went up)"}

COSTS = {                      # % of trade value unless noted; delivery equity, Nov 2026
    "brokerage_pct": 0.0,      # discount brokers charge 0 on delivery
    "brokerage_max": 20.0,     # ₹ cap per order when brokerage_pct > 0
    "stt_pct": 0.1,            # buy and sell
    "stamp_pct": 0.015,        # buy only
    "exch_pct": 0.00307,       # NSE transaction charge
    "sebi_pct": 0.0001,        # ₹10 / crore
    "gst_pct": 18.0,           # on brokerage + exchange charges
    "dp_flat": 23.6,           # ₹ per sell (₹20 + GST), portfolio only
    "slippage_pct": 0.05,      # per fill, against you
}

DEFAULTS = {
    "entry": "",
    "entry_mode": "next_open",      # next_open | signal_close | buy_stop
    "entry_level": "high",          # buy_stop level (expression on the signal day)
    "entry_valid_days": 1,          # buy_stop stays active this many sessions
    "max_gap_pct": None,            # skip a next_open fill gapping up more than this
    "stop": "atr:2",                # none | pct:N | atr:N | expr:<expression>
    "target": "r:2",                # none | pct:N | atr:N | r:N | expr:<expression>
    "trail": "none",                # none | pct:N | atr:N (from the highest high since entry)
    "max_hold": 20,                 # sessions; 0 = no limit
    "exit": "",                     # expression checked at each close -> exit next open
    "start": None, "end": None,     # ISO dates (signal dates)
    "exchanges": ["NSE", "BSE"],
    "min_turnover": 1e7,            # ₹ traded on the signal day (1 crore)
    "include_suspect": False,
    "costs": COSTS,
    "portfolio": {"capital": 1_000_000, "max_positions": 10, "sizing": "risk", "risk_pct": 1.0,
                  "max_alloc_pct": 20.0, "rank": "turnover", "rank_desc": True},
}


class SpecError(ValueError):
    pass


# ---------------------------------------------------------------- custom periods
# The live screener ships fixed periods (EMA 9/20/21/50/100/200, SMA 5…200,
# RSI 14). A backtest rule may use any period - ema13, sma30, rsi7 - and
# those are computed per symbol before the walk, with the same conventions
# (SMA-seeded EMA, Wilder RSI). Value at bar t uses closes up to and
# including t, exactly like the built-in fields on day t's row.
CUSTOM_RE = re.compile(r"\b(ema|sma|rsi)(\d{1,3})(?:_prev)?\b", re.I)
CUSTOM_MAX = 400


def custom_fields(*srcs):
    """Indicator names with a non-built-in period used in these expressions."""
    out = set()
    for src in srcs:
        for m in CUSTOM_RE.finditer(src or ""):
            kind, n = m.group(1).lower(), int(m.group(2))
            name = "%s%d" % (kind, n)
            if name in FIELDS:
                continue
            if not 2 <= n <= CUSTOM_MAX:
                raise SpecError("%s period must be 2-%d (got %d)" % (kind.upper(), CUSTOM_MAX, n))
            out.add(name)
    return sorted(out)


def _split_custom(name):
    m = re.fullmatch(r"(ema|sma|rsi)(\d+)", name)
    return m.group(1), int(m.group(2))


def custom_series(bars, names):
    """{name: [value per bar]} for custom-period indicators (None = warm-up)."""
    closes = [b[4] for b in bars]
    out = {}
    for name in names:
        kind, n = _split_custom(name)
        if kind == "ema":
            e = indicators.Ema(n)
            out[name] = [e.step(c) for c in closes]
        elif kind == "sma":
            vals, run = [], 0.0
            for i, c in enumerate(closes):
                run += c - (closes[i - n] if i >= n else 0.0)
                if i and i % 500 == 0:            # re-sum: no float drift over 10 years
                    run = math.fsum(closes[max(0, i - n + 1):i + 1])
                vals.append(run / n if i >= n - 1 else None)
            out[name] = vals
        else:   # rsi: Wilder, same steps as indicators.Base
            g, l = indicators.Rma(n), indicators.Rma(n)
            vals = [None]
            for a, b in zip(closes, closes[1:]):
                ch = b - a
                vals.append(indicators._rsi(g.step(max(ch, 0.0)), l.step(max(-ch, 0.0))))
            out[name] = vals[:len(closes)]
    return out


def _bt_fields(custom=()):
    f = {k: v for k, v in FIELDS.items() if k not in NOT_HISTORICAL}
    for name in custom:
        kind, n = _split_custom(name)
        fmt = "num" if kind == "rsi" else "price"
        f[name] = {"label": "%s %d" % (kind.upper(), n), "type": "num", "fmt": fmt, "group": "Custom",
                   "prev": name + "_prev"}
        f[name + "_prev"] = {"label": "%s %d (prev)" % (kind.upper(), n), "type": "num", "fmt": fmt,
                             "group": "Custom", "prev": None}
    return f


def _level(src, kinds, what):
    """'atr:2' -> ('atr', 2.0); 'expr:low' -> ('expr', 'low'); 'none' -> ('none', None)."""
    src = (src or "none").strip()
    if src.lower() in ("none", "off", ""):
        return ("none", None)
    kind, _, val = src.partition(":")
    kind = kind.strip().lower()
    if kind not in kinds:
        raise SpecError("%s must be one of %s (got %r)" % (what, ", ".join(k + ":…" for k in kinds), src))
    if kind == "expr":
        if not val.strip():
            raise SpecError("%s expr: needs an expression, e.g. expr:low" % what)
        return ("expr", val.strip())
    try:
        x = float(val)
    except ValueError:
        raise SpecError("%s %s: needs a number (got %r)" % (what, kind, val)) from None
    if not x > 0:
        raise SpecError("%s %s: must be > 0" % (what, kind))
    return (kind, x)


def prepare(spec):
    """Validate and normalise a spec dict. Returns (spec, warnings).
    Raises SpecError / expr.ExprError with a message meant for the user."""
    s = dict(DEFAULTS)
    s.update({k: v for k, v in (spec or {}).items() if v is not None})
    s["costs"] = dict(COSTS, **(spec or {}).get("costs") or {})
    s["portfolio"] = dict(DEFAULTS["portfolio"], **(spec or {}).get("portfolio") or {})
    warnings = []
    if not (s["entry"] or "").strip():
        raise SpecError("an entry rule is required, e.g. crosses_above(ema9, ema21) and turnover > 5cr")
    level_srcs = [v.partition(":")[2] for v in (s.get("stop"), s.get("target"))
                  if isinstance(v, str) and v.strip().lower().startswith("expr:")]
    s["_custom"] = custom_fields(s["entry"], s.get("exit"),
                                 s["entry_level"] if s["entry_mode"] == "buy_stop" else "", *level_srcs)
    fields = _bt_fields(s["_custom"])
    used = set()
    _, u = expr.compile_filter(s["entry"], fields)
    used |= u
    if (s.get("exit") or "").strip():
        _, u = expr.compile_filter(s["exit"], fields)
        used |= u
    if s["entry_mode"] not in ("next_open", "signal_close", "buy_stop"):
        raise SpecError("entry_mode must be next_open, signal_close or buy_stop")
    if s["entry_mode"] == "buy_stop":
        _, u = expr.compile_value(s["entry_level"], fields)
        used |= u
    s["_stop"] = _level(s["stop"], ("pct", "atr", "expr"), "stop")
    s["_target"] = _level(s["target"], ("pct", "atr", "r", "expr"), "target")
    s["_trail"] = _level(s["trail"], ("pct", "atr"), "trail")
    for k in ("_stop", "_target"):
        if s[k][0] == "expr":
            _, u = expr.compile_value(s[k][1], fields)
            used |= u
    if s["_target"][0] == "r" and s["_stop"][0] == "none":
        raise SpecError("target r:N needs a stop (R = entry - stop)")
    if s["_stop"][0] == "none" and s["_trail"][0] == "none" and not s["max_hold"] and not s.get("exit"):
        raise SpecError("no way out: set a stop, a trailing stop, max_hold or an exit rule")
    rank = s["portfolio"]["rank"]
    if rank not in fields:
        raise SpecError("rank field %r is not a field" % rank)
    used.add(rank)
    for d in ("start", "end"):
        if s[d]:
            try:
                datetime.date.fromisoformat(s[d])
            except ValueError:
                raise SpecError("%s must be a date like 2019-01-01" % d) from None
    p = s["portfolio"]
    if p["sizing"] not in ("risk", "equal"):
        raise SpecError("sizing must be risk or equal")
    if p["sizing"] == "risk" and s["_stop"][0] == "none":
        raise SpecError("risk sizing needs a stop; use sizing equal")
    for k, lo in (("capital", 1000), ("max_positions", 1), ("risk_pct", 0.01), ("max_alloc_pct", 0.1)):
        if not float(p[k]) >= lo:
            raise SpecError("portfolio %s must be >= %s" % (k, lo))
    s["max_hold"] = int(s["max_hold"] or 0)
    s["entry_valid_days"] = max(1, int(s["entry_valid_days"] or 1))
    s["_used"] = sorted(used)
    s["_need_static"] = bool(used & STATIC_FIELDS)
    s["_need_flags"] = bool(used & FLAG_FIELDS)
    for f, why in LOOKAHEAD.items():
        if f in used:
            warnings.append("%s: %s" % (f, why))
    if s["entry_mode"] == "signal_close":
        warnings.append("signal_close fills at the close of the signal day - the close is only known "
                        "after the session, so this is optimistic")
    return s, warnings


# ---------------------------------------------------------------- simulation
class _Compiled:
    def __init__(self, s):
        fields = _bt_fields(s.get("_custom") or ())
        self.s = s
        self.custom = s.get("_custom") or []
        self.entry, _ = expr.compile_filter(s["entry"], fields)
        self.exit = expr.compile_filter(s["exit"], fields)[0] if (s.get("exit") or "").strip() else None
        self.entry_level = expr.compile_value(s["entry_level"], fields)[0] if s["entry_mode"] == "buy_stop" else None
        self.stop = s["_stop"]
        self.target = s["_target"]
        self.trail = s["_trail"]
        self.stop_fn = expr.compile_value(self.stop[1], fields)[0] if self.stop[0] == "expr" else None
        self.target_fn = expr.compile_value(self.target[1], fields)[0] if self.target[0] == "expr" else None
        self.need_static = s["_need_static"]
        self.need_flags = set(s["_used"]) & FLAG_FIELDS    # empty set = no flags at all
        self.start, self.end = s.get("start"), s.get("end")
        self.min_turnover = float(s.get("min_turnover") or 0)
        self.rank = s["portfolio"]["rank"]
        self.mode = s["entry_mode"]
        self.max_hold = s["max_hold"]
        self.max_gap = s.get("max_gap_pct")
        self.valid_days = s["entry_valid_days"]


INFO_KEYS = ("sym", "name", "exchange", "series", "industry", "indices")


def _row(base, bar, bars, t, info, need_static, need_flags, cust=None):
    """The day's row as the live screener would show it at the close. Lazy:
    indicator groups are computed only when the rule reads one of their
    fields; pattern flags only when the rule uses a pattern."""
    d, o, h, l, c, v = bar
    row = indicators.LazyRow(base, c, h, l, v, o)
    for k in INFO_KEYS:
        row[k] = info.get(k)
    row.update(price=c, open=o, high=h, low=l, volume=v, hist_days=base.n, prev_volume=base.prev_volume)
    if cust:
        for k, arr in cust.items():
            row[k] = arr[t]
            row[k + "_prev"] = arr[t - 1] if t else None
    if need_flags:
        st = patterns.static(bars[max(0, t - STATIC_WINDOW):t], need_flags) if need_static else {}
        row.update(patterns.live_flags(st, row, c, v, need_flags))
    return row


def _levels(cp, sig, entry):
    """(stop, target) for a fill at `entry`, from the signal day's values.
    None level = not used. Returns None when the trade is invalid."""
    k, x = cp.stop
    if k == "none":
        stop = None
    elif k == "pct":
        stop = entry * (1 - x / 100.0)
    elif k == "atr":
        stop = entry - x * sig["atr"] if sig["atr"] else None
        if stop is None:
            return None
    else:
        stop = sig["stop"]
        if stop is None:
            return None
    if stop is not None and stop >= entry:
        return None
    k, x = cp.target
    if k == "none":
        target = None
    elif k == "pct":
        target = entry * (1 + x / 100.0)
    elif k == "atr":
        target = entry + x * sig["atr"] if sig["atr"] else None
        if target is None:
            return None
    elif k == "r":
        target = entry + x * (entry - stop)
    else:
        target = sig["target"]
        if target is None:
            return None
    if target is not None and target <= entry:
        return None
    return stop, target


def simulate(bars, info, cp, counters=None):
    """Walk one symbol's bars. Returns the list of trades (dicts)."""
    cnt = counters if counters is not None else {}

    def bump(k):
        cnt[k] = cnt.get(k, 0) + 1

    base = indicators.Base([])
    cust = custom_series(bars, cp.custom) if cp.custom else None
    # Forex (and some indices) carry no volume at all: there, volume 0 is
    # "not reported", not "no trades", so it cannot mark a day untradable.
    no_volume = sum(1 for b in bars if b[5] > 0) < 0.05 * len(bars)
    trades = []
    pos = None
    pend = None
    first_needed = cp.start or ""
    for t, bar in enumerate(bars):
        d, o, h, l, c, v = bar
        tradable = (v > 0 or no_volume) and h >= l > 0
        locked = tradable and o == h == l == c

        # ---- 1. a pending entry tries to fill
        if pend is not None and pos is None:
            fill = None
            if not tradable:
                pend["left"] -= 1
                if cp.mode == "next_open" or pend["left"] <= 0:
                    bump("no_fill_untradable")
                    pend = None
            elif locked:
                bump("no_fill_locked")
                pend = None
            elif cp.mode == "next_open":
                if cp.max_gap is not None and pend["close"] and (o / pend["close"] - 1) * 100 > cp.max_gap:
                    bump("no_fill_gap")
                else:
                    fill = (o, "open")
                pend = None if fill is None else pend
            else:   # buy_stop
                lvl = pend["level"]
                if o >= lvl:
                    if cp.max_gap is not None and (o / lvl - 1) * 100 > cp.max_gap:
                        bump("no_fill_gap")
                        pend = None
                    else:
                        fill = (o, "open")
                elif h >= lvl:
                    fill = (lvl, "intraday")
                else:
                    pend["left"] -= 1
                    if pend["left"] <= 0:
                        bump("not_triggered")
                        pend = None
            if fill is not None:
                entry, kind = fill
                lv = _levels(cp, pend["sig"], entry)
                if lv is None:
                    bump("invalid_levels")
                else:
                    pos = _open(pend, d, t, entry, lv, kind)
                pend = None

        # ---- 2. manage the open position on this bar
        exited = False
        if pos is not None and (pos["entry_i"] < t or pos["kind"] != "close"):
            entry_day = pos["entry_i"] == t
            if tradable:
                stop, target = pos["stop"], pos["target"]
                if pos.get("exit_next_open") and not entry_day:
                    _close(pos, d, t, o, pos["exit_next_open"], True, trades)
                    exited = True
                elif not entry_day and stop is not None and o <= stop:
                    _close(pos, d, t, o, "trail" if pos["trailed"] else "stop", True, trades)
                    exited = True
                elif not entry_day and target is not None and o >= target:
                    _close(pos, d, t, o, "target", True, trades)
                    exited = True
                else:
                    hit_s = stop is not None and l <= stop
                    # entry day of a buy_stop fill: the high may have come
                    # before the fill - never credit a target that day
                    hit_t = target is not None and h >= target and not (entry_day and pos["kind"] == "intraday")
                    if hit_s and hit_t:
                        bump("ambiguous")
                    if hit_s:
                        _close(pos, d, t, stop, "trail" if pos["trailed"] else "stop", False, trades)
                        exited = True
                    elif hit_t:
                        _close(pos, d, t, target, "target", False, trades)
                        exited = True
            if exited:
                pos = None
            else:
                pos["path"].append((d, c))
                pos["hi"] = max(pos["hi"], h)
                pos["lo"] = min(pos["lo"], l)
                if tradable:
                    pos["held"] += 1

        # ---- 3. the day's fields (only when something needs them)
        need_row = (pos is not None and not exited and (cp.exit or cp.trail[0] == "atr")) or \
                   (pos is None and pend is None and d >= first_needed and (cp.end is None or d <= cp.end))
        row = _row(base, bar, bars, t, info, cp.need_static, cp.need_flags, cust) if (need_row and base.n) else None

        # ---- 4. close-of-day management for the open position
        if pos is not None and pos["entry_i"] <= t:
            if cp.trail[0] != "none" and tradable:
                k, x = cp.trail
                if k == "pct":
                    ts = pos["hi"] * (1 - x / 100.0)
                else:
                    a = row.get("atr14") if row else None
                    ts = pos["hi"] - x * a if a else None
                if ts is not None and (pos["stop"] is None or ts > pos["stop"]):
                    pos["stop"] = ts
                    pos["trailed"] = True
            if cp.max_hold and pos["held"] >= cp.max_hold and tradable:
                _close(pos, d, t, c, "time", False, trades)
                exited = True
                pos = None
            elif cp.exit and row is not None and cp.exit(row):
                pos["exit_next_open"] = "rule"

        # ---- 5. a new signal at this close
        if row is not None and pos is None and pend is None and tradable and not exited:
            if cp.entry(row):
                bump("signals")
                if (row.get("turnover") or 0) < cp.min_turnover:
                    bump("below_min_turnover")
                else:
                    sig = {"atr": row.get("atr14"),
                           "stop": cp.stop_fn(row) if cp.stop_fn else None,
                           "target": cp.target_fn(row) if cp.target_fn else None,
                           "rank": row.get(cp.rank), "turnover": row.get("turnover")}
                    pend = {"sig": sig, "signal_date": d, "signal_i": t, "close": c,
                            "left": cp.valid_days}
                    if cp.mode == "buy_stop":
                        lvl = cp.entry_level(row)
                        if lvl is None or lvl <= 0:
                            bump("no_level")
                            pend = None
                        else:
                            pend["level"] = lvl
                    elif cp.mode == "signal_close":
                        lv = _levels(cp, sig, c)
                        if lv is None:
                            bump("invalid_levels")
                        else:
                            pos = _open(pend, d, t, c, lv, "close")
                            pos["path"].append((d, c))
                        pend = None
        base.advance(bar)

    if pos is not None:
        last = bars[-1]
        _close(pos, last[0], len(bars) - 1, last[4], "end", False, trades, keep_path=True)
    return trades


def _open(pend, d, t, entry, levels, kind):
    """kind: 'open' (filled at the open), 'intraday' (buy stop hit during the
    day) or 'close' (signal_close)."""
    stop, target = levels
    return {"signal_date": pend["signal_date"], "entry_date": d, "entry_i": t, "entry": entry,
            "stop0": stop, "stop": stop, "target": target, "kind": kind,
            "rank": pend["sig"]["rank"], "turnover": pend["sig"]["turnover"],
            "hi": entry, "lo": entry, "held": 0, "trailed": False, "path": [], "exit_next_open": None}


def _close(pos, d, t, price, reason, at_open, trades, keep_path=True):
    pos["path"].append((d, price))
    hi = max(pos["hi"], price)
    lo = min(pos["lo"], price)
    e = pos["entry"]
    closes = [pos["entry"]] + [p for _, p in pos["path"]]
    suspect = any(b <= 0 or abs(b / a - 1) > SUSPECT_MOVE for a, b in zip(closes, closes[1:]) if a > 0)
    risk = (e - pos["stop0"]) if pos["stop0"] is not None else None
    trades.append({
        "signal_date": pos["signal_date"], "entry_date": pos["entry_date"], "entry": e,
        "stop": pos["stop0"], "target": pos["target"], "exit_date": d, "exit": price, "reason": reason,
        "exit_at_open": at_open, "entry_kind": pos["kind"],
        # sessions exposed: entry day counts unless filled at its close; the
        # exit day counts unless left at its open
        "bars": t - pos["entry_i"] + (0 if pos["kind"] == "close" else 1) - (1 if at_open else 0),
        "ret_pct": (price / e - 1) * 100.0, "r": ((price - e) / risk) if risk else None,
        "mfe_pct": (hi / e - 1) * 100.0, "mae_pct": (lo / e - 1) * 100.0,
        "rank": pos["rank"], "turnover": pos["turnover"], "suspect": suspect,
        "path": pos["path"] if keep_path else None,
    })


# ---------------------------------------------------------------- costs & stats
def cost_pcts(c):
    """(buy %, sell %) of trade value, slippage included; DP is separate."""
    gst = c["gst_pct"] / 100.0
    fees = c["exch_pct"] + c["brokerage_pct"]
    buy = c["stt_pct"] + c["stamp_pct"] + c["sebi_pct"] + fees * (1 + gst) + c["slippage_pct"]
    sell = c["stt_pct"] + c["sebi_pct"] + fees * (1 + gst) + c["slippage_pct"]
    return buy / 100.0, sell / 100.0


def apply_costs(trades, costs):
    b, s = cost_pcts(costs)
    for t in trades:
        e, x = t["entry"], t["exit"]
        paid, got = e * (1 + b), x * (1 - s)
        t["net_pct"] = (got / paid - 1) * 100.0
        risk = (e - t["stop"]) if t["stop"] is not None else None
        t["net_r"] = ((got - paid) / risk) if risk else None
    return trades


def _bootstrap_ci(xs, n=1000, seed=7):
    """95 % interval of the mean by resampling the trades: if it spans 0,
    the edge is not distinguishable from luck."""
    if len(xs) < 5:
        return None
    rnd = random.Random(seed)
    k = len(xs)
    means = sorted(math.fsum(rnd.choices(xs, k=k)) / k for _ in range(n))
    return [means[int(0.025 * n)], means[int(0.975 * n) - 1]]


def trade_stats(trades, ci=False):
    n = len(trades)
    if not n:
        return {"trades": 0}
    net = [t["net_pct"] for t in trades]
    wins = [x for x in net if x > 0]
    losses = [x for x in net if x <= 0]
    rs = [t["net_r"] for t in trades if t["net_r"] is not None]
    streak = best = 0
    for x in net:
        streak = streak + 1 if x <= 0 else 0
        best = max(best, streak)
    reasons = {}
    for t in trades:
        reasons[t["reason"]] = reasons.get(t["reason"], 0) + 1
    gross_win, gross_loss = sum(wins), -sum(losses)
    return {
        "trades": n,
        "win_rate": len(wins) / n * 100.0,
        "avg_win_pct": statistics.fmean(wins) if wins else None,
        "avg_loss_pct": statistics.fmean(losses) if losses else None,
        "expectancy_pct": statistics.fmean(net),
        "expectancy_pct_ci95": _bootstrap_ci(net) if ci else None,
        "median_pct": statistics.median(net),
        "expectancy_r": statistics.fmean(rs) if rs else None,
        "expectancy_r_ci95": _bootstrap_ci(rs) if (rs and ci) else None,
        "profit_factor": (gross_win / gross_loss) if gross_loss > 0 else None,
        "avg_bars": statistics.fmean(t["bars"] for t in trades),
        "max_consec_losses": best,
        "best_pct": max(net), "worst_pct": min(net),
        "avg_mfe_pct": statistics.fmean(t["mfe_pct"] for t in trades),
        "avg_mae_pct": statistics.fmean(t["mae_pct"] for t in trades),
        "exit_reasons": reasons,
    }


def by_year(trades):
    out = {}
    for t in trades:
        out.setdefault(t["entry_date"][:4], []).append(t)
    rows = []
    for y in sorted(out):
        ts = out[y]
        net = [t["net_pct"] for t in ts]
        rs = [t["net_r"] for t in ts if t["net_r"] is not None]
        rows.append({"year": y, "trades": len(ts), "win_rate": sum(x > 0 for x in net) / len(ts) * 100.0,
                     "expectancy_pct": statistics.fmean(net),
                     "expectancy_r": statistics.fmean(rs) if rs else None})
    return rows


# ---------------------------------------------------------------- portfolio
def portfolio(trades, p, costs, dates):
    """Chronological account simulation over `dates` (trading days).

    Same day order as the market: exits at the open, entries at the open,
    buy-stop entries during the day, then intraday and closing exits, then
    entries at the close. Equity is marked to each close. Sizing uses the previous close's
    equity. No leverage, no shorting. Returns (curve, taken trades, stats)."""
    b, s = cost_pcts(costs)
    dp = float(costs.get("dp_flat") or 0)
    cap = float(p["capital"])
    maxpos = int(p["max_positions"])
    desc = bool(p.get("rank_desc", True))
    by_entry, by_exit = {}, {}
    for i, t in enumerate(trades):
        by_entry.setdefault(t["entry_date"], []).append(i)
    cash = cap
    held = {}        # trade idx -> {"shares", "last"}
    curve, taken = [], []
    skipped = {"slots": 0, "cash": 0}
    invested_frac = []
    equity = cap
    closes_by = {i: dict(t["path"]) for i, t in enumerate(trades)}

    def do_exits(d, at_open):
        nonlocal cash
        for i in list(by_exit.get(d, [])):
            t = trades[i]
            if t["exit_at_open"] != at_open or i not in held:
                continue
            h = held.pop(i)
            proceeds = h["shares"] * t["exit"] * (1 - s) - dp
            cash += proceeds
            rec = taken[h["k"]]
            rec["pnl"] = proceeds - h["cost"]
            rec["pnl_pct"] = rec["pnl"] / h["cost"] * 100.0

    def do_entries(d, kind):
        nonlocal cash
        cands = [i for i in by_entry.get(d, []) if trades[i]["entry_kind"] == kind]
        cands.sort(key=lambda i: (trades[i]["rank"] is None,
                                  -(trades[i]["rank"] or 0) if desc else (trades[i]["rank"] or 0)))
        for i in cands:
            t = trades[i]
            if len(held) >= maxpos:
                skipped["slots"] += 1
                continue
            px = t["entry"] * (1 + b)
            if p["sizing"] == "equal":
                alloc = equity / maxpos
            else:
                risk = t["entry"] - t["stop"]
                alloc = (equity * float(p["risk_pct"]) / 100.0 / risk) * t["entry"] if risk > 0 else 0
            alloc = min(alloc, equity * float(p["max_alloc_pct"]) / 100.0, cash)
            shares = int(alloc // px)
            if shares < 1:
                skipped["cash"] += 1
                continue
            cost = shares * px
            cash -= cost
            held[i] = {"shares": shares, "last": t["entry"], "cost": cost, "k": len(taken)}
            by_exit.setdefault(t["exit_date"], []).append(i)
            taken.append(dict({k: v for k, v in t.items() if k != "path"}, shares=shares,
                              value=cost, pnl=None, pnl_pct=None))

    for d in dates:
        do_exits(d, True)            # gap stops / exit-rule exits at the open
        do_entries(d, "open")
        do_entries(d, "intraday")    # buy stops (before that day's intraday exits)
        do_exits(d, False)           # stops / targets / time exits
        do_entries(d, "close")       # signal_close fills
        for i, h in held.items():
            c = closes_by[i].get(d)
            if c is not None:
                h["last"] = c
        pos_val = sum(h["shares"] * h["last"] for h in held.values())
        equity = cash + pos_val
        invested_frac.append(pos_val / equity if equity > 0 else 0)
        curve.append((d, equity))
    # anything still open at the end: marked at its last close
    return curve, taken, skipped, (statistics.fmean(invested_frac) * 100 if invested_frac else 0)


def curve_stats(curve, capital):
    if len(curve) < 2:
        return {}
    eq = [e for _, e in curve]
    d0 = datetime.date.fromisoformat(curve[0][0])
    d1 = datetime.date.fromisoformat(curve[-1][0])
    years = max((d1 - d0).days / 365.25, 1e-9)
    final = eq[-1]
    rets = [b / a - 1 for a, b in zip(eq, eq[1:]) if a > 0]
    peak, mdd, mdd_at, dd_start, longest, cur_start = eq[0], 0.0, None, None, 0, 0
    for i, e in enumerate(eq):
        if e >= peak:
            peak = e
            longest = max(longest, i - cur_start)
            cur_start = i
        dd = e / peak - 1
        if dd < mdd:
            mdd, mdd_at = dd, curve[i][0]
    longest = max(longest, len(eq) - 1 - cur_start)
    sd = statistics.pstdev(rets) if len(rets) > 1 else 0
    # bars per year as observed: ~248 for NSE, ~365 for crypto, ~260 for forex
    ppy = (len(eq) - 1) / years if years >= 0.5 else 248
    return {
        "start": curve[0][0], "end": curve[-1][0], "final": final,
        "total_return_pct": (final / capital - 1) * 100.0,
        "cagr_pct": ((final / capital) ** (1 / years) - 1) * 100.0 if final > 0 else -100.0,
        "max_drawdown_pct": mdd * 100.0, "max_drawdown_date": mdd_at,
        "longest_drawdown_days": longest,
        "sharpe": (statistics.fmean(rets) / sd * math.sqrt(ppy)) if sd > 0 else None,
        "volatility_pct": sd * math.sqrt(ppy) * 100.0,
    }


# ---------------------------------------------------------------- runner
_W = {}


INDIAN_RE = re.compile(r"(\.NS|\.BO)$|^\^(NSE|BSE|CNX)", re.I)
REFRESH_SECS = 12 * 3600


def ensure_history(ysym, client, root=BT_ROOT, max_age=REFRESH_SECS):
    """10-year daily bars for any Yahoo symbol, cached in `root`. NSE/BSE
    symbols and indices go through HistoryStore (split checks, IST partial-bar
    rule). Anything else (BTC-USD, EURUSD=X, AAPL, GC=F) is fetched whole and
    its most recent day dropped: it may still be trading in its own time zone,
    and a partial bar would be a look-ahead. Returns bars; on a network error
    returns the cached bars if any, else raises."""
    from . import yahoo
    from .history import HistoryStore
    path = os.path.join(root, _fname(ysym))
    doc = net.read_json(path)
    cached = [tuple(b) for b in doc["bars"]] if doc and doc.get("ysym") == ysym else None
    if cached and time.time() - (doc.get("fetched") or 0) < max_age:
        return cached
    try:
        if INDIAN_RE.search(ysym):
            store = HistoryStore(root, client, full_range=BT_RANGE, max_bars=BT_MAX_BARS)
            store.load([ysym])
            store.sync(ysym)
            return list(store.bars(ysym))
        bars, _, _ = yahoo.parse_chart_daily(client.get_json(yahoo.chart_urls(ysym, BT_RANGE, "1d")))
        cutoff = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=1)).date().isoformat()
        bars = [tuple(b) for b in bars if b[0] < cutoff][-BT_MAX_BARS:]
        if not bars:
            raise ValueError("no daily history for %s" % ysym)
        net.write_json(path, {"ysym": ysym, "fetched": int(time.time()), "bars": [list(b) for b in bars]})
        return bars
    except (net.FetchError, ValueError):
        if cached:
            return cached
        raise


def external_info(ysym):
    """Row info for an instrument that is not in the NSE/BSE universe."""
    return {"sym": ysym, "ysym": ysym, "exchange": "EXT", "name": ysym, "series": None,
            "industry": None, "indices": []}


def series(bars, names, info=None):
    """Per-bar values of `names` exactly as the backtester sees them on each
    day's row (same Base walk, same custom-period code). For chart overlays:
    what is drawn is what the rule was tested on."""
    custom = custom_fields(*names)
    fields = _bt_fields(custom)
    bad = [n for n in names if n not in fields]
    if bad:
        raise SpecError("unknown field(s): %s" % ", ".join(bad))
    flags = set(names) & FLAG_FIELDS
    need_static = bool(set(names) & STATIC_FIELDS)
    cust = custom_series(bars, custom) if custom else None
    base = indicators.Base([])
    info = info or {}
    out = {n: [] for n in names}
    for t, bar in enumerate(bars):
        row = _row(base, bar, bars, t, info, need_static, flags, cust) if base.n else None
        for n in names:
            v = row.get(n) if row is not None else None
            out[n].append(v if not isinstance(v, float) or math.isfinite(v) else None)
        base.advance(bar)
    return out


def _init_worker(spec, hist_root):
    _W["cp"] = _Compiled(spec)
    _W["root"] = hist_root


def _load_bars(root, ysym):
    doc = net.read_json(os.path.join(root, _fname(ysym)))
    if not doc or doc.get("ysym") != ysym:
        return None
    return [tuple(b) for b in doc["bars"]]


def _run_chunk(items):
    cp, root = _W["cp"], _W["root"]
    out, cnt, missing = [], {}, 0
    for info in items:
        bars = _load_bars(root, info["ysym"])
        if not bars:
            missing += 1
            continue
        for t in simulate(bars, info, cp, cnt):
            t["sym"], t["ysym"], t["exchange"] = info["sym"], info["ysym"], info["exchange"]
            out.append(t)
    cnt["missing_history"] = missing
    return out, cnt


def run(spec, universe_doc, hist_root=BT_ROOT, workers=None, progress=None, log=print):
    """Full backtest. Returns a JSON-able result dict."""
    t0 = time.time()
    s, warnings = prepare(spec)
    exch = set(s["exchanges"])
    syms = [x for x in universe_doc["symbols"] if x["exchange"] in exch]
    if s.get("symbols"):
        want = set(s["symbols"])
        syms = [x for x in syms if x["sym"] in want or x["ysym"] in want]
        known = {x["sym"] for x in syms} | {x["ysym"] for x in syms}
        # instruments outside the NSE/BSE list (index, crypto, forex, US...):
        # tested from their own cached history in hist_root
        syms += [external_info(y) for y in s["symbols"] if y not in known]
    if not syms:
        raise SpecError("no symbols to test")
    workers = workers or max(1, (os.cpu_count() or 2) - 1)
    trades, counters = [], {}
    nchunks = min(len(syms), max(1, workers * 8))
    chunks = [syms[i::nchunks] for i in range(nchunks)]
    done = 0

    def merge(res):
        nonlocal done
        tr, cnt = res
        trades.extend(tr)
        for k, v in cnt.items():
            counters[k] = counters.get(k, 0) + v
        done += 1
        if progress:
            progress(done / len(chunks))

    if workers == 1:
        _init_worker(s, hist_root)
        for ch in chunks:
            merge(_run_chunk(ch))
    else:
        with cf.ProcessPoolExecutor(workers, initializer=_init_worker, initargs=(s, hist_root)) as ex:
            for f in cf.as_completed([ex.submit(_run_chunk, ch) for ch in chunks]):
                merge(f.result())
    if counters.get("missing_history"):
        warnings.append("%d of %d symbols have no backtest history yet (run `main.py bt-sync`)"
                        % (counters["missing_history"], len(syms)))
    apply_costs(trades, s["costs"])
    n_suspect = sum(t["suspect"] for t in trades)
    if not s["include_suspect"] and n_suspect:
        warnings.append("%d trades crossed a >45%% one-day move (likely a bad or unadjusted Yahoo bar) "
                        "and were excluded" % n_suspect)
        trades = [t for t in trades if not t["suspect"]]
    trades.sort(key=lambda t: (t["entry_date"], t["sym"]))
    if counters.get("ambiguous"):
        n = counters["ambiguous"]
        warnings.append("%d day%s touched both stop and target; counted as stop%s (daily bars cannot "
                        "tell which came first)" % (n, "" if n == 1 else "s", "" if n == 1 else "s"))
    if not s.get("symbols"):
        warnings.append("survivorship bias: tested on today's listed stocks - companies delisted or merged "
                        "during the period are missing, which flatters results")

    bench_sym = s.get("benchmark") or BENCH
    bench = _load_bars(hist_root, bench_sym) or []
    path_dates = {d for t in trades for d, _ in t["path"]}
    first = s.get("start") or min((t["entry_date"] for t in trades), default=None) or \
        (bench[0][0] if bench else None)
    # through the end date, and on until the last trade signalled by then exits
    upper = max([s.get("end") or (bench[-1][0] if bench else "")] + list(path_dates))
    dates = sorted({b[0] for b in bench if (first is None or b[0] >= first) and b[0] <= upper} | path_dates)
    curve, taken, skipped, exposure = portfolio(trades, s["portfolio"], s["costs"], dates)
    cstats = curve_stats(curve, float(s["portfolio"]["capital"]))
    bstats, bcurve = {}, []
    if bench and curve:
        bmap = {b[0]: b[4] for b in bench}
        bd = [d for d, _ in curve if d in bmap]
        if bd:
            k = float(s["portfolio"]["capital"]) / bmap[bd[0]]
            bcurve = [(d, bmap[d] * k) for d in bd]
            bstats = curve_stats(bcurve, float(s["portfolio"]["capital"]))
    if len(trades) < 30:
        warnings.append("only %d trades: too few to tell skill from luck" % len(trades))
    ex = trade_stats(trades, ci=True)
    half = len(trades) // 2
    result = {
        "spec": {k: v for k, v in s.items() if not k.startswith("_")},
        "warnings": warnings,
        "universe": len(syms),
        "counters": counters,
        "every_signal": ex,
        "halves": [trade_stats(trades[:half]), trade_stats(trades[half:])] if half >= 10 else None,
        "by_year": by_year(trades),
        "portfolio": dict(cstats, trades_taken=len(taken), skipped=skipped, exposure_pct=exposure,
                          trade_stats=trade_stats([t for t in taken if t["pnl"] is not None])),
        "benchmark": dict(bstats, symbol=bench_sym) if bstats else None,
        "equity": _thin(curve), "bench_equity": _thin(bcurve),
        "trades": [{k: (round(v, 4) if isinstance(v, float) else v) for k, v in t.items() if k != "path"}
                   for t in trades],
        "taken": [{k: (round(v, 4) if isinstance(v, float) else v) for k, v in t.items()} for t in taken],
        "secs": round(time.time() - t0, 1),
    }
    return result


def _thin(curve, n=1500):
    if len(curve) <= n:
        return [[d, round(e, 2)] for d, e in curve]
    step = len(curve) / n
    idx = sorted({int(i * step) for i in range(n)} | {len(curve) - 1})
    return [[curve[i][0], round(curve[i][1], 2)] for i in idx]


RESULTS = "results/backtests"


def save_result(res, root=RESULTS):
    """results/backtests/<id>.json.gz; returns the path. id = time + rule slug."""
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    slug = "".join(ch if ch.isalnum() else "-" for ch in res["spec"]["entry"].lower())[:40].strip("-")
    rid = "%s_%s" % (stamp, slug or "rule")
    res["id"] = rid
    path = os.path.join(root, rid + ".json.gz")
    net.write_json(path, res)
    return path


def list_results(root=RESULTS, limit=50):
    try:
        names = sorted((f for f in os.listdir(root) if f.endswith(".json.gz")), reverse=True)[:limit]
    except OSError:
        return []
    out = []
    for n in names:
        doc = net.read_json(os.path.join(root, n))
        if not doc:
            continue
        pf, ex = doc.get("portfolio") or {}, doc.get("every_signal") or {}
        out.append({"id": doc.get("id") or n[:-8], "name": doc["spec"].get("name"), "entry": doc["spec"]["entry"], "stop": doc["spec"]["stop"],
                    "target": doc["spec"]["target"], "trades": ex.get("trades"),
                    "expectancy_r": ex.get("expectancy_r"), "cagr_pct": pf.get("cagr_pct"),
                    "max_drawdown_pct": pf.get("max_drawdown_pct")})
    return out


def load_result(rid, root=RESULTS):
    if not rid or "/" in rid or ".." in rid:
        return None
    return net.read_json(os.path.join(root, rid + ".json.gz"))


CSV_COLS = ["sym", "exchange", "signal_date", "entry_date", "entry", "stop", "target", "exit_date", "exit",
            "reason", "bars", "ret_pct", "net_pct", "r", "net_r", "mfe_pct", "mae_pct", "turnover"]


def write_csv_to(trades, f):
    import csv
    w = csv.writer(f)
    w.writerow(CSV_COLS)
    for t in trades:
        w.writerow([t.get(c) for c in CSV_COLS])


def write_csv(trades, path):
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        write_csv_to(trades, f)
