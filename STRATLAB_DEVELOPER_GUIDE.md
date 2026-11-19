# STRATLAB: Comprehensive Architecture & Developer Guide

> **Core Engineering Principle**: One unified trading engine, multiple data sources, multiple strategy-building interfaces, and a single deterministic execution model.

---

## 1. Architectural Overview & Data Provenance

STRATLAB maintains an immutable boundary between **genuine exchange data** and **estimated synthetic proxies**:

| Quality Level | Classification | Method | Confidence | Intended Use |
| :---: | :---: | :---: | :---: | :---: |
| **Level A** | **Exchange Verified** | Direct exchange trade prints with buy/sell aggressor flags | `1.0` | Exact footprint cluster ladders, stacked imbalances (3:1), high-frequency order flow |
| **Level B** | **Quote Classified** | Trades matched against contemporaneous Best Bid/Ask (BBO) | `0.85 – 0.95` | Running Delta & Cumulative Volume Delta (CVD) |
| **Level C** | **Tick-Rule Estimated** | Direction inferred via Lee-Ready tick rule ($P_t \gtrless P_{t-1}$) | `0.65` | Volume-at-price approximations, fallback CVD |
| **Level D** | **OHLCV Proxy** | Synthetic volume distribution derived from candle geometry (BVC) | `0.35` | Standard candlestick charts, classical indicators (EMA, RSI, MACD, SMC) |

---

## 2. Subsystem Directory Map

```
nse-screener/
├── shared/
│   └── schemas/
│       ├── provenance.py        # 4-tier DataQuality, AggressorSide, ProvenanceMetadata
│       ├── instrument.py        # Universal InstrumentMaster (Equities, Futures, Options, Crypto)
│       ├── market_data.py       # Candle, TradeTick, OrderBookDepth
│       ├── order_flow.py        # PriceCluster, FootprintBar, VolumeProfile, CVDPoint
│       └── execution.py         # PaperOrder, PaperFill, PaperPosition, PaperAccount
│
├── backend/app/
│   ├── database/
│   │   ├── parquet_manager.py   # Partitioned PyArrow storage (Snappy compression)
│   │   ├── duck.py              # Zero-copy DuckDB SQL engine for volume-at-price aggregations
│   │   └── redis_client.py      # Redis stream coordinator with in-memory fallback
│   ├── market_data/
│   │   ├── quality/             # SyntheticClassifier, SequenceGapDetector, MonotonicJitterBuffer
│   │   ├── normalizer/          # Bhavcopy, Yahoo JSON, and broker tick normalizers
│   │   ├── ingestion/           # Historical & Streaming ingestion workers
│   │   └── streaming/           # MarketFeedSimulator (high-frequency tick & footprint feeder)
│   ├── analytics/
│   │   ├── footprint/           # FootprintAggregator (Bid × Ask, 3:1 diagonal imbalances, POC)
│   │   ├── volume_profile/      # VolumeProfileEngine (70% Value Area VAH/VAL, HVN, LVN)
│   │   ├── delta/               # CVDEngine (Bar delta, running CVD, session resets at 09:15)
│   │   ├── smc/                 # SMCDetectionEngine (Fractal swings, BOS, CHoCH, Fair Value Gaps)
│   │   └── indicators/          # IndicatorEngine (SMA, EMA, RSI, MACD, ATR, anchored VWAP)
│   ├── strategy/
│   │   ├── ir/                  # StrategyIR, ConditionGroup, ConditionNode, Operand schemas
│   │   ├── registry/            # Central ComponentRegistry enforcing provenance limits
│   │   └── compiler/            # StrategyCompiler with AST compilation and provenance guards
│   ├── execution/
│   │   ├── portfolio/           # PortfolioLedger, Indian statutory taxes (STT, GST, Stamp, SEBI)
│   │   ├── paper/               # SimulatedMatchingEngine (Queue-ahead limit order modeling)
│   │   └── backtest/            # BacktestEngine (Zero look-ahead deterministic simulation)
│   └── api/
│       ├── main.py              # FastAPI application gateway with CORS middleware
│       └── routers/             # Market data, Strategy Studio, Paper trading, and WebSocket multiplexer
│
├── frontend/src/
│   ├── components/
│   │   ├── MarketExplorer.tsx           # Multi-market instrument catalog browser
│   │   ├── CanvasFootprintChart.tsx     # 60 FPS HTML5 Canvas Footprint (Pan, Zoom, 3:1 Imbalances)
│   │   ├── FootprintChart.tsx           # Detail cluster table ladder view
│   │   ├── VolumeProfileView.tsx        # 70% Value Area Volume Profile with POC/VAH/VAL
│   │   ├── StrategyGraphStudio.tsx      # React Flow style interactive node & edge graph builder
│   │   ├── VisualStrategyBuilder.tsx    # Visual condition blocks editor
│   │   └── PaperTradingDashboard.tsx    # Real-time paper desk with queue countdown & ledger
│   ├── hooks/
│   │   └── useMarketStream.ts           # Real-time WebSocket multiplexer hook with latency monitor
│   ├── types/
│   │   ├── domain.ts                    # TypeScript domain contracts
│   │   └── strategy.ts                  # TypeScript strategy IR & simulation contracts
│   ├── App.tsx                          # Tabbed workbench shell integrating all 5 modules
│   └── package.json                     # Vite + React + TailwindCSS build configuration
│
└── tests/
    ├── test_contracts.py       # Pydantic v2 invariant & serialization tests
    ├── test_storage.py         # Parquet, DuckDB, Redis, and SQL migration tests
    ├── test_market_data.py     # Ingestion, jitter buffer, and classifier tests
    ├── test_analytics.py       # Footprint, Volume Profile, CVD, and SMC tests
    ├── test_strategy_ir.py     # Strategy IR, Component Registry, and Compiler tests
    ├── test_execution.py       # Statutory taxes, queue matching, and backtest tests
    └── test_api.py             # FastAPI REST endpoints and WebSocket stream tests
```

---

## 3. Running the Platform Locally

### A. Environment Setup
```bash
# 1. Activate Python virtual environment
source .venv/bin/activate

# 2. Install backend dependencies
pip install fastapi uvicorn httpx pydantic duckdb pyarrow

# 3. Run all unit tests to verify system integrity
python -m unittest discover tests -v
# Output: Ran 150 tests in 0.65s — OK
```

### B. Launching the Backend API & WebSocket Gateway
```bash
# Start FastAPI server on port 8000
uvicorn backend.app.api.main:app --reload --host 0.0.0.0 --port 8000
```
* **API Documentation (Swagger UI)**: `http://localhost:8000/docs`
* **Health Check**: `http://localhost:8000/health`
* **WebSocket Multiplexer**: `ws://localhost:8000/ws/market/stream`

### C. Launching the Frontend Studio UI
```bash
cd frontend
npm install
npm run dev
# Vite server running at http://localhost:5173
```

---

## 4. REST & WebSocket API Reference

### Market Data Endpoints
* `GET /api/v1/market/instruments` — Query multi-market instrument master catalog.
* `GET /api/v1/market/candles?instrument_id=...&timeframe=5m&limit=50` — Historical OHLCV candles with provenance tags.
* `GET /api/v1/market/orderflow/profile?instrument_id=...` — 70% Value Area Volume Profile (POC, VAH, VAL, HVN, LVN).
* `POST /api/v1/market/simulation/start?interval=0.5` — Start background high-frequency tick simulation.
* `POST /api/v1/market/simulation/stop` — Stop simulation playback.

### Strategy Studio Endpoints
* `GET /api/v1/strategies/components` — Catalog of all registered indicators, order flow metrics, and SMC patterns.
* `POST /api/v1/strategies/compile` — Compiles visual Strategy IR, validates parameter boundaries, and enforces minimum data quality requirements.
* `POST /api/v1/strategies/backtest` — Executes historical simulation returning metrics, equity curve, and closed trades.

### Paper Trading Endpoints
* `POST /api/v1/paper/orders` — Submit paper order with simulated queue-ahead volume tracking.
* `GET /api/v1/paper/orders` — Order blotter with fill status.
* `GET /api/v1/paper/positions` — Active positions with unrealized PnL.
* `GET /api/v1/paper/account` — Real-time account equity, available cash, and statutory fees.

### WebSocket Channels (`/ws/market/stream`)
Clients send JSON subscription frames:
```json
{ "action": "subscribe", "channel": "candles:INS_NSE_RELIANCE" }
{ "action": "subscribe", "channel": "footprint:INS_NSE_RELIANCE" }
{ "action": "subscribe", "channel": "executions:PAPER_ACC_01" }
```

---

## 5. Adding Custom Indicators or Order Flow Studies

To register a new calculation component into STRATLAB:

1. Open `backend/app/strategy/registry/components.py`.
2. Register your component definition:
```python
ComponentRegistry.register(ComponentDefinition(
    name="supertrend",
    category="indicator",
    display_name="SuperTrend ATR Band",
    description="Trend-following ATR channel indicator",
    required_feed="candle",
    min_data_quality=DataQuality.LEVEL_D_OHLCV_PROXY,
    parameters={
        "period": ParameterDefinition(name="period", type="int", default=10, min_value=1),
        "multiplier": ParameterDefinition(name="multiplier", type="float", default=3.0, min_value=0.5),
    },
    output_type="level",
))
```
3. The component is instantly exposed to:
   * The **FastAPI Component Catalog** (`GET /api/v1/strategies/components`).
   * The **React Flow Node Graph** (`StrategyGraphStudio.tsx`).
   * The **Visual Condition Blocks** (`VisualStrategyBuilder.tsx`).
   * The **Strategy Compiler** (`StrategyCompiler.compile()`) with automatic provenance checks.
