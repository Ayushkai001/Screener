"""The live engine: polls quotes, keeps history in sync, maintains screener rows.

Work is split into small tasks consumed by a few worker threads that share
one rate limiter (so the whole process is polite to Yahoo, not each thread):

  priority 0  focus batch   - symbols currently on someone's screen, every
                              `focus_interval` s (default 3 s) while open
  priority 1  sweep batch   - the whole universe, 20 per spark request,
                              a new sweep at most every `sweep_interval` s
  history sync              - one v8 daily chart per symbol, most liquid first.
                              Its own queue with a guaranteed share of the
                              request budget (`hist_share`, 1 in 5): a full
                              sweep takes longer than the sweep interval while
                              open, so strict priority would starve history
                              (no "today's open", no split resyncs) all day.

Correctness rules (each is a bug that would otherwise show up on screen):
  * Indicators are only shown when the history "base" ends on the session
    before the quote's session AND its last close agrees with the official
    previous close within 1 % (then the official close replaces the last
    bar's close). Special sessions (Muhurat) that Yahoo lacks are patched in
    from the bhavcopy first (specials.py). A mismatch means a split/bonus, a missing
    day or a revised close: the indicators are blanked and the symbol is
    queued for a resync (at most twice a day so a permanent Yahoo
    inconsistency cannot loop forever; after that the date check alone
    decides, flagged hist_ok = false).
  * A symbol Yahoo stops returning (renamed/delisted) is retried a few
    sweeps, then dropped from the sweep - counted, never silently.
  * The calendar is cross-checked against the data: "open" per calendar but
    no tick today 15 minutes after the open, or ticks on a calendar holiday,
    raises a status warning.
"""

import datetime
import collections
import heapq
import itertools
import threading
import time
import traceback

from . import history as hist_mod
from . import indicators, net, patterns, specials, yahoo
from .clock import Calendar, IST, now_utc, ts_to_date

DEFAULTS = {
    "workers": 4,
    "rate": 6.0,
    "max_rate": 10.0,
    "focus_interval": 3.0,
    "sweep_interval_open": 10.0,
    "sweep_interval_idle": 900.0,
    "sweep_interval_auction": 60.0,
    "fetch_open": True,
    "min_turnover": 0.0,
    "drop_after_misses": 3,
    "hist_share": 0.25,        # history tasks per quote task when both are waiting
    "hist_share_open": 0.5,    # ... during the first minutes of the session (the open pass)
    "open_pass_secs": 1200.0,
    "hist_retries": 3,         # transient failures (network, 5xx, 429) retried, with backoff
}
# Base vs official previous close. Yahoo's closes equal the official ones on
# regular days; anything beyond 1 % is a split/bonus/missing session.
PREV_TOL = 0.01
OFFICIAL_RETRY = 1200.0   # seconds between attempts at the evening bhavcopy


class Engine:
    def __init__(self, universe, cfg=None, calendar=None, client=None, hist_root="data/history",
                 clock=now_utc, log=print):
        self.cfg = dict(DEFAULTS, **(cfg or {}))
        self.cal = calendar or Calendar()
        self.client = client or net.Client(net.RateLimiter(rate=self.cfg["rate"], max_rate=self.cfg["max_rate"]))
        self.history = hist_mod.HistoryStore(hist_root, self.client)
        self.specials = specials.Specials(self.cal, self.client,
                                          root=hist_root.rstrip("/").rsplit("/", 1)[0] + "/special"
                                          if "/" in hist_root else "special", log=log)
        data_root = hist_root.rstrip("/").rsplit("/", 1)[0] if "/" in hist_root else "."
        self.official = specials.Official(self.client, root=data_root + "/official", log=log)
        self._official_done = None    # ISO date whose official EOD is fully loaded
        self._official_next = 0.0     # monotonic time of the next attempt
        self.clock = clock
        self.log = log
        mt = self.cfg["min_turnover"]
        self.info = {s["ysym"]: s for s in universe["symbols"] if s.get("turnover", 0) >= mt}
        self.order = sorted(self.info, key=lambda y: -self.info[y].get("turnover", 0))
        self.quotes = {}
        self.rows = {}
        self._bases = {}           # ysym -> (key, Base, static, hist_ok, note)
        self.misses = {}
        self.dropped = set()
        self.resyncs = {}          # ysym -> (date, count)
        self.focus = {}            # ysym -> expiry (monotonic)
        self.version = 0
        self.changed = threading.Condition()
        self._lock = threading.RLock()
        self._tasks = []           # heap of (prio, seq, kind, payload): quote work
        self._hist_tasks = collections.deque()
        self._hist_credit = 0.0
        self._due_checked = None   # IST date of the last "which caches are behind" pass
        self._seq = itertools.count()
        self._queued_hist = set()
        self._inflight = 0
        self._sweep_left = 0
        self._last_sweep = 0.0
        self._last_focus = 0.0
        self._open_synced = None   # date for which the "today's open" pass ran
        self._open_pass_until = 0.0   # monotonic: history gets a bigger share until then
        self._hist_retry = {}         # ysym -> (due monotonic, attempt)
        self._stop = threading.Event()
        self.stats = {"sweeps": 0, "sweep_secs": None, "last_sweep_end": None, "hist_synced": 0,
                      "hist_failed": 0, "quote_batches": 0, "quote_failed": 0, "errors": []}
        self._sweep_started = None

    # ---- lifecycle ----------------------------------------------------
    def start(self):
        n = self.history.load(self.order)
        self.log("history cache: %d of %d symbols" % (n, len(self.order)))
        try:
            self.specials.load_all(self.clock().astimezone(IST).date())
        except Exception:
            self._error("specials", traceback.format_exc())
        self._queue_history_due()
        self._due_checked = self.clock().astimezone(IST).date()
        for i in range(self.cfg["workers"]):
            threading.Thread(target=self._worker, name="worker-%d" % i, daemon=True).start()
        threading.Thread(target=self._scheduler, name="scheduler", daemon=True).start()

    def stop(self):
        self._stop.set()

    # ---- scheduling ----------------------------------------------------
    def market_state(self):
        return self.cal.state(self.clock())

    def _sweep_interval(self, state):
        if state == "open":
            return self.cfg["sweep_interval_open"]
        if state in ("pre_open", "post_close"):
            return self.cfg["sweep_interval_auction"]
        return self.cfg["sweep_interval_idle"]

    def _push(self, prio, kind, payload):
        heapq.heappush(self._tasks, (prio, next(self._seq), kind, payload))

    def _scheduler(self):
        while not self._stop.is_set():
            try:
                self._schedule_once()
            except Exception:  # never let the scheduler die
                self._error("scheduler", traceback.format_exc())
            self._stop.wait(0.25)

    def _schedule_once(self):
        now_m = time.monotonic()
        state = self.market_state()
        with self._lock:
            # full sweep
            if self._sweep_left == 0 and now_m - self._last_sweep >= self._sweep_interval(state):
                syms = [s for s in self.order if s not in self.dropped]
                batches = [syms[i:i + yahoo.SPARK_MAX] for i in range(0, len(syms), yahoo.SPARK_MAX)]
                for b in batches:
                    self._push(1, "sweep", b)
                self._sweep_left = len(batches)
                self._last_sweep = now_m
                self._sweep_started = now_m
            # focus
            if state == "open" and now_m - self._last_focus >= self.cfg["focus_interval"]:
                live = [s for s, exp in self.focus.items() if exp > now_m and s in self.info]
                for s in [s for s, exp in self.focus.items() if exp <= now_m]:
                    del self.focus[s]
                live = live[:200]
                for i in range(0, len(live), yahoo.SPARK_MAX):
                    self._push(0, "focus", live[i:i + yahoo.SPARK_MAX])
                self._last_focus = now_m
        # once per day after the open: refetch daily bars to learn today's open
        today = self.clock().astimezone(IST).date()
        if (self.cfg["fetch_open"] and state == "open" and self._open_synced != today
                and self.clock().astimezone(IST).time() >= datetime.time(9, 16)):
            self._open_synced = today
            # every stock's open, most traded first: the gap filters are
            # most wanted right at the open, so history gets a bigger share
            self._open_pass_until = time.monotonic() + self.cfg["open_pass_secs"]
            for s in self.order:
                self.queue_history(s, force=True)
        # once per day after the close (bars final at 16:30): catch up every cache,
        # so a server left running overnight starts tomorrow with complete history
        local = self.clock().astimezone(IST)
        if self._due_checked != local.date() and local.time() >= datetime.time(16, 45):
            self._due_checked = local.date()
            self._queue_history_due()
        # official end-of-day numbers for the last completed session: tried
        # until both bhavcopies are out (~18:00 IST), every 20 min
        last = self.cal.last_completed_session(self.clock())
        if last.isoformat() != self._official_done and now_m >= self._official_next:
            self._official_next = now_m + OFFICIAL_RETRY
            with self._lock:
                self._push(1, "official", last)
        with self._lock:
            due = [s for s, (t, _) in self._hist_retry.items() if t <= now_m and s not in self._queued_hist]
        for s in due:
            self.queue_history(s, force=True)
            with self._lock:     # keep the attempt count; just not due again until it fails again
                t, n = self._hist_retry.get(s, (0, 0))
                self._hist_retry[s] = (float("inf"), n)
        self._calendar_check(state)

    def queue_history(self, s, force=False):
        with self._lock:
            if s in self._queued_hist:
                return
            if not force and self.history.has(s):
                return
            self._queued_hist.add(s)
            self._hist_tasks.append((2, 0, "hist", s))

    def _queue_history_due(self):
        """Symbols with no cache, or a cache older than the last completed session."""
        last = self.cal.last_completed_session(self.clock()).isoformat()
        for s in self.order:
            bars = self.history.bars(s)
            if not bars or bars[-1][0] < last:
                self.queue_history(s, force=True)

    def _next_task(self):
        with self._lock:
            if self._hist_tasks and (not self._tasks or self._hist_credit >= 1.0):
                self._hist_credit = max(0.0, self._hist_credit - 1.0)
                self._inflight += 1
                t = self._hist_tasks.popleft()
                # un-mark now, not when the task ends: the task itself may
                # re-queue the symbol (second resync), which must not be ignored
                self._queued_hist.discard(t[3])
                return t
            if self._tasks:
                if self._hist_tasks:
                    self._hist_credit += (self.cfg["hist_share_open"]
                                          if time.monotonic() < self._open_pass_until else self.cfg["hist_share"])
                self._inflight += 1
                return heapq.heappop(self._tasks)
        return None

    def _worker(self):
        while not self._stop.is_set():
            t = self._next_task()
            if t is None:
                self._stop.wait(0.2)
                continue
            prio, _, kind, payload = t
            try:
                if kind in ("sweep", "focus"):
                    self._do_quotes(payload)
                elif kind == "hist":
                    self._do_history(payload)
                elif kind == "official":
                    self._do_official(payload)
            except Exception:
                self._error(kind, traceback.format_exc())
            finally:
                with self._lock:
                    self._inflight -= 1
                    if kind == "sweep":
                        self._sweep_left -= 1
                        if self._sweep_left == 0:
                            self.stats["sweeps"] += 1
                            self.stats["sweep_secs"] = round(time.monotonic() - self._sweep_started, 1)
                            self.stats["last_sweep_end"] = int(time.time())

    def _error(self, where, msg):
        line = msg.strip().splitlines()[-1] if msg else where
        errs = self.stats["errors"]
        errs.append({"t": int(time.time()), "where": where, "msg": line[:300]})
        del errs[:-20]

    # ---- work ----------------------------------------------------------
    def _do_quotes(self, batch):
        self.stats["quote_batches"] += 1
        try:
            got = yahoo.parse_spark(self.client.get_json(yahoo.spark_urls(batch, "1d", "1d")))
        except (net.FetchError, ValueError) as e:
            self.stats["quote_failed"] += 1
            self._error("quotes", str(e))
            return
        changed = False
        for s in batch:
            q = got.get(s)
            if q is None:
                n = self.misses.get(s, 0) + 1
                self.misses[s] = n
                if n >= self.cfg["drop_after_misses"]:
                    self.dropped.add(s)
                continue
            self.misses.pop(s, None)
            old = self.quotes.get(s)
            if old and old["time"] == q["time"] and old["price"] == q["price"] and old["volume"] == q["volume"]:
                continue
            with self._lock:
                self.quotes[s] = q
            self._recompute(s)
            changed = True
        if changed:
            self._bump()

    def _do_history(self, s):
        try:
            self.history.sync(s, self.clock())
            self.stats["hist_synced"] += 1
        except (net.FetchError, ValueError) as e:
            self.stats["hist_failed"] += 1
            status = getattr(e, "status", None)
            if status != 404:
                self._error("history " + s, str(e))
            # A network blip (seen live: DNS failures for a minute at 09:57)
            # must not cost a stock its open / fresh history for the whole
            # day: transient failures retry after 30 s, 60 s, 90 s.
            transient = isinstance(e, net.FetchError) and (status is None or status == 429 or status >= 500)
            with self._lock:
                n = self._hist_retry.get(s, (0, 0))[1] + 1
                if transient and n <= self.cfg["hist_retries"]:
                    self._hist_retry[s] = (time.monotonic() + 30.0 * n, n)
            return
        with self._lock:
            self._hist_retry.pop(s, None)
            self._bases.pop(s, None)
        if s in self.quotes:
            self._recompute(s)
            self._bump()

    def _do_official(self, d):
        key = d.isoformat()
        before = self.official.get(key)
        complete = self.official.load(d)
        if complete:
            self._official_done = key
        doc = self.official.get(key)
        if doc and doc is not before:
            n = 0
            for s in list(self.quotes):
                if s in doc and ts_to_date(self.quotes[s]["time"]).isoformat() == key:
                    self._recompute(s)
                    n += 1
            if n:
                self.log("official EOD %s applied to %d rows" % (key, n))
                self._bump()

    def _bump(self):
        with self.changed:
            self.version += 1
            self.changed.notify_all()

    # ---- rows ----------------------------------------------------------
    def _base_for(self, s, q):
        """(Base, static, hist_ok, note) for the quote's session, cached."""
        session = ts_to_date(q["time"]).isoformat()
        key = (session, self.history.fetched(s))
        cached = self._bases.get(s)
        if cached and cached[0] == key:
            return cached[1:]
        bars = self.specials.patch(s, [b for b in self.history.bars(s) if b[0] < session])
        if not bars:
            res = (None, {}, False, "no history")
        else:
            pc = q.get("prev_close")
            raw_last = bars[-1][4]
            base = indicators.Base(bars, pc if pc and abs(raw_last / pc - 1) <= PREV_TOL else None)
            base.raw_prev_close = raw_last
            st = patterns.static(bars)
            ok, note = self._validate(s, base, q, session)
            res = (base, st, ok, note)
        self._bases[s] = (key,) + res
        return res

    def _validate(self, s, base, q, session):
        pc = q.get("prev_close")
        d = ts_to_date(q["time"])
        try:
            expected_last = self.cal.prev_trading_day(d).isoformat()
        except ValueError:
            expected_last = None
        date_ok = base.last_date == expected_last or (expected_last and not self.cal.year_known(d))
        raw = getattr(base, "raw_prev_close", base.prev_close)
        # The official previous close is the strong check: if our last close
        # equals it, the history is consistent even when the last bar's date is
        # older (an illiquid stock with no trade in the Muhurat session has no
        # bar for it anywhere). The date decides only when there is no
        # official previous close in the quote.
        if pc is not None:
            if raw and abs(raw - pc) / pc <= PREV_TOL:
                return True, ""
        elif date_ok:
            return True, ""
        today = self.clock().astimezone(IST).date().isoformat()
        day, count = self.resyncs.get(s, (today, 0))
        if day != today:
            count = 0
        if count < 2:
            self.resyncs[s] = (today, count + 1)
            self.queue_history(s, force=True)
            return False, "history out of date, resyncing"
        if pc is not None:
            # still disagrees after two fresh fetches: a corporate action Yahoo
            # has not applied, or a bad Yahoo series. Blank rather than mislead.
            return False, "history close %.2f disagrees with official prev close %.2f" % (raw, pc)
        return False, "history ends %s, expected %s" % (base.last_date, expected_last)

    def _recompute(self, s):
        with self._lock:
            q = self.quotes[s]
        info = self.info[s]
        base, st, ok, note = self._base_for(s, q)
        session = ts_to_date(q["time"]).isoformat()
        to = self.history.today_open.get(s)
        open_ = to[1] if to and to[0] == session else None
        if open_ is None:
            # After the close the session's full bar is in the history (spark
            # quotes carry no open at all): take the open from it.
            hb = self.history.bars(s)
            if hb and hb[-1][0] == session:
                open_ = hb[-1][1]
        price = q["price"]
        high, low, volume = q.get("day_high"), q.get("day_low"), q.get("volume")
        # After the bhavcopy is out, the exchange's own numbers win - but only
        # when the quote IS the final close (a live quote is never overridden).
        off = self.official.get(session)
        orow = off.get(s) if off else None
        official = bool(orow) and abs(price / orow[3] - 1) <= 0.0005
        if official:
            open_, high, low, price, volume = orow[0], orow[1], orow[2], orow[3], orow[4]
        row = {
            "ysym": s, "sym": info["sym"], "name": q.get("name") or info.get("name", ""),
            "exchange": info["exchange"], "series": info.get("series", ""),
            "industry": info.get("industry", ""), "indices": info.get("indices", []),
            "price": price, "open": open_, "high": high, "low": low,
            "volume": volume, "time": q["time"], "session": session, "official_eod": official,
            "hist_ok": ok, "note": note, "hist_days": base.n if base else 0,
        }
        frac = self.cal.session_fraction(self.clock()) if session == self.clock().astimezone(IST).date().isoformat() else 1.0
        if base is not None and ok:
            f = indicators.live(base, price, high, low, volume, open_, q.get("prev_close"), frac)
            row.update(f)
            row["prev_volume"] = base.prev_volume
            row.update(patterns.live_flags(st, f, price, volume))
        else:
            pc = q.get("prev_close")
            row["prev_close"] = pc
            row["change"] = price - pc if pc else None
            row["change_pct"] = (price / pc - 1) * 100 if pc else None
            row["turnover"] = price * volume if volume is not None else None
            row["gap_pct"] = (open_ / pc - 1) * 100 if (pc and open_) else None
        with self._lock:   # readers copy under the same lock: no resize mid-iteration
            self.rows[s] = row

    # ---- read side ---------------------------------------------------------
    def snapshot(self):
        now = time.time()
        with self._lock:
            rows = list(self.rows.values())
        out = []
        for r in rows:
            r = dict(r)
            r["age"] = int(now - r["time"])
            out.append(r)
        return out

    def set_focus(self, ysyms, ttl=15.0):
        exp = time.monotonic() + ttl
        with self._lock:
            for s in ysyms:
                self.focus[s] = exp

    def wait_change(self, version, timeout):
        with self.changed:
            if self.version == version:
                self.changed.wait(timeout)
            return self.version

    def _calendar_check(self, state):
        now = self.clock().astimezone(IST)
        self.calendar_warning = None
        if not self.quotes:
            return
        with self._lock:
            latest = max(q["time"] for q in self.quotes.values())
        latest_day = ts_to_date(latest)
        if state == "open" and now.time() >= datetime.time(9, 30) and latest_day < now.date() \
                and self.stats["sweeps"] > 0:
            self.calendar_warning = ("Calendar says the market is open, but no symbol has a tick today. "
                                     "Unlisted holiday or data outage?")
        elif state in ("holiday", "weekend") and latest_day == now.date():
            self.calendar_warning = ("Ticks are arriving on a day the calendar marks closed - "
                                     "special session? Add it to data/holidays.json.")

    def status(self):
        now = self.clock()
        with self._lock:
            hist_q = len(self._queued_hist)
            rows = len(self.rows)
            ok = sum(1 for r in self.rows.values() if r.get("hist_ok"))
        return {
            "now": now.astimezone(IST).isoformat(timespec="seconds"),
            "market": self.market_state(),
            "universe": len(self.info),
            "quoted": rows,
            "with_indicators": ok,
            "dropped": len(self.dropped),
            "history_queue": hist_q,
            "rate": round(self.client.limiter.rate, 2),
            "limiter": dict(self.client.limiter.stats),
            "version": self.version,
            "calendar_warning": getattr(self, "calendar_warning", None),
            **{k: v for k, v in self.stats.items() if k != "errors"},
            "errors": self.stats["errors"][-5:],
        }
