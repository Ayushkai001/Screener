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

EXT = {"NSE": ".NS", "BSE": ".BO"}


def _f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return 0.0


def parse(nse_rows, bse_rows):
    out = {}
    for exch, rows in (("BSE", bse_rows), ("NSE", nse_rows)):   # NSE last: wins on conflicts
        for r in rows:
            if r.get("FinInstrmTp") != "STK":
                continue
            o, h, l, c = (_f(r.get(k)) for k in ("OpnPric", "HghPric", "LwPric", "ClsPric"))
            pc = _f(r.get("PrvsClsgPric"))
            if c <= 0 or pc <= 0:
                continue
            out[r["TckrSymb"] + EXT[exch]] = [o or c, max(h, o, c), min(x for x in (l, o, c) if x > 0),
                                             c, _f(r.get("TtlTradgVol")), pc]
    return out


def fetch_day(client, d, log=print, what="bhavcopy"):
    """Both exchanges' bhavcopy rows for date d; an exchange not (yet)
    published comes back as []."""
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
    """Official end-of-day numbers for a regular session, from that day's
    bhavcopies (published around 18:00 IST).

    Why: Yahoo's volume is right for ~98 % of symbols, but on 2026-11-09 it
    was short by more than 5 % for 46 of them in the daily bar (several
    showed 0) and for 23 in the live quote (BLUEJET: 697,427 vs 1,597,985
    official - the quote stopped counting mid-session). Volume feeds relative
    volume, turnover and the double-bottom confirmation, so once the
    exchange's own numbers exist they replace Yahoo's for that session.

    Kept apart from Specials on purpose: these days are NOT history bars to
    insert (Yahoo has them); inserting the current session would double it.
    Cache: data/official/<date>.json.gz, written only when both exchanges are in.
    """

    def __init__(self, client, root="data/official", log=print, keep=10):
        self.client = client
        self.root = root
        self.log = log
        self.keep = keep
        self._days = {}

    def get(self, key):
        """{ysym: [o, h, l, c, v, prev_close]} for an ISO date, or None. Memory only."""
        return self._days.get(key)

    def load(self, d):
        """Cache or fetch. Returns True once both exchanges are in."""
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
    def __init__(self, calendar, client, root="data/special", log=print):
        self.cal = calendar
        self.client = client
        self.root = root
        self.log = log
        self._days = {}       # date_iso -> {ysym: bar} (empty dict = unavailable)

    def load_all(self, today):
        """Fetch/cache every special session up to `today` that is within the
        last two years (history depth)."""
        lo = today - datetime.timedelta(days=750)
        for d in sorted(self.cal.special):
            if lo <= d < today:   # today's bhavcopy is not out until the evening
                self._load(d)

    def _load(self, d):
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
        """Insert special-session bars missing from Yahoo's `bars`. Pure on
        inputs; returns a new list (or the same one when nothing applies)."""
        if not bars or not self._days:
            return bars
        have = {b[0] for b in bars}
        extra = []
        for key, day in self._days.items():
            row = day.get(ysym)
            if row is None or key in have or not (bars[0][0] < key):
                continue
            before = [b for b in bars if b[0] < key]
            if not before:
                continue
            o, h, l, c, v, pc = row
            k = before[-1][4] / pc
            if not 0.02 < k < 50:          # nonsense ratio: different instrument / bad data
                continue
            # Only a real split/bonus (1/2, 1/3, 1/10...) moves k far from 1. A
            # small k is Yahoo's stale close on an illiquid stock (WESTLEIRES:
            # 80.15 on Yahoo vs 84.15 official): rescaling would corrupt the bar.
            if abs(k - 1) < 0.15:
                k = 1.0
            extra.append((key, o * k, h * k, l * k, c * k, v / k))
        if not extra:
            return bars
        return sorted(list(bars) + extra, key=lambda b: b[0])
