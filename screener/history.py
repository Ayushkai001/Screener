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
INCR_RANGE = "5d"      # 5 days overlap: enough to bridge weekends and test split consistency
MAX_BARS = 520         # 2 years of trading sessions
MISMATCH = 0.01        # median overlap disagreement (1%) that signals a corporate split/bonus
HARD_MISMATCH = 0.05   # any single bar exceeding 5% deviation also signals an unadjusted split
FINAL_AFTER = datetime.time(16, 30)  # time after which today's bar is finalized on exchanges


def _fname(ysym):
    """Sanitize symbol name into a safe, cross-platform filename.
    
    Rationale:
    Indian tickers like 'M&M.NS' contain '&', and symbols on some platforms contain '*'.
    While Unix allows most characters in filenames, Windows and FAT32/exFAT drives reject
    reserved characters. Hex-encoding special characters ensures portable, safe cache filenames.
    """
    return re.sub(r"[^A-Za-z0-9._-]", lambda m: "_%02X" % ord(m.group()), ysym) + ".json.gz"


def merge(old, new, max_bars=MAX_BARS):
    """Merge newly fetched bars into existing cached history, verifying split scale consistency.

    Returns:
        (bars, ok): Merged bar list, and a boolean indicating whether the merge was valid.
                    If ok=False, a split/bonus occurred and the caller must trigger a full refetch.

    Rationale:
    1. Split Detection: When a company issues a 2-for-1 stock split or 1-for-1 bonus,
       Yahoo adjusts *all past historical prices* down by 50%. If we simply appended today's
       new half-price bars to yesterday's unadjusted cache, the chart would show a fake -50% crash,
       ruining SMA200, RSI, and support levels.
    2. Median Overlap Test: We compare the overlapping bars between cache and fetch.
       Checking the *median* deviation rather than max deviation ensures that a legitimate single-bar
       data revision by the exchange does not trigger an unnecessary full 2-year refetch.
    3. Gap Detection: If the engine was offline for weeks and the 5-day fetch has no overlap
       with the old cache, we cannot guarantee continuity and must force a full refetch.
    4. Configurable max_bars: Allows the backtester to retain 10 years of history while the live
       screener keeps 2 years without truncating backtest data.
    """
    if not old:
        return list(new), True
    if not new:
        return list(old), True
    cached = {b[0]: b for b in old}
    overlap = [b for b in new if b[0] in cached]

    # Calculate price deviation on overlapping sessions
    devs = sorted(abs(b[4] / cached[b[0]][4] - 1) if cached[b[0]][4] > 0 else 1.0 for b in overlap)
    if devs and (devs[len(devs) // 2] > MISMATCH or devs[-1] > HARD_MISMATCH):
        return list(old), False

    # If the new bars start strictly after the cache ends with zero overlap, a gap exists
    if not overlap and new[0][0] > old[-1][0]:
        return list(old), False

    # Splice older cached bars with fresh incoming bars
    first = new[0][0]
    bars = [b for b in old if b[0] < first] + list(new)
    return bars[-max_bars:], True


def drop_partial(bars, fetched_at):
    """Strip incomplete intraday bar from historical series if fetched before 16:30 IST.

    Returns:
        (closed_bars, partial_bar)

    Rationale:
    Indian markets close at 15:30 IST, but the official closing price is a volume-weighted average (VWAP)
    calculated between 15:00 and 15:30 that is only finalized and disseminated around 16:15-16:30 IST.
    Writing today's bar to disk before 16:30 would permanently store a mid-session price as the closed bar.
    However, we keep the partial bar's OPEN in memory because Yahoo's live spark feed omits open prices.
    """
    local = fetched_at.astimezone(IST)
    today = local.date().isoformat()
    if bars and bars[-1][0] == today and local.time() < FINAL_AFTER:
        return bars[:-1], bars[-1]
    return bars, None


class HistoryStore:
    """Thread-safe disk cache and memory store for daily OHLCV equity bars.
    
    Rationale:
    Screening 4,600 symbols in real-time requires instant memory access to 2 years of daily bars.
    Loading from disk at startup and persisting incremental updates ensures sub-millisecond
    indicator recalculations without continuous heavy API calls.
    """
    def __init__(self, root="data/history", client=None, full_range=FULL_RANGE, max_bars=MAX_BARS):
        # Rationale: Live screener needs 2 years (enough for SMA200 and 52W stats);
        # backtester can initialize with 10 years (data/history_bt) for multi-cycle testing.
        self.root = root
        self.client = client
        self.full_range = full_range
        self.max_bars = max_bars
        self._bars = {}       # ysym -> list of bars (closed only)
        self._fetched = {}    # ysym -> epoch timestamp of last successful sync
        self.today_open = {}  # ysym -> (date_iso, open) extracted from partial live bars
        self._lock = threading.Lock()
        os.makedirs(root, exist_ok=True)

    # ---- Disk Persistence ----
    def load(self, ysyms):
        """Pre-load historical bars from disk cache into memory at startup.
        
        Rationale:
        Allows the screener to become functional immediately upon launch without
        waiting for thousands of network requests.
        """
        n = 0
        for s in ysyms:
            doc = net.read_json(os.path.join(self.root, _fname(s)))
            if doc and isinstance(doc.get("bars"), list) and doc.get("ysym") == s:
                self._bars[s] = [tuple(b) for b in doc["bars"]]
                self._fetched[s] = doc.get("fetched", 0)
                n += 1
        return n

    def _save(self, s, bars, fetched):
        """Atomically persist symbol history to gzipped JSON on disk."""
        net.write_json(os.path.join(self.root, _fname(s)),
                       {"ysym": s, "fetched": fetched, "bars": [list(b) for b in bars]})

    # ---- Fast Memory Access ----
    def bars(self, s):
        """Return tuple of closed daily bars for symbol `s`."""
        return self._bars.get(s, ())

    def fetched(self, s):
        """Return epoch timestamp when symbol `s` was last synced."""
        return self._fetched.get(s, 0)

    def has(self, s):
        """Check if symbol `s` is present in the in-memory cache."""
        return s in self._bars

    # ---- Network Synchronization ----
    def sync(self, s, now=None, force_full=False):
        """Synchronize history for symbol `s` against Yahoo Finance v8 chart.
        
        Rationale:
        - If cached: requests an incremental 5-day range to minimize payload size and rate limits.
        - Split validation: if merge() detects a price mismatch in overlapping bars, automatically
          falls back to a full 2-year range fetch (force_full=True).
        - Saves 'today_open' in memory so gap calculations work during market hours.
        """
        now = now or now_utc()
        old = self._bars.get(s)
        mode = "full" if force_full or not old else "incr"
        # Query v8 chart endpoint
        bars, _, _ = yahoo.parse_chart_daily(self.client.get_json(
            yahoo.chart_urls(s, self.full_range if mode == "full" else INCR_RANGE, "1d")))
        # Drop today's bar if fetched before market session settles at 16:30 IST
        bars, partial = drop_partial([tuple(b) for b in bars], now)
        if mode == "incr":
            merged, ok = merge(old, bars, self.max_bars)
            # If scale mismatch or gap detected, refetch entire history from scratch
            if not ok:
                return self.sync(s, now, force_full=True)
            bars = merged
        bars = bars[-self.max_bars:]
        # Update thread-safe memory state
        with self._lock:
            self._bars[s] = bars
            self._fetched[s] = int(now.timestamp())
            if partial:
                self.today_open[s] = (partial[0], partial[1])
        # Persist updated history to disk cache
        self._save(s, bars, int(now.timestamp()))
        return mode
