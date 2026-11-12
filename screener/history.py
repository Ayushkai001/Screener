"""Daily OHLCV history per symbol, cached on disk, synced from Yahoo v8 chart.

data/history/<file>.json.gz = {"ysym", "fetched" (epoch), "bars": [[date,o,h,l,c,v],...]}

Bugs this module is built around:
  * Yahoo prices are split-adjusted *as of the fetch*. After a split/bonus,
    a cache from yesterday is on the old scale and every indicator (and the
    "change %") would be garbage. Incremental syncs therefore fetch 5 days and
    compare the overlap with the cache; any close that differs by more than
    1 % (median of the overlap) throws the cache away and refetches the full
    range. A single revised bar is accepted.
  * A bar fetched during the session is partial. It is never written to disk
    as a closed bar: bars dated "today" are dropped unless fetched after 16:30
    IST (the official close is a 30-min VWAP settled after 15:30, so even the
    15:30 last-traded price is not the close). Its OPEN is kept in memory
    (today_open) because spark - our live feed - does not send the open.
  * Ticker characters like & and * are fine on disk on macOS/Linux, but are
    escaped anyway so the cache works on any filesystem.
"""

import datetime
import os
import re
import threading

from . import net, yahoo
from .clock import IST, now_utc

FULL_RANGE = "2y"      # ~495 bars: enough warm-up for EMA200 / SMA200 / 52w
INCR_RANGE = "5d"
MAX_BARS = 520
MISMATCH = 0.01       # median overlap disagreement that means "re-adjusted series"
HARD_MISMATCH = 0.05  # any single bar this far off also means it
FINAL_AFTER = datetime.time(16, 30)


def _fname(ysym):
    return re.sub(r"[^A-Za-z0-9._-]", lambda m: "_%02X" % ord(m.group()), ysym) + ".json.gz"


def merge(old, new, max_bars=MAX_BARS):
    """Merge fresh bars into cached bars, keeping the last `max_bars`.
    Returns (bars, ok). ok=False means the overlap disagrees (split/bonus/data
    revision) and the caller must refetch the full range instead of trusting
    `old`. max_bars must be the store's own limit: the 10-year backtest store
    calling this with the screener's 520 would cut its history to two years."""
    if not old:
        return list(new), True
    if not new:
        return list(old), True
    cached = {b[0]: b for b in old}
    overlap = [b for b in new if b[0] in cached]
    # A split/bonus shifts *every* bar by the same factor; a one-off revision of
    # a single bar does not. Test the median so a lone revised bar is accepted
    # (taking Yahoo's new value) instead of refetching two years of history.
    devs = sorted(abs(b[4] / cached[b[0]][4] - 1) if cached[b[0]][4] > 0 else 1.0 for b in overlap)
    if devs and (devs[len(devs) // 2] > MISMATCH or devs[-1] > HARD_MISMATCH):
        return list(old), False
    if not overlap and new[0][0] > old[-1][0]:
        # a gap between cache end and fetched start: cannot tell what is missing
        return list(old), False
    first = new[0][0]
    bars = [b for b in old if b[0] < first] + list(new)
    return bars[-max_bars:], True


def drop_partial(bars, fetched_at):
    """Remove today's bar if it may still change (fetched before 16:30 IST)."""
    local = fetched_at.astimezone(IST)
    today = local.date().isoformat()
    if bars and bars[-1][0] == today and local.time() < FINAL_AFTER:
        return bars[:-1], bars[-1]
    return bars, None


class HistoryStore:
    def __init__(self, root="data/history", client=None, full_range=FULL_RANGE, max_bars=MAX_BARS):
        # The live screener keeps 2 years; the backtester's own store keeps 10
        # (data/history_bt) - two years is one market regime, too short to
        # judge a strategy on.
        self.root = root
        self.client = client
        self.full_range = full_range
        self.max_bars = max_bars
        self._bars = {}       # ysym -> list of bars (closed only)
        self._fetched = {}    # ysym -> epoch of last successful sync
        self.today_open = {}  # ysym -> (date_iso, open) from a partial bar
        self._lock = threading.Lock()
        os.makedirs(root, exist_ok=True)

    # ---- disk ---------------------------------------------------------
    def load(self, ysyms):
        n = 0
        for s in ysyms:
            doc = net.read_json(os.path.join(self.root, _fname(s)))
            if doc and isinstance(doc.get("bars"), list) and doc.get("ysym") == s:
                self._bars[s] = [tuple(b) for b in doc["bars"]]
                self._fetched[s] = doc.get("fetched", 0)
                n += 1
        return n

    def _save(self, s, bars, fetched):
        net.write_json(os.path.join(self.root, _fname(s)),
                       {"ysym": s, "fetched": fetched, "bars": [list(b) for b in bars]})

    # ---- access ---------------------------------------------------------
    def bars(self, s):
        return self._bars.get(s, ())

    def fetched(self, s):
        return self._fetched.get(s, 0)

    def has(self, s):
        return s in self._bars

    # ---- network ------------------------------------------------------
    def sync(self, s, now=None, force_full=False):
        """Bring one symbol up to date. Returns 'full' | 'incr' | raises FetchError/ValueError."""
        now = now or now_utc()
        old = self._bars.get(s)
        mode = "full" if force_full or not old else "incr"
        bars, _, _ = yahoo.parse_chart_daily(self.client.get_json(
            yahoo.chart_urls(s, self.full_range if mode == "full" else INCR_RANGE, "1d")))
        bars, partial = drop_partial([tuple(b) for b in bars], now)
        if mode == "incr":
            merged, ok = merge(old, bars, self.max_bars)
            if not ok:
                return self.sync(s, now, force_full=True)
            bars = merged
        bars = bars[-self.max_bars:]
        with self._lock:
            self._bars[s] = bars
            self._fetched[s] = int(now.timestamp())
            if partial:
                self.today_open[s] = (partial[0], partial[1])
        self._save(s, bars, int(now.timestamp()))
        return mode
