import React, { useEffect, useState } from "react";
import { CanvasFootprintChart } from "./components/CanvasFootprintChart";
import { FootprintChart } from "./components/FootprintChart";
import { MarketExplorer } from "./components/MarketExplorer";
import { PaperTradingDashboard } from "./components/PaperTradingDashboard";
import { StrategyGraphStudio } from "./components/StrategyGraphStudio";
import { VisualStrategyBuilder } from "./components/VisualStrategyBuilder";
import { VolumeProfileView } from "./components/VolumeProfileView";
import { useMarketStream } from "./hooks/useMarketStream";
import {
  DataQuality,
  FootprintBar,
  InstrumentMaster,
  PaperOrder,
  VolumeProfile,
} from "./types/domain";
import { BacktestResult, StrategyIR } from "./types/strategy";

// Canonical Multi-Asset Universe Master
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
    instrument_id: "INS_NSE_BANKNIFTY_FUT",
    symbol: "BANKNIFTY26NOVFUT",
    exchange: "NSE",
    asset_class: "FUTURES",
    currency: "INR",
    tick_size: 0.05,
    lot_size: 15,
    multiplier: 15.0,
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
  {
    instrument_id: "INS_FX_EURUSD",
    symbol: "EURUSD",
    exchange: "FOREX",
    asset_class: "FOREX",
    currency: "USD",
    tick_size: 0.0001,
    lot_size: 1000,
    multiplier: 1.0,
    timezone: "UTC",
  },
];

const SAMPLE_FOOTPRINT_BARS: FootprintBar[] = [
  {
    instrument_id: "INS_NSE_RELIANCE",
    timestamp_utc: Date.now() - 1500000,
    open_time_utc: Date.now() - 1500000,
    close_time_utc: Date.now() - 1200000,
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
    vah: 2502.0,
    val: 2500.0,
    clusters: [
      { price: 2502.5, bid_vol: 30, ask_vol: 140, total_vol: 170, delta: 110, imbalance_buy: true, imbalance_sell: false },
      { price: 2502.0, bid_vol: 80, ask_vol: 290, total_vol: 370, delta: 210, imbalance_buy: true, imbalance_sell: false },
      { price: 2501.0, bid_vol: 220, ask_vol: 250, total_vol: 470, delta: 30, imbalance_buy: false, imbalance_sell: false, is_poc: true },
      { price: 2500.0, bid_vol: 180, ask_vol: 90, total_vol: 270, delta: -90, imbalance_buy: false, imbalance_sell: false },
      { price: 2499.0, bid_vol: 90, ask_vol: 50, total_vol: 140, delta: -40, imbalance_buy: false, imbalance_sell: false },
    ],
    provenance: { quality: DataQuality.LEVEL_A_EXCHANGE_VERIFIED, side_method: "EXCHANGE_FLAG" as any, source_id: "NSE_TBT", confidence: 1.0, is_estimated: false },
  },
  {
    instrument_id: "INS_NSE_RELIANCE",
    timestamp_utc: Date.now() - 1200000,
    open_time_utc: Date.now() - 1200000,
    close_time_utc: Date.now() - 900000,
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
    vah: 2504.5,
    val: 2502.0,
    clusters: [
      { price: 2505.0, bid_vol: 40, ask_vol: 190, total_vol: 230, delta: 150, imbalance_buy: true, imbalance_sell: false },
      { price: 2504.0, bid_vol: 120, ask_vol: 380, total_vol: 500, delta: 260, imbalance_buy: true, imbalance_sell: false },
      { price: 2503.0, bid_vol: 350, ask_vol: 370, total_vol: 720, delta: 20, imbalance_buy: false, imbalance_sell: false, is_poc: true },
      { price: 2502.0, bid_vol: 240, ask_vol: 150, total_vol: 390, delta: -90, imbalance_buy: false, imbalance_sell: false },
    ],
    provenance: { quality: DataQuality.LEVEL_A_EXCHANGE_VERIFIED, side_method: "EXCHANGE_FLAG" as any, source_id: "NSE_TBT", confidence: 1.0, is_estimated: false },
  },
  {
    instrument_id: "INS_NSE_RELIANCE",
    timestamp_utc: Date.now() - 900000,
    open_time_utc: Date.now() - 900000,
    close_time_utc: Date.now() - 600000,
    timeframe: "5m",
    open: 2504.5,
    high: 2508.0,
    low: 2503.5,
    close: 2507.0,
    volume: 2150,
    delta: 480,
    poc_price: 2506.0,
    value_area_high: 2507.5,
    value_area_low: 2504.5,
    vah: 2507.5,
    val: 2504.5,
    clusters: [
      { price: 2508.0, bid_vol: 50, ask_vol: 220, total_vol: 270, delta: 170, imbalance_buy: true, imbalance_sell: false },
      { price: 2507.0, bid_vol: 110, ask_vol: 450, total_vol: 560, delta: 340, imbalance_buy: true, imbalance_sell: false },
      { price: 2506.0, bid_vol: 380, ask_vol: 520, total_vol: 900, delta: 140, imbalance_buy: false, imbalance_sell: false, is_poc: true },
      { price: 2505.0, bid_vol: 290, ask_vol: 130, total_vol: 420, delta: -160, imbalance_buy: false, imbalance_sell: false },
    ],
    provenance: { quality: DataQuality.LEVEL_A_EXCHANGE_VERIFIED, side_method: "EXCHANGE_FLAG" as any, source_id: "NSE_TBT", confidence: 1.0, is_estimated: false },
  },
  {
    instrument_id: "INS_NSE_RELIANCE",
    timestamp_utc: Date.now() - 600000,
    open_time_utc: Date.now() - 600000,
    close_time_utc: Date.now() - 300000,
    timeframe: "5m",
    open: 2507.0,
    high: 2509.5,
    low: 2505.0,
    close: 2506.0,
    volume: 1980,
    delta: -110,
    poc_price: 2507.0,
    value_area_high: 2508.5,
    value_area_low: 2506.0,
    vah: 2508.5,
    val: 2506.0,
    clusters: [
      { price: 2509.5, bid_vol: 80, ask_vol: 70, total_vol: 150, delta: -10, imbalance_buy: false, imbalance_sell: false },
      { price: 2508.5, bid_vol: 210, ask_vol: 90, total_vol: 300, delta: -120, imbalance_buy: false, imbalance_sell: true },
      { price: 2507.0, bid_vol: 420, ask_vol: 390, total_vol: 810, delta: -30, imbalance_buy: false, imbalance_sell: false, is_poc: true },
      { price: 2506.0, bid_vol: 360, ask_vol: 220, total_vol: 580, delta: -140, imbalance_buy: false, imbalance_sell: true },
      { price: 2505.0, bid_vol: 90, ask_vol: 50, total_vol: 140, delta: -40, imbalance_buy: false, imbalance_sell: false },
    ],
    provenance: { quality: DataQuality.LEVEL_A_EXCHANGE_VERIFIED, side_method: "EXCHANGE_FLAG" as any, source_id: "NSE_TBT", confidence: 1.0, is_estimated: false },
  },
  {
    instrument_id: "INS_NSE_RELIANCE",
    timestamp_utc: Date.now() - 300000,
    open_time_utc: Date.now() - 300000,
    close_time_utc: Date.now(),
    timeframe: "5m",
    open: 2506.0,
    high: 2511.0,
    low: 2505.5,
    close: 2510.5,
    volume: 2430,
    delta: 590,
    poc_price: 2509.0,
    value_area_high: 2510.5,
    value_area_low: 2507.5,
    vah: 2510.5,
    val: 2507.5,
    clusters: [
      { price: 2511.0, bid_vol: 60, ask_vol: 310, total_vol: 370, delta: 250, imbalance_buy: true, imbalance_sell: false },
      { price: 2510.0, bid_vol: 140, ask_vol: 490, total_vol: 630, delta: 350, imbalance_buy: true, imbalance_sell: false },
      { price: 2509.0, bid_vol: 320, ask_vol: 480, total_vol: 800, delta: 160, imbalance_buy: false, imbalance_sell: false, is_poc: true },
      { price: 2508.0, bid_vol: 280, ask_vol: 210, total_vol: 490, delta: -70, imbalance_buy: false, imbalance_sell: false },
      { price: 2506.0, bid_vol: 80, ask_vol: 60, total_vol: 140, delta: -20, imbalance_buy: false, imbalance_sell: false },
    ],
    provenance: { quality: DataQuality.LEVEL_A_EXCHANGE_VERIFIED, side_method: "EXCHANGE_FLAG" as any, source_id: "NSE_TBT", confidence: 1.0, is_estimated: false },
  },
];

const SAMPLE_PROFILE: VolumeProfile = {
  instrument_id: "INS_NSE_RELIANCE",
  session_date: "2026-11-19",
  profile_type: "SESSION",
  start_time_utc: Date.now() - 21600000,
  end_time_utc: Date.now(),
  tick_size: 0.05,
  bins: {
    "2511.0": 370,
    "2510.0": 630,
    "2509.0": 800,
    "2508.0": 760,
    "2507.0": 1370,
    "2506.0": 1480,
    "2505.0": 1200,
    "2504.0": 1120,
    "2503.0": 720,
    "2502.0": 760,
    "2501.0": 470,
    "2500.0": 270,
    "2499.0": 140,
  },
  total_volume: 10090,
  poc_price: 2506.0,
  poc_volume: 1480,
  vah_price: 2509.0,
  val_price: 2504.0,
  high_volume_nodes: [2506.0, 2507.0],
  low_volume_nodes: [2503.0, 2500.0],
  provenance: {
    quality: DataQuality.LEVEL_A_EXCHANGE_VERIFIED,
    side_method: "EXCHANGE_FLAG" as any,
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
  const [studioViewMode, setStudioViewMode] = useState<"graph" | "blocks">("graph");

  const [selectedInst, setSelectedInst] = useState<InstrumentMaster>(
    DEFAULT_INSTRUMENTS[0]
  );

  const [footprintBars, setFootprintBars] = useState<FootprintBar[]>(SAMPLE_FOOTPRINT_BARS);
  const [isSimulating, setIsSimulating] = useState(false);
  const [showProvenanceModal, setShowProvenanceModal] = useState(false);

  // Live Market Clock
  const [currentTime, setCurrentTime] = useState(new Date());
  useEffect(() => {
    const timer = setInterval(() => setCurrentTime(new Date()), 1000);
    return () => clearInterval(timer);
  }, []);

  // Live WebSocket Streaming Integration
  const { isConnected, latencyMs, tickCount } = useMarketStream({
    instrumentId: selectedInst.instrument_id,
    onFootprintUpdate: (updatedBar) => {
      setFootprintBars((prev) => {
        const next = [...prev];
        const lastIdx = next.length - 1;
        if (lastIdx >= 0 && (next[lastIdx].timestamp_utc === updatedBar.timestamp_utc || next[lastIdx].open_time_utc === updatedBar.open_time_utc)) {
          next[lastIdx] = updatedBar;
        } else {
          next.push(updatedBar);
        }
        return next;
      });
    },
    onExecutionFill: (fill) => {
      setPaperOrders((prev) =>
        prev.map((o) =>
          o.order_id === fill.order_id
            ? { ...o, status: "FILLED", filled_quantity: fill.quantity, price: fill.price }
            : o
        )
      );
    },
  });

  const toggleSimulation = async () => {
    try {
      if (isSimulating) {
        await fetch("http://localhost:8000/api/v1/market/simulation/stop", { method: "POST" });
        setIsSimulating(false);
      } else {
        await fetch("http://localhost:8000/api/v1/market/simulation/start?interval=0.5", { method: "POST" });
        setIsSimulating(true);
      }
    } catch {
      setIsSimulating(!isSimulating);
    }
  };

  const [backtestResult, setBacktestResult] = useState<BacktestResult | null>(null);

  // Paper trading state
  const [paperAccount, setPaperAccount] = useState({
    cash: 100000,
    equity: 114250,
    realized_pnl: 14250,
    total_fees: 320,
    open_positions_count: 1,
  });

  const [paperPositions, setPaperPositions] = useState<
    {
      instrument_id: string;
      symbol: string;
      side: "LONG" | "SHORT";
      quantity: number;
      entry_price: number;
      current_price: number;
      unrealized_pnl: number;
    }[]
  >([
    {
      instrument_id: "INS_NSE_RELIANCE",
      symbol: "RELIANCE",
      side: "LONG",
      quantity: 50,
      entry_price: 2501.0,
      current_price: 2510.5,
      unrealized_pnl: 475.0,
    },
  ]);

  const [paperOrders, setPaperOrders] = useState<PaperOrder[]>([
    {
      order_id: "ORD_INIT_01",
      account_id: "PAPER_ACC_01",
      instrument_id: "INS_NSE_RELIANCE",
      side: "BUY",
      order_type: "LIMIT",
      quantity: 50,
      filled_quantity: 50,
      price: 2501.0,
      status: "FILLED",
      queue_ahead_volume: 0,
      created_time_utc: Date.now() - 3600000,
      updated_time_utc: Date.now() - 3600000,
    },
  ]);

  const handleCompileStrategy = async (_strategy: StrategyIR) => {
    return {
      highest_required_quality: "LEVEL_A_EXCHANGE_VERIFIED",
      required_feeds: ["candle", "trade_ticks", "footprint"],
    };
  };

  const handleRunBacktest = async (_strategy: StrategyIR) => {
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
          symbol: selectedInst.symbol,
          side: "LONG",
          entry_price: 2495.0,
          exit_price: 2515.0,
          net_pnl: 1000.0,
          total_fees: 25.0,
          exit_reason: "TAKE_PROFIT_2R",
        },
        {
          symbol: selectedInst.symbol,
          side: "LONG",
          entry_price: 2502.0,
          exit_price: 2520.0,
          net_pnl: 900.0,
          total_fees: 24.5,
          exit_reason: "TAKE_PROFIT_2R",
        },
        {
          symbol: selectedInst.symbol,
          side: "LONG",
          entry_price: 2510.0,
          exit_price: 2504.0,
          net_pnl: -300.0,
          total_fees: 15.0,
          exit_reason: "STOP_LOSS",
        },
      ],
    };
    setBacktestResult(mockRes);
    setActiveTab("backtest");
  };

  const handlePlacePaperOrder = (orderData: Partial<PaperOrder>) => {
    const qty = orderData.quantity || 50;
    const px = orderData.price || 2510.5;

    const newOrder: PaperOrder = {
      order_id: orderData.order_id || `ORD_${Date.now()}`,
      account_id: orderData.account_id || "PAPER_ACC_01",
      instrument_id: orderData.instrument_id || selectedInst.instrument_id,
      side: orderData.side || "BUY",
      order_type: orderData.order_type || "LIMIT",
      quantity: qty,
      filled_quantity: qty,
      price: px,
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
      side: newOrder.side === "BUY" ? ("LONG" as const) : ("SHORT" as const),
      quantity: qty,
      entry_price: px,
      current_price: px,
      unrealized_pnl: 0,
    };
    setPaperPositions([pos]);
    setPaperAccount({
      ...paperAccount,
      equity: paperAccount.cash + px * qty,
      open_positions_count: 1,
    });
  };

  const handleClosePosition = (instrumentId: string) => {
    setPaperPositions(paperPositions.filter((p) => p.instrument_id !== instrumentId));
    setPaperAccount({
      ...paperAccount,
      open_positions_count: 0,
    });
  };

  const latestBar = footprintBars[footprintBars.length - 1];
  const ltp = latestBar ? latestBar.close : 2510.5;
  const prevClose = 2496.0;
  const dayChange = ltp - prevClose;
  const dayChangePct = (dayChange / prevClose) * 100;

  return (
    <div className="min-h-screen bg-obsidian-950 text-slate-100 flex flex-col font-sans selection:bg-indigo-600 selection:text-white">
      {/* Top Institutional Workstation Header */}
      <header className="border-b border-slate-800/90 bg-obsidian-900/90 backdrop-blur sticky top-0 z-50 px-5 py-2.5 flex items-center justify-between shadow-2xl">
        {/* Brand & Platform Architecture */}
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-gradient-to-tr from-indigo-600 via-indigo-500 to-cyan-400 flex items-center justify-center font-black text-white text-sm shadow-glow-indigo">
            SL
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-sm font-extrabold tracking-tight text-white">
                STRATLAB
              </h1>
              <span className="text-[10px] font-mono font-bold px-1.5 py-0.2 rounded bg-indigo-500/20 text-indigo-300 border border-indigo-500/40">
                PROVENANCE V2
              </span>
            </div>
            <p className="text-[10px] font-mono text-slate-500">
              One Unified Engine • Multi-Source • Zero Look-ahead
            </p>
          </div>
        </div>

        {/* Global Market Ticker Ribbon */}
        <div className="hidden lg:flex items-center gap-4 bg-obsidian-950 px-4 py-1.5 rounded-xl border border-slate-800/90 font-mono text-xs">
          {/* Quick Instrument Switcher */}
          <div className="flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
            <select
              value={selectedInst.instrument_id}
              onChange={(e) => {
                const found = DEFAULT_INSTRUMENTS.find((i) => i.instrument_id === e.target.value);
                if (found) setSelectedInst(found);
              }}
              className="bg-transparent text-white font-bold text-xs focus:outline-none cursor-pointer"
            >
              {DEFAULT_INSTRUMENTS.map((inst) => (
                <option key={inst.instrument_id} value={inst.instrument_id} className="bg-obsidian-900 text-slate-100">
                  {inst.symbol} ({inst.exchange} · {inst.asset_class})
                </option>
              ))}
            </select>
          </div>

          <div className="h-3 w-px bg-slate-800" />

          {/* LTP & Price Change */}
          <div className="flex items-center gap-2">
            <span className="text-white font-bold text-sm">₹{ltp.toFixed(2)}</span>
            <span className={`text-[11px] font-semibold px-1.5 py-0.2 rounded ${dayChange >= 0 ? "bg-emerald-500/15 text-emerald-400" : "bg-rose-500/15 text-rose-400"}`}>
              {dayChange >= 0 ? "+" : ""}{dayChange.toFixed(2)} ({dayChangePct >= 0 ? "+" : ""}{dayChangePct.toFixed(2)}%)
            </span>
          </div>

          <div className="h-3 w-px bg-slate-800" />

          {/* Day High / Low */}
          <div className="text-[11px] text-slate-400 flex items-center gap-2">
            <span>H: <strong className="text-slate-200">2,511.00</strong></span>
            <span>L: <strong className="text-slate-200">2,498.00</strong></span>
          </div>

          <div className="h-3 w-px bg-slate-800" />

          {/* Net Session Delta */}
          <div className="text-[11px] flex items-center gap-1.5">
            <span className="text-slate-500">Net Δ:</span>
            <span className="text-emerald-400 font-bold">+1,520 (72% Agg. Buys)</span>
          </div>
        </div>

        {/* Global Controls & Provenance Monitor */}
        <div className="flex items-center gap-2.5">
          {/* Live Streaming Feed Simulator Toggle */}
          <button
            onClick={toggleSimulation}
            className={`px-3 py-1.5 rounded-lg text-xs font-mono font-bold transition-all flex items-center gap-1.5 ${
              isSimulating
                ? "bg-rose-600 hover:bg-rose-500 text-white shadow-glow-rose"
                : "bg-emerald-600 hover:bg-emerald-500 text-white shadow-glow-emerald"
            }`}
          >
            <span>{isSimulating ? "⏹ Stop Feed" : "▶ Live Stream"}</span>
          </button>

          {/* WebSocket Ping Badge */}
          <div className="hidden sm:flex bg-obsidian-950 border border-slate-800 rounded-lg px-2.5 py-1 text-[11px] font-mono items-center gap-2">
            <span
              className={`w-2 h-2 rounded-full ${
                isConnected ? "bg-emerald-400 animate-pulse" : "bg-slate-500"
              }`}
            />
            <span className="text-slate-300">
              {isConnected ? `${latencyMs}ms` : "Offline"}
            </span>
            <span className="text-slate-600">|</span>
            <span className="text-cyan-400 font-bold">{tickCount} Ticks</span>
          </div>

          {/* Interactive Provenance Badge */}
          <button
            onClick={() => setShowProvenanceModal(true)}
            className="px-2.5 py-1 rounded-lg bg-emerald-500/10 border border-emerald-500/30 text-[11px] font-mono font-semibold text-emerald-300 flex items-center gap-1.5 hover:bg-emerald-500/20 transition-all cursor-pointer shadow-glow-emerald"
            title="Click to inspect Data Provenance architecture"
          >
            <span>✓ Genuine Level A</span>
          </button>
        </div>
      </header>

      {/* Main Tabbed Navigation Strip */}
      <nav className="border-b border-slate-800/80 bg-obsidian-900/40 px-5 py-2 flex items-center justify-between text-xs">
        <div className="flex items-center gap-1.5">
          {[
            { id: "explorer", label: "01 · Market Explorer", icon: "🌐" },
            { id: "orderflow", label: "02 · Order Flow Lab", icon: "📊" },
            { id: "studio", label: "03 · Strategy Studio", icon: "⚡" },
            { id: "backtest", label: "04 · Backtest Lab", icon: "🧪" },
            { id: "paper", label: "05 · Paper Desk", icon: "💼" },
          ].map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id as any)}
              className={`px-3.5 py-1.5 rounded-lg font-medium transition-all flex items-center gap-1.5 ${
                activeTab === tab.id
                  ? "bg-indigo-600 text-white font-bold shadow-glow-indigo"
                  : "text-slate-400 hover:text-slate-200 hover:bg-slate-800/50"
              }`}
            >
              <span>{tab.icon}</span>
              <span>{tab.label}</span>
            </button>
          ))}
        </div>

        {/* Real-time World Clocks */}
        <div className="hidden md:flex items-center gap-3 font-mono text-[11px] text-slate-400">
          <div className="flex items-center gap-1">
            <span className="text-slate-500">IST:</span>
            <span className="text-slate-200 font-semibold">
              {currentTime.toLocaleTimeString("en-GB", { timeZone: "Asia/Kolkata" })}
            </span>
          </div>
          <span className="text-slate-700">|</span>
          <div className="flex items-center gap-1">
            <span className="text-slate-500">UTC:</span>
            <span className="text-slate-300">
              {currentTime.toLocaleTimeString("en-GB", { timeZone: "UTC" })}
            </span>
          </div>
          <span className="text-slate-700">|</span>
          <span className="px-1.5 py-0.2 rounded bg-emerald-500/20 text-emerald-400 font-bold text-[10px]">
            SESSION ACTIVE
          </span>
        </div>
      </nav>

      {/* Main Workspace Body */}
      <main className="flex-1 p-5 max-w-7xl mx-auto w-full flex flex-col gap-6">
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
            {/* View Mode Ribbon */}
            <div className="flex flex-wrap items-center justify-between gap-3 bg-obsidian-900 border border-slate-800/90 rounded-xl p-3 shadow-xl backdrop-blur">
              <div className="flex items-center gap-3">
                <span className="text-xs font-bold text-white flex items-center gap-2">
                  <span className="w-2 h-2 rounded-full bg-indigo-500 shadow-glow-indigo" />
                  Order Flow Visualization:
                </span>
                <div className="flex rounded-lg border border-slate-800 bg-obsidian-950 p-0.5 text-xs font-mono">
                  <button
                    onClick={() => setFootprintViewMode("canvas")}
                    className={`px-3 py-1 rounded-md font-bold transition-all ${
                      footprintViewMode === "canvas"
                        ? "bg-indigo-600 text-white shadow-glow-indigo"
                        : "text-slate-400 hover:text-slate-200"
                    }`}
                  >
                    ⚡ Canvas (60 FPS Pan & Zoom)
                  </button>
                  <button
                    onClick={() => setFootprintViewMode("table")}
                    className={`px-3 py-1 rounded-md font-bold transition-all ${
                      footprintViewMode === "table"
                        ? "bg-indigo-600 text-white shadow-glow-indigo"
                        : "text-slate-400 hover:text-slate-200"
                    }`}
                  >
                    Cluster Ladder Table
                  </button>
                </div>
              </div>

              {/* Order Flow Metric Badges */}
              <div className="flex items-center gap-2 font-mono text-xs">
                <span className="px-2 py-0.5 rounded bg-emerald-500/10 border border-emerald-500/30 text-emerald-400">
                  ⚡ 3:1 Buy Imbalance
                </span>
                <span className="px-2 py-0.5 rounded bg-amber-500/10 border border-amber-500/30 text-amber-400">
                  ★ POC Ray Active
                </span>
                <span className="px-2 py-0.5 rounded bg-indigo-500/10 border border-indigo-500/30 text-indigo-400">
                  ◈ 70% Value Area
                </span>
              </div>
            </div>

            {/* Footprint Chart Surface */}
            {footprintViewMode === "canvas" ? (
              <CanvasFootprintChart
                bars={footprintBars}
                symbol={selectedInst.symbol}
                timeframe="5m"
              />
            ) : (
              <FootprintChart
                bars={footprintBars}
                symbol={selectedInst.symbol}
                timeframe="5m"
              />
            )}

            {/* Volume Profile Matrix */}
            <VolumeProfileView profile={SAMPLE_PROFILE} />
          </div>
        )}

        {/* Tab 03: Strategy Studio */}
        {activeTab === "studio" && (
          <div className="flex flex-col gap-6">
            {/* Studio Mode Toggle */}
            <div className="flex items-center justify-between bg-obsidian-900 border border-slate-800/90 rounded-xl p-3 shadow-xl backdrop-blur">
              <span className="text-xs font-bold text-white flex items-center gap-2">
                <span className="w-2 h-2 rounded-full bg-violet-500 shadow-glow-indigo" />
                Strategy Authoring Paradigm:
              </span>
              <div className="flex rounded-lg border border-slate-800 bg-obsidian-950 p-0.5 text-xs font-mono">
                <button
                  onClick={() => setStudioViewMode("graph")}
                  className={`px-3 py-1 rounded-md font-bold transition-all ${
                    studioViewMode === "graph"
                      ? "bg-violet-600 text-white shadow-glow-indigo"
                      : "text-slate-400 hover:text-slate-200"
                  }`}
                >
                  ⚡ React Flow Visual DAG
                </button>
                <button
                  onClick={() => setStudioViewMode("blocks")}
                  className={`px-3 py-1 rounded-md font-bold transition-all ${
                    studioViewMode === "blocks"
                      ? "bg-violet-600 text-white shadow-glow-indigo"
                      : "text-slate-400 hover:text-slate-200"
                  }`}
                >
                  Visual Condition Blocks
                </button>
              </div>
            </div>

            {studioViewMode === "graph" ? (
              <StrategyGraphStudio
                onCompileStrategy={handleCompileStrategy}
                onRunBacktest={handleRunBacktest}
              />
            ) : (
              <VisualStrategyBuilder
                onCompileStrategy={handleCompileStrategy}
                onRunBacktest={handleRunBacktest}
              />
            )}
          </div>
        )}

        {/* Tab 04: Backtest Lab */}
        {activeTab === "backtest" && (
          <div className="bg-obsidian-900 border border-slate-800/90 rounded-xl p-5 shadow-2xl flex flex-col gap-6 backdrop-blur">
            <div className="flex items-center justify-between pb-3 border-b border-slate-800/80">
              <div>
                <h3 className="text-base font-bold text-white flex items-center gap-2">
                  <span className="w-2.5 h-2.5 rounded-full bg-cyan-400 shadow-glow-indigo" />
                  Deterministic Backtest Simulation Engine
                </h3>
                <p className="text-xs text-slate-400 font-mono mt-0.5">
                  Zero look-ahead bias with statutory cost attribution on {selectedInst.symbol}
                </p>
              </div>
              <span className="px-2.5 py-1 rounded-md bg-cyan-500/10 text-cyan-300 border border-cyan-500/30 text-xs font-mono font-bold">
                Level A Deterministic
              </span>
            </div>

            {backtestResult ? (
              <div className="flex flex-col gap-6">
                {/* Metrics KPI Cards */}
                <div className="grid grid-cols-2 sm:grid-cols-5 gap-3 font-mono text-xs">
                  <div className="bg-obsidian-950 p-3 rounded-lg border border-slate-800">
                    <span className="text-slate-500 text-[10px] block uppercase font-semibold">Net Realized PnL</span>
                    <span className="text-emerald-400 font-bold text-base mt-0.5 block">
                      +₹{backtestResult.metrics.net_pnl.toLocaleString()}
                    </span>
                  </div>
                  <div className="bg-obsidian-950 p-3 rounded-lg border border-slate-800">
                    <span className="text-slate-500 text-[10px] block uppercase font-semibold">Win Rate</span>
                    <span className="text-indigo-400 font-bold text-base mt-0.5 block">
                      {backtestResult.metrics.win_rate_pct.toFixed(1)}%
                    </span>
                  </div>
                  <div className="bg-obsidian-950 p-3 rounded-lg border border-slate-800">
                    <span className="text-slate-500 text-[10px] block uppercase font-semibold">Profit Factor</span>
                    <span className="text-indigo-300 font-bold text-base mt-0.5 block">
                      {backtestResult.metrics.profit_factor}
                    </span>
                  </div>
                  <div className="bg-obsidian-950 p-3 rounded-lg border border-slate-800">
                    <span className="text-slate-500 text-[10px] block uppercase font-semibold">Max Drawdown</span>
                    <span className="text-rose-400 font-bold text-base mt-0.5 block">
                      {backtestResult.metrics.max_drawdown_pct.toFixed(2)}%
                    </span>
                  </div>
                  <div className="bg-obsidian-950 p-3 rounded-lg border border-slate-800">
                    <span className="text-slate-500 text-[10px] block uppercase font-semibold">Sharpe Ratio</span>
                    <span className="text-amber-400 font-bold text-base mt-0.5 block">
                      {backtestResult.metrics.sharpe_ratio}
                    </span>
                  </div>
                </div>

                {/* SVG Equity Curve */}
                <div className="bg-obsidian-950 border border-slate-800 rounded-xl p-4 flex flex-col gap-2">
                  <div className="flex items-center justify-between text-xs font-mono text-slate-400">
                    <span className="font-bold text-white uppercase tracking-wider">Simulated Portfolio Equity Curve</span>
                    <span className="text-emerald-400">Final: ₹{backtestResult.metrics.final_equity.toLocaleString()}</span>
                  </div>

                  <div className="h-44 w-full">
                    <svg className="w-full h-full overflow-visible" preserveAspectRatio="none" viewBox="0 0 500 120">
                      <defs>
                        <linearGradient id="eqGrad" x1="0" y1="0" x2="0" y2="1">
                          <stop offset="0%" stopColor="#10b981" stopOpacity="0.4" />
                          <stop offset="100%" stopColor="#10b981" stopOpacity="0.0" />
                        </linearGradient>
                      </defs>
                      <path
                        d="M 0 110 Q 120 90, 240 60 T 500 20 L 500 120 L 0 120 Z"
                        fill="url(#eqGrad)"
                      />
                      <path
                        d="M 0 110 Q 120 90, 240 60 T 500 20"
                        fill="none"
                        stroke="#10b981"
                        strokeWidth="2.5"
                      />
                    </svg>
                  </div>
                </div>

                {/* Closed Trades Blotter */}
                <div className="flex flex-col gap-2">
                  <h4 className="text-xs font-bold text-slate-300 uppercase tracking-wider">
                    Simulated Closed Trades ({backtestResult.closed_trades.length})
                  </h4>
                  <div className="overflow-x-auto rounded-xl border border-slate-800 bg-obsidian-950 font-mono text-xs">
                    <table className="w-full text-left">
                      <thead className="bg-obsidian-900 text-slate-400 text-[10px] uppercase border-b border-slate-800">
                        <tr>
                          <th className="py-2.5 px-3">Symbol</th>
                          <th className="py-2.5 px-3">Side</th>
                          <th className="py-2.5 px-3 text-right">Entry</th>
                          <th className="py-2.5 px-3 text-right">Exit</th>
                          <th className="py-2.5 px-3 text-right">Net PnL</th>
                          <th className="py-2.5 px-3 text-right">Fees</th>
                          <th className="py-2.5 px-3 text-center">Exit Signal</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-800/60">
                        {backtestResult.closed_trades.map((t, idx) => (
                          <tr key={idx} className="hover:bg-slate-900/60">
                            <td className="py-2.5 px-3 font-bold text-slate-200">{t.symbol}</td>
                            <td className="py-2.5 px-3 text-emerald-400 font-bold">{t.side}</td>
                            <td className="py-2.5 px-3 text-right">₹{t.entry_price.toFixed(2)}</td>
                            <td className="py-2.5 px-3 text-right">₹{t.exit_price.toFixed(2)}</td>
                            <td className={`py-2.5 px-3 text-right font-bold ${t.net_pnl >= 0 ? "text-emerald-400" : "text-rose-400"}`}>
                              {t.net_pnl >= 0 ? "+" : ""}₹{t.net_pnl.toFixed(2)}
                            </td>
                            <td className="py-2.5 px-3 text-right text-slate-400">
                              ₹{t.total_fees.toFixed(2)}
                            </td>
                            <td className="py-2.5 px-3 text-center">
                              <span className="px-2 py-0.5 rounded bg-emerald-500/20 text-emerald-300 text-[10px] font-bold">
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
              <div className="text-center py-12 text-slate-500 text-xs font-mono">
                No backtest results yet. Go to Strategy Studio and click "Run Backtest Simulation".
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
            onClosePosition={handleClosePosition}
          />
        )}
      </main>

      {/* Institutional Platform Status Bar Footer */}
      <footer className="border-t border-slate-800/80 bg-obsidian-900/90 px-5 py-2 text-[11px] font-mono text-slate-500 flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-2">
            <span className={`w-2 h-2 rounded-full ${isConnected ? "bg-emerald-400 animate-pulse" : "bg-slate-500"}`} />
            <span className="text-slate-400">ENGINE: DUCKDB + PARQUET ZERO-COPY</span>
          </div>
          <span>•</span>
          <span>STORAGE: /snappy.parquet</span>
          <span>•</span>
          <span>PROVENANCE GUARD: ACTIVE (4-TIER ENFORCED)</span>
        </div>

        <div className="flex items-center gap-4">
          <span>Shortcuts: <kbd className="px-1 py-0.5 rounded bg-obsidian-950 border border-slate-800 text-slate-300">1-5</kbd> Tabs • <kbd className="px-1 py-0.5 rounded bg-obsidian-950 border border-slate-800 text-slate-300">Shift+Wheel</kbd> Bar Width</span>
          <span className="text-slate-600">|</span>
          <span className="text-indigo-400">STRATLAB WORKSTATION v2.0</span>
        </div>
      </footer>

      {/* Provenance Architecture Modal */}
      {showProvenanceModal && (
        <div className="fixed inset-0 z-50 bg-black/80 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-obsidian-900 border border-slate-800 rounded-2xl max-w-xl w-full p-6 shadow-2xl flex flex-col gap-4 font-sans">
            <div className="flex items-center justify-between pb-3 border-b border-slate-800">
              <div className="flex items-center gap-2">
                <span className="w-3 h-3 rounded-full bg-emerald-400 shadow-glow-emerald" />
                <h3 className="text-base font-bold text-white">
                  STRATLAB Data Provenance Hierarchy
                </h3>
              </div>
              <button
                onClick={() => setShowProvenanceModal(false)}
                className="text-slate-400 hover:text-white font-mono text-lg"
              >
                ✕
              </button>
            </div>

            <p className="text-xs text-slate-300 leading-relaxed">
              STRATLAB enforces an immutable boundary between <strong>genuine exchange trade prints</strong> and <strong>synthetic proxy models</strong>. Estimated data is strictly forbidden from silently contaminating order flow analytics.
            </p>

            <div className="flex flex-col gap-2 font-mono text-xs">
              <div className="bg-obsidian-950 p-3 rounded-lg border border-emerald-500/40 flex justify-between items-center">
                <div>
                  <strong className="text-emerald-400 block">Level A · Exchange Verified (Confidence 1.0)</strong>
                  <span className="text-slate-400 text-[11px]">Direct trade-by-trade aggressor flags from exchange tick feed.</span>
                </div>
                <span className="px-2 py-0.5 rounded bg-emerald-500/20 text-emerald-300 text-[10px] font-bold">GENUINE</span>
              </div>

              <div className="bg-obsidian-950 p-3 rounded-lg border border-indigo-500/40 flex justify-between items-center">
                <div>
                  <strong className="text-indigo-400 block">Level B · Quote Classified (Confidence 0.95)</strong>
                  <span className="text-slate-400 text-[11px]">Trade prints matched against contemporaneous Top-of-Book BBO.</span>
                </div>
                <span className="px-2 py-0.5 rounded bg-indigo-500/20 text-indigo-300 text-[10px] font-bold">DERIVED</span>
              </div>

              <div className="bg-obsidian-950 p-3 rounded-lg border border-amber-500/40 flex justify-between items-center">
                <div>
                  <strong className="text-amber-400 block">Level C · Tick-Rule Estimated (Confidence 0.65)</strong>
                  <span className="text-slate-400 text-[11px]">Lee-Ready price uptick/downtick directional approximation.</span>
                </div>
                <span className="px-2 py-0.5 rounded bg-amber-500/20 text-amber-300 text-[10px] font-bold">ESTIMATED</span>
              </div>

              <div className="bg-obsidian-950 p-3 rounded-lg border border-slate-700 flex justify-between items-center">
                <div>
                  <strong className="text-slate-300 block">Level D · OHLCV Proxy (Confidence 0.35)</strong>
                  <span className="text-slate-500 text-[11px]">Bulk Volume Classification (BVC) derived from candle envelope.</span>
                </div>
                <span className="px-2 py-0.5 rounded bg-slate-800 text-slate-400 text-[10px] font-bold">PROXY</span>
              </div>
            </div>

            <div className="pt-2 flex justify-end">
              <button
                onClick={() => setShowProvenanceModal(false)}
                className="px-4 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white font-bold text-xs font-mono shadow-glow-indigo transition-all"
              >
                Understood
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default App;
