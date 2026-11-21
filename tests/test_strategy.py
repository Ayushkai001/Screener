"""STRATLAB: Strategy IR compiler, custom-period indicators, and the engine
fixes that came with them (10-year merge limit, volume-less instruments)."""

import copy
import datetime
import math
import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from screener import backtest as bt  # noqa: E402
from screener import history, indicators  # noqa: E402
from screener import strategy as st  # noqa: E402

D0 = datetime.date(2020, 1, 1)


def ind(i, p=None, **kw):
    return dict({"kind": "ind", "ind": i, "params": p or {}}, **kw)


def val(v):
    return {"kind": "value", "value": v}


def cond(left, op, right=None, **kw):
    c = {"type": "cond", "left": left, "op": op}
    if right is not None:
        c["right"] = right
    c.update(kw)
    return c


def group(op, *items, negate=False):
    return {"type": "group", "op": op, "negate": negate, "items": list(items)}


def ir_with(entry, **kw):
    ir = st.default_strategy()
    ir["entry"] = entry
    ir.update(kw)
    return ir


def wave(n, v=1000.0):
    """Deterministic up/down closes: plenty of crosses and RSI swings."""
    out = []
    for i in range(n):
        c = 100 + 10 * math.sin(i / 7.0) + 3 * math.sin(i / 2.3) + i * 0.02
        out.append(((D0 + datetime.timedelta(days=i)).isoformat(), c, c * 1.01, c * 0.99, c, v))
    return out


class TestCompile(unittest.TestCase):
    def test_default_compiles(self):
        spec, warnings = st.compile_strategy(st.default_strategy())
        self.assertEqual(spec["entry"], "crosses_above(ema9, ema21) and price > ema50")
        self.assertEqual(spec["exit"], "crosses_below(ema9, ema21)")
        self.assertEqual((spec["stop"], spec["target"]), ("pct:3", "pct:6"))
        self.assertEqual(spec["symbols"], ["RELIANCE.NS"])
        self.assertEqual(spec["benchmark"], "RELIANCE.NS")      # single instrument: vs its own buy & hold
        self.assertEqual(spec["portfolio"]["max_positions"], 1)
        self.assertEqual(warnings, [])

    def test_nested_groups_and_operators(self):
        e = group("and",
                  cond(ind("close"), ">", ind("ema", {"period": 200})),
                  group("or",
                        cond(ind("rsi", {"period": 7}), "between", val(40), right2=val(70)),
                        cond(ind("volume"), ">", ind("avg_vol20", mult=2)),
                        cond(ind("ema", {"period": 13}), "rising"),
                        {"type": "pattern", "pattern": "double_bottom", "negate": True}),
                  group("and", cond(ind("rsi"), ">", val(80)), negate=True))
        spec, _ = st.compile_strategy(ir_with(e))
        self.assertEqual(spec["entry"], "price > ema200 and (40 <= rsi7 <= 70 or volume > avg_vol20 * 2 "
                                        "or ema13 > ema13_prev or not double_bottom) and (not (rsi14 > 80))")

    def test_rising_on_close_uses_prev_close(self):
        spec, _ = st.compile_strategy(ir_with(group("and", cond(ind("close"), "rising"))))
        self.assertEqual(spec["entry"], "price > prev_close")

    def test_disabled_and_empty_groups_are_skipped(self):
        e = group("and", cond(ind("close"), ">", val(1)), group("or"),
                  cond(ind("close"), "<", val(5), disabled=True))
        self.assertEqual(st.compile_strategy(ir_with(e))[0]["entry"], "price > 1")

    def test_errors_name_the_path(self):
        cases = [
            (group("and"), "entry: add at least one condition"),
            (group("and", cond(ind("turnover"), "crosses_above", val(5))), "entry.items[0].left"),
            (group("and", cond(ind("ema", {"period": 1}), ">", val(5))), "entry.items[0].left.params.period"),
            (group("and", cond(ind("close"), "==", val(5))), "entry.items[0].op"),
            (group("and", cond(ind("nope"), ">", val(5))), "unknown indicator"),
            (group("and", cond(ind("close"), ">", {"kind": "value", "value": "abc"})), "entry.items[0].right.value"),
            (group("and", {"type": "pattern", "pattern": "nope"}), "unknown pattern"),
        ]
        for entry, msg in cases:
            with self.subTest(msg=msg):
                with self.assertRaises(st.StrategyError) as cm:
                    st.compile_strategy(ir_with(entry))
                self.assertIn(msg, str(cm.exception))

    def test_risk_execution_universe_costs(self):
        ir = st.default_strategy()
        ir["instrument"] = {"mode": "universe", "exchanges": ["NSE", "XYZ"], "min_turnover": 5e7}
        ir["risk"] = {"stop": {"type": "level", "level": ind("db_stop")}, "target": {"type": "r", "value": 2},
                      "trail": {"type": "atr", "value": 3}, "max_hold": 40}
        ir["execution"] = {"entry_mode": "buy_stop", "entry_level": ind("high"), "entry_valid_days": 3}
        ir["costs"] = {"profile": "flat", "fee_pct": 0.2, "slippage_pct": 0.1}
        ir["portfolio"] = {"capital": 1e6, "sizing": "risk", "risk_pct": 1}     # slots left to the default
        spec, warnings = st.compile_strategy(ir)
        self.assertEqual((spec["stop"], spec["target"], spec["trail"]), ("expr:db_stop", "r:2", "atr:3"))
        self.assertEqual((spec["entry_mode"], spec["entry_level"], spec["entry_valid_days"]), ("buy_stop", "high", 3))
        self.assertEqual(spec["exchanges"], ["NSE"])
        self.assertEqual(spec["min_turnover"], 5e7)
        self.assertNotIn("symbols", spec)
        self.assertEqual((spec["portfolio"]["max_positions"], spec["portfolio"]["max_alloc_pct"]), (10, 20))
        b, s = bt.cost_pcts(spec["costs"])
        self.assertAlmostEqual(b * 100, 0.3)        # fee + slippage, nothing Indian
        self.assertAlmostEqual(s * 100, 0.3)
        self.assertEqual(spec["costs"]["dp_flat"], 0)

    def test_short_and_intraday_refused(self):
        with self.assertRaises(st.StrategyError):
            st.compile_strategy(ir_with(st.default_strategy()["entry"], action="SELL"))
        with self.assertRaises(st.StrategyError):
            st.compile_strategy(ir_with(st.default_strategy()["entry"], timeframe="5m"))

    def test_bad_symbol_refused(self):
        ir = st.default_strategy()
        ir["instrument"] = {"mode": "symbol", "symbols": ["../../etc/passwd"]}
        with self.assertRaises(st.StrategyError):
            st.compile_strategy(ir)

    def test_chart_fields(self):
        f = st.chart_fields(st.default_strategy())
        self.assertEqual([(x["field"], x["overlay"]) for x in f],
                         [("ema9", "price"), ("ema21", "price"), ("ema50", "price")])

    def test_templates_compile(self):
        for name in os.listdir(os.path.join(ROOT, "strategies")):
            if name.startswith("example-"):
                with self.subTest(name):
                    st.compile_strategy(st.load(name[:-5], os.path.join(ROOT, "strategies")))


class TestLibrary(unittest.TestCase):
    def test_save_load_delete(self):
        with tempfile.TemporaryDirectory() as d:
            ir = st.default_strategy()
            ir["name"] = "My EMA idea!"
            saved = st.save(ir, d)
            self.assertEqual(saved["id"], "my-ema-idea")
            self.assertEqual(st.load("my-ema-idea", d)["name"], "My EMA idea!")
            self.assertEqual([s["id"] for s in st.list_saved(d)], ["my-ema-idea"])
            self.assertIsNone(st.load("../x", d))
            self.assertTrue(st.delete("my-ema-idea", d))
            self.assertEqual(st.list_saved(d), [])

    def test_unrunnable_not_saved(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(st.StrategyError):
                st.save(ir_with(group("and")), d)
            self.assertEqual(os.listdir(d), [])


class TestCustomPeriods(unittest.TestCase):
    def test_custom_equals_builtin(self):
        """The any-period code must give exactly the built-in fields' values."""
        bars = wave(400)
        cust = bt.custom_series(bars, ["ema21", "sma50", "rsi14"])
        series = bt.series(bars, ["ema21", "sma50", "rsi14"])
        for k in cust:
            for t, (a, b) in enumerate(zip(cust[k], series[k])):
                if t == 0:
                    continue        # day 0 has no row in the walk
                if a is None or b is None:
                    self.assertEqual(a, b, (k, t))
                else:
                    self.assertAlmostEqual(a, b, places=9, msg=(k, t))

    def test_custom_fields_detected(self):
        self.assertEqual(bt.custom_fields("ema13 > ema21 and rsi7 < 30", "crosses_above(sma30, sma200)"),
                         ["ema13", "rsi7", "sma30"])
        with self.assertRaises(bt.SpecError):
            bt.custom_fields("ema999 > 1")

    def test_crosses_with_custom_period(self):
        bars = wave(300)
        cp = bt._Compiled(bt.prepare({"entry": "crosses_above(ema5, ema13)", "stop": "pct:5",
                                      "target": "pct:5", "min_turnover": 0})[0])
        trades = bt.simulate(bars, {"sym": "W"}, cp)
        self.assertGreater(len(trades), 3)
        e5 = bt.custom_series(bars, ["ema5", "ema13"])
        idx = {b[0]: i for i, b in enumerate(bars)}
        for t in trades:
            i = idx[t["signal_date"]]
            self.assertGreater(e5["ema5"][i], e5["ema13"][i])
            self.assertLessEqual(e5["ema5"][i - 1], e5["ema13"][i - 1])
            self.assertEqual(idx[t["entry_date"]], i + 1)          # never filled on the signal bar

    def test_ema10_built_in(self):
        from screener import fields
        self.assertIn("ema10", fields.FIELDS)
        self.assertIn("ema10_prev", fields.FIELDS)
        bars = wave(100)
        b = indicators.Base(bars)
        f = indicators.live(b, 100.0)
        self.assertIsNotNone(f.get("ema10"))
        self.assertEqual(bt.custom_fields("ema10 > ema20"), [])

    def test_supertrend_and_stoch_backtest(self):
        bars = wave(300)
        cp = bt._Compiled(bt.prepare({"entry": "supertrend_dir == 1 and stoch_bull_cross", "stop": "pct:3",
                                      "target": "pct:6", "min_turnover": 0})[0])
        trades = bt.simulate(bars, {"sym": "W"}, cp)
        self.assertIsInstance(trades, list)

    def test_custom_indicators_extended(self):
        cf = bt.custom_fields("atr10 < 5 and high > high_35d and low < low_15d")
        self.assertEqual(sorted(cf), ["atr10", "high_35d", "low_15d"])
        bars = wave(100)
        cs = bt.custom_series(bars, cf)
        self.assertEqual(len(cs["atr10"]), len(bars))
        self.assertEqual(len(cs["high_35d"]), len(bars))
        self.assertEqual(len(cs["low_15d"]), len(bars))

    def test_short_selling_execution(self):
        bars = wave(300)
        spec, _ = st.compile_strategy({
            "action": "SHORT",
            "instrument": {"mode": "symbol", "symbols": ["RELIANCE.NS"]},
            "entry": {"type": "group", "op": "and", "items": [
                {"type": "cond", "left": {"kind": "ind", "ind": "ema", "params": {"period": 5}},
                 "op": "crosses_below", "right": {"kind": "ind", "ind": "ema", "params": {"period": 13}}}
            ]},
            "risk": {"stop": {"type": "pct", "value": 3}, "target": {"type": "pct", "value": 5}},
            "execution": {"entry_mode": "next_open"},
        })
        cp = bt._Compiled(spec)
        trades = bt.simulate(bars, {"sym": "W"}, cp)
        self.assertGreater(len(trades), 0)
        for tr in trades:
            self.assertEqual(tr["side"], "short")
            if tr["exit"] < tr["entry"]:
                self.assertGreater(tr["ret_pct"], 0)
            elif tr["exit"] > tr["entry"]:
                self.assertLess(tr["ret_pct"], 0)


class TestEngineFixes(unittest.TestCase):
    def test_merge_keeps_store_limit(self):
        old = [((D0 + datetime.timedelta(days=i)).isoformat(), 1, 1, 1, 100.0, 1) for i in range(2400)]
        new = [old[-1], ((D0 + datetime.timedelta(days=2400)).isoformat(), 1, 1, 1, 100.0, 1)]
        bars, ok = history.merge(old, new, 2600)
        self.assertTrue(ok)
        self.assertEqual(len(bars), 2401)                     # not cut to the screener's 520
        self.assertEqual(len(history.merge(old, new)[0]), history.MAX_BARS)

    def test_forex_without_volume_trades(self):
        bars = [(d, o, h, l, c, 0.0) for d, o, h, l, c, _ in wave(300)]
        cp = bt._Compiled(bt.prepare({"entry": "crosses_above(ema9, ema21)", "stop": "pct:2",
                                      "target": "pct:2", "min_turnover": 0})[0])
        self.assertGreater(len(bt.simulate(bars, {"sym": "FX"}, cp)), 0)

    def test_mostly_volume_still_blocks_zero_days(self):
        rows = wave(300)
        zero = {r[0] for r in rows[::10]}
        bars = [(d, o, h, l, c, 0.0 if d in zero else v) for d, o, h, l, c, v in rows]
        cp = bt._Compiled(bt.prepare({"entry": "crosses_above(ema9, ema21)", "stop": "pct:2",
                                      "target": "pct:2", "min_turnover": 0})[0])
        for t in bt.simulate(bars, {"sym": "EQ"}, cp):
            self.assertNotIn(t["entry_date"], zero)

    def test_external_symbol_runs_from_cache(self):
        with tempfile.TemporaryDirectory() as d:
            bars = wave(400)
            bt.net.write_json(os.path.join(d, bt._fname("BTC-USD")),
                              {"ysym": "BTC-USD", "fetched": 0, "bars": [list(b) for b in bars]})
            spec, _ = st.compile_strategy(dict(st.default_strategy(), instrument={"mode": "symbol",
                                                                                  "symbols": ["BTC-USD"]}))
            res = bt.run(spec, {"symbols": []}, hist_root=d, workers=1, log=lambda *a: None)
            self.assertGreater(res["every_signal"]["trades"], 0)
            self.assertEqual(res["benchmark"]["symbol"], "BTC-USD")
            self.assertFalse(any("survivorship" in w for w in res["warnings"]))


class TestStrategyAPI(unittest.TestCase):
    def test_plain_python_strategy_long_and_short(self):
        from screener.strategy_api import BaseStrategy, Action, run_strategy, Bar, Position

        class SimpleStrat(BaseStrategy):
            def on_bar(self, bar: Bar, position: Position, indicators: dict):
                # Buy on even multiples of 30, sell 10 bars later
                if position.side == "flat":
                    if bar.index % 40 == 10:
                        return Action.BUY
                    elif bar.index % 40 == 30:
                        return Action.SHORT
                elif position.side == "long" and position.bars_held >= 5:
                    return Action.SELL
                elif position.side == "short" and position.bars_held >= 5:
                    return Action.COVER
                return Action.HOLD

        bars = wave(160)
        res = run_strategy(SimpleStrat(), bars, capital=100000.0, stop_pct=2.0, target_pct=4.0)
        self.assertGreater(res["trades_count"], 0)
        self.assertIn("win_rate_pct", res)
        self.assertIn("max_drawdown_pct", res)
        self.assertEqual(len(res["equity_curve"]), len(bars))
        
        # Check that both long and short trades occurred
        sides = {t["side"] for t in res["trades"]}
        self.assertIn("long", sides)
        self.assertIn("short", sides)


if __name__ == "__main__":
    unittest.main()
