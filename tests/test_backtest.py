"""Backtester: fills, exits, costs and the portfolio, on hand-made bars."""

import datetime
import gzip
import json
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from screener import backtest as bt  # noqa: E402
from screener import indicators  # noqa: E402

D0 = datetime.date(2024, 1, 1)
INFO = {"sym": "TEST", "ysym": "TEST.NS", "exchange": "NSE", "name": "Test", "series": "EQ",
        "industry": "", "indices": []}


def bars_from(rows):
    """rows: (o, h, l, c, v) tuples -> dated bars on consecutive days."""
    return [((D0 + datetime.timedelta(days=i)).isoformat(), *r) for i, r in enumerate(rows)]


def flat(n, px=100.0, v=1000.0):
    return [(px, px * 1.01, px * 0.99, px, v)] * n


def run(rows, **spec):
    base = {"entry": "hist_days == 30", "min_turnover": 0, "stop": "pct:5", "target": "pct:10",
            "max_hold": 0, "portfolio": {"sizing": "equal"}}
    base.update(spec)
    s, _ = bt.prepare(base)
    cnt = {}
    trades = bt.simulate(bars_from(rows), INFO, bt._Compiled(s), cnt)
    return trades, cnt


class TestWalkEqualsRebuild(unittest.TestCase):
    def test_advance_matches_fresh_base(self):
        with open(os.path.join(ROOT, "tests", "fixtures", "chart_RELIANCE.NS_2y.json.gz"), "rb") as f:
            from screener import yahoo
            bars, _, _ = yahoo.parse_chart_daily(json.loads(gzip.decompress(f.read())))
        walked = indicators.Base([])
        for t, b in enumerate(bars):
            if t in (1, 15, 60, 199, 250, 300, len(bars) - 1):
                fresh = indicators.Base(bars[:t])
                a = indicators.live(walked, b[4], b[2], b[3], b[5], b[1], None, 1.0)
                z = indicators.live(fresh, b[4], b[2], b[3], b[5], b[1], None, 1.0)
                for k in z:
                    if isinstance(z[k], float):
                        self.assertAlmostEqual(a[k], z[k], places=6, msg="%s at %d" % (k, t))
                    else:
                        self.assertEqual(a[k], z[k], "%s at %d" % (k, t))
            walked.advance(b)

    def test_year_close_tracks_year_change(self):
        b = indicators.Base([("2024-12-30", 1, 1, 1, 10, 1), ("2024-12-31", 1, 1, 1, 11, 1)])
        b.advance(("2025-01-02", 1, 1, 1, 12, 1))
        self.assertEqual(b.year_open_close, 11)
        self.assertEqual(indicators.Base([("2024-12-31", 1, 1, 1, 11, 1), ("2025-01-02", 1, 1, 1, 12, 1)]).year_open_close, 11)


class TestFillsAndExits(unittest.TestCase):
    def test_signal_on_close_fills_next_open(self):
        rows = flat(31) + [(101, 103, 100, 102, 1000)] + flat(5, 102)
        (t,), cnt = run(rows, max_hold=3)
        self.assertEqual(t["signal_date"], bars_from(rows)[30][0])
        self.assertEqual(t["entry_date"], bars_from(rows)[31][0])
        self.assertEqual(t["entry"], 101)              # the next OPEN, not the signal close
        self.assertEqual(t["reason"], "time")
        self.assertEqual(t["bars"], 3)
        self.assertEqual(cnt["signals"], 1)

    def test_gap_below_stop_exits_at_open(self):
        rows = flat(31) + [(100, 101, 99, 100, 1000), (90, 92, 88, 91, 1000)] + flat(3, 91)
        (t,), _ = run(rows)
        self.assertEqual(t["reason"], "stop")
        self.assertEqual(t["exit"], 90)                # the open, worse than the 95 stop
        self.assertTrue(t["exit_at_open"])
        self.assertAlmostEqual(t["r"], -2.0)

    def test_stop_and_target_same_day_counts_as_stop(self):
        rows = flat(31) + [(100, 100.5, 99.5, 100, 1000), (100, 111, 94, 100, 1000)] + flat(3)
        (t,), cnt = run(rows)
        self.assertEqual(t["reason"], "stop")
        self.assertAlmostEqual(t["exit"], 95)
        self.assertEqual(cnt["ambiguous"], 1)

    def test_target_hit(self):
        rows = flat(31) + [(100, 100.5, 99.5, 100, 1000), (101, 112, 100, 108, 1000)] + flat(3, 108)
        (t,), _ = run(rows)
        self.assertEqual(t["reason"], "target")
        self.assertAlmostEqual(t["exit"], 110)
        self.assertAlmostEqual(t["r"], 2.0)

    def test_no_fill_on_zero_volume_or_locked_day(self):
        rows = flat(31) + [(100, 100, 100, 100, 0)] + flat(5)
        trades, cnt = run(rows)
        self.assertEqual(trades, [])
        self.assertEqual(cnt["no_fill_untradable"], 1)
        rows = flat(31) + [(105, 105, 105, 105, 500)] + flat(5, 105)
        trades, cnt = run(rows)
        self.assertEqual(trades, [])
        self.assertEqual(cnt["no_fill_locked"], 1)

    def test_buy_stop_fills_at_level_and_never_credits_target_that_day(self):
        # level = signal-day high (101); next day trades 100.5 -> 115: fill 101,
        # target 111.1 touched but the high may have come first -> not credited
        rows = flat(31) + [(100.5, 115, 100, 112, 1000)] + flat(3, 112)
        (t,), _ = run(rows, entry_mode="buy_stop", entry_level="high", max_hold=2)
        self.assertAlmostEqual(t["entry"], 101)
        self.assertEqual(t["entry_kind"], "intraday")
        self.assertEqual(t["reason"], "target")         # credited on day 2 instead
        self.assertEqual(t["exit_date"], bars_from(rows)[32][0])

    def test_buy_stop_expires(self):
        rows = flat(31) + flat(3, 99)
        trades, cnt = run(rows, entry_mode="buy_stop", entry_level="high * 1.05", entry_valid_days=2)
        self.assertEqual(trades, [])
        self.assertEqual(cnt["not_triggered"], 1)

    def test_atr_trailing_stop_ratchets(self):
        up = [(100 + i, 101 + i, 99 + i, 100.5 + i, 1000) for i in range(10)]
        rows = flat(31) + up + [(105, 105, 95, 96, 1000)] + flat(3, 96)
        (t,), _ = run(rows, stop="atr:3", target="none", trail="atr:2")
        self.assertEqual(t["reason"], "trail")
        self.assertGreater(t["exit"], t["stop"])         # trailed above the initial stop

    def test_exit_rule_exits_next_open(self):
        rows = flat(31) + [(100, 101, 99, 100, 1000), (100, 101, 99, 97, 1000), (98, 99, 96, 97, 1000)] + flat(2, 97)
        (t,), _ = run(rows, stop="pct:20", target="none", exit="change_pct < -2")
        self.assertEqual(t["reason"], "rule")
        self.assertEqual((t["exit"], t["exit_date"]), (98, bars_from(rows)[33][0]))

    def test_invalid_levels_skip_trade(self):
        # expr stop above the fill (signal-day high as the stop)
        rows = flat(31) + flat(5)
        trades, cnt = run(rows, stop="expr:high * 1.1")
        self.assertEqual(trades, [])
        self.assertEqual(cnt["invalid_levels"], 1)

    def test_suspect_path_flagged(self):
        rows = flat(31) + [(100, 101, 99, 100, 1000), (10, 11, 9, 10, 1000)] + flat(2, 10)
        (t,), _ = run(rows, stop="pct:95", target="none", max_hold=3)
        self.assertTrue(t["suspect"])


class TestSpec(unittest.TestCase):
    def test_errors(self):
        for spec, msg in (({"entry": ""}, "entry rule"), ({"entry": "rsi14 >"}, "unexpected"),
                          ({"entry": "rsi14 > 1", "stop": "atr:x"}, "number"),
                          ({"entry": "rsi14 > 1", "stop": "none", "target": "r:2"}, "needs a stop"),
                          ({"entry": "age > 1"}, "unknown field"),
                          ({"entry": "rsi14 > 1", "stop": "none", "target": "none", "max_hold": 5,
                           "portfolio": {"sizing": "risk"}}, "risk sizing")):
            with self.assertRaises(ValueError) as cm:
                bt.prepare(spec)
            self.assertIn(msg, str(cm.exception))

    def test_lookahead_warning(self):
        _, w = bt.prepare({"entry": '"NIFTY50" in indices'})
        self.assertTrue(any("look-ahead" in x for x in w))


class TestCostsAndPortfolio(unittest.TestCase):
    def test_costs(self):
        b, s = bt.cost_pcts(bt.COSTS)
        # buy: STT .1 + stamp .015 + SEBI .0001 + exch .00307*1.18 + slip .05
        self.assertAlmostEqual(b * 100, 0.1 + 0.015 + 0.0001 + 0.00307 * 1.18 + 0.05)
        self.assertAlmostEqual(s * 100, 0.1 + 0.0001 + 0.00307 * 1.18 + 0.05)
        t = bt.apply_costs([{"entry": 100.0, "exit": 100.0, "stop": 95.0}], bt.COSTS)[0]
        self.assertLess(t["net_pct"], -0.3)                # a flat trade loses the costs

    def _trade(self, sym, ed, xd, e, x, rank=1.0):
        return {"sym": sym, "entry_date": ed, "exit_date": xd, "entry": e, "exit": x, "stop": e * 0.9,
                "entry_kind": "open", "exit_at_open": False, "rank": rank,
                "path": [(ed, e), (xd, x)], "net_pct": 0, "net_r": 0}

    def test_slots_and_cash_conservation(self):
        trades = [self._trade("A", "2024-01-02", "2024-01-03", 100, 110, rank=3),
                  self._trade("B", "2024-01-02", "2024-01-03", 50, 50, rank=2),
                  self._trade("C", "2024-01-02", "2024-01-03", 20, 20, rank=1)]
        costs = dict(bt.COSTS, **{k: 0 for k in bt.COSTS})
        p = {"capital": 10000, "max_positions": 2, "sizing": "equal", "risk_pct": 1, "max_alloc_pct": 100,
             "rank": "turnover", "rank_desc": True}
        curve, taken, skipped, _ = bt.portfolio(trades, p, costs, ["2024-01-02", "2024-01-03"])
        self.assertEqual([t["sym"] for t in taken], ["A", "B"])   # best rank first, 2 slots
        self.assertEqual(skipped["slots"], 1)
        # A: 50 shares 100 -> 110 = +500; B flat. No costs -> equity 10500
        self.assertAlmostEqual(curve[-1][1], 10500)

    def test_risk_sizing(self):
        trades = [self._trade("A", "2024-01-02", "2024-01-03", 100, 100)]
        costs = dict(bt.COSTS, **{k: 0 for k in bt.COSTS})
        p = {"capital": 100000, "max_positions": 10, "sizing": "risk", "risk_pct": 1, "max_alloc_pct": 100,
             "rank": "turnover", "rank_desc": True}
        _, taken, _, _ = bt.portfolio(trades, p, costs, ["2024-01-02", "2024-01-03"])
        self.assertEqual(taken[0]["shares"], 100)          # 1 % of 1L = 1000 / risk 10 per share


if __name__ == "__main__":
    unittest.main()
