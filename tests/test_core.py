"""Unit tests. Run: .venv/bin/python -m unittest discover -s tests -v"""

import datetime
import gzip
import json
import math
import os
import random
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from screener import clock, expr, fields, history, indicators, net, patterns, universe, yahoo  # noqa: E402
from screener.clock import IST, Calendar  # noqa: E402

FIX = os.path.join(ROOT, "tests", "fixtures")


def load(name):
    with open(os.path.join(FIX, name), "rb") as f:
        return json.loads(gzip.decompress(f.read()))


def ist(y, m, d, hh=0, mm=0):
    return datetime.datetime(y, m, d, hh, mm, tzinfo=IST)


# ---------------------------------------------------------------- clock
class TestClock(unittest.TestCase):
    def setUp(self):
        self.cal = Calendar()

    def test_holiday_and_weekend(self):
        self.assertEqual(self.cal.state(ist(2026, 11, 10, 11)), "holiday")   # Balipratipada
        self.assertEqual(self.cal.state(ist(2026, 11, 7, 11)), "weekend")
        self.assertEqual(self.cal.state(ist(2026, 11, 9, 11)), "open")

    def test_session_boundaries(self):
        self.assertEqual(self.cal.state(ist(2026, 11, 9, 9, 0)), "pre_open")
        self.assertEqual(self.cal.state(ist(2026, 11, 9, 9, 14)), "pre_open")
        self.assertEqual(self.cal.state(ist(2026, 11, 9, 9, 15)), "open")
        self.assertEqual(self.cal.state(ist(2026, 11, 9, 15, 29)), "open")
        self.assertEqual(self.cal.state(ist(2026, 11, 9, 15, 30)), "post_close")
        self.assertEqual(self.cal.state(ist(2026, 11, 9, 16, 0)), "closed")
        self.assertEqual(self.cal.state(ist(2026, 11, 9, 8, 59)), "closed")

    def test_prev_trading_day_skips_holiday_and_weekend(self):
        self.assertEqual(self.cal.prev_trading_day(datetime.date(2026, 11, 11)), datetime.date(2026, 11, 9))
        self.assertEqual(self.cal.prev_trading_day(datetime.date(2026, 11, 4)), datetime.date(2026, 11, 3))
        self.assertEqual(self.cal.prev_trading_day(datetime.date(2026, 10, 21)), datetime.date(2026, 10, 19))

    def test_muhurat_is_previous_session_for_monday(self):
        # official previous close on Mon 11-09 is the Sunday Muhurat close
        self.assertEqual(self.cal.prev_trading_day(datetime.date(2026, 11, 9)), datetime.date(2026, 11, 8))
        self.assertEqual(self.cal.prev_trading_day(datetime.date(2026, 11, 9), include_special=False),
                         datetime.date(2026, 11, 6))
        self.assertEqual(self.cal.state(ist(2026, 11, 8, 18)), "special")   # hours unknown

    def test_last_completed_session(self):
        self.assertEqual(self.cal.last_completed_session(ist(2026, 11, 10, 13)), datetime.date(2026, 11, 9))
        self.assertEqual(self.cal.last_completed_session(ist(2026, 11, 9, 12)), datetime.date(2026, 11, 6))
        self.assertEqual(self.cal.last_completed_session(ist(2026, 11, 9, 15, 31)), datetime.date(2026, 11, 9))

    def test_special_session(self):
        cal = Calendar(special={datetime.date(2026, 11, 8): (datetime.time(18), datetime.time(19))})
        self.assertEqual(cal.state(ist(2026, 11, 8, 18, 30)), "open")
        self.assertEqual(cal.state(ist(2026, 11, 8, 12)), "closed")
        # Yahoo never has the special bar, so "is the cache current" skips it
        self.assertEqual(cal.last_completed_session(ist(2026, 11, 8, 20)), datetime.date(2026, 11, 6))
        self.assertEqual(cal.specials_between("2026-11-06", "2026-11-09"), [datetime.date(2026, 11, 8)])

    def test_ts_to_date_is_ist(self):
        # 2026-11-09 03:45 UTC = 09:15 IST, and 20:00 UTC = 01:30 IST next day
        self.assertEqual(clock.ts_to_date(1794195900), datetime.date(2026, 11, 9))
        t = int(datetime.datetime(2026, 11, 9, 20, 0, tzinfo=clock.UTC).timestamp())
        self.assertEqual(clock.ts_to_date(t), datetime.date(2026, 11, 10))

    def test_naive_rejected(self):
        with self.assertRaises(ValueError):
            self.cal.state(datetime.datetime(2026, 11, 9, 11))

    def test_parse_now(self):
        self.assertEqual(clock.parse_now("2026-11-09 10:15"), ist(2026, 11, 9, 10, 15))
        self.assertEqual(clock.parse_now("2026-11-09T04:45Z"), ist(2026, 11, 9, 10, 15))

    def test_session_fraction(self):
        self.assertAlmostEqual(self.cal.session_fraction(ist(2026, 11, 9, 12, 22, )), 187 / 375, places=3)
        self.assertEqual(self.cal.session_fraction(ist(2026, 11, 10, 12)), 0.0)


# ---------------------------------------------------------------- yahoo
class TestYahoo(unittest.TestCase):
    def test_spark_fixture(self):
        q = yahoo.parse_spark(load("spark_2026-11-09.json.gz"))
        self.assertIn("M&M.NS", q)
        self.assertIn("BAJAJ-AUTO.NS", q)
        self.assertNotIn("TATAMOTORS.NS", q)   # renamed after demerger: just absent
        # official previous close via chartPreviousClose (interval=1d sends no previousClose)
        self.assertEqual(q["RELIANCE.NS"]["prev_close"], 1324.0)
        self.assertEqual(q["M&M.NS"]["prev_close"], 3267.8)
        self.assertEqual(q["RELIANCE.NS"]["price"], 1324.4)

    def test_chart_prev_close_not_used_for_long_range(self):
        meta = {"regularMarketPrice": 10, "regularMarketTime": 1, "chartPreviousClose": 5, "range": "2y"}
        self.assertIsNone(yahoo.quote_from_meta(meta)["prev_close"])

    def test_bad_quotes_rejected(self):
        self.assertIsNone(yahoo.quote_from_meta({"regularMarketPrice": 0, "regularMarketTime": 1}))
        self.assertIsNone(yahoo.quote_from_meta({"regularMarketPrice": None, "regularMarketTime": 1}))
        self.assertIsNone(yahoo.quote_from_meta({"regularMarketPrice": 5}))

    def test_urls(self):
        u = yahoo.spark_urls(["M&M.NS", "BAJAJ-AUTO.NS"])[0]
        self.assertIn("M%26M.NS,BAJAJ-AUTO.NS", u)
        with self.assertRaises(ValueError):
            yahoo.spark_urls(["X.NS"] * 21)
        self.assertIn("/M%26M.NS?", yahoo.chart_urls("M&M.NS")[0])

    def test_chart_fixture(self):
        bars, meta, _ = yahoo.parse_chart_daily(load("chart_RELIANCE.NS_2y.json.gz"))
        self.assertGreater(len(bars), 450)
        dates = [b[0] for b in bars]
        self.assertEqual(dates, sorted(set(dates)))
        for d, o, h, l, c, v in bars:
            self.assertTrue(l <= min(o, c) <= max(o, c) <= h, d)
            self.assertGreater(c, 0)

    def test_chart_nulls_and_duplicates(self):
        t0 = 1794195900
        doc = {"chart": {"result": [{"meta": {}, "timestamp": [t0 - 86400 * 3, t0 - 86400, t0, t0 + 3600],
                                     "indicators": {"quote": [{
                                         "open": [10, None, 11, 11], "high": [None, None, 12, 13],
                                         "low": [9, None, 10, 10], "close": [10, None, 11.5, 12.5],
                                         "volume": [100, None, None, 300]}]}}]}}
        bars, _, _ = yahoo.parse_chart_daily(doc)
        self.assertEqual(len(bars), 2)                       # null close dropped, same-day dup merged
        self.assertEqual(bars[-1][4], 12.5)                  # later duplicate wins
        self.assertEqual(bars[0][2], 10)                     # missing high filled from o/c


# ---------------------------------------------------------------- indicators
def naive_sma(xs, n):
    return sum(xs[-n:]) / n


def naive_ema(xs, n):
    e = sum(xs[:n]) / n
    a = 2 / (n + 1)
    for x in xs[n:]:
        e += a * (x - e)
    return e


def naive_rsi(xs, n=14):
    ch = [b - a for a, b in zip(xs, xs[1:])]
    g = [max(c, 0) for c in ch]
    l = [max(-c, 0) for c in ch]
    ag, al = sum(g[:n]) / n, sum(l[:n]) / n
    for i in range(n, len(ch)):
        ag = (ag * (n - 1) + g[i]) / n
        al = (al * (n - 1) + l[i]) / n
    return 100 - 100 / (1 + ag / al) if al else 100.0


def synth_bars(n=300, seed=7, start=100.0):
    rnd = random.Random(seed)
    bars, c = [], start
    d = datetime.date(2025, 1, 1)
    for i in range(n):
        o = c * (1 + rnd.uniform(-0.01, 0.01))
        c = max(1.0, o * (1 + rnd.uniform(-0.03, 0.03)))
        h = max(o, c) * (1 + rnd.uniform(0, 0.01))
        l = min(o, c) * (1 - rnd.uniform(0, 0.01))
        bars.append(((d + datetime.timedelta(days=i)).isoformat(), o, h, l, c, rnd.randint(1000, 9000)))
    return bars


class TestIndicators(unittest.TestCase):
    def setUp(self):
        self.bars = synth_bars()
        self.closes = [b[4] for b in self.bars]

    def test_live_step_equals_full_recompute(self):
        """Base(history) + live(last bar) must equal indicators of the full series."""
        last = self.bars[-1]
        f = indicators.live(indicators.Base(self.bars[:-1]), last[4], last[2], last[3], last[5], last[1])
        full = indicators.Base(self.bars)
        for n in indicators.EMA_N:
            self.assertAlmostEqual(f["ema%d" % n], full.ema[n].v, places=9)
        for n in indicators.SMA_N:
            self.assertAlmostEqual(f["sma%d" % n], naive_sma(self.closes, n), places=9)
            self.assertAlmostEqual(f["sma%d_prev" % n], naive_sma(self.closes[:-1], n), places=9)
        self.assertAlmostEqual(f["rsi14"], indicators._rsi(full.rsi_g.v, full.rsi_l.v), places=9)
        self.assertAlmostEqual(f["atr14"], full.atr.v, places=9)
        self.assertAlmostEqual(f["macd"], full.ema12.v - full.ema26.v, places=9)
        self.assertAlmostEqual(f["macd_signal"], full.macd_sig.v, places=9)
        self.assertAlmostEqual(f["adx14"], full.adx.v, places=9)

    def test_against_naive(self):
        last = self.bars[-1]
        f = indicators.live(indicators.Base(self.bars[:-1]), last[4], last[2], last[3], last[5], last[1])
        self.assertAlmostEqual(f["ema20"], naive_ema(self.closes, 20), places=9)
        self.assertAlmostEqual(f["ema200"], naive_ema(self.closes, 200), places=9)
        self.assertAlmostEqual(f["rsi14"], naive_rsi(self.closes), places=9)
        self.assertAlmostEqual(f["rsi14_prev"], naive_rsi(self.closes[:-1]), places=9)
        w = self.closes[-20:]
        m = sum(w) / 20
        sd = math.sqrt(sum((x - m) ** 2 for x in w) / 20)
        self.assertAlmostEqual(f["bb_upper"], m + 2 * sd, places=9)

    def test_insufficient_history_is_none_not_zero(self):
        short = self.bars[:30]
        f = indicators.live(indicators.Base(short), 100.0, 101, 99, 1000)
        self.assertIsNone(f["sma200"])
        self.assertIsNone(f["ema50"])
        self.assertIsNotNone(f["sma20"])
        self.assertIsNotNone(f["rsi14"])
        # a recent listing: the "52-week" high is the high since listing
        self.assertEqual(f["high_52w"], max([b[2] for b in short] + [101]))
        self.assertIsNone(indicators.live(indicators.Base(self.bars[:19]), 50.0)["high_52w"])
        # exactly n-1 closed bars: live SMA uses them + today's price
        f = indicators.live(indicators.Base(self.bars[:19]), 50.0)
        self.assertAlmostEqual(f["sma20"], (sum(self.closes[:19]) + 50.0) / 20)

    def test_official_close_override(self):
        b = indicators.Base(self.bars, official_prev_close=123.0)
        self.assertEqual(b.prev_close, 123.0)
        f = indicators.live(b, 123.0 * 1.02)
        self.assertAlmostEqual(f["change_pct"], 2.0)

    def test_rsi_flat(self):
        flat = [("2026-01-%02d" % (i + 1), 10, 10, 10, 10, 1) for i in range(20)]
        f = indicators.live(indicators.Base(flat), 10.0)
        self.assertEqual(f["rsi14"], 50.0)

    def test_rvol_tod(self):
        f = indicators.live(indicators.Base(self.bars), 100, volume=1000, session_fraction=0.5)
        av = sum(b[5] for b in self.bars[-20:]) / 20
        self.assertAlmostEqual(f["rvol"], 1000 / av)
        self.assertAlmostEqual(f["rvol_tod"], 2000 / av)
        f = indicators.live(indicators.Base(self.bars), 100, volume=1000, session_fraction=0.01)
        self.assertAlmostEqual(f["rvol_tod"], f["rvol"])


# ---------------------------------------------------------------- expr
F = fields.FIELDS


def ev(src, row):
    fn, _ = expr.compile_filter(src, F)
    return fn(row)


class TestExpr(unittest.TestCase):
    row = {"price": 105.0, "prev_close": 100.0, "rsi14": 25.0, "sma200": 90.0, "volume": 2e6,
           "turnover": 2.1e8, "exchange": "NSE", "indices": ["NIFTY50", "NIFTY100"], "industry": "IT",
           "name": "Infosys Ltd", "ema9": 11.0, "ema21": 10.5, "ema9_prev": 10.0, "ema21_prev": 10.4,
           "change_pct": 5.0, "breakout_20d": True, "sma50": None, "sym": "INFY"}

    def test_basic(self):
        self.assertTrue(ev("rsi14 < 30 and price > sma200", self.row))
        self.assertFalse(ev("rsi14 > 30 or price < sma200", self.row))
        self.assertTrue(ev("price - prev_close == 5", self.row))
        self.assertTrue(ev("(price / prev_close - 1) * 100 >= 4.99", self.row))
        self.assertTrue(ev("-price < 0", self.row))

    def test_suffixes(self):
        self.assertTrue(ev("turnover > 20cr", self.row))
        self.assertFalse(ev("turnover > 25cr", self.row))
        self.assertTrue(ev("volume >= 20L", self.row))
        self.assertTrue(ev("volume > 1999k", self.row))

    def test_strings_and_lists(self):
        self.assertTrue(ev('exchange == "nse"', self.row))
        self.assertTrue(ev('"NIFTY50" in indices', self.row))
        self.assertTrue(ev('industry in ["IT", "Healthcare"]', self.row))
        self.assertTrue(ev('industry not in ["Healthcare"]', self.row))
        self.assertTrue(ev('contains(name, "infosys")', self.row))
        self.assertFalse(ev('exchange == 5', self.row))

    def test_chained(self):
        self.assertTrue(ev("20 < rsi14 < 30", self.row))
        self.assertFalse(ev("26 < rsi14 < 30", self.row))

    def test_null_is_unknown_not_false(self):
        self.assertFalse(ev("sma50 > 0", self.row))
        self.assertFalse(ev("not (sma50 > 0)", self.row))       # unknown stays unknown
        self.assertTrue(ev("sma50 > 0 or rsi14 < 30", self.row))  # unknown or true = true
        self.assertFalse(ev("sma50 > 0 and rsi14 < 30", self.row))
        self.assertFalse(ev("price / 0 > 1", self.row))

    def test_crosses(self):
        self.assertTrue(ev("crosses_above(ema9, ema21)", self.row))
        self.assertFalse(ev("crosses_below(ema9, ema21)", self.row))
        self.assertTrue(ev("crosses_above(close, 104)", self.row))  # close->price, prev->prev_close
        with self.assertRaises(expr.ExprError):
            expr.compile_filter("crosses_above(turnover, 5)", F)

    def test_bool_fields_and_aliases(self):
        self.assertTrue(ev("breakout_20d and rsi < 30", self.row))
        self.assertTrue(ev("not breakout_20d or chg > 4", self.row))

    def test_empty_matches_all(self):
        self.assertTrue(ev("", self.row))
        self.assertTrue(ev("   ", self.row))

    def test_errors(self):
        for bad in ["rsi14 <", "foo > 1", "price >> 2", "(price > 1", "abs()", "price > 1 1",
                    "__import__('os')", "price.__class__"]:
            with self.assertRaises(expr.ExprError, msg=bad):
                expr.compile_filter(bad, F)

    def test_unknown_field_suggests(self):
        with self.assertRaises(expr.ExprError) as cm:
            expr.compile_filter("rsi15 > 3", F)
        self.assertIn("rsi14", str(cm.exception))


# ---------------------------------------------------------------- history
class TestHistory(unittest.TestCase):
    old = [("2026-11-0%d" % d, 0, 0, 0, c, 0) for d, c in [(2, 100), (3, 101), (4, 102), (5, 103), (6, 104)]]

    def test_noise_accepted(self):
        new = [("2026-11-05", 0, 0, 0, 103.6, 0), ("2026-11-06", 0, 0, 0, 104.4, 0), ("2026-11-09", 0, 0, 0, 105, 0)]
        bars, ok = history.merge(self.old, new)
        self.assertTrue(ok)
        self.assertEqual([b[0] for b in bars][-3:], ["2026-11-05", "2026-11-06", "2026-11-09"])
        self.assertEqual(bars[-2][4], 104.4)   # Yahoo's revision is taken

    def test_split_detected(self):
        new = [("2026-11-05", 0, 0, 0, 51.5, 0), ("2026-11-06", 0, 0, 0, 52, 0), ("2026-11-09", 0, 0, 0, 53, 0)]
        self.assertFalse(history.merge(self.old, new)[1])

    def test_gap_detected(self):
        new = [("2026-11-20", 0, 0, 0, 100, 0)]
        self.assertFalse(history.merge(self.old, new)[1])

    def test_drop_partial(self):
        bars = list(self.old) + [("2026-11-09", 1, 2, 0.5, 1.5, 10)]
        kept, partial = history.drop_partial(bars, ist(2026, 11, 9, 12))
        self.assertEqual(len(kept), len(self.old))
        self.assertEqual(partial[0], "2026-11-09")
        kept, partial = history.drop_partial(bars, ist(2026, 11, 9, 17))
        self.assertEqual(len(kept), len(bars))
        self.assertIsNone(partial)

    def test_fname_escapes(self):
        self.assertEqual(history._fname("M&M.NS"), "M_26M.NS.json.gz")

    def test_store_roundtrip_and_corrupt_cache(self):
        with tempfile.TemporaryDirectory() as d:
            st = history.HistoryStore(d)
            st._save("A.NS", self.old, 5)
            with open(os.path.join(d, history._fname("B.NS")), "wb") as f:
                f.write(b"\x1f\x8bgarbage")
            st2 = history.HistoryStore(d)
            self.assertEqual(st2.load(["A.NS", "B.NS", "C.NS"]), 1)
            self.assertEqual(st2.bars("A.NS")[-1][4], 104)


# ---------------------------------------------------------------- specials
class TestSpecials(unittest.TestCase):
    def test_patch_inserts_and_rescales(self):
        from screener import specials
        sp = specials.Specials(Calendar(), client=None, root="/nonexistent")
        rows = [{"FinInstrmTp": "STK", "TckrSymb": "HDFCBANK", "OpnPric": "788.9", "HghPric": "795",
                 "LwPric": "782.55", "ClsPric": "784.1", "PrvsClsgPric": "788.25", "TtlTradgVol": "7207078"}]
        sp._days["2026-11-08"] = specials.parse(rows, [])
        bars = [("2026-11-05", 0, 0, 0, 760.0, 1), ("2026-11-06", 0, 0, 0, 788.25, 1), ("2026-11-09", 0, 0, 0, 798.15, 1)]
        out = sp.patch("HDFCBANK.NS", bars)
        self.assertEqual([b[0] for b in out], ["2026-11-05", "2026-11-06", "2026-11-08", "2026-11-09"])
        self.assertAlmostEqual(out[2][4], 784.1)
        # a 1:2 split after the session: Yahoo's history is halved, the patch follows
        halved = [(d, o, h, l, c / 2, v) for d, o, h, l, c, v in bars]
        self.assertAlmostEqual(sp.patch("HDFCBANK.NS", halved)[2][4], 392.05)
        self.assertIs(sp.patch("OTHER.NS", bars), bars)
        # a small factor is a stale Yahoo close, not a split: no rescale
        stale = [(d, o, h, l, c * 0.95 if d == "2026-11-06" else c, v) for d, o, h, l, c, v in bars]
        self.assertAlmostEqual(sp.patch("HDFCBANK.NS", stale)[2][4], 784.1)
        # history that already ends before the special day: appended at the end
        out = sp.patch("HDFCBANK.NS", bars[:2])
        self.assertEqual(out[-1][0], "2026-11-08")


# ---------------------------------------------------------------- universe
def bhav(sym, isin, series, tv, typ="STK", src="NSE"):
    return {"TckrSymb": sym, "ISIN": isin, "SctySrs": series, "TtlTrfVal": str(tv), "FinInstrmTp": typ,
            "FinInstrmNm": sym + " LTD", "ClsPric": "10"}


class TestUniverse(unittest.TestCase):
    def test_build(self):
        nse = [bhav("M&M", "I1", "EQ", 900), bhav("BAJAJ-AUTO", "I2", "EQ", 800), bhav("SGB", "I3", "GB", 5),
               bhav("SMEX", "I4", "SM", 5), bhav("TFT", "I5", "BE", 7), bhav("ETF1", "I6", "EQ", 1, typ="ETF"),
               bhav("GOLDBEES", "I7", "EQ", 9999)]          # an ETF that the bhavcopy calls STK/EQ
        bse = [bhav("MM", "I1", "A", 100), bhav("ONLYB", "I9", "X", 50), bhav("DEBT", "I10", "F", 50),
               bhav("MON100", "INF247L01AP3", "B", 70),
               bhav("SMEB", "I11", "M", 1), dict(bhav("BETF", "I12", "X", 60), FinInstrmNm="XYZ NIFTY ETF")]
        idx = {"NIFTY50": [{"Symbol": "M&M", "Industry": "Automobile"}]}
        eq_l = [{"SYMBOL": "M&M", "NAME OF COMPANY": "Mahindra & Mahindra Ltd"},
                {"SYMBOL": "BAJAJ-AUTO", "NAME OF COMPANY": "Bajaj Auto Limited"},
                {"SYMBOL": "TFT", "NAME OF COMPANY": "TFT Ltd"}]
        out = universe.build(nse, bse, eq_l, idx)
        ys = [r["ysym"] for r in out]
        self.assertEqual(ys, ["M&M.NS", "BAJAJ-AUTO.NS", "ONLYB.BO", "TFT.NS"])  # by turnover
        mm = out[0]
        self.assertTrue(mm["also_bse"])
        self.assertEqual(mm["industry"], "Automobile")
        self.assertEqual(mm["indices"], ["NIFTY50"])
        self.assertEqual(mm["name"], "Mahindra & Mahindra Ltd")
        sme = universe.build(nse, bse, include_sme=True)
        self.assertIn("SMEX.NS", [r["ysym"] for r in sme])
        self.assertIn("SMEB.BO", [r["ysym"] for r in sme])
        nse_only = universe.build(nse, bse, exchanges=("NSE",))
        self.assertNotIn("ONLYB.BO", [r["ysym"] for r in nse_only])

    def test_header_whitespace(self):
        rows = universe._rows("SYMBOL, SERIES\nABC, EQ\n")
        self.assertEqual(rows, [{"SYMBOL": "ABC", "SERIES": "EQ"}])


# ---------------------------------------------------------------- patterns
def w_bars():
    """Uptrend, then a clean W over ~40 days, then a neckline breakout."""
    closes = [80 + i * 0.25 for i in range(80)]                 # rising base for the SMA50 filter
    top = closes[-1]
    leg = [top - (top - 90) * k / 10 for k in range(1, 11)]     # down to 90  (L1)
    up = [90 + 12 * k / 10 for k in range(1, 11)]               # up to 102   (neckline)
    dn = [102 - 11.5 * k / 10 for k in range(1, 11)]            # down to 90.5 (L2)
    rec = [90.5 + 10 * k / 8 for k in range(1, 8)]              # back up toward neckline (100.5)
    closes += leg + up + dn + rec
    d0 = datetime.date(2025, 1, 1)
    return [((d0 + datetime.timedelta(days=i)).isoformat(), c, c * 1.005, c * 0.995, c, 1000)
            for i, c in enumerate(closes)]


class TestPatterns(unittest.TestCase):
    def test_double_bottom_found(self):
        db = patterns.double_bottom(w_bars())
        self.assertIsNotNone(db)
        self.assertAlmostEqual(db["l1"], 90, places=6)
        self.assertAlmostEqual(db["l2"], 90.5, places=6)
        self.assertAlmostEqual(db["neckline"], 102, places=6)

    def test_double_bottom_breakout_needs_volume(self):
        bars = w_bars()
        st = patterns.static(bars)
        base = indicators.Base(bars)
        quiet = indicators.live(base, 103.0, volume=1000, session_fraction=1.0)
        loud = indicators.live(base, 103.0, volume=2000, session_fraction=1.0)
        self.assertFalse(patterns.live_flags(st, quiet, 103.0, 1000)["double_bottom"])
        fl = patterns.live_flags(st, loud, 103.0, 2000)
        self.assertTrue(fl["double_bottom"])
        self.assertGreater(fl["db_score"], 50)
        below = indicators.live(base, 101.0, volume=5000, session_fraction=1.0)
        self.assertFalse(patterns.live_flags(st, below, 101.0, 5000)["double_bottom"])

    def test_old_breakout_is_not_a_new_one(self):
        """Broke the neckline 3 sessions ago: no longer a breakout signal, even
        on big volume - it is a follow-through with days_since = 3."""
        bars = w_bars()
        d = datetime.date.fromisoformat(bars[-1][0])
        for i, c in enumerate((103.0, 104.0, 105.0), 1):
            bars.append(((d + datetime.timedelta(days=i)).isoformat(), c, c * 1.005, c * 0.995, c, 1000))
        st = patterns.static(bars)
        self.assertEqual(st["double_bottom"]["broke_ago"], 2)
        f = indicators.live(indicators.Base(bars), 106.0, volume=5000, session_fraction=1.0)
        fl = patterns.live_flags(st, f, 106.0, 5000)
        self.assertFalse(fl["double_bottom"])
        self.assertFalse(fl["db_forming"])
        self.assertEqual(fl["db_days_since_breakout"], 3)

    def test_forming_and_plan(self):
        bars = w_bars()
        st = patterns.static(bars)
        db = st["double_bottom"]
        f = indicators.live(indicators.Base(bars), 101.0, volume=1000, session_fraction=1.0)
        fl = patterns.live_flags(st, f, 101.0, 1000)
        self.assertTrue(fl["db_forming"])
        self.assertFalse(fl["double_bottom"])
        self.assertIsNone(fl["db_days_since_breakout"])
        risk = 102 - db["low"]                        # entry = neckline while forming
        self.assertAlmostEqual(fl["db_entry"], 102)
        self.assertAlmostEqual(fl["db_target_1r"], 102 + risk)
        self.assertAlmostEqual(fl["db_target_2r"], 102 + 2 * risk)
        self.assertAlmostEqual(fl["db_risk_pct"], risk / 102 * 100)
        self.assertAlmostEqual(fl["db_target"], 102 + (102 - min(90, 90.5)))
        # breakout today on volume: days_since 0, no longer forming
        f = indicators.live(indicators.Base(bars), 103.0, volume=2000, session_fraction=1.0)
        fl = patterns.live_flags(st, f, 103.0, 2000)
        self.assertTrue(fl["double_bottom"])
        self.assertEqual(fl["db_days_since_breakout"], 0)
        self.assertFalse(fl["db_forming"])

    def test_downtrend_rejected(self):
        bars = w_bars()
        # replace the rising base with a steep decline -> SMA50 falling into L2
        n = 80
        steep = [200 - i * 1.3 for i in range(n)]
        bars = [(b[0], c, c, c, c, 1000) for b, c in zip(bars[:n], steep)] + bars[n:]
        self.assertIsNone(patterns.double_bottom(bars))

    def test_breakout_20d(self):
        bars = synth_bars(60)
        f = indicators.live(indicators.Base(bars), 10_000.0)
        self.assertTrue(patterns.live_flags({}, f, 10_000.0, 1)["breakout_20d"])


# ---------------------------------------------------------------- net
class TestRateLimiter(unittest.TestCase):
    def test_aimd(self):
        t = [0.0]
        slept = []
        rl = net.RateLimiter(rate=4, min_rate=1, max_rate=8, step=1, cooldown=10,
                             clock=lambda: t[0], sleep=lambda s: slept.append(s))
        rl.acquire()
        rl.acquire()
        self.assertAlmostEqual(slept[-1], 0.25)
        rl.on_429()
        self.assertEqual(rl.rate, 2)
        rl.acquire()
        self.assertGreaterEqual(slept[-1], 8.0)   # cool-down (10 s +-20 %)
        rl.on_429(); rl.on_429(); rl.on_429()
        self.assertEqual(rl.rate, 2)              # same window: in-flight 429s cut only once
        for _ in range(3):
            t[0] += 20                            # next windows
            rl.on_429()
        self.assertEqual(rl.rate, 1)              # floored
        for _ in range(20):
            rl.on_ok()
        self.assertEqual(rl.rate, 8)              # capped

    def test_client_retries_429_then_gives_up_on_404(self):
        calls = []

        def fake(url, timeout, headers):
            calls.append(url)
            if len(calls) == 1:
                raise net.FetchError("429", 429)
            return b'{"ok": 1}'
        c = net.Client(net.RateLimiter(rate=1000, cooldown=0), sleep=lambda s: None)
        c.get_raw = fake
        self.assertEqual(c.get_json(["a", "b"]), {"ok": 1})
        self.assertEqual(calls, ["a", "b"])      # alternates hosts

        def nf(url, timeout, headers):
            calls.append(url)
            raise net.FetchError("404", 404)
        c.get_raw = nf
        calls.clear()
        with self.assertRaises(net.FetchError):
            c.get("x")
        self.assertEqual(len(calls), 1)

    def test_write_atomic(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "sub", "x.json.gz")
            net.write_json(p, {"a": 1})
            self.assertEqual(net.read_json(p), {"a": 1})
            self.assertEqual([f for f in os.listdir(os.path.dirname(p))], ["x.json.gz"])
            self.assertIsNone(net.read_json(os.path.join(d, "missing.json")))


if __name__ == "__main__":
    unittest.main()
