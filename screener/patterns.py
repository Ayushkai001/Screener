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
    """Find indices i >= start where closes[i] is the strict local minimum across window [i-k .. i+k].

    Rationale:
    A true technical pivot trough requires that prices both before and after index `i` were strictly higher.
    Using a strict local minimum window prevents flat trading ranges from generating false trough signals.
    """
    out = []
    for i in range(max(k, start), len(closes) - k):
        w = closes[i - k:i + k + 1]
        c = closes[i]
        if c == min(w) and w.count(c) == 1:
            out.append(i)
    return out


def double_bottom(bars, lookback=60, k=5, min_sep=15, max_sep=60, tol=0.03):
    """Detect Double Bottom ('W') reversal structures on daily closing bars.

    Algorithm & Design Rationale:
    1. Local Minima: Finds pivot troughs within the last `lookback` (60) bars with a ±5-day clearance window.
    2. Temporal Separation: Trough 1 (L1) must occur strictly before Trough 2 (L2), separated by between
       15 and 60 trading days. Less than 15 days is high-frequency chop; more than 60 days loses structural relevance.
    3. Price Symmetry: Troughs must match within 3% tolerance (|L1 - L2| / L1 <= 0.03) to ensure a shared support zone.
    4. Genuine Reversal (Neckline): The peak close between L1 and L2 must be at least 6% (2*tol) above the troughs.
       Without this, flat consolidation channels would falsely qualify as 'W' patterns.
    5. Structural Integrity: No closing price after L2 may breach below the lower trough (which would invalidate the pattern).
    6. Trend Filter: The 50-day SMA at L2 must not be more than 2% below the 50-day SMA at L1. Two troughs in a
       steep downtrend typically form a continuation bear flag rather than a reliable reversal.
    7. Breakout Freshness (`broke_ago`): Tracks whether the breakout closed above the neckline today (0), in prior
       sessions (1+), or is still forming (None). This prevents stocks that broke out weeks ago from repeatedly matching.

    Returns:
        Candidate dictionary with structural levels (troughs, neckline, height, dates, symmetry) or None.
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
            # Verify trough price symmetry within tolerance (3%)
            if abs(l1 - l2) / l1 > tol:
                continue
            neck_i = max(range(i1 + 1, i2), key=lambda j: closes[j])
            neck = closes[neck_i]
            # Ensure meaningful bounce height between troughs
            if neck < max(l1, l2) * (1 + 2 * tol):
                continue
            low = min(l1, l2)
            # Ensure price has not broken below support after the second trough
            if min(closes[i2:]) < low:
                continue
            # Trend filter: ensure 50-day SMA is not collapsing
            if i1 >= 49:
                s1 = sum(closes[i1 - 49:i1 + 1]) / 50
                s2 = sum(closes[i2 - 49:i2 + 1]) / 50
                if s2 < s1 * 0.98:
                    continue
            else:
                continue
            sym = 1 - abs(l1 - l2) / l1 / tol  # 1.0 = identical trough prices
            broke = next((j for j in range(i2 + 1, len(closes)) if closes[j] > neck), None)
            cand = {
                "l1": l1, "l1_date": bars[i1][0], "l2": l2, "l2_date": bars[i2][0],
                "neckline": neck, "neck_date": bars[neck_i][0], "sep": sep,
                "low": min(bars[i1][3], bars[i2][3]),  # intraday trough low for the stop-loss level
                "symmetry": sym,
                "height": neck - low,
                "broke_ago": None if broke is None else len(closes) - 1 - broke,
                "broke_date": None if broke is None else bars[broke][0],
            }
            # Rank candidates: prioritize more recent second troughs and lower overall support
            key = (i2, -low)
            if best is None or key > best[0]:
                best = (key, cand)
    return best[1] if best else None


# Sets of pattern field names for fast dependency pruning
FLAG_BOX = {"bull_flag", "bull_flag_breakout"}
RANGE7 = {"nr7", "inside_day"}
DB_FIELDS = {"double_bottom", "db_forming", "db_score", "db_neckline", "db_target", "db_stop", "db_entry",
             "db_risk_pct", "db_target_1r", "db_target_2r", "db_days_since_breakout", "db_l1_date", "db_l2_date"}


def _want(want, names):
    """Helper to check if any of `names` are required by the caller's `want` set."""
    return want is None or not want.isdisjoint(names)


def static(bars, want=None):
    """Compute structural pattern levels from closed daily bars.

    Rationale:
    Expensive pattern discovery (Double Bottom scanning, Bull Flag impulse poles) is executed
    only once per day on closed bars. The `want` parameter allows backtest passes to skip
    calculating patterns not referenced in the strategy rules.
    """
    st = {}
    closes = [b[4] for b in bars[-16:]] if want is not None and not _want(want, DB_FIELDS) else [b[4] for b in bars]
    n = len(bars)

    # Bull Flag pattern: +10% impulse move over 10 sessions, followed by 5-day tight consolidation (<=5% range)
    if n >= 16 and _want(want, FLAG_BOX):
        pole0, pole1 = closes[-16], closes[-6]
        box = closes[-5:]
        if pole0 > 0 and pole1 / pole0 - 1 > 0.10 and (max(box) - min(box)) / min(box) <= 0.05:
            st["flag"] = {"top": max(b[2] for b in bars[-5:]), "bottom": min(box), "pole_pct": (pole1 / pole0 - 1) * 100}

    # Range contractions: NR7 (narrowest daily range of 7 sessions) and Inside Day (range inside previous day's)
    if n >= 7 and _want(want, RANGE7):
        ranges = [b[2] - b[3] for b in bars[-7:]]
        st["nr7"] = ranges[-1] == min(ranges) and ranges.count(ranges[-1]) == 1
        st["inside_day"] = bars[-1][2] < bars[-2][2] and bars[-1][3] > bars[-2][3]

    # Double bottom structure
    if _want(want, DB_FIELDS):
        db = double_bottom(bars)
        if db:
            st["double_bottom"] = db
    return st


def _gt(a, b):
    """Null-safe greater-than comparison."""
    return a is not None and b is not None and a > b


def _le(a, b):
    """Null-safe less-than-or-equal comparison."""
    return a is not None and b is not None and a <= b


# Direct live boolean pattern flags evaluated against live price and indicator fields
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
    """Combine static structural patterns with live price/volume metrics to produce instant pattern signals.

    Rationale:
    Executed on every incoming quote tick.
    - Evaluates Simple break/cross flags.
    - Double Bottom Trade Plan:
      Calculates explicit trade planning levels: entry (neckline or price), stop (intraday low of lowest trough),
      measured target (neckline + height), 1R/2R multiples, and a composite 0-100 quality score.
      A Double Bottom breakout requires volume expansion (rvol_tod >= 1.5).
    """
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
        # Volume expansion confirmation: >= 1.5x expected time-adjusted volume
        vol_ok = gt(f.get("rvol_tod"), 1.5 - 1e-9)
        closed_break = db.get("broke_ago")
        if closed_break is None:
            # If price has never closed above neckline:
            # Under neckline = still forming; through neckline = breakout day on volume
            out["db_forming"] = price <= neck
            if price > neck:
                out["db_days_since_breakout"] = 0
                out["double_bottom"] = vol_ok
        else:
            out["db_days_since_breakout"] = closed_break + 1

        # Calculate formal trade plan
        entry = max(price, neck)
        stop = db["low"]
        risk = entry - stop
        target = neck + db["height"]  # Classical measured move
        out["db_entry"], out["db_stop"], out["db_target"] = entry, stop, target
        if risk > 0:
            out["db_risk_pct"] = risk / entry * 100.0
            out["db_target_1r"], out["db_target_2r"] = entry + risk, entry + 2 * risk
        rr = (target - entry) / risk if risk > 0 else 0.0

        # Composite Pattern Quality Score (0 to 100 points):
        # - Symmetry: up to 40 pts (troughs at equal price)
        # - Volume: up to 30 pts (higher volume expansion above 1.5x threshold)
        # - Duration: up to 20 pts (longer base accumulation up to 60 days)
        # - Risk/Reward: up to 10 pts (favorable measured move vs stop distance)
        score = (40 * max(0.0, db["symmetry"])
                 + 30 * (min(1.0, 0.5 + (rv - 1.5) / 3.0) if rv >= 1.5 else 0.0)
                 + 20 * min(1.0, db["sep"] / 60.0)
                 + 10 * min(1.0, max(0.0, rr) / 2.0))
        out["db_score"] = round(score)
    return out
