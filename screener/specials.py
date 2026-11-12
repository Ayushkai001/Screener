"""Bars for special sessions (Muhurat trading, Budget-day Sundays) that Yahoo
does not carry, taken from the official NSE/BSE bhavcopy of that date.

Why it matters: after Muhurat (Sunday 2026-11-08) the official previous close
of every stock on Monday is the Muhurat close. Without the bar, change % is
right (it uses the official previous close) but every indicator's "previous
day" is the Friday, and the history/quote consistency check fails for every
symbol that moved during the session.

Split safety: bhavcopy prices are unadjusted, Yahoo's are split-adjusted as of
the fetch. Each special bar is rescaled by
    factor = Yahoo close of the session before / bhavcopy PrvsClsgPric
so a split after the special session cannot put this one bar on the old scale.
Factors within 15 % of 1 are ignored (stale Yahoo closes on illiquid BSE names,
not splits).

Cache: data/special/<date>.json.gz = {ysym: [o, h, l, c, v, prev_close]}
"""

import datetime
import os

from . import net, universe

# Suffixes mapping exchange names to Yahoo symbol identifiers
EXT = {"NSE": ".NS", "BSE": ".BO"}


def _f(x):
    """Safely cast value to float, defaulting to 0.0 on missing or invalid entries."""
    try:
        return float(x)
    except (TypeError, ValueError):
        return 0.0


def parse(nse_rows, bse_rows):
    """Parse raw Bhavcopy CSV rows into a mapping of {yahoo_symbol: [open, high, low, close, volume, prev_close]}.

    Rationale:
    1. Only 'STK' instrument types are processed, filtering out bonds and indices.
    2. BSE rows are processed first, then NSE rows. For dual-listed stocks, NSE rows
       overwrite BSE rows so the National Stock Exchange price wins on conflicts.
    3. Low price calculation protects against zero-value reporting: min of non-zero entries.
    """
    out = {}
    for exch, rows in (("BSE", bse_rows), ("NSE", nse_rows)):   # NSE last: wins on conflicts
        for r in rows:
            if r.get("FinInstrmTp") != "STK":
                continue
            o, h, l, c = (_f(r.get(k)) for k in ("OpnPric", "HghPric", "LwPric", "ClsPric"))
            pc = _f(r.get("PrvsClsgPric"))
            # Require positive close and previous close to be considered valid
            if c <= 0 or pc <= 0:
                continue
            out[r["TckrSymb"] + EXT[exch]] = [
                o or c,
                max(h, o, c),
                min(x for x in (l, o, c) if x > 0),
                c,
                _f(r.get("TtlTradgVol")),
                pc
            ]
    return out


def fetch_day(client, d, log=print, what="bhavcopy"):
    """Fetch both NSE and BSE official Bhavcopy rows for a given calendar date `d`.

    Returns:
        (nse_rows, bse_rows)

    Rationale:
    Exchanges publish Bhavcopy archives independently. If one exchange's file is not yet
    available (e.g. BSE delayed upload), it returns an empty list without failing the entire call.
    """
    key, stamp = d.isoformat(), d.strftime("%Y%m%d")
    try:
        nse = universe._rows(universe._decode(net.unzip_single(client.get(universe.NSE_BHAV % stamp))))
        if nse and "TckrSymb" not in nse[0]:
            nse = []
    except net.FetchError as e:
        log("%s %s: NSE bhavcopy unavailable (%s)" % (what, key, e))
        nse = []
    try:
        bse = universe._rows(universe._decode(client.get(universe.BSE_BHAV % stamp, headers=universe.BSE_HEADERS)))
        if bse and "TckrSymb" not in bse[0]:
            bse = []
    except net.FetchError as e:
        log("%s %s: BSE bhavcopy unavailable (%s)" % (what, key, e))
        bse = []
    return nse, bse


class Official:
    """Official end-of-day numbers for regular sessions, sourced from official Bhavcopies.

    Rationale:
    1. Volume Accuracy: Yahoo's free quote endpoints under-report traded volume for ~2% of
       Indian equities (e.g., BLUEJET on 2026-11-09 recorded 697k on Yahoo vs 1.6M on official bhavcopy).
       Replacing volume with official exchange data ensures relative volume (rvol) and
       Double Bottom volume confirmation are 100% accurate.
    2. Overwrites Only When Final: The override is applied only when the quote price matches
       the day's official close, guaranteeing that active intraday quotes are never overwritten.
    3. Distinct from Specials: These dates already exist in Yahoo's history; they are applied
       to live rows as metadata corrections rather than inserted as extra history bars.
    """

    def __init__(self, client, root="data/official", log=print, keep=10):
        self.client = client
        self.root = root
        self.log = log
        self.keep = keep
        self._days = {}  # date_iso -> {ysym: [o, h, l, c, v, prev_close]}

    def get(self, key):
        """Retrieve cached official session data for an ISO date string."""
        return self._days.get(key)

    def load(self, d):
        """Load from disk cache or fetch from exchange Bhavcopies.
        
        Returns True once both NSE and BSE data are successfully downloaded and cached.
        """
        key = d.isoformat()
        path = os.path.join(self.root, key + ".json.gz")
        doc = net.read_json(path)
        if doc is not None:
            self._days[key] = doc
            return True
        nse, bse = fetch_day(self.client, d, self.log, "official EOD")
        doc = parse(nse, bse)
        if doc:
            self._days[key] = doc
        if nse and bse:
            net.write_json(path, doc)
            self.log("official EOD %s: %d symbols from the bhavcopies" % (key, len(doc)))
            self._prune()
            return True
        return False

    def _prune(self):
        """Retain only the last `keep` (10) official EOD files on disk and in memory.
        
        Rationale:
        Only recent sessions are needed for live row corrections. Pruning prevents
        unbounded disk storage growth.
        """
        try:
            files = sorted(f for f in os.listdir(self.root) if f.endswith(".json.gz"))
        except OSError:
            return
        for f in files[:-self.keep]:
            try:
                os.remove(os.path.join(self.root, f))
            except OSError:
                pass
        for k in sorted(self._days)[:-self.keep]:
            del self._days[k]


class Specials:
    """Manages injection of special session bars (e.g. Diwali Muhurat) missing from Yahoo.

    Rationale:
    Yahoo completely omits bars for 1-hour holiday trading sessions (Muhurat).
    However, on the subsequent regular trading session, the exchange's official previous close
    is the Muhurat close. By reading the official Bhavcopy and patching the missing bar into
    the symbol's historical series, all technical indicators remain mathematically continuous.
    """

    def __init__(self, calendar, client, root="data/special", log=print):
        self.cal = calendar
        self.client = client
        self.root = root
        self.log = log
        self._days = {}  # date_iso -> {ysym: [o, h, l, c, v, pc]}

    def load_all(self, today):
        """Pre-load/cache all special sessions occurring within the 2-year history window."""
        lo = today - datetime.timedelta(days=750)
        for d in sorted(self.cal.special):
            if lo <= d < today:  # today's bhavcopy is not published until evening
                self._load(d)

    def _load(self, d):
        """Load single special session date from cache or fetch from Bhavcopy."""
        key = d.isoformat()
        if key in self._days:
            return self._days[key]
        path = os.path.join(self.root, key + ".json.gz")
        doc = net.read_json(path)
        if doc is None:
            nse, bse = fetch_day(self.client, d, self.log, "special session")
            doc = parse(nse, bse)
            if doc:
                net.write_json(path, doc)
                self.log("special session %s: %d bars from the bhavcopy" % (key, len(doc)))
        self._days[key] = doc or {}
        return self._days[key]

    def patch(self, ysym, bars):
        """Insert missing special-session bars into a symbol's historical series, with split adjustment.

        Rationale:
        1. Pure function on inputs: returns a new sorted list of bars.
        2. Split-Adjustment Factor (k):
           Bhavcopy prices are raw/unadjusted; Yahoo prices are split-adjusted.
           If a stock had a 2-for-1 split after Muhurat, Yahoo's pre-Muhurat bar is adjusted by 0.5,
           while the Bhavcopy bar is unadjusted.
           We compute `k = before[-1][4] / pc` (ratio of Yahoo's prior close to the Bhavcopy previous close).
           Rescaling the Bhavcopy bar by `k` aligns it precisely with Yahoo's split-adjusted scale.
        3. Noise threshold:
           If `abs(k - 1) < 0.15`, the discrepancy is caused by minor illiquid price rounding,
           not a corporate action split (which are typically 1:2, 1:5, 1:10). We set k = 1.0
           to avoid distorting un-split stocks.
        """
        if not bars or not self._days:
            return bars
        have = {b[0] for b in bars}
        extra = []
        for key, day in self._days.items():
            row = day.get(ysym)
            # Skip if symbol was not traded, bar already exists, or session is older than history
            if row is None or key in have or not (bars[0][0] < key):
                continue
            before = [b for b in bars if b[0] < key]
            if not before:
                continue
            o, h, l, c, v, pc = row
            # Calculate split adjustment ratio
            k = before[-1][4] / pc
            if not 0.02 < k < 50:  # Safety check against absurd ratios (different instruments)
                continue
            # If deviation is less than 15%, treat as normal price drift rather than a corporate split
            if abs(k - 1) < 0.15:
                k = 1.0
            extra.append((key, o * k, h * k, l * k, c * k, v / k))
        if not extra:
            return bars
        return sorted(list(bars) + extra, key=lambda b: b[0])
