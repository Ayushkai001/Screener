-- ============================================================================
-- STRATLAB Initial Database Migration: 001_initial_schema.sql
-- Subsystems: Instruments, Strategies, Backtests, Paper Trading, Users
-- PostgreSQL 14+ compatible with UUID extension
-- ============================================================================

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ----------------------------------------------------------------------------
-- DOMAIN A: INSTRUMENTS & DATA SOURCES
-- ----------------------------------------------------------------------------

CREATE TABLE exchanges (
    id VARCHAR(16) PRIMARY KEY, -- 'NSE', 'BSE', 'MCX', 'BINANCE'
    name VARCHAR(64) NOT NULL,
    country VARCHAR(3) DEFAULT 'IND',
    timezone VARCHAR(64) DEFAULT 'Asia/Kolkata',
    regular_open_time TIME DEFAULT '09:15:00',
    regular_close_time TIME DEFAULT '15:30:00',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE instruments (
    id VARCHAR(32) PRIMARY KEY, -- 'INS_NSE_RELIANCE'
    symbol VARCHAR(32) NOT NULL,
    exchange_id VARCHAR(16) NOT NULL REFERENCES exchanges(id),
    asset_class VARCHAR(16) NOT NULL, -- 'EQUITY', 'FUTURES', 'OPTIONS', etc.
    currency VARCHAR(8) NOT NULL DEFAULT 'INR',
    tick_size NUMERIC(10, 4) NOT NULL,
    lot_size INT NOT NULL DEFAULT 1,
    multiplier NUMERIC(12, 4) DEFAULT 1.0,
    timezone VARCHAR(64) DEFAULT 'Asia/Kolkata',
    
    -- Derivative Contract Fields
    expiry DATE,
    strike NUMERIC(12, 4),
    option_type VARCHAR(4), -- 'CE', 'PE'
    underlying_id VARCHAR(32) REFERENCES instruments(id),
    
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT uq_instrument UNIQUE (symbol, exchange_id, COALESCE(expiry, '1970-01-01'), COALESCE(strike, 0), COALESCE(option_type, ''))
);

CREATE INDEX idx_instruments_sym_exch ON instruments(symbol, exchange_id);
CREATE INDEX idx_instruments_asset_class ON instruments(asset_class);

CREATE TABLE data_sources (
    id VARCHAR(32) PRIMARY KEY, -- 'NSE_TBT', 'ZERODHA_WS', 'YAHOO_HIST'
    name VARCHAR(64) NOT NULL,
    provider VARCHAR(64) NOT NULL,
    has_candles BOOLEAN DEFAULT FALSE,
    has_trades BOOLEAN DEFAULT FALSE,
    has_depth BOOLEAN DEFAULT FALSE,
    has_aggressor_flag BOOLEAN DEFAULT FALSE,
    default_quality_tier INT NOT NULL, -- 1 = Level A, 2 = Level B, 3 = Level C, 4 = Level D
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE dataset_manifests (
    id VARCHAR(64) PRIMARY KEY, -- Hash or slug
    instrument_id VARCHAR(32) NOT NULL REFERENCES instruments(id),
    source_id VARCHAR(32) NOT NULL REFERENCES data_sources(id),
    start_date DATE NOT NULL,
    end_date DATE NOT NULL,
    timeframe VARCHAR(16) NOT NULL,
    record_count BIGINT NOT NULL,
    data_quality INT NOT NULL,
    file_path VARCHAR(256) NOT NULL,
    checksum VARCHAR(64) NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- ----------------------------------------------------------------------------
-- DOMAIN B: STRATEGY MANAGEMENT
-- ----------------------------------------------------------------------------

CREATE TABLE strategies (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL,
    name VARCHAR(128) NOT NULL,
    description TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE strategy_versions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    strategy_id UUID NOT NULL REFERENCES strategies(id) ON DELETE CASCADE,
    version INT NOT NULL,
    strategy_json JSONB NOT NULL,
    hash VARCHAR(64) NOT NULL, -- SHA-256 of canonical strategy_json
    created_at TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT uq_strategy_version UNIQUE (strategy_id, version)
);

CREATE INDEX idx_strategy_versions_hash ON strategy_versions(hash);

-- ----------------------------------------------------------------------------
-- DOMAIN C: BACKTESTING & REPRODUCIBILITY
-- ----------------------------------------------------------------------------

CREATE TABLE backtest_runs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL,
    strategy_version_id UUID NOT NULL REFERENCES strategy_versions(id),
    instrument_id VARCHAR(32) NOT NULL REFERENCES instruments(id),
    timeframe VARCHAR(16) NOT NULL,
    start_date DATE NOT NULL,
    end_date DATE NOT NULL,
    data_manifest_id VARCHAR(64) REFERENCES dataset_manifests(id),
    status VARCHAR(16) NOT NULL, -- 'PENDING', 'RUNNING', 'DONE', 'FAILED'
    config JSONB NOT NULL,       -- Portfolio, fees, slippage settings
    metrics JSONB,              -- Final performance indicators
    error_message TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    completed_at TIMESTAMPTZ
);

CREATE INDEX idx_backtest_runs_user ON backtest_runs(user_id);
CREATE INDEX idx_backtest_runs_strat ON backtest_runs(strategy_version_id);

CREATE TABLE backtest_trades (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    run_id UUID NOT NULL REFERENCES backtest_runs(id) ON DELETE CASCADE,
    signal_date TIMESTAMPTZ NOT NULL,
    entry_date TIMESTAMPTZ NOT NULL,
    exit_date TIMESTAMPTZ NOT NULL,
    side VARCHAR(8) NOT NULL,
    entry_price NUMERIC(16, 4) NOT NULL,
    exit_price NUMERIC(16, 4) NOT NULL,
    quantity INT NOT NULL,
    pnl NUMERIC(16, 4) NOT NULL,
    pnl_pct NUMERIC(10, 4) NOT NULL,
    r_multiple NUMERIC(10, 4),
    exit_reason VARCHAR(32) NOT NULL, -- 'STOP', 'TARGET', 'TRAIL', 'RULE', 'TIME'
    data_quality INT NOT NULL
);

CREATE INDEX idx_backtest_trades_run ON backtest_trades(run_id);

-- ----------------------------------------------------------------------------
-- DOMAIN E: PAPER TRADING LEDGERS
-- ----------------------------------------------------------------------------

CREATE TABLE paper_accounts (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL,
    name VARCHAR(64) NOT NULL,
    currency VARCHAR(8) DEFAULT 'INR',
    balance NUMERIC(16, 4) NOT NULL,
    equity NUMERIC(16, 4) NOT NULL,
    margin_used NUMERIC(16, 4) DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE paper_positions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    account_id UUID NOT NULL REFERENCES paper_accounts(id) ON DELETE CASCADE,
    instrument_id VARCHAR(32) NOT NULL REFERENCES instruments(id),
    quantity INT NOT NULL, -- Signed (+ for Long, - for Short, 0 for Flat)
    avg_entry_price NUMERIC(16, 4) NOT NULL,
    current_price NUMERIC(16, 4) NOT NULL,
    unrealized_pnl NUMERIC(16, 4) DEFAULT 0,
    realized_pnl NUMERIC(16, 4) DEFAULT 0,
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT uq_paper_pos UNIQUE (account_id, instrument_id)
);

CREATE TABLE paper_orders (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    account_id UUID NOT NULL REFERENCES paper_accounts(id) ON DELETE CASCADE,
    instrument_id VARCHAR(32) NOT NULL REFERENCES instruments(id),
    side VARCHAR(8) NOT NULL,        -- 'BUY', 'SELL'
    order_type VARCHAR(16) NOT NULL, -- 'MARKET', 'LIMIT', 'STOP_LOSS', 'STOP_LIMIT'
    price NUMERIC(16, 4),
    stop_price NUMERIC(16, 4),
    quantity INT NOT NULL,
    filled_quantity INT DEFAULT 0,
    avg_fill_price NUMERIC(16, 4),
    status VARCHAR(16) NOT NULL,     -- 'PENDING', 'QUEUED', 'FILLED', 'CANCELLED', 'REJECTED'
    queue_ahead_volume BIGINT DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_paper_orders_account ON paper_orders(account_id);
CREATE INDEX idx_paper_orders_status ON paper_orders(status);

CREATE TABLE paper_fills (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    order_id UUID NOT NULL REFERENCES paper_orders(id) ON DELETE CASCADE,
    account_id UUID NOT NULL REFERENCES paper_accounts(id) ON DELETE CASCADE,
    instrument_id VARCHAR(32) NOT NULL REFERENCES instruments(id),
    price NUMERIC(16, 4) NOT NULL,
    quantity INT NOT NULL,
    fee NUMERIC(12, 4) DEFAULT 0,
    slippage NUMERIC(12, 4) DEFAULT 0,
    executed_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_paper_fills_order ON paper_fills(order_id);

CREATE TABLE paper_snapshots (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    account_id UUID NOT NULL REFERENCES paper_accounts(id) ON DELETE CASCADE,
    timestamp TIMESTAMPTZ NOT NULL,
    balance NUMERIC(16, 4) NOT NULL,
    equity NUMERIC(16, 4) NOT NULL,
    margin_used NUMERIC(16, 4) NOT NULL,
    unrealized_pnl NUMERIC(16, 4) NOT NULL
);

CREATE INDEX idx_paper_snapshots_acct_time ON paper_snapshots(account_id, timestamp);

-- ----------------------------------------------------------------------------
-- DOMAIN F: USERS & USER PREFERENCES
-- ----------------------------------------------------------------------------

CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    email VARCHAR(255) UNIQUE NOT NULL,
    name VARCHAR(128),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE watchlists (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name VARCHAR(64) NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE watchlist_instruments (
    watchlist_id UUID NOT NULL REFERENCES watchlists(id) ON DELETE CASCADE,
    instrument_id VARCHAR(32) NOT NULL REFERENCES instruments(id) ON DELETE CASCADE,
    sort_order INT DEFAULT 0,
    PRIMARY KEY (watchlist_id, instrument_id)
);

CREATE TABLE chart_layouts (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name VARCHAR(64) NOT NULL,
    layout_json JSONB NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
