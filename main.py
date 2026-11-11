#!/usr/bin/env python3
"""NSE/BSE real-time screener.

    python3 main.py universe [--sme] [--exchange nse|bse|both]   build data/universe.json
    python3 main.py sync [--limit N]                             fetch daily history (foreground)
    python3 main.py serve [--port 8765]                          live screener UI in the browser
    python3 main.py scan "rsi14 < 30 and turnover > 5cr" [--sort rsi14 --asc --limit 30]
    python3 main.py bt-sync [--top N]                            10 years of daily history for backtests
    python3 main.py backtest "crosses_above(ema9, ema21)" [--stop atr:2 --target r:2 --hold 20 ...]

Options for every command come from data/config.json too (CLI wins):
    {"exchanges": ["NSE","BSE"], "include_sme": false, "workers": 4, "rate": 6,
     "min_turnover": 0, "port": 8765}

Data: Yahoo Finance (free, unofficial; NSE/BSE quotes polled, not streamed)
and the official NSE/BSE bhavcopies. A screen is a list of charts that match a
rule, not advice to buy or sell anything.
"""

import argparse
import datetime
import os
import sys
import time

from screener import net, universe
from screener.clock import IST, Calendar, now_utc

DATA = "data"
UNIVERSE = os.path.join(DATA, "universe.json")
CONFIG = os.path.join(DATA, "config.json")


def load_config():
    return net.read_json(CONFIG) or {}


def exchanges_from(a, cfg):
    if getattr(a, "exchange", None):
        return {"nse": ("NSE",), "bse": ("BSE",), "both": ("NSE", "BSE")}[a.exchange]
    return tuple(cfg.get("exchanges", ("NSE", "BSE")))


def cmd_universe(a, cfg):
    client = net.Client(net.RateLimiter(rate=2.0))
    doc = universe.fetch_and_build(client, include_sme=a.sme or cfg.get("include_sme", False),
                                   exchanges=exchanges_from(a, cfg))
    net.write_json(UNIVERSE, doc)
    by = {}
    for s in doc["symbols"]:
        by[s["exchange"]] = by.get(s["exchange"], 0) + 1
    print("Universe: %d symbols (%s) -> %s" % (doc["count"], ", ".join("%s %d" % kv for kv in sorted(by.items())), UNIVERSE))
    return 0


def ensure_universe(cfg, cal):
    """Load the universe; rebuild it when missing or older than the last
    completed session's bhavcopy (new listings, renames, suspensions)."""
    doc = net.read_json(UNIVERSE)
    want = cal.last_completed_session(now_utc())
    have = None
    if doc:
        have = max((d for d in (doc.get("bhavcopy") or {}).values() if d), default=None)
    # bhavcopies appear ~18:00-19:00 IST; before then yesterday's is the newest
    stale = doc is None or (have or "") < cal.prev_trading_day(want).isoformat() or (
        (have or "") < want.isoformat() and now_utc().astimezone(IST).hour >= 19)
    if stale:
        print("Universe %s; rebuilding..." % ("missing" if doc is None else "from %s is stale" % have))
        try:
            client = net.Client(net.RateLimiter(rate=2.0))
            doc = universe.fetch_and_build(client, include_sme=cfg.get("include_sme", False),
                                           exchanges=tuple(cfg.get("exchanges", ("NSE", "BSE"))))
            net.write_json(UNIVERSE, doc)
        except net.FetchError as e:
            if doc is None:
                raise SystemExit("cannot build the universe: %s" % e)
            print("warning: rebuild failed (%s); using the cached universe" % e)
    print("Universe: %d symbols (bhavcopy %s)" % (doc["count"], doc.get("bhavcopy")))
    return doc


def make_engine(cfg, a=None):
    from screener.engine import Engine
    cal = Calendar.load(os.path.join(DATA, "holidays.json"))
    doc = ensure_universe(cfg, cal)
    if a is not None and getattr(a, "top", None):
        doc = dict(doc, symbols=doc["symbols"][:a.top])   # most traded first
    eng_cfg = {k: cfg[k] for k in ("workers", "rate", "max_rate", "focus_interval", "sweep_interval_open",
                                   "sweep_interval_idle", "fetch_open", "min_turnover") if k in cfg}
    return Engine(doc, eng_cfg, cal, hist_root=os.path.join(DATA, "history"))


def cmd_serve(a, cfg):
    from screener import server
    eng = make_engine(cfg, a)
    eng.start()
    server.serve(eng, a.host or cfg.get("host", "127.0.0.1"), a.port or cfg.get("port", 8765))
    return 0


def cmd_sync(a, cfg):
    eng = make_engine(cfg, a)
    n = eng.history.load(eng.order)
    eng._queue_history_due()                 # fills the queue; we run it here instead
    rank = {s: i for i, s in enumerate(eng.order)}
    todo = sorted(eng._queued_hist, key=rank.get)
    eng._tasks.clear()
    eng._hist_tasks.clear()
    eng._queued_hist.clear()
    print("History cache: %d; to sync: %d" % (n, len(todo)))
    import concurrent.futures as cf
    t0, done, fail, last_log = time.time(), 0, 0, 0.0
    with cf.ThreadPoolExecutor(eng.cfg["workers"]) as ex:
        futs = {ex.submit(eng.history.sync, s): s for s in todo}
        for f in cf.as_completed(futs):
            try:
                f.result()
                done += 1
            except (net.FetchError, ValueError):
                fail += 1
            if time.time() - last_log >= 15 or done + fail == len(todo):
                last_log = time.time()
                print("  %d/%d  %.0fs  rate %.1f/s  429s %d" % (done + fail, len(todo), time.time() - t0,
                                                                eng.client.limiter.rate,
                                                                eng.client.limiter.stats["429"]))
    print("Synced %d, failed %d in %.0fs" % (done, fail, time.time() - t0))
    return 0 if done else 1


def fmt(v, kind):
    if v is None:
        return "-"
    if kind == "pct":
        return "%+.2f%%" % v
    if kind == "vol":
        return "%.2fL" % (v / 1e5) if v < 1e7 else "%.2fCr" % (v / 1e7)
    if kind == "money":
        return "₹%.2fCr" % (v / 1e7)
    if isinstance(v, bool):
        return "yes" if v else ""
    if isinstance(v, float):
        return "%.2f" % v
    return str(v)


def cmd_scan(a, cfg):
    from screener import server
    from screener.fields import FIELDS
    eng = make_engine(cfg, a)
    eng.cfg["fetch_open"] = False
    try:
        server._compile(a.filter)   # fail fast on a bad filter, before any network
    except Exception as e:
        print("filter error: %s" % e, file=sys.stderr)
        return 1
    eng.start()
    t0 = time.time()
    while eng.stats["sweeps"] < 1 and time.time() - t0 < a.timeout:
        time.sleep(0.5)
    hq = eng.status()["history_queue"]
    if hq:
        print("note: %d symbols still waiting for history (run `main.py sync` first for full indicators)" % hq)
    res = server.screen(eng, {"filter": a.filter, "sort": a.sort, "desc": "0" if a.asc else "1",
                              "limit": str(a.limit), "cols": a.cols})
    eng.stop()
    cols = [c for c in res["columns"] if c not in ("ysym", "hist_ok", "note", "age")]
    idx = [res["columns"].index(c) for c in cols]
    table = [[fmt(r[i], FIELDS.get(c, {}).get("fmt")) for i, c in zip(idx, cols)] for r in res["rows"]]
    widths = [max(len(c), *(len(t[k]) for t in table)) if table else len(c) for k, c in enumerate(cols)]
    st = res["status"]
    print("%s | market %s | matched %d of %d quoted" % (st["now"], st["market"], res["matched"], res["total"]))
    print("  ".join(c.upper().ljust(w) for c, w in zip(cols, widths)))
    for t in table:
        print("  ".join(x.ljust(w) for x, w in zip(t, widths)))
    print("A screen is a list of charts that match a rule, not a list of stocks to buy.")
    return 0 if res["matched"] else 1


def _amount(x):
    """'1cr' / '50L' / '5k' / '250000' -> float."""
    x = str(x).strip().lower().replace(",", "").replace("₹", "")
    for suf, k in (("cr", 1e7), ("l", 1e5), ("k", 1e3)):
        if x.endswith(suf):
            return float(x[:-len(suf)]) * k
    return float(x)


def cmd_bt_sync(a, cfg):
    """10-year daily history for the backtester (data/history_bt). Separate
    from the screener's 2-year cache; incremental after the first run."""
    from screener import backtest as bt
    from screener.history import HistoryStore
    cal = Calendar.load(os.path.join(DATA, "holidays.json"))
    doc = ensure_universe(cfg, cal)
    syms = [s["ysym"] for s in doc["symbols"]]
    if a.top:
        syms = syms[:a.top]
    syms = [bt.BENCH] + syms
    client = net.Client(net.RateLimiter(rate=cfg.get("rate", 6), max_rate=cfg.get("max_rate", 10)))
    store = HistoryStore(bt.BT_ROOT, client, full_range=bt.BT_RANGE, max_bars=bt.BT_MAX_BARS)
    have = store.load(syms)
    last = cal.last_completed_session(now_utc()).isoformat()
    todo = [s for s in syms if not store.bars(s) or store.bars(s)[-1][0] < last]
    print("Backtest history: %d cached, %d to sync (10 years each; the first run takes ~15 min)" % (have, len(todo)))
    import concurrent.futures as cf
    t0, done, fail, last_log = time.time(), 0, 0, 0.0
    with cf.ThreadPoolExecutor(cfg.get("workers", 4)) as ex:
        futs = {ex.submit(store.sync, s): s for s in todo}
        for f in cf.as_completed(futs):
            try:
                f.result()
                done += 1
            except (net.FetchError, ValueError):
                fail += 1
            if time.time() - last_log >= 15 or done + fail == len(todo):
                last_log = time.time()
                print("  %d/%d  %.0fs  rate %.1f/s  429s %d" % (done + fail, len(todo), time.time() - t0,
                                                                client.limiter.rate, client.limiter.stats["429"]))
    print("Synced %d, failed %d in %.0fs" % (done, fail, time.time() - t0))
    return 0


def bt_spec_from_args(a):
    spec = {"entry": a.filter, "entry_mode": a.entry_mode, "entry_level": a.level,
            "entry_valid_days": a.valid, "max_gap_pct": a.max_gap, "stop": a.stop, "target": a.target,
            "trail": a.trail, "max_hold": a.hold, "exit": a.exit or "", "start": a.start, "end": a.end,
            "min_turnover": _amount(a.min_turnover),
            "portfolio": {"capital": _amount(a.capital), "max_positions": a.positions, "sizing": a.sizing,
                          "risk_pct": a.risk, "max_alloc_pct": a.max_alloc, "rank": a.rank,
                          "rank_desc": not a.asc},
            "costs": {"slippage_pct": a.slippage}}
    if a.exchange:
        spec["exchanges"] = {"nse": ["NSE"], "bse": ["BSE"], "both": ["NSE", "BSE"]}[a.exchange]
    return spec


def print_bt(res):
    ex, pf, bm = res["every_signal"], res["portfolio"], res.get("benchmark") or {}

    def f(v, fmt="%.2f"):
        return "-" if v is None else fmt % v
    print("\nEvery signal (each trade on its own, after costs): %d trades" % ex.get("trades", 0))
    if ex.get("trades"):
        ci = ex.get("expectancy_r_ci95")
        print("  win rate %s%%  avg win %s%%  avg loss %s%%  profit factor %s" % (
            f(ex["win_rate"], "%.1f"), f(ex["avg_win_pct"]), f(ex["avg_loss_pct"]), f(ex["profit_factor"])))
        print("  expectancy %s%% / trade, %s R  (95%% CI of R: %s)  avg hold %.1f days" % (
            f(ex["expectancy_pct"]), f(ex["expectancy_r"], "%.3f"),
            "%.3f .. %.3f" % tuple(ci) if ci else "-", ex["avg_bars"]))
        print("  exits: %s" % ", ".join("%s %d" % kv for kv in sorted(ex["exit_reasons"].items())))
    if pf.get("final"):
        print("Portfolio %s .. %s: %d trades taken (%d skipped: no slot, %d: no cash), exposure %.0f%%" % (
            pf["start"], pf["end"], pf["trades_taken"], pf["skipped"]["slots"], pf["skipped"]["cash"],
            pf["exposure_pct"]))
        print("  CAGR %s%%  total %s%%  max drawdown %s%%  Sharpe %s" % (
            f(pf["cagr_pct"]), f(pf["total_return_pct"]), f(pf["max_drawdown_pct"]), f(pf["sharpe"])))
    if bm:
        print("NIFTY 50 buy & hold, same dates: CAGR %s%%  max drawdown %s%%  Sharpe %s" % (
            f(bm["cagr_pct"]), f(bm["max_drawdown_pct"]), f(bm["sharpe"])))
    if res["by_year"]:
        print("By year: " + "  ".join("%s: %d tr %+.2f%%" % (y["year"], y["trades"], y["expectancy_pct"])
                                      for y in res["by_year"]))
    for w in res["warnings"]:
        print("note: " + w)
    print("Past results on today's stock list; not a forecast and not investment advice.")


def cmd_backtest(a, cfg):
    from screener import backtest as bt
    cal = Calendar.load(os.path.join(DATA, "holidays.json"))
    doc = net.read_json(UNIVERSE) or ensure_universe(cfg, cal)
    if a.top:
        doc = dict(doc, symbols=doc["symbols"][:a.top])
    spec = bt_spec_from_args(a)
    try:
        bt.prepare(spec)
    except (ValueError, bt.SpecError) as e:
        print("error: %s" % e, file=sys.stderr)
        return 1
    last = [0.0]

    def progress(x):
        if time.time() - last[0] > 5 or x >= 1:
            last[0] = time.time()
            print("  %3.0f%%" % (x * 100))
    res = bt.run(spec, doc, workers=a.workers, progress=progress)
    path = bt.save_result(res)
    print_bt(res)
    print("saved %s (%.0fs)" % (path, res["secs"]))
    if a.csv:
        bt.write_csv(res["trades"], a.csv)
        print("trades -> %s" % a.csv)
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    u = sub.add_parser("universe")
    u.add_argument("--sme", action="store_true")
    u.add_argument("--exchange", choices=["nse", "bse", "both"])
    s = sub.add_parser("serve")
    s.add_argument("--host")
    s.add_argument("--port", type=int)
    s.add_argument("--top", type=int, help="only the N most traded symbols")
    y = sub.add_parser("sync")
    y.add_argument("--top", type=int, help="only the N most traded symbols")
    c = sub.add_parser("scan")
    c.add_argument("filter")
    c.add_argument("--sort", default="turnover")
    c.add_argument("--asc", action="store_true")
    c.add_argument("--limit", type=int, default=30)
    c.add_argument("--cols", default="sym,price,change_pct,volume,rvol_tod,rsi14,turnover,industry")
    c.add_argument("--timeout", type=float, default=120)
    c.add_argument("--top", type=int, help="only the N most traded symbols")
    z = sub.add_parser("bt-sync")
    z.add_argument("--top", type=int, help="only the N most traded symbols")
    b = sub.add_parser("backtest")
    b.add_argument("filter", help="entry rule (screener filter language)")
    b.add_argument("--entry-mode", default="next_open", choices=["next_open", "signal_close", "buy_stop"])
    b.add_argument("--level", default="high", help="buy_stop level expression (default: signal-day high)")
    b.add_argument("--valid", type=int, default=1, help="days a buy_stop stays active")
    b.add_argument("--max-gap", type=float, help="skip fills gapping up more than this %%")
    b.add_argument("--stop", default="atr:2", help="none | pct:N | atr:N | expr:<expression>")
    b.add_argument("--target", default="r:2", help="none | pct:N | atr:N | r:N | expr:<expression>")
    b.add_argument("--trail", default="none", help="none | pct:N | atr:N")
    b.add_argument("--hold", type=int, default=20, help="max sessions in a trade (0 = no limit)")
    b.add_argument("--exit", help="exit rule checked at each close, e.g. 'price < ema21'")
    b.add_argument("--from", dest="start")
    b.add_argument("--to", dest="end")
    b.add_argument("--exchange", choices=["nse", "bse", "both"])
    b.add_argument("--min-turnover", default="1cr")
    b.add_argument("--capital", default="10L")
    b.add_argument("--positions", type=int, default=10)
    b.add_argument("--sizing", default="risk", choices=["risk", "equal"])
    b.add_argument("--risk", type=float, default=1.0, help="%% of equity risked per trade (sizing risk)")
    b.add_argument("--max-alloc", type=float, default=20.0, help="max %% of equity in one position")
    b.add_argument("--rank", default="turnover", help="field to pick by when signals exceed free slots")
    b.add_argument("--asc", action="store_true", help="rank ascending")
    b.add_argument("--slippage", type=float, default=0.05, help="%% per fill")
    b.add_argument("--top", type=int, help="only the N most traded symbols")
    b.add_argument("--workers", type=int)
    b.add_argument("--csv", help="also write the trade list to this CSV")
    a = p.parse_args(argv)
    try:   # progress must reach logs even when stdout is a file/pipe (nohup, launchd)
        sys.stdout.reconfigure(line_buffering=True)
    except AttributeError:
        pass
    cfg = load_config()
    os.makedirs(DATA, exist_ok=True)
    return {"universe": cmd_universe, "serve": cmd_serve, "sync": cmd_sync, "scan": cmd_scan,
            "bt-sync": cmd_bt_sync, "backtest": cmd_backtest}[a.cmd](a, cfg)


if __name__ == "__main__":
    sys.exit(main())
