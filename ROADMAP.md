# NSE Stock Screener — Professional-Grade Build Roadmap

> **Version**: 2.0 — Evaluated & Updated 2026-10-24
> **Architecture Reference**: `day-trader-skill` by Jakeschincariol (file:///Users/ayushk/Desktop/day-trader-skill)
> **Project Root**: `/Users/ayushk/Desktop/nse-screener`

---

## Table of Contents
1. [Project Mission](#1-project-mission)
2. [How We Use the Reference Repository](#2-how-we-use-the-reference-repository)
3. [Gap Analysis — What the Reference Cannot Do](#3-gap-analysis)
4. [Final Project Structure](#4-final-project-structure)
5. [Data Flow & File Contracts](#5-data-flow--file-contracts)
6. [Phase-by-Phase Implementation Plan](#6-phase-by-phase-implementation-plan)
7. [Technical Design Decisions](#7-technical-design-decisions)
8. [Edge Cases & Mitigations](#8-edge-cases--mitigations)
9. [Quality Gates Per Phase](#9-quality-gates-per-phase)
10. [Build Order & Dependencies](#10-build-order--dependencies)

---

## 1. Project Mission

Build a **professional-grade, autonomous NSE Chart Screener and Trade Planning Engine** that:

- Scans the **entire NSE equity universe** (1,700+ listed equities, NIFTY 50/500 focus) for high-probability technical setups.
- Specialises in **Double Bottom ('W' Pattern)** detection, **Multi-week Closing High Breakouts**, **Bull Flags**, and **Opening Range Breakouts (ORB)** adapted for Indian market timing (09:15 IST).
- Applies **quantitative risk management and position sizing** in Indian Rupees (₹).
- **Replays setups historically** before any capital is allocated (Monte Carlo + historical outcome analysis).
- Runs on **zero paid APIs** — free Yahoo Finance endpoints only.
- Ships as a clean **CLI tool** with structured JSON output suitable for Telegram alerts, dashboards, or broker API integration.

---

## 2. How We Use the Reference Repository

The reference code lives at: `/Users/ayushk/Desktop/day-trader-skill`
Individual skill modules installed at: `/Users/ayushk/Desktop/nse-screener/.agents/skills/`

We use it in **three ways**: direct algorithm adoption, architectural pattern adoption, and test fixture inspiration.

### 2a. Direct Algorithm Adoption (copy logic, adapt constants)

| Algorithm | Source File | What We Take | What We Change |
| :--- | :--- | :--- | :--- |
| **Batched Yahoo Spark API** | `trader-scanner/scan.py` | Chunked 20-symbol requests, query2→query1 fallback, retry on 429/5xx | Params for `.NS` tickers; interval=`1d` for NSE |
| **V8 Chart API** (OHLCV) | `trader-scanner/scan.py` | Full OHLCV bars with highs/lows for intraday scans | Bar alignment checks for 09:15 IST grid instead of 09:30 ET |
| **Wilder's RSI(14)** | `trader-scanner/scan.py` | Pure-Python EMA-based RSI — zero dependencies | No change needed; math is universal |
| **20-Day Closing High Breakout** | `trader-scanner/scan.py` `breakout_20d` | `last_close > max(closes[-21:-1])` | Keep identical |
| **Bull Flag Detection** | `trader-scanner/scan.py` `bull_flag` | +10% over 10 sessions, last 5 closes in 5% range | Tweak thresholds after backtesting on NSE |
| **Monte Carlo Replay Engine** | `trader-timemachine/timemachine.py` | 10,000 replays using ratio-scaled historical bars, seed-reproducible | Session bar count: NSE = 75 bars/day (09:15–15:30), not 78 |
| **R-Multiple Position Sizing** | `trader-budget/` | `qty = floor(max_risk / (entry - stop))` | Replace USD with INR; NSE tick size = ₹0.05 |
| **Risk Gate Logic** | `trader-risk/` | Stop required, reward:risk min, daily loss limit, entry window | Entry window → 09:15–13:00 IST; add NSE circuit filter check |
| **Rate Limiting / Politeness** | `trader-scanner/scan.py` | Jittered pause between requests, exponential backoff | Keep identical |

### 2b. Architectural Pattern Adoption (design, not code)

| Pattern | How Reference Does It | How We Implement It |
| :--- | :--- | :--- |
| **Decoupled stage pipeline** | Each skill reads/writes a single JSON contract file | Each module reads/writes `data/*.json`; stages independently testable |
| **Zero external dependencies** | Pure `urllib`, `json`, `math`, `argparse`, `random`, `datetime` | Same — no `pandas`, `numpy`, `ta-lib`, or `requests` in core |
| **Exit code contract** | Exit 0 = found results; Exit 1 = nothing or error | Identical convention |
| **`--offline PATH` for backtesting** | Pass a local JSON or `.json.gz` file instead of live fetching | Implemented on every scan command for reproducible backtests |
| **`--now` clock pinning** | Pin the clock for replay and tests | IST clock: `--now "2026-10-24 10:30"` interpreted as IST |
| **Two-stage ORB scan** | Stage 1: cheap spark closes → candidates. Stage 2: v8 OHLCV for candidates only | Identical two-stage approach; reduces API calls ~60x on 1,700 stocks |

### 2c. Test Infrastructure Reference

The reference ships 315 unit tests (`/tests/`). We build a parallel test suite under `tests/` using the same fixture pattern (saved Yahoo JSON responses as `.json.gz` files for offline testing).

---

## 3. Gap Analysis — What the Reference Cannot Do

These are **new capabilities built from scratch** — not present in the reference repo.

| Gap | Why It Doesn't Exist in Reference | Our Solution |
| :--- | :--- | :--- |
| **Double Bottom ('W') Detection** | No pattern identifies two-trough reversal structures | Build `patterns/double_bottom.py` — trough detection, neckline, symmetry, volume confirmation |
| **NSE Universe Fetching** | Hardcoded to Nasdaq Trader FTP | Build `universe.py` using NSE's official EQUITY_L.csv |
| **Indian Market Hours** | Hardcoded 09:30 ET, 78 bars/session | 09:15 IST, 75 bars/session; Muhurat trading as a special mode |
| **NSE Circuit Filter Awareness** | No concept of upper/lower circuit limits | Add circuit band check: if close within 0.5% of limit, exclude from entries |
| **Bhavcopy Historical Data** | No Indian EOD data source | Optional Bhavcopy ingestion as fallback/supplement to Yahoo |
| **NSE Holiday Calendar** | Ships with NYSE 2026-2027 holidays | Build `calendar_nse.py` with NSE 2026-2027 holidays + Muhurat sessions |
| **INR Tick Size Rounding** | Rounds to the cent (0.01) | Round to nearest 5 paise (0.05) for NSE equity orders |
| **NIFTY Index Filtering** | No index-membership concept | `--index nifty50 / nifty500 / total` to filter universe |
| **Sector/Industry Tagging** | No sector metadata | Pull sector tags from NSE equity master CSV |
| **Web Dashboard (Optional)** | CLI only | Lightweight HTML report using only stdlib |

---

## 4. Final Project Structure

```
nse-screener/
│
├── main.py                    # CLI entry point — orchestrates all phases
│
├── nse/                       # Core library (all pure stdlib)
│   ├── __init__.py
│   ├── universe.py            # Phase 1: NSE equity universe builder
│   ├── data.py                # Phase 2: Yahoo Finance data engine (spark + v8)
│   ├── calendar_nse.py        # NSE trading calendar (holidays, early-closes)
│   ├── indicators.py          # RSI, ATR, SMA, EMA — pure math
│   ├── scanner.py             # Phase 3: Pattern rules engine
│   ├── patterns/
│   │   ├── __init__.py
│   │   ├── double_bottom.py   # W-pattern detection (PRIMARY NEW PATTERN)
│   │   ├── orb.py             # Opening Range Breakout (IST-adjusted)
│   │   ├── breakout.py        # 20-day / 52-week high breakouts
│   │   ├── bull_flag.py       # Consolidation after impulse move
│   │   └── oversold.py        # RSI oversold + bounce
│   ├── risk.py                # Phase 4: Stop/target calculation, R-sizing
│   └── timemachine.py         # Phase 5: Monte Carlo + historical replay
│
├── data/                      # Runtime JSON state (git-ignored)
│   ├── universe_nse.json      # Cleaned NSE equity list + metadata
│   ├── watchlist.json         # Scanner output — today's setups
│   ├── plan.json              # Active trade plan (entry/stop/target)
│   └── prices_cache/          # Cached Yahoo responses (keyed by symbol+date)
│
├── results/                   # Human-readable outputs (git-ignored)
│   ├── scan_YYYY-MM-DD.json   # Dated scan results archive
│   └── report_YYYY-MM-DD.html # Optional HTML report
│
├── tests/                     # Unit + integration tests
│   ├── fixtures/              # Saved Yahoo JSON responses (.json.gz)
│   └── test_*.py
│
├── config.json                # User config (account size, risk %, filters)
├── ROADMAP.md                 # This file
└── README.md
```

---

## 5. Data Flow & File Contracts

### Stage Pipeline (mirrors reference pattern)

```
universe.py      →   data/universe_nse.json
      ↓
data.py          →   data/prices_cache/<SYMBOL>_<DATE>_<INTERVAL>.json.gz
      ↓
scanner.py       →   data/watchlist.json
      ↓
risk.py          →   data/plan.json
      ↓
timemachine.py   →   data/timemachine.json
```

### `data/universe_nse.json` schema
```json
{
  "as_of": "2026-10-24",
  "source": "NSE EQUITY_L.csv",
  "count": 1843,
  "symbols": [
    {
      "symbol": "RELIANCE",
      "yf_symbol": "RELIANCE.NS",
      "name": "Reliance Industries Ltd",
      "series": "EQ",
      "sector": "Energy",
      "index_member": ["NIFTY50", "NIFTY500"]
    }
  ]
}
```

### `data/watchlist.json` schema
```json
{
  "mode": "daily",
  "as_of": "2026-10-24T09:00:00+05:30",
  "universe": 1843,
  "scanned": 1798,
  "failed": 45,
  "hits": [
    {
      "symbol": "RELIANCE.NS",
      "name": "Reliance Industries Ltd",
      "setup": "breakout_20d",
      "last_close": 2980.50,
      "volume": 4200000,
      "rsi14": 62.3,
      "sector": "Energy"
    }
  ]
}
```

### `data/plan.json` schema
```json
{
  "symbol": "RELIANCE.NS",
  "date": "2026-10-24",
  "entry": 2985.00,
  "entry_time": "09:45",
  "stop": 2952.00,
  "stop_rule": "double_bottom_trough",
  "target": 3051.00,
  "target_r": 2.0,
  "risk_per_share": 33.00,
  "qty": 30,
  "max_loss_inr": 990.00
}
```

---

## 6. Phase-by-Phase Implementation Plan

### Phase 1: NSE Universe Manager (`nse/universe.py`)

**Reference Analogy**: `scan.py universe` (Nasdaq Trader FTP → filtered list)

**Source**: `https://archives.nseindia.com/content/equities/EQUITY_L.csv`
Official NSE equity master CSV — updated daily, publicly accessible, no auth required.

**Algorithm**:
1. Fetch EQUITY_L.csv (or load from cache if <24h old).
2. Filter rules (in order):
   - Keep only series `EQ` — exclude `BE`, `SM`, `IL`, `ST`, `GB`.
   - Exclude tickers containing `-` (suspended / special series).
   - Exclude names containing: `ETF`, `INDEX`, `FUND`, `NIFTY`, `SENSEX`.
   - Minimum participation: last traded date within 10 trading days.
3. Append `.NS` suffix for Yahoo Finance compatibility.
4. Enrich with sector/index membership from NIFTY constituent CSVs.
5. Write `data/universe_nse.json`.

**CLI**:
```bash
python3 main.py universe                    # Full NSE equity list
python3 main.py universe --index nifty500   # NIFTY 500 only
python3 main.py universe --index nifty50    # NIFTY 50 only
```

---

### Phase 2: Resilient Data Engine (`nse/data.py`)

**Reference Analogy**: Yahoo spark + v8 chart fetchers in `scan.py`

**A. Spark Fetcher** (batch — for daily scans):
- Endpoint: `query2.yahoofinance.com/v7/finance/spark?symbols=A.NS,B.NS,...&range=3mo&interval=1d`
- 20 symbols per request. Returns: closes, volume, last price.
- Fallback to `query1` on 429/5xx. One retry after 5-second backoff.
- Used for: daily pre-market scans (closes-only patterns).

**B. V8 Chart Fetcher** (per-symbol — for pattern confirmation + ORB):
- Endpoint: `query2.yahoofinance.com/v8/finance/chart/RELIANCE.NS?range=60d&interval=5m`
- Full OHLCV with timestamps.
- Used for: ORB stage 2 confirmation, Double Bottom trough analysis, Time Machine.

**Caching**:
- Cache in `data/prices_cache/<SYMBOL>_<DATE>_<INTERVAL>.json.gz`.
- Daily bars: re-fetch if cache >4 hours old.
- Intraday bars: re-fetch if cache >5 minutes old (during market hours).
- `--offline PATH`: bypass all network calls; read from local file.

---

### Phase 3: Pattern & Screener Engine (`nse/scanner.py` + `nse/patterns/`)

**Reference Analogy**: `scan.py` daily and ORB scan rules

#### 3A. Patterns Carried Over From Reference (adapted)

| Pattern | File | Rule |
| :--- | :--- | :--- |
| `breakout_20d` | `patterns/breakout.py` | `last_close > max(closes[-21:-1])` |
| `bull_flag` | `patterns/bull_flag.py` | Up >10% over 10 sessions; last 5 closes in 5% band |
| `reclaim_ma20` | `patterns/breakout.py` | Crossed from below 20-day SMA |
| `oversold` | `patterns/oversold.py` | RSI(14) < 30 |
| `oversold_bounce` | `patterns/oversold.py` | RSI(14) was < 30 yesterday; today closed up |
| `orb` | `patterns/orb.py` | First 5-min bar to close above range high after 09:15 IST |

#### 3B. NEW: Double Bottom Detection (`patterns/double_bottom.py`)

Primary new pattern not in the reference. Algorithm:

```
1. Find LOCAL MINIMA in last 60 trading days on daily closes:
   - Trough L[i] if close[i] < close[i±k] for k = 1..5 (5-day lookback window)

2. Identify L1 (first trough) and L2 (second trough):
   - Two lowest qualifying local minima
   - L1 must occur before L2 (temporal order enforced)
   - Minimum trough separation: >= 15 trading days (prevents spike noise)
   - Maximum trough separation: <= 60 trading days (prevents stale patterns)

3. Symmetry validation:
   - |L1 - L2| / L1 <= 0.03  (troughs within 3% of each other in price)

4. Neckline (P) = highest close between L1 and L2

5. Breakout confirmation (both required):
   - Last close > P  (neckline close breakout)
   - Volume on breakout day >= 1.5x average 20-day volume

6. Pattern quality score (0–100):
   - Symmetry:   40 pts  (tighter troughs = higher score)
   - Volume:     30 pts  (volume multiplier above 1.5x threshold)
   - Duration:   20 pts  (longer base = higher quality)
   - R:R ratio:  10 pts  (neckline-to-target vs. stop depth)

Output per signal:
  L1_price, L1_date, L2_price, L2_date, neckline_price,
  entry, stop, target_1r, target_2r, quality_score
```

**Trend filter** (new, prevents false positives):
- The 50-day SMA must be flat or rising (within ±2% over the window).
- Stocks in a confirmed downtrend are excluded.

---

### Phase 4: Trade Planner & Risk Engine (`nse/risk.py`)

**Reference Analogy**: `trader-exit/` + `trader-budget/` + `trader-risk/`

**Pattern-specific Stop Loss Rules**:

| Pattern | Stop Rule | Calculation |
| :--- | :--- | :--- |
| `double_bottom` | Trough low | `min(L1, L2) - 1 tick`, rounded to ₹0.05 |
| `orb` | Range midpoint | `(range_high + range_low) / 2`, rounded down |
| `breakout_20d` | Prior day low | `prev_day_low * 0.995` |
| `bull_flag` | Flag low | Lowest close in the 5-day consolidation |

**Position Sizing** (adapted from `trader-budget` to INR):
```python
risk_inr    = account_size * max_risk_pct        # e.g. ₹1,00,000 * 0.01 = ₹1,000
risk_per_sh = entry_price - stop_price           # e.g. ₹2985 - ₹2952 = ₹33
qty         = floor(risk_inr / risk_per_sh)      # e.g. floor(1000/33) = 30 shares
trade_value = qty * entry_price                  # e.g. 30 * ₹2985 = ₹89,550
```

**Risk Gate** (adapted from `trader-risk`). Block trade if any of:
- `risk_per_sh <= 0` (stop at or above entry)
- `trade_value > account_size * max_position_pct` (oversized position)
- `reward_risk < 1.5` (below minimum R:R)
- Last close within 0.5% of NSE circuit band
- Time is after 13:00 IST (too late for a clean day trade)
- Daily loss limit already reached

---

### Phase 5: Historical Replay & Simulator (`nse/timemachine.py`)

**Reference Analogy**: `trader-timemachine/timemachine.py`

**NSE Adaptations**:
- Session = **75 five-minute bars** (09:15–15:30 IST; 375 min / 5 = 75 bars)
- Pool = past 60 days of **complete sessions** (all 75 bars present)
- Muhurat and half-day sessions are excluded from the pool
- `--until` defaults to `15:25` IST (5 min before close)
- Seed = 19 (same as reference for cross-system reproducibility)

**Output format** (identical to reference):
```
10,000 replays — 10:00 to 15:30 IST (66 bars), seed 19.
  target first   34.2 %
  stop first     28.7 %
  neither        37.1 %   still open at 15:25 IST
  green          55.1 %   target first, or above entry at 15:25
  Price at 15:25: median 2991.50, 90% between 2965.00 and 3021.00
  Average R: +0.18
History: same rule on 47 real sessions fired 21 times:
  9 target, 8 stop, 4 neither. Average R +0.24.
Leans toward the target: target first 34.2% vs stop first 28.7%.
```

---

### Phase 6: Orchestration & CLI (`main.py`)

**Full command surface**:
```bash
# Universe
python3 main.py universe
python3 main.py universe --index nifty500

# Pre-market daily scan (before 09:15 IST)
python3 main.py scan daily
python3 main.py scan daily --pattern double_bottom
python3 main.py scan daily --index nifty50 --min-price 100 --min-volume 500000

# Intraday ORB scan (after 09:30 IST)
python3 main.py scan orb
python3 main.py scan orb --at 09:45
python3 main.py scan orb --or-minutes 30

# Trade planning
python3 main.py plan RELIANCE.NS
python3 main.py plan RELIANCE.NS --rr 2.0

# Monte Carlo simulation
python3 main.py simulate RELIANCE.NS
python3 main.py simulate RELIANCE.NS --replays 20000

# Backtesting (offline)
python3 main.py scan daily --offline data/fixtures/daily_2026-10-20.json.gz
python3 main.py scan orb   --offline data/fixtures/orb_2026-10-20.json.gz --now "2026-10-20 10:00"
```

**Formatted terminal output**:
```
NSE Daily Scan — 2026-10-24 08:55 IST
Universe: 1,798 scanned / 1,843 total (45 failed) | Liquid: 1,204 | Hits: 18

SYMBOL           PATTERN          CLOSE      VOL(L)    RSI14    SCORE    SECTOR
───────────────────────────────────────────────────────────────────────────────
RELIANCE.NS      breakout_20d     2980.50    42.1      62.3     —        Energy
HDFCBANK.NS      double_bottom    1712.00    89.6      44.8     78/100   Financials
INFY.NS          bull_flag        1920.00    38.2      55.1     —        IT
TCS.NS           reclaim_ma20     4250.00    21.4      49.7     —        IT
```

---

### Phase 7: HTML Report & Alerts (Optional)

Using **only Python stdlib** (`string.Template`, `json`, `urllib`):
- Self-contained `results/report_YYYY-MM-DD.html` with scan table, trade plan card.
- Telegram/Webhook alert via single HTTPS POST (`urllib.request`).
- No JavaScript frameworks, no external CSS.

---

## 7. Technical Design Decisions

| Decision | Choice | Rationale |
| :--- | :--- | :--- |
| **Dependencies** | Zero external libraries | Portable, audit-friendly, no pip failures in prod |
| **Data source** | Yahoo Finance (free, unofficial) | Same as reference; proven at scale on 5,000+ stocks |
| **Config format** | `config.json` | Human-readable; safe to version-control (no secrets) |
| **Bar alignment** | Strict 5-min grid (09:15, 09:20…) | Prevents live-tick lookahead bias |
| **Timezone** | All timestamps in IST (+05:30) | Single-timezone system; no conversion ambiguity |
| **Reproducibility** | `random.Random(seed=19)` in Monte Carlo | Same plan + data + seed = identical output anywhere |
| **Exit codes** | 0 = results found, 1 = no results or error | Composable in shell pipelines and CI |
| **Partial results** | Always reported as partial | Never round a partial scan up to "full market" |
| **Disclaimer** | Printed on every run | Not financial advice; no edge guarantee implied |

---

## 8. Edge Cases & Mitigations

1. **Lookahead bias — live unclosed candles**
   *Risk*: A 5-min bar at 10:15:34 IST hasn't completed; using it creates false signals.
   *Fix*: A bar is valid only when `bar_open_time + 5 minutes <= clock_now`.

2. **NSE circuit filter freeze**
   *Risk*: Stocks at upper/lower circuit cannot be exited; stop-loss becomes unexecutable.
   *Fix*: Exclude symbols whose last close is within 0.5% of their declared circuit band (sourced from Bhavcopy).

3. **Yahoo rate limiting (HTTP 429)**
   *Fix*: query2 → query1 fallback; 5-second wait + one retry; jittered 0.3s pause between batch requests.

4. **Missing intraday bars (halted stocks)**
   *Risk*: Stock with 40/75 bars passes Stage 1 (spark) as a candidate, then fails Stage 2 silently.
   *Fix*: Stage 2 v8 chart marks a chart "unusable" if any bar from 09:15 to cutoff is missing.

5. **NSE holidays and Muhurat sessions**
   *Fix*: `calendar_nse.py` contains 2026-2027 holidays + Muhurat. ORB scan prints one plain error and exits on non-trading days.

6. **Yahoo stale or zero prices for .NS tickers**
   *Fix*: Validate `regularMarketPrice > 0` and `regularMarketTime` is within last session. Stale = treated as failed symbol.

7. **Double Bottom false positives in downtrends**
   *Risk*: Downtrending stock makes two troughs but continues lower.
   *Fix*: 50-day SMA must be flat or rising (±2% tolerance). Downtrending stocks excluded at the scanner level.

8. **Position sizing returns 0 shares**
   *Risk*: Stop too wide; max loss buys < 1 share.
   *Fix*: Refuse with: `"Stop too wide: 0 shares would be sized. Widen max_loss or tighten stop."` Never round up to 1.

---

## 9. Quality Gates Per Phase

Each phase passes before the next begins.

| Phase | Gate Condition |
| :--- | :--- |
| **Phase 1** | `python3 main.py universe` returns >1,500 symbols in <10 seconds. `data/universe_nse.json` is valid JSON with correct schema. |
| **Phase 2** | Batch fetch of 50 NIFTY 50 symbols completes in <30 seconds. Cache round-trip verified. `--offline` mode works. |
| **Phase 3** | Daily scan on 100 NIFTY 500 symbols produces ≥1 hit per pattern on a known historical date. All patterns pass unit tests against fixture data. |
| **Phase 4** | `plan.json` generated for ≥2 symbols. Math verified: `qty * risk_per_share <= max_loss_inr`. Risk gate blocks 100% of invalid setups in tests. |
| **Phase 5** | 10,000 replay simulation completes in <15 seconds. Seed 19 produces identical output on second run (reproducibility confirmed). |
| **Phase 6** | Full end-to-end `scan → plan → simulate` pipeline runs without errors. Exit code 0 on hits, 1 on no hits. |

---

## 10. Build Order & Dependencies

```
Phase 1: nse/universe.py + nse/calendar_nse.py
    ↓
Phase 2: nse/data.py + nse/indicators.py
    ↓
Phase 3: nse/scanner.py + nse/patterns/*.py
    ↓
Phase 4: nse/risk.py
    ↓
Phase 5: nse/timemachine.py
    ↓
Phase 6: main.py  (full CLI, end-to-end)
    ↓ (optional)
Phase 7: HTML Report + Telegram Alerts
```

**Immediate next action → Start Phase 1**: Build `nse/universe.py` and `nse/calendar_nse.py`.

---

*This roadmap is the ground truth for this project. Any design decision that contradicts it must be explicitly documented here before implementation begins.*

---

## 11. v3 — Real-time NSE + BSE Screener (2026-11-10)

The goal became a **TradingView-style live screener** covering NSE and BSE. The decisions below override earlier sections where they conflict. Each one was checked against live data on 2026-11-10.

### What is built (blocks 1–12, 54 offline tests)
| Block | Module | Status |
|---|---|---|
| Clock, NSE calendar 2026, special sessions | `screener/clock.py` | done |
| Adaptive rate limiter, retries, atomic cache | `screener/net.py` | done |
| Yahoo spark/v8 parsers | `screener/yahoo.py` | done |
| NSE + BSE universe (4,577 symbols) | `screener/universe.py` | done |
| Daily history cache, split detection | `screener/history.py` | done |
| Muhurat/special-session bars | `screener/specials.py` | done |
| Incremental indicators (≈60 fields) | `screener/indicators.py` | done |
| Patterns incl. Double Bottom (§3B) | `screener/patterns.py` | done |
| Filter language | `screener/expr.py` | done |
| Live engine | `screener/engine.py` | done |
| HTTP + SSE server, browser UI | `screener/server.py`, `web/index.html` | done; checked 2026-11-10 in headless Chrome (desktop, light/dark, 390 px phone); not yet in market hours |
| CLI | `main.py` | done |

### Deviations from v2 (and why)
1. **Package `screener/`, not `nse/`.** It covers BSE too.
2. **BSE included.** BSE-only companies (about 1,590) come from the BSE bhavcopy. A company listed on both exchanges appears once, on NSE, matched by ISIN. BSE's JSON API is blocked by Akamai; the bhavcopy CSV is not. Yahoo takes BSE symbols by ticker (`RELIANCE.BO`), not by scrip code.
3. **Universe from the bhavcopy, not EQUITY_L alone.** The bhavcopy lists only what actually traded. Tickers with `-` and `&` are kept (`BAJAJ-AUTO`, `M&M`), so the v2 rule "exclude tickers containing `-`" was a bug. Series `BE`/`BZ` are kept and tagged.
4. **Web UI (SSE) instead of CLI-only**, still using only the standard library (`http.server`). The CLI `scan` command remains.
5. **Change % uses the official previous close.** On a `range=1d` spark this is `meta.chartPreviousClose`; `previousClose` is absent when `interval=1d`. On longer ranges `chartPreviousClose` is the close *before the range starts*, so using it there would be wrong.
6. **Special sessions:** Yahoo has no data at all for Muhurat (2026-11-08), daily or intraday, yet the next day's official previous close is the Muhurat close. Those bars are patched in from that day's bhavcopy and rescaled for later splits.
7. **Split detection:** the incremental sync compares 5 days of overlap. A *median* deviation above 1% (or any single bar above 5%) triggers a full refetch. A single revised bar is accepted.
8. **No `v7/quote`:** the crumb endpoint returns 429 for this client. Only spark (≤20 symbols, else HTTP 400) and v8 chart are used.
9. **Today's open:** spark sends no open. A v8 sync pass after 09:16 learns it, so gap filters fill in over the first minutes of the session.
10. **NULL semantics:** missing values are *unknown* (SQL-style), never 0. `not (rsi14 > 70)` does not match a stock with no RSI.
11. **52-week high/low over the history that exists** (min 20 sessions), as TradingView does, instead of blank below a year: recent listings breaking their post-listing high are a setup in their own right. `hist_days` exposes the depth; preset "Recent listings at a new high".
12. **Open after the close** comes from the session's own daily bar (spark has none); before this fix every row's open and gap were blank outside market hours.
13. **Double bottom in stages** (§3B): `db_forming` (under the neckline, never closed above it), `double_bottom` (breakout *today*: no earlier close above the neckline, price through it on ≥1.5× time-adjusted volume), and `db_days_since_breakout` for follow-through. Before this, any stock above its neckline matched, including breakouts weeks old and already past their target. Plan fields per §3B output: `db_entry` (neckline while forming, price after), `db_stop` (lower trough's intraday low), `db_risk_pct`, `db_target_1r/2r`, `db_target` (measured move). Presets carry a ₹1 cr turnover floor.
14. **Official end-of-day numbers override Yahoo** once the evening bhavcopies are out (`data/official/`, retried every 20 min from the close). Checked on 2026-11-09 against both bhavcopies for 4,000 symbols: Yahoo's price and previous close matched 100 %, but its volume was short by >5 % for 23 live quotes (BLUEJET 697k vs 1.60M) and 46 daily bars (some 0). Applied only when the quote equals the official close, so a live quote is never overwritten; rows carry `official_eod`. Past days' volumes in the history (used for averages) are still Yahoo's.
15. **Backtester (Phase 5's "Time Machine", daily version)** in `screener/backtest.py` + `/backtest`. Uses a separate 10-year store (`data/history_bt`, `main.py bt-sync`; the screener keeps 2 years). Rules are screener filters evaluated by walking `indicators.Base` one bar at a time (`advance()`; proven equal to a rebuild in tests) with lazily computed field groups, so a run over 4,200 stocks x 10 years takes 1-4 min on 6 cores. Muhurat bars are not patched into the 10-year history (Yahoo lacks them; one hour a year).
16. **Engine hardening from the first live session (2026-11-11):** transient history failures (a minute of DNS errors at 09:57) are retried after 30/60/90 s instead of leaving the stock without today's open all day; the 09:16 open pass gets half the request budget for its first 20 minutes.

### Next blocks
1. **Market-hours check** of the UI (the off-hours check is done). Then tune `focus_interval` and `sweep_interval_open` against the observed 429 rate.
2. **Intraday layer:** 5-minute bars for on-screen symbols, giving VWAP and ORB (§3A) on the 09:15 IST grid. Only completed bars count (`start + 5 min <= now`).
3. **Circuit-band awareness:** NSE price bands (`sec_list.csv`) feed `at_upper_circuit` / `at_lower_circuit` fields and the risk gate (§4).
4. **Broker tick feed (optional):** a provider interface so a broker WebSocket (Upstox, Angel One SmartAPI, Dhan, Kite) can replace the Yahoo poller for true tick-by-tick data. API keys stay in environment variables, never in config files.
5. **Trade planner / risk / Monte Carlo** (Phases 4–5) on top of the screener rows. The daily backtester is done (deviation 15); still open: intraday (5-minute) backtests, walk-forward parameter search, and a survivorship-free universe (needs historical bhavcopies of delisted names).
6. **Calendar 2027** once NSE publishes it (into `clock.py`, or `data/holidays.json` meanwhile).
