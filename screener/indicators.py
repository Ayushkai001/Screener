"""Technical indicators, computed incrementally.

The screener re-evaluates every symbol on every tick, so recomputing RSI over
500 bars for 4,500 symbols each second is wasteful. Instead:

    Base   = state of every indicator after the last CLOSED daily bar
             (built once per day per symbol from history)
    live() = Base + one step with today's live bar (price, day high/low, volume)

Each recurrence is written once as a `step` and used both to build the base
from history and to take the live step, so the live value is exactly what a
full recompute would give with today's partial bar appended (the way
TradingView's screener shows indicators intraday).

Conventions (match TradingView defaults):
  RSI / ATR / ADX use Wilder's RMA, seeded with an SMA of the first n values.
  EMA uses alpha 2/(n+1), seeded with the SMA of the first n values.
  Prices are Yahoo split-adjusted closes (not dividend-adjusted), as TV does.
Not enough history -> None. None never compares true in a filter, so a stock
with 30 days of history simply does not match "sma200 > ..." - it is not
treated as zero.
"""

import math

SMA_N = (5, 10, 20, 50, 100, 200)
EMA_N = (9, 20, 21, 50, 100, 200)
MIN_52W_BARS = 20
CLOSE_WINDOWS = sorted({n for n in SMA_N} | {n - 1 for n in SMA_N})
VOL_WINDOWS = (10, 20, 50)
PERF = {"chg_1w": 5, "chg_1m": 21, "chg_3m": 63, "chg_6m": 126, "chg_1y": 250}


# ---- step functions (shared by base build and live step) ----------------

class Ema:
    __slots__ = ("n", "a", "v", "seed")

    def __init__(self, n):
        self.n, self.a, self.v, self.seed = n, 2.0 / (n + 1), None, []

    def step(self, x):
        if self.v is None:
            self.seed.append(x)
            if len(self.seed) == self.n:
                self.v = sum(self.seed) / self.n
                self.seed = None
            return self.v
        self.v += self.a * (x - self.v)
        return self.v

    def peek(self, x):
        """Value after one more step, without changing state."""
        if self.v is None:
            if self.seed is not None and len(self.seed) == self.n - 1:
                return (sum(self.seed) + x) / self.n
            return None
        return self.v + self.a * (x - self.v)


class Rma(Ema):
    """Wilder's moving average (alpha = 1/n)."""

    def __init__(self, n):
        super().__init__(n)
        self.a = 1.0 / n


def _rsi(ag, al):
    if ag is None or al is None:
        return None
    if al == 0:
        return 100.0 if ag > 0 else 50.0
    return 100.0 - 100.0 / (1.0 + ag / al)


def true_range(h, l, prev_c):
    if prev_c is None:
        return h - l
    return max(h - l, abs(h - prev_c), abs(l - prev_c))


class Base:
    """Indicator state after the last closed bar.

    Built by stepping through the bars once; `advance(bar)` steps one more
    closed bar in place. The backtester walks a symbol's whole history with
    one Base (O(n) instead of rebuilding for every day, O(n^2)); the live
    engine builds a fresh one per day and never advances it. Both go through
    the same `_push` / `_finish`, so a walked state equals a rebuilt one.
    """

    TAIL = 260     # longest look-back of any window field (52 weeks = 250)

    def __init__(self, bars, official_prev_close=None):
        # bars: [(date, o, h, l, c, v), ...] closed, ascending.
        # official_prev_close: NSE/BSE's official close for the last bar.
        # Yahoo's bar may hold the last traded price instead; the official
        # close is what change % and TradingView use, so it replaces it.
        if bars and official_prev_close:
            d, o, h, l, _, v = bars[-1]
            c = official_prev_close
            bars = list(bars[:-1]) + [(d, o, max(h, c), min(l, c), c, v)]
        self.n = 0
        self.last_date = None
        self._c, self._h, self._l, self._v = [], [], [], []
        self.ema = {n: Ema(n) for n in EMA_N}
        self.ema12, self.ema26, self.macd_sig = Ema(12), Ema(26), Ema(9)
        self.rsi_g, self.rsi_l = Rma(14), Rma(14)
        self.atr = Rma(14)
        self.pdm, self.mdm, self.adx_tr, self.adx = Rma(14), Rma(14), Rma(14), Rma(14)
        self.macd_prev = None
        self._year = None
        self._last_close_prior_year = None
        # running window sums (exactly re-summed at every trim, so float
        # drift cannot build up): closes over n and n-1 days, volume over n
        self._cs = {w: 0.0 for w in CLOSE_WINDOWS}
        self._vs = {w: 0.0 for w in VOL_WINDOWS}
        for b in bars:
            self._push(b)
        self._finish()

    def advance(self, bar):
        """Step one more closed bar (backtest walk)."""
        self._push(bar)
        self._finish()

    def _push(self, bar):
        d, o, h, l, c, v = bar
        year = d[:4]
        if self._year is not None and year != self._year:
            self._last_close_prior_year = self._c[-1]
        self._year = year
        for e in self.ema.values():
            e.step(c)
        e12, e26 = self.ema12.step(c), self.ema26.step(c)
        if e12 is not None and e26 is not None:
            self.macd_prev = e12 - e26
            self.macd_sig.step(self.macd_prev)
        if self._c:
            pc, ph, pl = self._c[-1], self._h[-1], self._l[-1]
            ch = c - pc
            self.rsi_g.step(max(ch, 0.0))
            self.rsi_l.step(max(-ch, 0.0))
            tr = true_range(h, l, pc)
            self.atr.step(tr)
            up, dn = h - ph, pl - l
            self.pdm.step(up if up > dn and up > 0 else 0.0)
            self.mdm.step(dn if dn > up and dn > 0 else 0.0)
            t = self.adx_tr.step(tr)
            dx = _dx(self.pdm.v, self.mdm.v, t)
            if dx is not None:
                self.adx.step(dx)
        cs, vs, closes, vols = self._cs, self._vs, self._c, self._v
        closes.append(c)
        self._h.append(h)
        self._l.append(l)
        vols.append(v)
        n = len(closes)
        for w in CLOSE_WINDOWS:
            cs[w] += c - (closes[-w - 1] if n > w else 0.0)
        for w in VOL_WINDOWS:
            vs[w] += v - (vols[-w - 1] if n > w else 0.0)
        if n > 2 * self.TAIL:          # amortised trim + exact re-sum
            for a in (self._c, self._h, self._l, self._v):
                del a[:-self.TAIL]
            for w in CLOSE_WINDOWS:
                cs[w] = sum(closes[-w:])
            for w in VOL_WINDOWS:
                vs[w] = sum(vols[-w:])
        self.n += 1
        self.last_date = d

    def _finish(self):
        """Window fields from the tails (every look-back is <= TAIL, so the
        `len(...) >= n` tests below are the same as on the full history)."""
        closes, highs, lows, vols = self._c, self._h, self._l, self._v
        self.prev_close = closes[-1] if closes else None
        self.prev_high = highs[-1] if highs else None
        self.prev_low = lows[-1] if lows else None
        self.prev_volume = vols[-1] if vols else None
        # SMA: keep the sum of the last n-1 closes (live adds today's price)
        self.sma_sum = {}
        self.sma_prev = {}
        cs, L = self._cs, len(closes)
        for n in SMA_N:
            self.sma_sum[n] = cs[n - 1] if L >= n - 1 else None
            self.sma_prev[n] = cs[n] / n if L >= n else None
        # volume averages over CLOSED days (today's partial volume would bias them)
        self.avg_vol = {n: (self._vs[n] / n if L >= n else None) for n in VOL_WINDOWS}
        self.high_20c = max(closes[-20:]) if len(closes) >= 20 else None
        self.low_20c = min(closes[-20:]) if len(closes) >= 20 else None
        # Over whatever history exists, like TradingView: a stock listed 3
        # months ago shows its post-listing high (a classic IPO-base setup),
        # not a blank. The row's `hist_days` says how much history that is.
        self.high_52w = max(highs[-250:]) if len(highs) >= MIN_52W_BARS else None
        self.low_52w = min(lows[-250:]) if len(lows) >= MIN_52W_BARS else None
        self.perf_ref = {k: (closes[-n] if len(closes) >= n else None) for k, n in PERF.items()}
        # 20-day Bollinger needs the last 19 closes
        self.bb_tail = closes[-19:] if len(closes) >= 19 else None
        self.year_open_close = self._last_close_prior_year


def _dx(pdm, mdm, tr):
    if pdm is None or mdm is None or not tr:
        return None
    pdi, mdi = 100.0 * pdm / tr, 100.0 * mdm / tr
    s = pdi + mdi
    return 100.0 * abs(pdi - mdi) / s if s else 0.0


def _pct(a, b):
    if a is None or b is None or b == 0:
        return None
    return (a / b - 1.0) * 100.0


class _Ctx:
    """Inputs of one live step, computed once and shared by the groups."""
    __slots__ = ("price", "hi", "lo", "pc", "tr", "volume", "open_", "frac")

    def __init__(self, base, price, high, low, volume, open_, prev_close, session_fraction):
        hi = price if high is None or high < price else high
        lo = price if low is None or low > price else low
        if open_ is not None:
            hi = open_ if open_ > hi else hi
            lo = open_ if open_ < lo else lo
        self.price, self.hi, self.lo, self.volume, self.open_ = price, hi, lo, volume, open_
        self.pc = base.prev_close if base.prev_close is not None else prev_close
        self.tr = true_range(hi, lo, self.pc)
        self.frac = session_fraction


SMA_KEYS = [(n, "sma%d" % n, "sma%d_prev" % n) for n in SMA_N]
EMA_KEYS = [(n, "ema%d" % n, "ema%d_prev" % n) for n in EMA_N]


def _g_basic(base, x):
    price, pc, open_, hi, lo = x.price, x.pc, x.open_, x.hi, x.lo
    return {
        "prev_close": pc,
        "change": (price - pc) if pc else None,
        "change_pct": _pct(price, pc),
        "gap_pct": _pct(open_, pc) if open_ else None,
        "chg_from_open": _pct(price, open_) if open_ else None,
        "range_pct": _pct(hi, lo) if lo else None,
        "close_in_range": ((price - lo) / (hi - lo)) if hi > lo else None,
    }


def _g_sma(base, x):
    f = {}
    for n, k, kp in SMA_KEYS:
        s = base.sma_sum[n]
        f[k] = (s + x.price) / n if s is not None else None
        f[kp] = base.sma_prev[n]
    return f


def _g_ema(base, x):
    f = {}
    for n, k, kp in EMA_KEYS:
        e = base.ema[n]
        f[k] = e.peek(x.price)
        f[kp] = e.v
    return f


def _g_rsi(base, x):
    price, pc = x.price, x.pc
    ag = base.rsi_g.peek(max(price - pc, 0.0)) if pc else None
    al = base.rsi_l.peek(max(pc - price, 0.0)) if pc else None
    return {"rsi14": _rsi(ag, al), "rsi14_prev": _rsi(base.rsi_g.v, base.rsi_l.v)}


def _g_macd(base, x):
    e12, e26 = base.ema12.peek(x.price), base.ema26.peek(x.price)
    macd = (e12 - e26) if (e12 is not None and e26 is not None) else None
    sig = base.macd_sig.peek(macd) if macd is not None else None
    return {"macd": macd, "macd_signal": sig,
            "macd_hist": (macd - sig) if (macd is not None and sig is not None) else None,
            "macd_prev": base.macd_prev, "macd_signal_prev": base.macd_sig.v}


def _g_atr(base, x):
    atr = base.atr.peek(x.tr)
    return {"atr14": atr, "atr_pct": (atr / x.price * 100.0) if atr is not None else None}


def _g_adx(base, x):
    if base.prev_high is None:
        return {"adx14": None, "plus_di": None, "minus_di": None}
    up, dn = x.hi - base.prev_high, base.prev_low - x.lo
    pdm = base.pdm.peek(up if up > dn and up > 0 else 0.0)
    mdm = base.mdm.peek(dn if dn > up and dn > 0 else 0.0)
    t = base.adx_tr.peek(x.tr)
    dx = _dx(pdm, mdm, t)
    return {"adx14": base.adx.peek(dx) if dx is not None else None,
            "plus_di": 100.0 * pdm / t if (pdm is not None and t) else None,
            "minus_di": 100.0 * mdm / t if (mdm is not None and t) else None}


def _g_bb(base, x):
    if base.bb_tail is None:
        return {"bb_upper": None, "bb_lower": None, "bb_pctb": None, "bb_width": None}
    w = base.bb_tail + [x.price]
    m = sum(w) / 20.0
    sd = math.sqrt(sum((v - m) ** 2 for v in w) / 20.0)  # population sd, as TV
    up, lo = m + 2 * sd, m - 2 * sd
    return {"bb_upper": up, "bb_lower": lo, "bb_pctb": (x.price - lo) / (4 * sd) if sd else None,
            "bb_width": (4 * sd / m * 100.0) if m else None}


def _g_range(base, x):
    h52 = max(base.high_52w, x.hi) if base.high_52w is not None else None
    l52 = min(base.low_52w, x.lo) if base.low_52w is not None else None
    return {"high_52w": h52, "low_52w": l52, "from_52w_high": _pct(x.price, h52),
            "from_52w_low": _pct(x.price, l52), "high_20d": base.high_20c, "low_20d": base.low_20c}


def _g_perf(base, x):
    f = {k: _pct(x.price, ref) for k, ref in base.perf_ref.items()}
    f["chg_ytd"] = _pct(x.price, base.year_open_close)
    return f


def _g_vol(base, x):
    volume = x.volume
    f = {"avg_vol10": base.avg_vol[10], "avg_vol20": base.avg_vol[20], "avg_vol50": base.avg_vol[50]}
    av = base.avg_vol[20]
    rvol = (volume / av) if (volume is not None and av) else None
    f["rvol"] = rvol
    # time-of-day relative volume: today's volume vs. the share of an average
    # day expected by now. Linear in time, so it overstates in the first hour
    # (volume is U-shaped intraday); hidden until 5 % of the session passed.
    if rvol is not None and x.frac is not None and x.frac >= 0.05:
        f["rvol_tod"] = rvol / x.frac
    else:
        f["rvol_tod"] = rvol
    f["turnover"] = x.price * volume if volume is not None else None
    return f


GROUPS = [_g_basic, _g_sma, _g_ema, _g_rsi, _g_macd, _g_atr, _g_adx, _g_bb, _g_range, _g_perf, _g_vol]


def live(base, price, high=None, low=None, volume=None, open_=None, prev_close=None,
         session_fraction=None):
    """One live step. Returns a dict of indicator fields (values may be None)."""
    x = _Ctx(base, price, high, low, volume, open_, prev_close, session_fraction)
    f = {}
    for g in GROUPS:
        f.update(g(base, x))
    return f


def _field_groups():
    """field name -> group function, found by running each group once."""
    b = Base([("2000-01-03", 1.0, 1.0, 1.0, 1.0, 1.0)])
    x = _Ctx(b, 1.0, 1.0, 1.0, 1.0, 1.0, None, 1.0)
    return {k: g for g in GROUPS for k in g(b, x)}


FIELD_GROUP = _field_groups()


class LazyRow(dict):
    """A row whose indicator groups are computed on first `get` of one of
    their fields. A backtest rule touching rsi14 and sma200 computes 2 of the
    11 groups instead of all ~110 fields every day. Only `.get` is lazy -
    which is all the filter language and patterns.live_flags use."""
    __slots__ = ("_base", "_x", "_done")

    def __init__(self, base, price, high, low, volume, open_, session_fraction=1.0):
        super().__init__()
        self._base = base
        self._x = _Ctx(base, price, high, low, volume, open_, None, session_fraction)
        self._done = set()

    def get(self, k, default=None):
        if k in self:
            return dict.__getitem__(self, k)
        g = FIELD_GROUP.get(k)
        if g is not None and g not in self._done:
            self._done.add(g)
            self.update(g(self._base, self._x))
            return dict.get(self, k, default)
        return default
