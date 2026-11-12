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

# Official exchange data endpoints (public, no authentication needed)
# Rationale: Standardized UDiFF format CSVs published by NSE and BSE after each trading day.
NSE_BHAV = "https://nsearchives.nseindia.com/content/cm/BhavCopy_NSE_CM_0_0_0_%s_F_0000.csv.zip"
BSE_BHAV = "https://www.bseindia.com/download/BhavCopy/Equity/BhavCopy_BSE_CM_0_0_0_%s_F_0000.CSV"
NSE_EQUITY_L = "https://nsearchives.nseindia.com/content/equities/EQUITY_L.csv"
NSE_INDEX = "https://nsearchives.nseindia.com/content/indices/%s.csv"

# NIFTY index constituent lists for industry/sector tagging and index membership.
INDEX_FILES = {
    "NIFTY50": "ind_nifty50list",
    "NIFTY100": "ind_nifty100list",
    "NIFTY200": "ind_nifty200list",
    "NIFTY500": "ind_nifty500list",
    "MIDCAP150": "ind_niftymidcap150list",
    "SMALLCAP250": "ind_niftysmallcap250list",
    "TOTALMARKET": "ind_niftytotalmarket_list",
}
# Rationale: BSE's server rejects requests lacking an official referer header.
BSE_HEADERS = {"Referer": "https://www.bseindia.com/"}

# Tradable equity series on NSE:
#   EQ: Normal rolling settlement equities.
#   BE: Book Entry / Trade-for-Trade (delivery only, no intraday netting).
#   BZ: Non-compliant / surveillance category (trade-for-trade).
NSE_SERIES = {"EQ", "BE", "BZ"}

# Regex pattern for identifying ETF / mutual fund / trust keywords in names.
# Rationale: Filter out exchange-traded funds, gold bees, REITs and InvITs
# so the universe contains only operating corporate equities.
FUND_NAME = re.compile(r"\bETF\b|\bBEES\b|MUTUAL FUND|\bFUND\b.*\bGR(OWTH)?\b|INVIT|\bREIT\b", re.I)

# Small & Medium Enterprise (SME) series (excluded by default unless --sme is requested).
NSE_SME = {"SM", "ST"}

# Allowed BSE trading groups:
#   A (large-cap liquid), B (mid/small-cap liquid), T (trade-to-trade),
#   X/XT/Z/ZP/P/R (surveillance, small-cap equity).
#   Excludes F (fixed income / debt), G (government securities), E/IF (mutual funds).
BSE_GROUPS = {"A", "B", "T", "X", "XT", "Z", "ZP", "P", "R"}
BSE_SME = {"M", "MT", "MS", "TS"}


def _rows(text):
    """Parse CSV text into a list of row dicts with stripped whitespace from headers and values.
    
    Rationale:
    NSE's EQUITY_L.csv notoriously contains leading spaces in column names like ' SERIES'.
    Stripping headers and fields guarantees dictionary lookups like row['SERIES'] work reliably.
    """
    rdr = csv.reader(io.StringIO(text))
    try:
        head = [h.strip() for h in next(rdr)]
    except StopIteration:
        return []
    return [dict(zip(head, (c.strip() for c in row))) for row in rdr if row]


def _f(x):
    """Safely convert text number to float, defaulting to 0.0 on missing/corrupt values."""
    try:
        return float(x)
    except (TypeError, ValueError):
        return 0.0


def _decode(body):
    """Decode raw bytes into UTF-8 text with BOM stripping.
    
    Rationale:
    NSE and BSE CSV files often include a UTF-8 Byte Order Mark (BOM: \xef\xbb\xbf).
    'utf-8-sig' automatically strips the BOM so the first column name is not mangled.
    """
    return body.decode("utf-8-sig", errors="replace")


def latest_bhavcopy(client, exchange, today, max_back=10, log=print):
    """Find and download the most recent available daily Bhavcopy file.

    Returns:
        (date, rows): Calendar date of the Bhavcopy and list of row dicts.

    Rationale:
    Exchanges publish the current day's Bhavcopy around 18:00-19:00 IST.
    During market hours, on weekends, or on exchange holidays, today's file does not exist yet.
    Stepping back day-by-day (skipping weekends) finds the latest completed session's data.
    """
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
                # Validate that the file is an actual Bhavcopy by checking for ticker symbol header
                if rows and "TckrSymb" in rows[0]:
                    return d, rows
            except net.FetchError as e:
                # 404 or 403 means the file is not yet generated for that date; continue stepping back
                if e.status not in (404, 403, None):
                    raise
        d -= datetime.timedelta(days=1)
    raise net.FetchError("no %s bhavcopy in the %d days up to %s" % (exchange, max_back, today))


def build(nse_rows, bse_rows, equity_l_rows=None, index_rows=None, include_sme=False,
          exchanges=("NSE", "BSE")):
    """Pure compilation function: builds deduplicated equity universe from parsed raw rows.

    Rationale & Core Rules:
    1. Bhavcopy as Primary Truth: Only equities that actually traded in the latest session
       are included. EQUITY_L alone contains suspended/delisted names Yahoo cannot quote.
    2. ISIN Deduplication: Many large companies (e.g. RELIANCE, TCS) trade on both NSE and BSE.
       Using the unique International Securities Identification Number (ISIN), dual-listed
       stocks are represented once under NSE with 'also_bse=True', avoiding double-counting.
    3. ETF Exclusion: In India, all mutual funds and ETFs have ISINs beginning with 'INF'.
       Filtering by 'isin.startswith("INF")' reliably drops index ETFs and gold funds that
       trade under series EQ.
    4. Series & Instrument Filtering: FinInstrmTp must be 'STK' (stocks). Debt, preference shares,
       and non-equity warrants are excluded.
    5. Prioritized by Turnover: Output list is sorted descending by daily traded turnover,
       ensuring high-liquidity stocks are polled first by the live engine.
    """
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

    # Process National Stock Exchange equities
    if "NSE" in exchanges:
        for r in nse_rows:
            if r.get("FinInstrmTp") != "STK" or r.get("SctySrs") not in nse_series:
                continue
            sym, isin = r.get("TckrSymb", ""), r.get("ISIN", "")
            # Must appear in the official equity master to ensure it is not an ETF
            if not sym or (names and sym not in names and r["SctySrs"] not in NSE_SME):
                continue
            # Drop mutual funds and ETFs by ISIN
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
            # If the same ISIN trades in both EQ and BE series on NSE, keep the more liquid one
            if isin and isin in by_isin:
                if row["turnover"] <= by_isin[isin]["turnover"]:
                    continue
                out.remove(by_isin[isin])
            out.append(row)
            if isin:
                by_isin[isin] = row

    # Process Bombay Stock Exchange equities (for BSE-only listed companies)
    for r in bse_rows if "BSE" in exchanges else []:
        if r.get("FinInstrmTp") != "STK" or r.get("SctySrs") not in bse_groups:
            continue
        # Exclude mutual fund / ETF units
        if FUND_NAME.search(r.get("FinInstrmNm") or "") or r.get("ISIN", "").startswith("INF"):
            continue
        sym, isin = r.get("TckrSymb", ""), r.get("ISIN", "")
        if not sym:
            continue
        # If already added via NSE, simply flag that it also trades on BSE
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

    # Sort all symbols descending by daily turnover (most-traded first).
    # Guarantees unique Yahoo symbols so duplicate ticker bugs cannot shadow rows.
    seen, uniq = set(), []
    for row in sorted(out, key=lambda x: -x["turnover"]):
        if row["ysym"] not in seen:
            seen.add(row["ysym"])
            uniq.append(row)
    return uniq


def fetch_and_build(client, include_sme=False, exchanges=("NSE", "BSE"), log=print, now=None):
    """Fetch external exchange CSV files and compile universe.json document.
    
    Rationale:
    Orchestrates downloading latest Bhavcopies, EQUITY_L, and NIFTY index CSVs.
    If an optional index file or EQUITY_L fails (e.g. temporary NSE server glitch),
    it records a non-fatal warning and falls back to Bhavcopy names, ensuring
    universe construction does not halt.
    """
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
