"""Chart patterns on daily bars.

Split in two so a tick costs almost nothing:
  static(bars)            structure from CLOSED bars, once per day per symbol
                          (troughs, neckline, flag box, NR7, ...)
  live_flags(st, f, q)    booleans using the live price/volume + indicator fields

A pattern that "fires" intraday on a live price can un-fire by the close
(the bar is not complete). Each flag therefore exists twice in spirit: live
(what you see now, like TradingView) and the `*_confirmed` variants computed
only on closed bars for end-of-day / backtest use.
"""


def _local_minima(closes, k, start=0):
    """Indices i >= start where closes[i] is the strict minimum of
    closes[i-k..i+k]. (`start` only skips work: a minimum at i does not
    depend on anything before i-k.)"""
    out = []
    for i in range(max(k, start), len(closes) - k):
        w = closes[i - k:i + k + 1]
        c = closes[i]
        if c == min(w) and w.count(c) == 1:
            out.append(i)
    return out


def double_bottom(bars, lookback=60, k=5, min_sep=15, max_sep=60, tol=0.03):
    """W pattern on closes (roadmap 3B), structure only (no breakout test).

    1. local minima with a +-k-day window inside the last `lookback` bars
    2. L1 before L2, min_sep <= separation <= max_sep trading days
    3. |L1-L2|/L1 <= tol
    4. neckline = highest close between L1 and L2, and it must be a real
       bounce: at least 2*tol above the higher trough (otherwise it's a flat
       range, not a W)
    5. no close after L2 below the lower trough (pattern not broken)
    6. trend filter: SMA50 at L2 vs SMA50 at L1 not down more than 2 %
       (two troughs in a downtrend are usually a continuation)
    7. `broke_ago`: closed bars since the first close above the neckline
       after L2 (0 = the last closed bar), or None while it is still forming.
       Without this a breakout from weeks ago - already past its target -
       kept matching as if it were new.
    Returns the best candidate (lowest troughs, most recent L2) or None.
    """
    closes = [b[4] for b in bars]
    if len(closes) < max(lookback, 50 + lookback // 2):
        return None
    start = len(closes) - lookback
    mins = _local_minima(closes, k, start)
    best = None
    for a in range(len(mins)):
        for b in range(a + 1, len(mins)):
            i1, i2 = mins[a], mins[b]
            sep = i2 - i1
            if sep < min_sep or sep > max_sep:
                continue
            l1, l2 = closes[i1], closes[i2]
            if abs(l1 - l2) / l1 > tol:
                continue
            neck_i = max(range(i1 + 1, i2), key=lambda j: closes[j])
            neck = closes[neck_i]
            if neck < max(l1, l2) * (1 + 2 * tol):
                continue
            low = min(l1, l2)
            if min(closes[i2:]) < low:
                continue
            if i1 >= 49:
                s1 = sum(closes[i1 - 49:i1 + 1]) / 50
                s2 = sum(closes[i2 - 49:i2 + 1]) / 50
                if s2 < s1 * 0.98:
                    continue
            else:
                continue
            sym = 1 - abs(l1 - l2) / l1 / tol             # 1 = identical troughs
            broke = next((j for j in range(i2 + 1, len(closes)) if closes[j] > neck), None)
            cand = {
                "l1": l1, "l1_date": bars[i1][0], "l2": l2, "l2_date": bars[i2][0],
                "neckline": neck, "neck_date": bars[neck_i][0], "sep": sep,
                "low": min(bars[i1][3], bars[i2][3]),     # intraday trough low for the stop
                "symmetry": sym,
                "height": neck - low,
                "broke_ago": None if broke is None else len(closes) - 1 - broke,
                "broke_date": None if broke is None else bars[broke][0],
            }
            key = (i2, -low)
            if best is None or key > best[0]:
                best = (key, cand)
    return best[1] if best else None


FLAG_BOX = {"bull_flag", "bull_flag_breakout"}
RANGE7 = {"nr7", "inside_day"}
DB_FIELDS = {"double_bottom", "db_forming", "db_score", "db_neckline", "db_target", "db_stop", "db_entry",
             "db_risk_pct", "db_target_1r", "db_target_2r", "db_days_since_breakout", "db_l1_date", "db_l2_date"}


def _want(want, names):
    return want is None or not want.isdisjoint(names)


def static(bars, want=None):
    """Closed-bar structure for live pattern checks. `want` (a set of field
    names, None = all) skips structure nobody asked for - the backtester
    calls this every day of every symbol."""
    st = {}
    closes = [b[4] for b in bars[-16:]] if want is not None and not _want(want, DB_FIELDS) else [b[4] for b in bars]
    n = len(bars)
    # bull flag (reference repo): up >10 % over the 10 sessions before the last
    # 5, then the last 5 closes inside a 5 % range. The live price must stay in
    # the box (flag intact) - breaking above the box top is bull_flag_breakout.
    if n >= 16 and _want(want, FLAG_BOX):
        pole0, pole1 = closes[-16], closes[-6]
        box = closes[-5:]
        if pole0 > 0 and pole1 / pole0 - 1 > 0.10 and (max(box) - min(box)) / min(box) <= 0.05:
            st["flag"] = {"top": max(b[2] for b in bars[-5:]), "bottom": min(box), "pole_pct": (pole1 / pole0 - 1) * 100}
    if n >= 7 and _want(want, RANGE7):
        ranges = [b[2] - b[3] for b in bars[-7:]]
        st["nr7"] = ranges[-1] == min(ranges) and ranges.count(ranges[-1]) == 1
        st["inside_day"] = bars[-1][2] < bars[-2][2] and bars[-1][3] > bars[-2][3]
    if _want(want, DB_FIELDS):
        db = double_bottom(bars)
        if db:
            st["double_bottom"] = db
    return st


def _gt(a, b):
    return a is not None and b is not None and a > b


def _le(a, b):
    return a is not None and b is not None and a <= b


# simple flags: name -> fn(f, price)
_SIMPLE = {
    "breakout_20d": lambda f, p: _gt(p, f.get("high_20d")),
    "breakdown_20d": lambda f, p: f.get("low_20d") is not None and p < f.get("low_20d"),
    "new_52w_high": lambda f, p: f.get("high_52w") is not None and p >= f.get("high_52w"),
    "new_52w_low": lambda f, p: f.get("low_52w") is not None and p <= f.get("low_52w"),
    "reclaim_ma20": lambda f, p: _le(f.get("prev_close"), f.get("sma20_prev")) and _gt(p, f.get("sma20")),
    "golden_cross": lambda f, p: _le(f.get("sma50_prev"), f.get("sma200_prev")) and _gt(f.get("sma50"), f.get("sma200")),
    "death_cross": lambda f, p: _gt(f.get("sma50_prev"), f.get("sma200_prev")) and _le(f.get("sma50"), f.get("sma200")),
    "macd_bull_cross": lambda f, p: _le(f.get("macd_prev"), f.get("macd_signal_prev")) and _gt(f.get("macd"), f.get("macd_signal")),
    "oversold": lambda f, p: f.get("rsi14") is not None and f.get("rsi14") < 30,
    "overbought": lambda f, p: _gt(f.get("rsi14"), 70),
    "oversold_bounce": lambda f, p: (f.get("rsi14_prev") is not None and f.get("rsi14_prev") < 30
                                     and _gt(p, f.get("prev_close"))),
    "volume_shock": lambda f, p: _gt(f.get("rvol_tod"), 3.0),
    "gap_up": lambda f, p: _gt(f.get("gap_pct"), 2.0),
    "gap_down": lambda f, p: f.get("gap_pct") is not None and f.get("gap_pct") < -2.0,
}


def live_flags(st, f, price, volume, want=None):
    """Pattern booleans from static structure + live fields. `want` = the
    field names needed (None = all, as the live screener uses)."""
    gt = _gt
    out = {}
    for k, fn in _SIMPLE.items():
        if want is None or k in want:
            out[k] = fn(f, price)
    if _want(want, RANGE7):
        out["nr7"] = bool(st.get("nr7"))
        out["inside_day"] = bool(st.get("inside_day"))
    if _want(want, FLAG_BOX):
        flag = st.get("flag")
        out["bull_flag"] = bool(flag) and flag["bottom"] <= price <= flag["top"]
        out["bull_flag_breakout"] = bool(flag) and price > flag["top"]
    if not _want(want, DB_FIELDS):
        return out
    db = st.get("double_bottom")
    out["double_bottom"] = out["db_forming"] = False
    for k in ("db_score", "db_neckline", "db_target", "db_stop", "db_entry", "db_risk_pct",
              "db_target_1r", "db_target_2r", "db_days_since_breakout", "db_l1_date", "db_l2_date"):
        out[k] = None
    if db:
        neck = db["neckline"]
        out["db_neckline"] = neck
        out["db_l1_date"], out["db_l2_date"] = db["l1_date"], db["l2_date"]
        rv = f.get("rvol_tod") or 0.0
        vol_ok = gt(f.get("rvol_tod"), 1.5 - 1e-9)
        closed_break = db.get("broke_ago")
        if closed_break is None:
            # Stage by today's price: still under the neckline = forming;
            # through it now = breakout day (counts with >= 1.5x volume,
            # time-of-day adjusted while the session runs).
            out["db_forming"] = price <= neck
            if price > neck:
                out["db_days_since_breakout"] = 0
                out["double_bottom"] = vol_ok
        else:
            out["db_days_since_breakout"] = closed_break + 1
        # Plan (roadmap 3B output): entry at the neckline while forming, at
        # the current price after; stop under the lower trough's intraday low;
        # measured move = neckline + pattern height; 1R / 2R from the entry.
        entry = max(price, neck)
        stop = db["low"]
        risk = entry - stop
        target = neck + db["height"]
        out["db_entry"], out["db_stop"], out["db_target"] = entry, stop, target
        if risk > 0:
            out["db_risk_pct"] = risk / entry * 100.0
            out["db_target_1r"], out["db_target_2r"] = entry + risk, entry + 2 * risk
        rr = (target - entry) / risk if risk > 0 else 0.0
        score = (40 * max(0.0, db["symmetry"])
                 + 30 * (min(1.0, 0.5 + (rv - 1.5) / 3.0) if rv >= 1.5 else 0.0)
                 + 20 * min(1.0, db["sep"] / 60.0)
                 + 10 * min(1.0, max(0.0, rr) / 2.0))
        out["db_score"] = round(score)
    return out
