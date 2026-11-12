# NSE · BSE Real-time Screener

A TradingView-style stock screener for every NSE and BSE equity (~4,200 symbols: 2,600 NSE + 1,600 BSE-only),
updating live in the browser. Python standard library only, with no `pip install` step.

```bash
.venv/bin/python main.py universe        # NSE + BSE symbol list from the official bhavcopies (~7 s)
.venv/bin/python main.py sync            # 2 years of daily history, once (~10 min; cached, incremental after)
.venv/bin/python main.py serve           # open http://127.0.0.1:8765/
.venv/bin/python main.py scan "rsi14 < 30 and turnover > 5cr" --sort rsi14 --asc
.venv/bin/python main.py bt-sync         # 10 years of daily history for backtests, once (~13 min, ~100 MB)
.venv/bin/python main.py backtest "double_bottom and turnover > 1cr" --stop expr:db_stop --target expr:db_target --hold 40
.venv/bin/python -m unittest discover -s tests   # 100 tests, offline
```

`serve` works without `sync`: quotes show right away and indicators fill in
as the background history sync reaches each symbol, most-traded first.

## Filter language

```
rsi14 < 30 and price > sma200 and turnover > 5cr
crosses_above(ema9, ema21) and 40 < rsi14 < 70
breakout_20d and rvol_tod > 2
"NIFTY50" in indices and change_pct > 1
industry in ["IT", "Healthcare"] or contains(name, "bank")
double_bottom and db_score >= 60
```

- Operators: `and or not`, `< <= > >= == !=`, `in` / `not in`, `+ - * /`. Comparisons can be chained.
- Number suffixes: `5k`, `10L`, `2cr`.
- Functions: `crosses_above`, `crosses_below`, `abs`, `min`, `max`, `pct(a,b)`, `contains`.
- About 110 fields: price/volume, SMA/EMA 5–200, RSI, MACD, ADX/DI, ATR, Bollinger, 52-week stats, performance, relative volume, and 19 pattern flags (breakouts, 52w highs, crosses, bull flag, double bottom with a 0–100 score, NR7, gaps…).
- `high_52w`/`low_52w` use whatever history exists (at least 20 sessions), like TradingView, so a recent listing shows its post-listing high; `hist_days` says how many sessions that is.
- A field with no value never matches. For example, `sma200` on a stock with 6 months of history is empty, not zero.

## Backtesting

Open **http://127.0.0.1:8765/backtest** (or the *Backtest* tab, which carries over the current screener filter).
The entry rule is a screener filter; it is evaluated at every day's close over 10 years of daily bars for every
NSE and BSE stock, with exactly the indicator code the live screener uses.

| | |
|---|---|
| Entry | next day's open (default) · a buy stop at a level (`high`, `db_neckline`…) valid N days · the signal day's close (optimistic) |
| Exit | stop `pct:5` / `atr:2` / `expr:db_stop` · target `r:2` / `pct:10` / `atr:3` / `expr:db_target` · trailing `atr:3` / `pct:8` · max days · an exit rule (`price < ema21`, filled next open) |
| Portfolio | capital, max positions, risk-%-per-trade or equal-weight sizing, max % in one stock, which signals win when slots are full |
| Costs | STT 0.1% both sides, stamp 0.015% on buys, NSE/SEBI fees + 18% GST, ₹23.6 DP per sell, slippage per fill |
| Output | CAGR, max drawdown, Sharpe vs NIFTY 50 buy-and-hold; expectancy in % and R with a 95% bootstrap interval; win rate, profit factor, by-year table, first vs second half, R distribution, every trade (CSV) |

Realism rules: a signal can only trade from the next session; a gap through the stop fills at the open; a day that
touches both stop and target counts as a stop; no fills on zero-volume or single-price (circuit-locked) days; trades
through a >45% one-day move (bad Yahoo data) are dropped. **Still biased upward by survivorship**: the stock list
is today's, so companies that were delisted or merged are missing. Index membership (`indices`) is today's too, so
the page warns when a rule uses it. Results are saved in `results/backtests/`.

## STRATLAB Studio: build strategies without code

Open **http://127.0.0.1:8765/studio**. You build a strategy with dropdowns instead of writing rules:

1. **Market**: one instrument (any NSE/BSE stock, NIFTY/BANKNIFTY/SENSEX, BTC-USD, EURUSD=X, GC=F, AAPL... any
   Yahoo symbol, whose 10-year history is fetched on first use), or every NSE/BSE stock at once.
2. **Entry conditions**: `[indicator] [crosses above / is above / is between / is rising…] [indicator or value]`,
   with ALL/ANY groups that can be nested and negated, plus the 20 pattern flags. EMA, SMA and RSI accept **any period**
   (EMA 13, SMA 30, RSI 2). The right-hand side takes a multiplier (`volume > 2 × avg volume 20`).
3. **Exit & risk**: stop (% / ATR / at a level such as the signal-day low or the double-bottom stop), target
   (% / R / ATR / level), trailing stop, max days, and an exit rule built the same way.
4. **Sizing & costs**: capital, all-in or fixed-risk sizing, India delivery charges or a flat % for other markets.

**Chart builder:** *Draw level* → click the chart → "when the close crosses above 2,512" becomes a condition.
*Draw zone* → two clicks → "close is inside the zone". Drawn rules show as dashed lines and are ordinary
conditions in the builder (tagged *chart*), so you can edit them there.

**Results:** net profit, CAGR against buy & hold of the same instrument (NIFTY 50 for the universe), win rate,
profit factor, drawdown, expectancy in R, Sharpe, time in market, a 95% "is this luck?" check, equity curve, a
year-by-year table, and every trade. Click a trade to see its entry, stop and target on the chart. **Library** holds
templates, your saved strategies and recent runs (reopen a run with its strategy).

How it works: both builders produce one JSON format, the *Strategy IR* (`screener/strategy.py`, saved in
`strategies/`). It compiles to the filter language above and runs on the same backtester, with the same fills,
costs and bias rules. The rule the Studio shows under the builder is exactly what is tested. The indicator lines
on the chart are computed by the backtester's own code, so they show exactly the values the rule was tested on.

Not yet: intraday timeframes, short selling, options chains, SMC patterns (FVG, BOS, CHoCH, liquidity sweeps),
parameter optimisation and walk-forward tests.

## How "real-time" works and its limits

| | |
|---|---|
| Quotes | Yahoo spark is polled 20 symbols per request. A full sweep of all NSE+BSE symbols takes about 25–30 s. Symbols currently on screen are refreshed every 3 s. |
| Latency | Seconds, not ticks. Yahoo's NSE/BSE quotes are near real-time but unofficial. Every row carries its data age, and rows older than 5 minutes during market hours show a "stale" badge. For true tick-by-tick data, a broker WebSocket feed can replace the poller (see ROADMAP §11). |
| Indicators | Recomputed incrementally on each tick from yesterday's state plus the live price. The math matches TradingView's (Wilder RSI/ATR/ADX, SMA-seeded EMA). |
| Change % | Measured from the official previous close (NSE/BSE bhavcopy), including after Muhurat sessions. |
| After the close | Once the exchanges publish the day's bhavcopy (~18:00 IST), the official open/high/low/close/volume replace Yahoo's for that session (`official_eod` = true). Yahoo's volume is short for ~2 % of symbols. |
| Rate limits | One adaptive limiter (AIMD) is shared by the whole process: it halves the request rate on HTTP 429 and backs off globally. |

## Layout

```
main.py                CLI: universe | sync | serve | scan
screener/clock.py      IST clock, NSE holidays + special sessions, market state
screener/net.py        rate limiter, retries, atomic cache writes
screener/yahoo.py      spark / v8 chart parsers (defensive)
screener/universe.py   NSE + BSE symbol list (bhavcopy, EQUITY_L, NIFTY lists), ISIN dedupe
screener/history.py    daily bars cache, incremental sync, split detection
screener/specials.py   Muhurat/special-session bars from the bhavcopy (Yahoo lacks them)
screener/indicators.py incremental indicators (base + live step)
screener/patterns.py   breakouts, bull flag, double bottom, NR7, crosses…
screener/expr.py       filter language (no eval), three-valued NULL logic
screener/fields.py     field registry + presets
screener/engine.py     live engine: scheduler, workers, rows, validation
screener/backtest.py   backtester: day-by-day walk, fills/exits, costs, portfolio, statistics, any-period EMA/SMA/RSI
screener/strategy.py   STRATLAB Strategy IR: validation, compiler to rules, catalog, save/load
screener/server.py     HTTP + Server-Sent Events, backtest jobs
screener/web/index.html  the screener UI (vanilla JS, works offline)
screener/web/backtest.html  the backtest UI
screener/web/studio.html    STRATLAB Studio (visual + chart builder, results); vendor/ = Lightweight Charts 4.2 (Apache-2.0)
strategies/            saved strategies (example-*.json are the templates)
data/                  runtime cache (universe, history, special sessions; safe to delete)
```

Configuration lives in `data/config.json`, which is optional:
`{"exchanges": ["NSE","BSE"], "include_sme": false, "workers": 4, "rate": 6, "min_turnover": 0, "port": 8765}`.
Holidays and special-session hours not yet built in go in `data/holidays.json`:
`{"holidays": ["2027-01-26"], "special_sessions": {"2027-10-29": ["18:00","19:00"]}}`.

A screen is a list of charts that match a rule, not a list of stocks to buy. This is not investment advice.
# Screener
