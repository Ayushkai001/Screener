"""The tradable NSE + BSE equity universe -> data/universe.json.

Sources (all public, no auth, verified Nov 2026):
  NSE bhavcopy (UDiFF)  nsearchives.nseindia.com/content/cm/BhavCopy_NSE_CM_0_0_0_YYYYMMDD_F_0000.csv.zip
  NSE equity master     nsearchives.nseindia.com/content/equities/EQUITY_L.csv
  NIFTY constituents    nsearchives.nseindia.com/content/indices/ind_<index>list.csv
  BSE bhavcopy (UDiFF)  www.bseindia.com/download/BhavCopy/Equity/BhavCopy_BSE_CM_0_0_0_YYYYMMDD_F_0000.CSV

Rules, and the bug each one prevents:
  * The bhavcopy is the primary list: only what actually traded on the last
    session. EQUITY_L alone includes suspended names Yahoo has no data for.
  * The newest bhavcopy is found by stepping back from today until a file
    exists: today's is published around 18:00 IST, and holidays have none.
  * One company listed on both exchanges appears once (dedupe by ISIN), on
    NSE, with `also_bse`. Without this every dual-listed stock shows twice.
  * Symbols are kept verbatim: BAJAJ-AUTO and M&M are real tickers (the
    roadmap's "exclude tickers containing '-'" rule would drop them).
  * EQUITY_L's header has leading spaces (" SERIES"); headers are stripped.
  * ETFs trade as instrument STK, series EQ in the NSE bhavcopy (358 of them on
    2026-11-09: gold/silver/index/liquid ETFs). EQUITY_L lists equities only,
    so when it is available an NSE row must be in it. (Yahoo's NV20.NS even
    switched from the ETF's price to an index level - junk in a screen.)
  * ISINs starting "INF" are mutual-fund units (ETFs) on either exchange - the
    exact test; BSE's MON100 (an ETF in group B) has no "ETF" in its name.
  * Series kept on NSE: EQ, BE (trade-for-trade), BZ (non-compliant, T4T);
    SME series SM/ST only with include_sme. Everything else (bonds, gold
    bonds, ETFs' N* series, InvITs IV, REITs RR) is out.
  * BSE groups kept: A B T X XT Z ZP P R (+ M MT MS TS SME with include_sme);
    F (debt), G (govt), E/IF (funds/trusts) are out.
  * A failed optional source (index lists, EQUITY_L) degrades the result
    (no sector tags) with a warning instead of failing the build.
"""

import csv
import datetime
import io
import re

from . import net
from .clock import IST, now_utc

NSE_BHAV = "https://nsearchives.nseindia.com/content/cm/BhavCopy_NSE_CM_0_0_0_%s_F_0000.csv.zip"
BSE_BHAV = "https://www.bseindia.com/download/BhavCopy/Equity/BhavCopy_BSE_CM_0_0_0_%s_F_0000.CSV"
NSE_EQUITY_L = "https://nsearchives.nseindia.com/content/equities/EQUITY_L.csv"
NSE_INDEX = "https://nsearchives.nseindia.com/content/indices/%s.csv"
INDEX_FILES = {
    "NIFTY50": "ind_nifty50list",
    "NIFTY100": "ind_nifty100list",
    "NIFTY200": "ind_nifty200list",
    "NIFTY500": "ind_nifty500list",
    "MIDCAP150": "ind_niftymidcap150list",
    "SMALLCAP250": "ind_niftysmallcap250list",
    "TOTALMARKET": "ind_niftytotalmarket_list",
}
BSE_HEADERS = {"Referer": "https://www.bseindia.com/"}

NSE_SERIES = {"EQ", "BE", "BZ"}
FUND_NAME = re.compile(r"\bETF\b|\bBEES\b|MUTUAL FUND|\bFUND\b.*\bGR(OWTH)?\b|INVIT|\bREIT\b", re.I)
NSE_SME = {"SM", "ST"}
BSE_GROUPS = {"A", "B", "T", "X", "XT", "Z", "ZP", "P", "R"}
BSE_SME = {"M", "MT", "MS", "TS"}


def _rows(text):
    rdr = csv.reader(io.StringIO(text))
    try:
        head = [h.strip() for h in next(rdr)]
    except StopIteration:
        return []
    return [dict(zip(head, (c.strip() for c in row))) for row in rdr if row]


def _f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return 0.0


def _decode(body):
    return body.decode("utf-8-sig", errors="replace")


def latest_bhavcopy(client, exchange, today, max_back=10, log=print):
    """Step back from `today` until the exchange's bhavcopy exists.
    Returns (date, rows)."""
    d = today
    for _ in range(max_back):
        if d.weekday() < 5:
            stamp = d.strftime("%Y%m%d")
            try:
                if exchange == "NSE":
                    body = net.unzip_single(client.get(NSE_BHAV % stamp))
                else:
                    body = client.get(BSE_BHAV % stamp, headers=BSE_HEADERS)
                rows = _rows(_decode(body))
                if rows and "TckrSymb" in rows[0]:
                    return d, rows
            except net.FetchError as e:
                if e.status not in (404, 403, None):
                    raise
        d -= datetime.timedelta(days=1)
    raise net.FetchError("no %s bhavcopy in the %d days up to %s" % (exchange, max_back, today))


def build(nse_rows, bse_rows, equity_l_rows=None, index_rows=None, include_sme=False,
          exchanges=("NSE", "BSE")):
    """Pure function: parsed source rows -> list of symbol dicts. Testable offline.
    index_rows: {"NIFTY50": [rows...], ...}"""
    names = {}
    for r in equity_l_rows or []:
        sym = r.get("SYMBOL")
        if sym:
            names[sym] = r.get("NAME OF COMPANY") or ""

    industry, members = {}, {}
    for tag, rows in (index_rows or {}).items():
        for r in rows:
            sym = r.get("Symbol")
            if not sym:
                continue
            members.setdefault(sym, []).append(tag)
            if r.get("Industry"):
                industry[sym] = r["Industry"]

    nse_series = NSE_SERIES | (NSE_SME if include_sme else set())
    bse_groups = BSE_GROUPS | (BSE_SME if include_sme else set())
    out, by_isin = [], {}

    if "NSE" in exchanges:
        for r in nse_rows:
            if r.get("FinInstrmTp") != "STK" or r.get("SctySrs") not in nse_series:
                continue
            sym, isin = r.get("TckrSymb", ""), r.get("ISIN", "")
            if not sym or (names and sym not in names and r["SctySrs"] not in NSE_SME):
                continue          # not in the equity master: ETF / fund unit
            if isin.startswith("INF"):
                continue
            row = {
                "sym": sym,
                "ysym": sym + ".NS",
                "exchange": "NSE",
                "name": names.get(sym) or r.get("FinInstrmNm", ""),
                "isin": isin,
                "series": r["SctySrs"],
                "industry": industry.get(sym, ""),
                "indices": sorted(set(members.get(sym, []))),
                "turnover": _f(r.get("TtlTrfVal")),
                "last_close": _f(r.get("ClsPric")),
                "also_bse": False,
            }
            if isin and isin in by_isin:   # same ISIN twice on NSE (EQ + BE): keep the liquid one
                if row["turnover"] <= by_isin[isin]["turnover"]:
                    continue
                out.remove(by_isin[isin])
            out.append(row)
            if isin:
                by_isin[isin] = row

    for r in bse_rows if "BSE" in exchanges else []:
        if r.get("FinInstrmTp") != "STK" or r.get("SctySrs") not in bse_groups:
            continue
        if FUND_NAME.search(r.get("FinInstrmNm") or "") or r.get("ISIN", "").startswith("INF"):
            continue
        sym, isin = r.get("TckrSymb", ""), r.get("ISIN", "")
        if not sym:
            continue
        if isin and isin in by_isin:
            by_isin[isin]["also_bse"] = True
            continue
        row = {
            "sym": sym,
            "ysym": sym + ".BO",
            "exchange": "BSE",
            "name": (r.get("FinInstrmNm") or "").title(),
            "isin": isin,
            "series": r["SctySrs"],
            "industry": "",
            "indices": [],
            "turnover": _f(r.get("TtlTrfVal")),
            "last_close": _f(r.get("ClsPric")),
            "also_bse": True,
        }
        out.append(row)
        if isin:
            by_isin[isin] = row

    # Yahoo symbols must be unique: an NSE ticker and a BSE ticker never share a
    # suffix, but guard anyway so a duplicate can never shadow a row.
    seen, uniq = set(), []
    for row in sorted(out, key=lambda x: -x["turnover"]):
        if row["ysym"] not in seen:
            seen.add(row["ysym"])
            uniq.append(row)
    return uniq


def fetch_and_build(client, include_sme=False, exchanges=("NSE", "BSE"), log=print, now=None):
    today = (now or now_utc()).astimezone(IST).date()
    warnings = []
    nse_date, nse_rows = latest_bhavcopy(client, "NSE", today, log=log) if "NSE" in exchanges else (None, [])
    log("NSE bhavcopy %s: %d rows" % (nse_date, len(nse_rows)))
    bse_date, bse_rows = (None, [])
    if "BSE" in exchanges:
        try:
            bse_date, bse_rows = latest_bhavcopy(client, "BSE", today, log=log)
            log("BSE bhavcopy %s: %d rows" % (bse_date, len(bse_rows)))
        except net.FetchError as e:
            warnings.append("BSE bhavcopy unavailable (%s): universe is NSE only" % e)
    eq_l = []
    try:
        eq_l = _rows(_decode(client.get(NSE_EQUITY_L)))
    except net.FetchError as e:
        warnings.append("EQUITY_L unavailable (%s): names from bhavcopy" % e)
    index_rows = {}
    for tag, fname in INDEX_FILES.items():
        try:
            index_rows[tag] = _rows(_decode(client.get(NSE_INDEX % fname)))
        except net.FetchError as e:
            warnings.append("index list %s unavailable (%s)" % (tag, e))
    syms = build(nse_rows, bse_rows, eq_l, index_rows, include_sme, exchanges)
    for w in warnings:
        log("warning: " + w)
    return {
        "as_of": (now or now_utc()).astimezone(IST).isoformat(timespec="seconds"),
        "bhavcopy": {"NSE": nse_date and nse_date.isoformat(), "BSE": bse_date and bse_date.isoformat()},
        "count": len(syms),
        "warnings": warnings,
        "symbols": syms,
    }
