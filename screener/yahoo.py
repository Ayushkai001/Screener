"""Yahoo Finance: URL builders and defensive parsers (spark + v8 chart).

Facts verified against live responses (Nov 2026), each one a bug if ignored:
  * spark answers HTTP 400 for more than 20 symbols in one request.
  * spark returns closes only (no open/high/low/volume arrays); the quote
    snapshot lives in `meta`: regularMarketPrice/Time/DayHigh/DayLow/Volume.
  * The official previous close (= NSE bhavcopy PrvsClsgPric) is
    meta.previousClose, which spark sends for interval=5m/1m but NOT for
    interval=1d; there only meta.chartPreviousClose has it - and only because
    range=1d. For longer ranges chartPreviousClose is the close *before the
    range starts*, so it is used only when meta.range == "1d".
  * Yahoo's daily bars match the official bhavcopy OHLCV on regular days,
    but Yahoo has NO data for special sessions (Muhurat trading 2026-11-08:
    no daily bar, no intraday bars). The next day's previousClose is the
    special session's close, which therefore differs from Yahoo's last bar
    (HDFCBANK: 784.10 official vs 788.25 on Yahoo's 11-06 bar). specials.py
    fills those bars from the bhavcopy.
  * Unknown / renamed symbols (TATAMOTORS.NS after the demerger) are simply
    missing from a spark answer; the rest of the batch is fine.
  * Symbols with & must be URL-encoded (M&M.NS -> M%26M.NS); hyphens are
    legal (BAJAJ-AUTO.NS). BSE works by ticker (RELIANCE.BO), not by scrip
    code (500325.BO returns nothing).
  * Arrays may contain null (no trade in that interval); daily bars may be
    duplicated for the current day; the live bar is partial.
"""

import urllib.parse

from .clock import ts_to_date

# Redundant endpoint hosts for Yahoo Finance API queries.
# Rationale: Providing query1 and query2 enables the HTTP Client to alternate
# hosts upon receiving 5xx server errors or timeouts.
HOSTS = ("https://query1.finance.yahoo.com", "https://query2.finance.yahoo.com")

# Maximum number of symbols allowed in a single spark request.
# Rationale: Yahoo's /v7/finance/spark endpoint strictly rejects any request
# with 21 or more symbols with HTTP 400 Bad Request.
SPARK_MAX = 20


def ysym(sym, exchange):
    """Convert an exchange ticker into a Yahoo Finance symbol.
    
    Rationale:
    Yahoo identifies National Stock Exchange equities with the suffix '.NS'
    and Bombay Stock Exchange equities with '.BO'.
    """
    return sym + (".NS" if exchange == "NSE" else ".BO")


def _q(sym):
    """URL-encode symbol names, encoding all characters including '&'.
    
    Rationale:
    Tickers like 'M&M.NS' contain '&'. If not explicitly percent-encoded (M%26M.NS),
    the query string parser interprets '&M.NS' as a distinct query parameter,
    corrupting the symbol list and returning missing data for Mahindra & Mahindra.
    """
    return urllib.parse.quote(sym, safe="")


def spark_urls(symbols, rng="1d", interval="1d"):
    """Construct /v7/finance/spark URLs for batched quote requests.
    
    Rationale:
    Polling 20 symbols per spark request is ~20x more efficient than querying
    individual chart endpoints. Both host mirrors are returned for failover.
    """
    if not 0 < len(symbols) <= SPARK_MAX:
        raise ValueError("spark takes 1..%d symbols, got %d" % (SPARK_MAX, len(symbols)))
    path = "/v7/finance/spark?symbols=%s&range=%s&interval=%s" % (
        ",".join(_q(s) for s in symbols), rng, interval)
    return [h + path for h in HOSTS]


def chart_urls(sym, rng="2y", interval="1d"):
    """Construct /v8/finance/chart URLs for daily historical bars.
    
    Rationale:
    'events=div%2Csplits' is requested so that stock split events are returned
    in the metadata payload, allowing HistoryStore to detect and adjust for splits.
    """
    path = "/v8/finance/chart/%s?range=%s&interval=%s&events=div%%2Csplits" % (_q(sym), rng, interval)
    return [h + path for h in HOSTS]


def _num(x):
    """Sanitize raw API values to float or None.
    
    Rationale:
    Financial API responses frequently contain None, string values, NaN, or Infinity
    (e.g., zero volume trades or unpriced suspensions). Sanitizing to None prevents
    TypeError in math calculations and produces valid JSON (standard JSON.parse in
    browsers rejects NaN/Infinity as invalid syntax).
    """
    if x is None:
        return None
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    if v != v or v in (float("inf"), float("-inf")):
        return None
    return v


def quote_from_meta(meta):
    """Extract and normalize live market metrics from a spark/chart `meta` dictionary.
    
    Rationale:
    Yahoo's spark endpoint returns full quote metrics (price, day high/low, volume)
    inside `meta`, not in the price array.
    
    Crucial previous-close nuance:
    For interval='1d', spark omits `previousClose`, but populates `chartPreviousClose`.
    However, `chartPreviousClose` only equals yesterday's close when range='1d'; on multi-day
    ranges, `chartPreviousClose` represents the price before the entire multi-day range began!
    Thus, `chartPreviousClose` is only safe to use when range='1d'.
    """
    price = _num(meta.get("regularMarketPrice"))
    t = meta.get("regularMarketTime")
    # If the price is missing, zero, or un-timestamped, the quote is unusable.
    if not price or price <= 0 or not t:
        return None
    period = (meta.get("currentTradingPeriod") or {}).get("regular") or {}
    return {
        "price": price,
        "time": int(t),
        "day_high": _num(meta.get("regularMarketDayHigh")),
        "day_low": _num(meta.get("regularMarketDayLow")),
        "volume": _num(meta.get("regularMarketVolume")),
        "prev_close": _num(meta.get("previousClose")) or (
            _num(meta.get("chartPreviousClose")) if meta.get("range") == "1d" else None),
        "high_52w": _num(meta.get("fiftyTwoWeekHigh")),
        "low_52w": _num(meta.get("fiftyTwoWeekLow")),
        "period_start": period.get("start"),
        "period_end": period.get("end"),
        "name": meta.get("longName") or meta.get("shortName"),
    }


def parse_spark(doc):
    """Parse batch spark JSON response into a mapping of {symbol: quote_dict}.
    
    Rationale:
    Yahoo does not fail the entire batch if one symbol is delisted or renamed;
    it simply omits that symbol from the results. Parsing defensively into a dict
    allows the engine worker to track individual misses without failing other symbols.
    """
    sp = doc.get("spark") if isinstance(doc, dict) else None
    if not isinstance(sp, dict):
        raise ValueError("not a spark response")
    if sp.get("error"):
        raise ValueError("spark error: %s" % (sp["error"].get("description") or sp["error"]))
    out = {}
    for r in sp.get("result") or []:
        resp = r.get("response") or []
        if not resp:
            continue
        q = quote_from_meta(resp[0].get("meta") or {})
        if q is None:
            continue
        ts = resp[0].get("timestamp") or []
        closes = ((resp[0].get("indicators") or {}).get("quote") or [{}])[0].get("close") or []
        # Store non-null closing ticks if present in the spark response
        q["bars"] = [(int(t), c) for t, c in zip(ts, closes) if _num(c) is not None]
        out[r.get("symbol")] = q
    return out


def parse_chart_daily(doc):
    """Parse v8 chart JSON (interval=1d) into normalized daily bars, metadata, and split events.

    Returns:
        (bars, meta, splits)
        bars: [[date_iso, open, high, low, close, volume], ...] sorted ascending by IST date.

    Rationale:
    1. Illiquid stocks on BSE frequently have missing open, high, or low in Yahoo's feed.
       We impute missing OHLC values from `close` so that range calculations (ATR, Bollinger)
       never encounter None values.
    2. Yahoo occasionally outputs multiple bars for the same calendar date. Grouping by
       `ts_to_date(t).isoformat()` deduplicates entries, retaining the latest valid bar.
    3. Corporate split events (numerator / denominator) are parsed into float multipliers
       to allow the HistoryStore to verify scale consistency.
    """
    ch = doc.get("chart") if isinstance(doc, dict) else None
    if not isinstance(ch, dict):
        raise ValueError("not a chart response")
    if ch.get("error"):
        raise ValueError("chart error: %s" % (ch["error"].get("description") or ch["error"]))
    res = (ch.get("result") or [None])[0]
    if not res:
        raise ValueError("empty chart result")
    meta = res.get("meta") or {}
    ts = res.get("timestamp") or []
    q = ((res.get("indicators") or {}).get("quote") or [{}])[0]
    o, h, l, c, v = (q.get(k) or [] for k in ("open", "high", "low", "close", "volume"))
    by_date = {}
    for i, t in enumerate(ts):
        close = _num(c[i] if i < len(c) else None)
        if close is None or close <= 0:
            continue
        # Fallback to close if open, high, or low are missing on illiquid names
        op = _num(o[i] if i < len(o) else None) or close
        hi = _num(h[i] if i < len(h) else None) or max(op, close)
        lo = _num(l[i] if i < len(l) else None) or min(op, close)
        vol = _num(v[i] if i < len(v) else None) or 0.0
        hi = max(hi, op, close)
        lo = min(lo, op, close)
        # Convert timestamp to IST calendar date (guarantees correct Indian session date)
        d = ts_to_date(t).isoformat()
        by_date[d] = [d, op, hi, lo, close, vol]
    # Sort chronologically
    bars = [by_date[d] for d in sorted(by_date)]
    # Extract stock split events
    splits = []
    for ev in ((res.get("events") or {}).get("splits") or {}).values():
        try:
            splits.append((ts_to_date(ev["date"]).isoformat(), ev["numerator"] / ev["denominator"]))
        except (KeyError, TypeError, ZeroDivisionError):
            pass
    return bars, meta, sorted(splits)
