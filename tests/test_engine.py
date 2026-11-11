"""Engine + server integration, offline (fake Yahoo client fed from fixtures)."""

import datetime
import gzip
import json
import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from screener import engine, history, net, server, yahoo  # noqa: E402
from screener.clock import IST, Calendar  # noqa: E402

FIX = os.path.join(ROOT, "tests", "fixtures")


def fixture(name):
    with open(os.path.join(FIX, name), "rb") as f:
        return json.loads(gzip.decompress(f.read()))


class FakeClient:
    """Answers spark from the 2026-11-09 fixture and v8 charts from fixtures."""

    def __init__(self):
        self.limiter = net.RateLimiter(rate=1e6, cooldown=0)
        self.spark = fixture("spark_2026-11-09.json.gz")
        self.calls = []

    def get_json(self, urls, headers=None):
        url = urls[0] if isinstance(urls, list) else urls
        self.calls.append(url)
        if "/v7/finance/spark" in url:
            return self.spark
        if "/v8/finance/chart/" in url:
            sym = url.split("/v8/finance/chart/")[1].split("?")[0].replace("%26", "_26")
            path = os.path.join(FIX, "chart_%s_2y.json.gz" % sym)
            if not os.path.exists(path):
                raise net.FetchError("404", 404)
            return fixture(os.path.basename(path))
        raise net.FetchError("404", 404)

    def get(self, *a, **k):
        raise net.FetchError("no network in tests", 404)


UNIVERSE = {"symbols": [
    {"sym": "RELIANCE", "ysym": "RELIANCE.NS", "exchange": "NSE", "name": "Reliance", "series": "EQ",
     "industry": "Oil Gas & Consumable Fuels", "indices": ["NIFTY50"], "turnover": 3e10},
    {"sym": "M&M", "ysym": "M&M.NS", "exchange": "NSE", "name": "M&M", "series": "EQ",
     "industry": "Automobile and Auto Components", "indices": ["NIFTY50"], "turnover": 2e10},
    {"sym": "PASUFIN", "ysym": "PASUFIN.BO", "exchange": "BSE", "name": "Pasupati Fincap", "series": "X",
     "industry": "", "indices": [], "turnover": 1e5},
    {"sym": "TATAMOTORS", "ysym": "TATAMOTORS.NS", "exchange": "NSE", "name": "gone", "series": "EQ",
     "industry": "", "indices": [], "turnover": 1},
]}

NOW = datetime.datetime(2026, 11, 10, 13, 0, tzinfo=IST)   # holiday, day after the fixture session


class TestEngineOffline(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        cal = Calendar(special={})   # the fixture's Muhurat bar is not part of this test
        self.eng = engine.Engine(UNIVERSE, {"drop_after_misses": 2}, cal, FakeClient(),
                                 hist_root=os.path.join(self.tmp.name, "history"),
                                 clock=lambda: NOW, log=lambda *a: None)
        # history synced at 17:00 on 11-09 would contain 11-09; we sync "as of" the
        # morning of 11-09 so the base ends on 11-06, like a live Monday session
        for s in ("RELIANCE.NS", "M&M.NS", "PASUFIN.BO"):
            self.eng.history.sync(s, datetime.datetime(2026, 11, 9, 10, 0, tzinfo=IST))

    def tearDown(self):
        self.tmp.cleanup()

    def test_rows_and_validation(self):
        batch = [s["ysym"] for s in UNIVERSE["symbols"]]
        self.eng._do_quotes(batch)
        rows = {r["ysym"]: r for r in self.eng.snapshot()}
        self.assertNotIn("TATAMOTORS.NS", rows)
        rel = rows["RELIANCE.NS"]
        self.assertEqual(rel["prev_close"], 1324.0)            # official close (Muhurat), not Yahoo's 1320
        self.assertAlmostEqual(rel["change_pct"], (1324.4 / 1324.0 - 1) * 100)
        # base ends 11-06 but the official prev close is from the 11-08 session:
        # without the special-session bar this is a 0.3 % mismatch -> accepted within 1 %
        self.assertTrue(rel["hist_ok"], rel["note"])
        self.assertIsNotNone(rel["rsi14"])
        self.assertIsNotNone(rel["sma200"])
        # today's partial bar from the 10:00 sync gave us the open
        self.assertEqual(rel["open"], 1317.0)
        mm = rows["M&M.NS"]
        self.assertEqual(mm["prev_close"], 3267.8)
        # M&M's Muhurat close differs from 11-06 by 0.6 % -> within tolerance too
        self.assertTrue(mm["hist_ok"], mm["note"])

    def test_open_after_close_comes_from_session_bar(self):
        """Spark quotes carry no open. Synced after the close, the session's own
        bar is in the history and must supply it (it was blank on every row)."""
        e = self.eng
        e.history.sync("M&M.NS", datetime.datetime(2026, 11, 9, 17, 0, tzinfo=IST))
        e.history.today_open.pop("M&M.NS", None)
        e._do_quotes(["M&M.NS"])
        r = e.rows["M&M.NS"]
        last = e.history.bars("M&M.NS")[-1]
        self.assertEqual(last[0], "2026-11-09")
        self.assertEqual(r["open"], last[1])
        self.assertAlmostEqual(r["gap_pct"], (last[1] / r["prev_close"] - 1) * 100)
        self.assertTrue(r["hist_ok"], r["note"])          # the session bar is not in the base

    def test_official_eod_replaces_yahoo_volume(self):
        """After the bhavcopy, the exchange's volume/OHLC win - but only when the
        quote is the final close (a live quote is never overridden)."""
        e = self.eng
        e._do_quotes(["RELIANCE.NS"])
        q = e.quotes["RELIANCE.NS"]
        self.assertFalse(e.rows["RELIANCE.NS"]["official_eod"])
        e.official._days["2026-11-09"] = {"RELIANCE.NS": [1318.0, 1330.0, 1310.0, q["price"], 25_000_000.0, 1324.0]}
        e._recompute("RELIANCE.NS")
        r = e.rows["RELIANCE.NS"]
        self.assertTrue(r["official_eod"])
        self.assertEqual((r["volume"], r["open"], r["high"], r["low"]), (25_000_000.0, 1318.0, 1330.0, 1310.0))
        self.assertAlmostEqual(r["turnover"], q["price"] * 25_000_000.0)
        self.assertAlmostEqual(r["rvol"], 25_000_000.0 / r["avg_vol20"])
        # a quote that is not the official close (still trading) keeps Yahoo's numbers
        e.quotes["RELIANCE.NS"] = dict(q, price=q["price"] + 5)
        e._recompute("RELIANCE.NS")
        self.assertFalse(e.rows["RELIANCE.NS"]["official_eod"])
        self.assertEqual(e.rows["RELIANCE.NS"]["volume"], q["volume"])

    def test_official_fetch_failure_is_harmless(self):
        e = self.eng
        e._do_official(datetime.date(2026, 11, 9))         # FakeClient: every bhavcopy 404s
        self.assertIsNone(e._official_done)
        self.assertIsNone(e.official.get("2026-11-09"))

    def test_transient_history_failure_is_retried(self):
        e = self.eng

        def boom(*a, **k):
            raise net.FetchError("network error: nodename nor servname provided", None)
        real = e.history.sync
        e.history.sync = boom
        e._do_history("RELIANCE.NS")
        self.assertIn("RELIANCE.NS", e._hist_retry)
        due, n = e._hist_retry["RELIANCE.NS"]
        self.assertEqual(n, 1)
        e._hist_retry["RELIANCE.NS"] = (0.0, n)             # make it due now
        e._schedule_once()
        self.assertIn("RELIANCE.NS", e._queued_hist)
        # a 404 (symbol gone) is not retried
        e.history.sync = lambda *a, **k: (_ for _ in ()).throw(net.FetchError("404", 404))
        e._do_history("M&M.NS")
        self.assertNotIn("M&M.NS", e._hist_retry)
        # success clears the retry state
        e.history.sync = real
        e._do_history("RELIANCE.NS")
        self.assertNotIn("RELIANCE.NS", e._hist_retry)

    def test_misses_drop_symbol(self):
        batch = [s["ysym"] for s in UNIVERSE["symbols"]]
        self.eng._do_quotes(batch)
        self.eng._do_quotes(batch)
        self.assertIn("TATAMOTORS.NS", self.eng.dropped)
        self.assertNotIn("RELIANCE.NS", self.eng.dropped)

    def test_mismatch_queues_resync_then_flags(self):
        self.eng._do_quotes(["RELIANCE.NS"])
        q = dict(self.eng.quotes["RELIANCE.NS"], prev_close=1500.0, time=self.eng.quotes["RELIANCE.NS"]["time"] + 1)
        self.eng.quotes["RELIANCE.NS"] = q
        self.eng._bases.clear()
        self.eng._recompute("RELIANCE.NS")
        r = self.eng.rows["RELIANCE.NS"]
        self.assertFalse(r["hist_ok"])
        self.assertIsNone(r.get("rsi14"))                       # blanked, not wrong
        self.assertIn("RELIANCE.NS", self.eng._queued_hist)
        self.assertAlmostEqual(r["change_pct"], (1324.4 / 1500 - 1) * 100)   # still from official prev close

    def test_screen_filter_sort_and_json(self):
        self.eng._do_quotes([s["ysym"] for s in UNIVERSE["symbols"]])
        res = server.screen(self.eng, {"filter": 'exchange == "NSE" and rsi14 > 0', "sort": "change_pct",
                                       "desc": "1", "cols": "sym,price,change_pct,rsi14"})
        self.assertEqual(res["ysyms"], ["M&M.NS", "RELIANCE.NS"])
        json.dumps(res, allow_nan=False)                      # never NaN/Infinity on the wire
        res = server.screen(self.eng, {"sort": "db_score", "desc": "1"})
        self.assertEqual(len(res["rows"]), 3)                  # None sorts last, nothing crashes
        with self.assertRaises(Exception):
            server.screen(self.eng, {"sort": "nope"})

    def test_illiquid_without_special_bar_is_valid(self):
        """No trade in Muhurat -> no special bar, base ends a day 'early', but
        the official prev close equals our last close: history is fine."""
        self.eng.cal = Calendar(special={datetime.date(2026, 11, 8): None})
        self.eng._do_quotes(["PASUFIN.BO"])
        q = self.eng.quotes["PASUFIN.BO"]
        base_last = [b for b in self.eng.history.bars("PASUFIN.BO") if b[0] < "2026-11-09"][-1]
        self.eng.quotes["PASUFIN.BO"] = dict(q, prev_close=base_last[4])
        self.eng._bases.clear()
        self.eng._queued_hist.clear()      # the fixture's real Muhurat close queued it above
        self.eng._hist_tasks.clear()
        self.eng._recompute("PASUFIN.BO")
        r = self.eng.rows["PASUFIN.BO"]
        self.assertTrue(r["hist_ok"], r["note"])
        self.assertNotIn("PASUFIN.BO", self.eng._queued_hist)

    def test_second_resync_is_not_dropped(self):
        e = self.eng
        e._do_quotes(["RELIANCE.NS"])
        e.quotes["RELIANCE.NS"] = dict(e.quotes["RELIANCE.NS"], prev_close=1500.0)
        e._bases.clear()
        e._recompute("RELIANCE.NS")                      # 1st mismatch -> queued
        t = e._next_task()
        self.assertEqual(t[2:], ("hist", "RELIANCE.NS"))
        e._do_history("RELIANCE.NS")                     # still wrong -> must re-queue
        self.assertIn("RELIANCE.NS", e._queued_hist)
        e._do_history(e._next_task()[3])                 # 2nd resync -> final verdict
        r = e.rows["RELIANCE.NS"]
        self.assertFalse(r["hist_ok"])
        self.assertIn("disagrees", r["note"])
        self.assertNotIn("RELIANCE.NS", e._queued_hist)

    def test_history_not_starved_by_sweeps(self):
        e = self.eng
        for i in range(100):
            e._push(1, "sweep", ["X%d" % i])
        for s in ("A.NS", "B.NS", "C.NS"):
            e.queue_history(s, force=True)
        kinds = [e._next_task()[2] for _ in range(20)]
        self.assertEqual(kinds.count("hist"), 3)          # all three ran within 20 tasks
        self.assertLessEqual(kinds.index("hist"), 5)
        # with no quote work waiting, history takes everything
        e._tasks.clear()
        e.queue_history("D.NS", force=True)
        self.assertEqual(e._next_task()[2], "hist")

    def test_clean(self):
        self.assertIsNone(server.clean(float("nan")))
        self.assertIsNone(server.clean(float("inf")))
        self.assertEqual(server.clean(1.234567), 1.2346)

    def test_sort_key_none_last_both_ways(self):
        rows = [{"x": 2}, {"x": None}, {"x": 5}, {"x": "a"}]
        nums = [r for r in rows if not isinstance(r["x"], str)]
        self.assertEqual([r["x"] for r in sorted(nums, key=server._sort_key("x", True))], [5, 2, None])
        self.assertEqual([r["x"] for r in sorted(nums, key=server._sort_key("x", False))], [2, 5, None])
        strs = [{"x": "b"}, {"x": None}, {"x": "A"}]
        self.assertEqual([r["x"] for r in sorted(strs, key=server._sort_key("x", True))], ["b", "A", None])


if __name__ == "__main__":
    unittest.main()
