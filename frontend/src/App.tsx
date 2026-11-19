import React, { useState } from "react";
import { CanvasFootprintChart } from "./components/CanvasFootprintChart";
import { FootprintChart } from "./components/FootprintChart";
import { MarketExplorer } from "./components/MarketExplorer";
import { PaperTradingDashboard } from "./components/PaperTradingDashboard";
import { VisualStrategyBuilder } from "./components/VisualStrategyBuilder";
import { VolumeProfileView } from "./components/VolumeProfileView";
import {
  AssetClass,
  DataQuality,
  FootprintBar,
  InstrumentMaster,
  PaperOrder,
  VolumeProfile,
} from "./types/domain";
import { BacktestResult, StrategyIR } from "./types/strategy";

// Mock Sample Data for Initial View
const DEFAULT_INSTRUMENTS: InstrumentMaster[] = [
  {
    instrument_id: "INS_NSE_RELIANCE",
    symbol: "RELIANCE",
    exchange: "NSE",
    asset_class: "EQUITY",
    currency: "INR",
    tick_size: 0.05,
    lot_size: 1,
    multiplier: 1.0,
    timezone: "Asia/Kolkata",
  },
  {
    instrument_id: "INS_NSE_NIFTY_FUT",
    symbol: "NIFTY26NOVFUT",
    exchange: "NSE",
    asset_class: "FUTURES",
    currency: "INR",
    tick_size: 0.05,
    lot_size: 50,
    multiplier: 50.0,
    timezone: "Asia/Kolkata",
    expiry: "2026-11-26",
  },
  {
    instrument_id: "INS_BINANCE_BTCUSDT",
    symbol: "BTCUSDT",
    exchange: "BINANCE",
    asset_class: "CRYPTO",
    currency: "USDT",
    tick_size: 0.1,
    lot_size: 1,
    multiplier: 1.0,
    timezone: "UTC",
  },
];

const SAMPLE_FOOTPRINT_BARS: FootprintBar[] = [
  {
    instrument_id: "INS_NSE_RELIANCE",
    timestamp_utc: Date.now() - 1500000,
    timeframe: "5m",
    open: 2499.0,
    high: 2502.5,
    low: 2498.0,
    close: 2502.0,
    volume: 1420,
    delta: 220,
    poc_price: 2501.0,
    value_area_high: 2502.0,
    value_area_low: 2500.0,
    clusters: [
      { price: 2502.5, bid_volume: 30, ask_volume: 140, total_volume: 170, delta: 110, delta_pct: 64.7, is_buy_imbalance: true, is_sell_imbalance: false },
      { price: 2502.0, bid_volume: 80, ask_volume: 290, total_volume: 370, delta: 210, delta_pct: 56.7, is_buy_imbalance: true, is_sell_imbalance: false },
      { price: 2501.0, bid_volume: 220, ask_volume: 250, total_volume: 470, delta: 30, delta_pct: 6.3, is_buy_imbalance: false, is_sell_imbalance: false },
      { price: 2500.0, bid_volume: 180, ask_volume: 90, total_volume: 270, delta: -90, delta_pct: -33.3, is_buy_imbalance: false, is_sell_imbalance: false },
      { price: 2499.0, bid_volume: 90, ask_volume: 50, total_volume: 140, delta: -40, delta_pct: -28.5, is_buy_imbalance: false, is_sell_imbalance: false },
    ],
    provenance: { quality: DataQuality.LEVEL_A_EXCHANGE_VERIFIED, side_method: "EXCHANGE_FLAG", source_id: "NSE_TBT", confidence: 1.0, is_estimated: false },
  },
  {
    instrument_id: "INS_NSE_RELIANCE",
    timestamp_utc: Date.now() - 1200000,
    timeframe: "5m",
    open: 2502.0,
    high: 2505.0,
    low: 2501.0,
    close: 2504.5,
    volume: 1840,
    delta: 340,
    poc_price: 2503.0,
    value_area_high: 2504.5,
    value_area_low: 2502.0,
    clusters: [
      { price: 2505.0, bid_volume: 40, ask_volume: 190, total_volume: 230, delta: 150, delta_pct: 65.2, is_buy_imbalance: true, is_sell_imbalance: false },
      { price: 2504.0, bid_volume: 120, ask_volume: 380, total_volume: 500, delta: 260, delta_pct: 52.0, is_buy_imbalance: true, is_sell_imbalance: false },
      { price: 2503.0, bid_volume: 350, ask_volume: 370, total_volume: 720, delta: 20, delta_pct: 2.7, is_buy_imbalance: false, is_sell_imbalance: false },
      { price: 2502.0, bid_volume: 240, ask_volume: 150, total_volume: 390, delta: -90, delta_pct: -23.0, is_buy_imbalance: false, is_sell_imbalance: false },
    ],
    provenance: { quality: DataQuality.LEVEL_A_EXCHANGE_VERIFIED, side_method: "EXCHANGE_FLAG", source_id: "NSE_TBT", confidence: 1.0, is_estimated: false },
  },
  {
    instrument_id: "INS_NSE_RELIANCE",
    timestamp_utc: Date.now() - 900000,
    timeframe: "5m",
    open: 2504.5,
    high: 2508.0,
    low: 2504.0,
    close: 2507.5,
    volume: 2310,
    delta: 580,
    poc_price: 2506.0,
    value_area_high: 2507.5,
    value_area_low: 2505.0,
    clusters: [
      { price: 2508.0, bid_volume: 50, ask_volume: 220, total_volume: 270, delta: 170, delta_pct: 62.9, is_buy_imbalance: true, is_sell_imbalance: false },
      { price: 2507.0, bid_volume: 110, ask_volume: 450, total_volume: 560, delta: 340, delta_pct: 60.7, is_buy_imbalance: true, is_sell_imbalance: false },
      { price: 2506.0, bid_volume: 380, ask_volume: 520, total_volume: 900, delta: 140, delta_pct: 15.5, is_buy_imbalance: false, is_sell_imbalance: false },
      { price: 2505.0, bid_volume: 290, ask_volume: 210, total_volume: 500, delta: -80, delta_pct: -16.0, is_buy_imbalance: false, is_sell_imbalance: false },
      { price: 2504.0, bid_volume: 60, ask_volume: 20, total_volume: 80, delta: -40, delta_pct: -50.0, is_buy_imbalance: false, is_sell_imbalance: false },
    ],
    provenance: { quality: DataQuality.LEVEL_A_EXCHANGE_VERIFIED, side_method: "EXCHANGE_FLAG", source_id: "NSE_TBT", confidence: 1.0, is_estimated: false },
  },
  {
    instrument_id: "INS_NSE_RELIANCE",
    timestamp_utc: Date.now() - 600000,
    timeframe: "5m",
    open: 2507.5,
    high: 2509.0,
    low: 2503.5,
    close: 2504.0,
    volume: 2750,
    delta: -430,
    poc_price: 2506.0,
    value_area_high: 2507.0,
    value_area_low: 2504.5,
    clusters: [
      { price: 2509.0, bid_volume: 90, ask_volume: 30, total_volume: 120, delta: -60, delta_pct: -50.0, is_buy_imbalance: false, is_sell_imbalance: false },
      { price: 2508.0, bid_volume: 340, ask_volume: 90, total_volume: 430, delta: -250, delta_pct: -58.1, is_buy_imbalance: false, is_sell_imbalance: true },
      { price: 2507.0, bid_volume: 480, ask_volume: 150, total_volume: 630, delta: -330, delta_pct: -52.3, is_buy_imbalance: false, is_sell_imbalance: true },
      { price: 2506.0, bid_volume: 420, ask_volume: 410, total_volume: 830, delta: -10, delta_pct: -1.2, is_buy_imbalance: false, is_sell_imbalance: false },
      { price: 2505.0, bid_volume: 380, ask_volume: 240, total_volume: 620, delta: -140, delta_pct: -22.5, is_buy_imbalance: false, is_sell_imbalance: false },
      { price: 2504.0, bid_volume: 90, ask_volume: 30, total_volume: 120, delta: -60, delta_pct: -50.0, is_buy_imbalance: false, is_sell_imbalance: false },
    ],
    provenance: { quality: DataQuality.LEVEL_A_EXCHANGE_VERIFIED, side_method: "EXCHANGE_FLAG", source_id: "NSE_TBT", confidence: 1.0, is_estimated: false },
  },
  {
    instrument_id: "INS_NSE_RELIANCE",
    timestamp_utc: Date.now() - 300000,
    timeframe: "5m",
    open: 2504.0,
    high: 2506.5,
    low: 2502.0,
    close: 2505.5,
    volume: 1980,
    delta: 190,
    poc_price: 2505.0,
    value_area_high: 2506.0,
    value_area_low: 2503.5,
    clusters: [
      { price: 2506.5, bid_volume: 40, ask_volume: 160, total_volume: 200, delta: 120, delta_pct: 60.0, is_buy_imbalance: true, is_sell_imbalance: false },
      { price: 2505.0, bid_volume: 310, ask_volume: 450, total_volume: 760, delta: 140, delta_pct: 18.4, is_buy_imbalance: false, is_sell_imbalance: false },
      { price: 2504.0, bid_volume: 290, ask_volume: 260, total_volume: 550, delta: -30, delta_pct: -5.4, is_buy_imbalance: false, is_sell_imbalance: false },
      { price: 2503.0, bid_volume: 240, ask_volume: 180, total_volume: 420, delta: -60, delta_pct: -14.2, is_buy_imbalance: false, is_sell_imbalance: false },
      { price: 2502.0, bid_volume: 40, ask_volume: 10, total_volume: 50, delta: -30, delta_pct: -60.0, is_buy_imbalance: false, is_sell_imbalance: false },
    ],
    provenance: { quality: DataQuality.LEVEL_A_EXCHANGE_VERIFIED, side_method: "EXCHANGE_FLAG", source_id: "NSE_TBT", confidence: 1.0, is_estimated: false },
  },
];

const SAMPLE_PROFILE: VolumeProfile = {
  instrument_id: "INS_NSE_RELIANCE",
  session_date: "2026-11-19",
  profile_type: "SESSION",
  start_time_utc: Date.now() - 3600000,
  end_time_utc: Date.now(),
  tick_size: 0.05,
  bins: {
    "2505.0": 1200,
    "2504.0": 4500,
    "2503.0": 9800,
    "2502.0": 6200,
    "2501.0": 2100,
  },
  total_volume: 23800,
  poc_price: 2503.0,
  poc_volume: 9800,
  vah_price: 2504.0,
  val_price: 2502.0,
  high_volume_nodes: [2503.0],
  low_volume_nodes: [2501.0],
  provenance: {
    quality: DataQuality.LEVEL_A_EXCHANGE_VERIFIED,
    side_method: "EXCHANGE_FLAG",
    source_id: "NSE_TBT",
    confidence: 1.0,
    is_estimated: false,
  },
};

export const App: React.FC = () => {
  const [activeTab, setActiveTab] = useState<
    "explorer" | "orderflow" | "studio" | "backtest" | "paper"
  >("orderflow");

  const [footprintViewMode, setFootprintViewMode] = useState<"canvas" | "table">("canvas");

  const [selectedInst, setSelectedInst] = useState<InstrumentMaster>(
    DEFAULT_INSTRUMENTS[0]
  );

  const [backtestResult, setBacktestResult] = useState<BacktestResult | null>(null);

  // Paper trading state
  const [paperAccount, setPaperAccount] = useState({
    cash: 100000,
    equity: 100000,
    realized_pnl: 0,
    total_fees: 0,
    open_positions_count: 0,
  });

  const [paperPositions, setPaperPositions] = useState<any[]>([]);
  const [paperOrders, setPaperOrders] = useState<PaperOrder[]>([]);

  const handleCompileStrategy = async (strategy: StrategyIR) => {
    // Simulated compilation response
    return {
      highest_required_quality: "LEVEL_A_EXCHANGE_VERIFIED",
      required_feeds: ["candle", "trade_ticks", "footprint"],
    };
  };

  const handleRunBacktest = async (strategy: StrategyIR) => {
    // Simulated backtest run response
    const mockRes: BacktestResult = {
      metrics: {
        total_trades: 14,
        winning_trades: 9,
        losing_trades: 5,
        win_rate_pct: 64.28,
        profit_factor: 2.15,
        net_pnl: 14250.0,
        total_fees: 320.0,
        max_drawdown_pct: 3.4,
        sharpe_ratio: 1.85,
        final_equity: 113930.0,
      },
      equity_curve: Array.from({ length: 20 }, (_, i) => ({
        timestamp_utc: Date.now() - (20 - i) * 3600000,
        equity: 100000 + i * 720,
        cash: 100000 + i * 500,
        drawdown_pct: i === 5 ? 1.5 : 0.0,
      })),
      closed_trades: [
        {
          instrument_id: selectedInst.instrument_id,
          symbol: selectedInst.symbol,
          side: "LONG",
          quantity: 100,
          entry_price: 2500.0,
          exit_price: 2580.0,
          entry_time_utc: Date.now() - 7200000,
          exit_time_utc: Date.now() - 3600000,
          gross_pnl: 8000.0,
          net_pnl: 7920.0,
          total_fees: 80.0,
          exit_reason: "TARGET",
        },
      ],
    };
    setBacktestResult(mockRes);
    setActiveTab("backtest");
  };

  const handlePlacePaperOrder = (orderData: Partial<PaperOrder>) => {
    const newOrder: PaperOrder = {
      order_id: orderData.order_id || `ORD_${Date.now()}`,
      account_id: orderData.account_id || "PAPER_ACC_01",
      instrument_id: orderData.instrument_id || selectedInst.instrument_id,
      side: orderData.side || "BUY",
      order_type: orderData.order_type || "LIMIT",
      quantity: orderData.quantity || 50,
      price: orderData.price || 2502.0,
      status: "FILLED",
      queue_ahead_volume: 0,
      created_time_utc: Date.now(),
      updated_time_utc: Date.now(),
    };

    setPaperOrders([newOrder, ...paperOrders]);

    // Update positions
    const pos = {
      instrument_id: selectedInst.instrument_id,
      symbol: selectedInst.symbol,
      side: newOrder.side === "BUY" ? "LONG" : "SHORT",
      quantity: newOrder.quantity,
      entry_price: newOrder.price || 2502.0,
      current_price: 2504.5,
      unrealized_pnl: (2504.5 - (newOrder.price || 2502.0)) * newOrder.quantity,
    };
    setPaperPositions([pos]);
    setPaperAccount({
      ...paperAccount,
      equity: paperAccount.cash + pos.unrealized_pnl,
      open_positions_count: 1,
    });
  };

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col font-sans">
      {/* Top Navbar */}
      <header className="border-b border-slate-800 bg-slate-900/80 backdrop-blur sticky top-0 z-50 px-6 py-3.5 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-gradient-to-tr from-indigo-600 to-cyan-500 flex items-center justify-center font-black text-white text-sm shadow-lg shadow-indigo-600/30">
            SL
          </div>
          <div>
            <h1 className="text-sm font-extrabold tracking-tight text-white flex items-center gap-2">
              STRATLAB
              <span className="text-[10px] font-mono px-1.5 py-0.2 rounded bg-indigo-500/20 text-indigo-300 border border-indigo-500/40">
                PROVENANCE V2
              </span>
            </h1>
            <p className="text-[10px] text-slate-400">
              One Engine • Multi-Source • Visual IR • Queue Execution
            </p>
          </div>
        </div>

        {/* Global Active Ticker Indicator */}
        <div className="flex items-center gap-3">
          <div className="bg-slate-950 border border-slate-800 rounded-lg px-3 py-1 text-xs font-mono flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-emerald-400"></span>
            <span className="text-slate-400">{selectedInst.exchange}:</span>
            <span className="font-bold text-slate-100">{selectedInst.symbol}</span>
            <span className="text-[10px] text-slate-500">({selectedInst.asset_class})</span>
          </div>

          <div className="px-2.5 py-1 rounded-md bg-emerald-500/10 border border-emerald-500/30 text-[11px] font-mono font-semibold text-emerald-400 flex items-center gap-1.5">
            <span>✓ Genuine Order Flow</span>
          </div>
        </div>
      </header>

      {/* Main Tabs Navigation */}
      <nav className="border-b border-slate-800/80 bg-slate-900/40 px-6 py-2 flex items-center gap-1 text-xs">
        {[
          { id: "explorer", label: "01 · Market Explorer" },
          { id: "orderflow", label: "02 · Order Flow Lab" },
          { id: "studio", label: "03 · Strategy Studio" },
          { id: "backtest", label: "04 · Backtest Lab" },
          { id: "paper", label: "05 · Paper Trading" },
        ].map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id as any)}
            className={`px-4 py-1.5 rounded-lg font-medium transition-all ${
              activeTab === tab.id
                ? "bg-indigo-600 text-white font-bold shadow-md shadow-indigo-600/30"
                : "text-slate-400 hover:text-slate-200 hover:bg-slate-800/40"
            }`}
          >
            {tab.label}
          </button>
        ))}
      </nav>

      {/* Tab Panels */}
      <main className="flex-1 p-6 max-w-7xl mx-auto w-full flex flex-col gap-6">
        {/* Tab 01: Market Explorer */}
        {activeTab === "explorer" && (
          <MarketExplorer
            instruments={DEFAULT_INSTRUMENTS}
            selectedInstrumentId={selectedInst.instrument_id}
            onSelectInstrument={(inst) => {
              setSelectedInst(inst);
              setActiveTab("orderflow");
            }}
          />
        )}

        {/* Tab 02: Order Flow Lab */}
        {activeTab === "orderflow" && (
          <div className="flex flex-col gap-6">
            {/* View Mode Toggle */}
            <div className="flex items-center justify-between bg-slate-900 border border-slate-800 rounded-lg p-2.5">
              <span className="text-xs font-semibold text-slate-300">
                Footprint Rendering Engine:
              </span>
              <div className="flex rounded-md border border-slate-700 overflow-hidden text-xs font-mono">
                <button
                  onClick={() => setFootprintViewMode("canvas")}
                  className={`px-3 py-1 font-bold transition-all ${
                    footprintViewMode === "canvas"
                      ? "bg-indigo-600 text-white shadow-md shadow-indigo-600/30"
                      : "bg-slate-950 text-slate-400 hover:text-slate-200"
                  }`}
                >
                  ⚡ Canvas (60 FPS Pan & Zoom)
                </button>
                <button
                  onClick={() => setFootprintViewMode("table")}
                  className={`px-3 py-1 font-bold transition-all ${
                    footprintViewMode === "table"
                      ? "bg-indigo-600 text-white shadow-md shadow-indigo-600/30"
                      : "bg-slate-950 text-slate-400 hover:text-slate-200"
                  }`}
                >
                  Cluster Table Ladder
                </button>
              </div>
            </div>

            {footprintViewMode === "canvas" ? (
              <CanvasFootprintChart
                bars={SAMPLE_FOOTPRINT_BARS}
                symbol={selectedInst.symbol}
                timeframe="5m"
              />
            ) : (
              <FootprintChart
                bars={SAMPLE_FOOTPRINT_BARS}
                symbol={selectedInst.symbol}
                timeframe="5m"
              />
            )}

            <VolumeProfileView profile={SAMPLE_PROFILE} />
          </div>
        )}

        {/* Tab 03: Strategy Studio */}
        {activeTab === "studio" && (
          <VisualStrategyBuilder
            onCompileStrategy={handleCompileStrategy}
            onRunBacktest={handleRunBacktest}
          />
        )}

        {/* Tab 04: Backtest Lab */}
        {activeTab === "backtest" && (
          <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-2xl flex flex-col gap-5">
            <div className="flex items-center justify-between pb-3 border-b border-slate-800">
              <div>
                <h3 className="text-lg font-bold text-slate-100 flex items-center gap-2">
                  <span className="w-2 h-2 rounded-full bg-cyan-400"></span>
                  Historical Backtest Lab
                </h3>
                <p className="text-xs text-slate-400">
                  Zero look-ahead deterministic simulation on {selectedInst.symbol}
                </p>
              </div>
            </div>

            {backtestResult ? (
              <div className="flex flex-col gap-5">
                {/* Metrics KPI Cards */}
                <div className="grid grid-cols-2 sm:grid-cols-5 gap-3 font-mono text-xs">
                  <div className="bg-slate-950 p-3 rounded-lg border border-slate-800">
                    <span className="text-slate-500 text-[10px] block">Net Realized PnL</span>
                    <span className="text-emerald-400 font-bold text-base">
                      +₹{backtestResult.metrics.net_pnl.toLocaleString()}
                    </span>
                  </div>
                  <div className="bg-slate-950 p-3 rounded-lg border border-slate-800">
                    <span className="text-slate-500 text-[10px] block">Win Rate</span>
                    <span className="text-indigo-400 font-bold text-base">
                      {backtestResult.metrics.win_rate_pct.toFixed(1)}%
                    </span>
                  </div>
                  <div className="bg-slate-950 p-3 rounded-lg border border-slate-800">
                    <span className="text-slate-500 text-[10px] block">Profit Factor</span>
                    <span className="text-indigo-300 font-bold text-base">
                      {backtestResult.metrics.profit_factor}
                    </span>
                  </div>
                  <div className="bg-slate-950 p-3 rounded-lg border border-slate-800">
                    <span className="text-slate-500 text-[10px] block">Max Drawdown</span>
                    <span className="text-rose-400 font-bold text-base">
                      {backtestResult.metrics.max_drawdown_pct.toFixed(2)}%
                    </span>
                  </div>
                  <div className="bg-slate-950 p-3 rounded-lg border border-slate-800">
                    <span className="text-slate-500 text-[10px] block">Annualized Sharpe</span>
                    <span className="text-amber-400 font-bold text-base">
                      {backtestResult.metrics.sharpe_ratio}
                    </span>
                  </div>
                </div>

                {/* Closed Trades Blotter */}
                <div className="flex flex-col gap-2">
                  <h4 className="text-xs font-bold text-slate-300 uppercase tracking-wider">
                    Simulated Closed Trades ({backtestResult.closed_trades.length})
                  </h4>
                  <div className="overflow-x-auto rounded-lg border border-slate-800 font-mono text-xs">
                    <table className="w-full text-left">
                      <thead className="bg-slate-950 text-slate-400 text-[10px] uppercase border-b border-slate-800">
                        <tr>
                          <th className="py-2 px-3">Symbol</th>
                          <th className="py-2 px-3">Side</th>
                          <th className="py-2 px-3 text-right">Entry</th>
                          <th className="py-2 px-3 text-right">Exit</th>
                          <th className="py-2 px-3 text-right">Net PnL</th>
                          <th className="py-2 px-3 text-right">Fees</th>
                          <th className="py-2 px-3 text-center">Reason</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-800/60">
                        {backtestResult.closed_trades.map((t, idx) => (
                          <tr key={idx} className="hover:bg-slate-800/30">
                            <td className="py-2 px-3 font-bold text-slate-200">{t.symbol}</td>
                            <td className="py-2 px-3 text-emerald-400 font-bold">{t.side}</td>
                            <td className="py-2 px-3 text-right">{t.entry_price.toFixed(2)}</td>
                            <td className="py-2 px-3 text-right">{t.exit_price.toFixed(2)}</td>
                            <td className="py-2 px-3 text-right text-emerald-400 font-bold">
                              +₹{t.net_pnl.toFixed(2)}
                            </td>
                            <td className="py-2 px-3 text-right text-slate-400">
                              ₹{t.total_fees.toFixed(2)}
                            </td>
                            <td className="py-2 px-3 text-center">
                              <span className="px-1.5 py-0.5 rounded bg-emerald-500/20 text-emerald-300 text-[10px] font-bold">
                                {t.exit_reason}
                              </span>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              </div>
            ) : (
              <div className="text-center py-12 text-slate-500 text-xs">
                No backtest results yet. Go to Strategy Studio and click "Run Backtest
                Simulation".
              </div>
            )}
          </div>
        )}

        {/* Tab 05: Paper Trading */}
        {activeTab === "paper" && (
          <PaperTradingDashboard
            account={paperAccount}
            positions={paperPositions}
            orders={paperOrders}
            selectedSymbol={selectedInst.symbol}
            selectedInstrumentId={selectedInst.instrument_id}
            onSubmitOrder={handlePlacePaperOrder}
          />
        )}
      </main>
    </div>
  );
};
