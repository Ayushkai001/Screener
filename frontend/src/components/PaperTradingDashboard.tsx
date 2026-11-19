import React, { useState } from "react";
import { OrderSide, OrderType, PaperOrder } from "../types/domain";

interface AccountSummary {
  cash: number;
  equity: number;
  realized_pnl: number;
  total_fees: number;
  open_positions_count: number;
}

interface PositionRow {
  instrument_id: string;
  symbol: string;
  side: "LONG" | "SHORT";
  quantity: number;
  entry_price: number;
  current_price: number;
  unrealized_pnl: number;
}

interface PaperTradingDashboardProps {
  account: AccountSummary;
  positions: PositionRow[];
  orders: PaperOrder[];
  selectedSymbol: string;
  selectedInstrumentId: string;
  onSubmitOrder: (order: Partial<PaperOrder>) => void;
  onClosePosition?: (instrumentId: string) => void;
  onCancelOrder?: (orderId: string) => void;
}

export const PaperTradingDashboard: React.FC<PaperTradingDashboardProps> = ({
  account,
  positions,
  orders,
  selectedSymbol,
  selectedInstrumentId,
  onSubmitOrder,
  onClosePosition,
}) => {
  const [side, setSide] = useState<OrderSide>("BUY");
  const [orderType, setOrderType] = useState<OrderType>("LIMIT");
  const [quantity, setQuantity] = useState(50);
  const [price, setPrice] = useState(2502.0);

  const orderValue = (orderType === "LIMIT" ? price : 2502.0) * quantity;
  // Indian statutory cost estimation (approx 0.1% delivery or 0.03% intraday)
  const estimatedFees = Math.round(orderValue * 0.00035 * 100) / 100;

  const handlePlaceOrder = (e: React.FormEvent) => {
    e.preventDefault();
    const orderId = `ORD_${Date.now()}`;
    onSubmitOrder({
      order_id: orderId,
      account_id: "PAPER_ACC_01",
      instrument_id: selectedInstrumentId,
      side,
      order_type: orderType,
      quantity,
      price: orderType === "LIMIT" ? price : 2502.0,
      created_time_utc: Date.now(),
      updated_time_utc: Date.now(),
    });
  };

  const handleQuickQuantity = (addQty: number) => {
    setQuantity((prev) => Math.max(1, prev + addQty));
  };

  return (
    <div className="flex flex-col gap-6 w-full font-sans text-[#f4f4f6]">
      {/* Paytech-Inspired Top Hero: Wallet Value + Portfolio Risk Score */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
        {/* Left 2 Cols: Wallet Value Hero */}
        <div className="lg:col-span-2 bg-[#121214] border border-[#202026] rounded-3xl p-6 shadow-2xl flex flex-col justify-between gap-6 relative overflow-hidden">
          <div className="flex items-center justify-between">
            <div>
              <span className="text-xs font-mono text-[#8e8e96] uppercase tracking-wider block">
                Portfolio Net Value
              </span>
              <div className="flex items-center gap-3 mt-1">
                <h2 className="text-3xl sm:text-4xl font-black text-white tracking-tight">
                  ₹{account.equity.toLocaleString(undefined, { minimumFractionDigits: 2 })}
                </h2>
                <span className="px-2.5 py-0.5 rounded-full bg-[#D4F638]/15 text-[#D4F638] border border-[#D4F638]/30 text-xs font-mono font-bold">
                  +14.25%
                </span>
              </div>
            </div>

            {/* Quick action pill buttons */}
            <div className="flex items-center gap-2">
              <span className="text-xs font-mono text-[#D4F638] bg-[#D4F638]/15 px-3 py-1 rounded-full border border-[#D4F638]/30 font-bold">
                Target: {selectedSymbol}
              </span>
            </div>
          </div>

          {/* Timeframe Filter Pills (Matching Paytech Screenshot) */}
          <div className="flex flex-wrap items-center gap-2 pt-2 border-t border-[#1c1c22]">
            {["1h", "8h", "1d", "1w", "1m", "6m", "1y"].map((tf) => (
              <button
                key={tf}
                type="button"
                className={`px-3.5 py-1 rounded-full text-xs font-mono font-bold transition-all cursor-pointer ${
                  tf === "1d"
                    ? "bg-[#202028] text-white border border-[#32323c]"
                    : "text-[#a0a0ab] hover:text-white hover:bg-[#18181c]"
                }`}
              >
                {tf}
              </button>
            ))}
          </div>
        </div>

        {/* Right 1 Col: Portfolio Risk Score (Exact Paytech Image Card) */}
        <div className="bg-[#121214] border border-[#202026] rounded-3xl p-6 shadow-2xl flex flex-col justify-between gap-4">
          <div className="flex items-start justify-between">
            <div>
              <h3 className="text-lg font-black text-white leading-tight">
                Portfolio<br />Risk Score
              </h3>
            </div>
            <span className="text-[10px] font-mono text-[#a0a0ab] text-right">
              Updated:<br /><strong className="text-white">Just Now</strong>
            </span>
          </div>

          {/* Electric Lime Progress Bar from Reference Image */}
          <div className="flex flex-col gap-2">
            <div className="w-full h-3 bg-[#1e1e24] rounded-full overflow-hidden p-0.5">
              <div
                className="h-full bg-[#D4F638] rounded-full shadow-[0_0_10px_rgba(212,246,56,0.5)]"
                style={{ width: "72%" }}
              />
            </div>
            <div className="flex justify-between items-center text-[10px] font-mono text-[#a0a0ab]">
              <span className="text-[#D4F638] font-bold">Low Risk</span>
              <span className="text-[#70707c]">High Risk</span>
            </div>
          </div>

          <div className="text-[11px] font-mono text-[#a0a0ab] bg-[#0c0c0e] rounded-xl p-2.5 border border-[#1a1a20]">
            ⚡ Statutory fees optimized: <strong className="text-white">₹{account.total_fees.toFixed(2)}</strong> paid
          </div>
        </div>
      </div>

      {/* 4 KPI Cards (Matching Bottom Row of Paytech Reference Image) */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3.5 text-xs font-mono">
        <div className="bg-[#121214] p-4 rounded-2xl border border-[#202026]">
          <span className="text-[#a0a0ab] text-[10px] block uppercase font-bold tracking-wider">Realized PL</span>
          <span className={`font-black text-xl mt-1 block ${account.realized_pnl >= 0 ? "text-[#D4F638]" : "text-rose-400"}`}>
            {account.realized_pnl >= 0 ? "+" : ""}₹{account.realized_pnl.toFixed(2)}
          </span>
          <span className="text-[10px] text-emerald-400 font-bold block mt-0.5">
            +27% Today
          </span>
        </div>

        <div className="bg-[#121214] p-4 rounded-2xl border border-[#202026]">
          <span className="text-[#a0a0ab] text-[10px] block uppercase font-bold tracking-wider">Unrealized PL</span>
          <span className="text-white font-black text-xl mt-1 block">
            +₹475.00
          </span>
          <span className="text-[10px] text-emerald-400 font-bold block mt-0.5">
            +11.8% Today
          </span>
        </div>

        <div className="bg-[#121214] p-4 rounded-2xl border border-[#202026]">
          <span className="text-[#a0a0ab] text-[10px] block uppercase font-bold tracking-wider">Available Cash</span>
          <span className="text-white font-black text-xl mt-1 block">
            ₹{account.cash.toLocaleString(undefined, { minimumFractionDigits: 2 })}
          </span>
          <span className="text-[10px] text-[#a0a0ab] block mt-0.5">
            Liquid Reserve
          </span>
        </div>

        <div className="bg-[#121214] p-4 rounded-2xl border border-[#202026]">
          <span className="text-[#a0a0ab] text-[10px] block uppercase font-bold tracking-wider">Open Positions</span>
          <span className="text-[#D4F638] font-black text-xl mt-1 block">
            {account.open_positions_count} Active
          </span>
          <span className="text-[10px] text-[#D4F638] font-bold block mt-0.5">
            Matching Active
          </span>
        </div>
      </div>

      {/* Main Order Entry & Portfolio Blotter */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left Column: Interactive Order Entry Pad */}
        <form
          onSubmit={handlePlaceOrder}
          className="bg-[#121214] border border-[#202026] rounded-3xl p-5 flex flex-col gap-4 shadow-xl"
        >
          <div className="flex items-center justify-between border-b border-[#1c1c22] pb-3">
            <span className="text-xs font-bold text-white uppercase tracking-wider">
              Quick Order Ticket
            </span>
            <span className="text-[10px] font-mono text-[#D4F638] bg-[#D4F638]/15 px-2.5 py-0.5 rounded-full border border-[#D4F638]/30 font-bold">
              Instant Fill
            </span>
          </div>

          {/* Buy / Sell Toggle Buttons (Paytech Style) */}
          <div className="grid grid-cols-2 gap-2">
            <button
              type="button"
              onClick={() => setSide("BUY")}
              className={`py-3 rounded-2xl font-sans font-black text-xs transition-all cursor-pointer ${
                side === "BUY"
                  ? "bg-[#D4F638] text-black shadow-[0_0_20px_rgba(212,246,56,0.3)] font-black"
                  : "bg-[#18181c] text-[#a0a0ab] hover:text-white"
              }`}
            >
              BUY / LONG
            </button>
            <button
              type="button"
              onClick={() => setSide("SELL")}
              className={`py-3 rounded-2xl font-sans font-black text-xs transition-all cursor-pointer ${
                side === "SELL"
                  ? "bg-rose-500 text-white shadow-[0_0_20px_rgba(244,63,94,0.3)] font-black"
                  : "bg-[#18181c] text-[#a0a0ab] hover:text-white"
              }`}
            >
              SELL / SHORT
            </button>
          </div>

          {/* Order Type Toggle */}
          <div className="flex flex-col gap-1.5 text-xs">
            <label className="text-[#a0a0ab] font-medium">Order Execution Type</label>
            <div className="grid grid-cols-2 gap-2 font-mono">
              <button
                type="button"
                onClick={() => setOrderType("LIMIT")}
                className={`py-2 rounded-xl text-xs font-semibold border cursor-pointer ${
                  orderType === "LIMIT"
                    ? "bg-[#202028] border-[#D4F638] text-[#D4F638] font-bold shadow-[0_0_15px_rgba(212,246,56,0.25)]"
                    : "bg-[#18181c] border-[#22222a] text-[#a0a0ab]"
                }`}
              >
                Limit (Book Queue)
              </button>
              <button
                type="button"
                onClick={() => setOrderType("MARKET")}
                className={`py-2 rounded-xl text-xs font-semibold border cursor-pointer ${
                  orderType === "MARKET"
                    ? "bg-[#202028] border-[#D4F638] text-[#D4F638] font-bold shadow-[0_0_15px_rgba(212,246,56,0.25)]"
                    : "bg-[#18181c] border-[#22222a] text-[#a0a0ab]"
                }`}
              >
                Market (Aggressive)
              </button>
            </div>
          </div>

          {/* Quantity with Quick Add Pills */}
          <div className="flex flex-col gap-2 text-xs">
            <div className="flex items-center justify-between">
              <label className="text-[#a0a0ab] font-medium">Quantity (Units)</label>
              <div className="flex gap-1.5">
                {[10, 25, 50, 100].map((q) => (
                  <button
                    key={q}
                    type="button"
                    onClick={() => handleQuickQuantity(q)}
                    className="px-2 py-0.5 rounded-full bg-[#18181c] hover:bg-[#22222a] border border-[#26262e] text-[10px] font-mono text-white cursor-pointer"
                  >
                    +{q}
                  </button>
                ))}
              </div>
            </div>
            <input
              type="number"
              min="1"
              value={quantity}
              onChange={(e) => setQuantity(Math.max(1, parseInt(e.target.value) || 1))}
              className="bg-[#0c0c0e] border border-[#24242c] focus:border-lime-primary rounded-xl px-4 py-2.5 text-white font-mono text-sm focus:outline-none"
            />
          </div>

          {/* Price (if Limit) */}
          {orderType === "LIMIT" && (
            <div className="flex flex-col gap-1.5 text-xs">
              <label className="text-[#8e8e96] font-medium">Limit Price (₹)</label>
              <input
                type="number"
                step="0.05"
                value={price}
                onChange={(e) => setPrice(parseFloat(e.target.value) || 0)}
                className="bg-[#0c0c0e] border border-[#24242c] focus:border-lime-primary rounded-xl px-4 py-2.5 text-white font-mono text-sm focus:outline-none"
              />
            </div>
          )}

          {/* Ticket Calculations */}
          <div className="bg-[#0c0c0e] rounded-2xl p-3 border border-[#1e1e24] text-xs font-mono flex flex-col gap-1 text-[#8e8e96]">
            <div className="flex justify-between">
              <span>Order Notional:</span>
              <strong className="text-white">₹{orderValue.toLocaleString(undefined, { minimumFractionDigits: 2 })}</strong>
            </div>
            <div className="flex justify-between text-[11px]">
              <span>Est. Statutory Charges:</span>
              <span className="text-lime-primary">₹{estimatedFees.toFixed(2)}</span>
            </div>
          </div>

          {/* Submit Order Button */}
          <button
            type="submit"
            className={`w-full py-3.5 rounded-2xl font-black font-sans text-sm transition-all transform hover:scale-[1.01] active:scale-95 shadow-xl cursor-pointer ${
              side === "BUY"
                ? "bg-lime-primary hover:bg-lime-hover text-black shadow-glow-lime"
                : "bg-rose-500 hover:bg-rose-400 text-white shadow-glow-rose"
            }`}
          >
            Submit {side} Order ({quantity} @ {orderType === "LIMIT" ? `₹${price}` : "MKT"})
          </button>
        </form>

        {/* Right 2 Columns: Transactions & Positions (Paytech Card Style) */}
        <div className="lg:col-span-2 flex flex-col gap-6">
          {/* Active Positions */}
          <div className="bg-[#121214] border border-[#202026] rounded-3xl p-5 shadow-xl flex flex-col gap-4">
            <div className="flex items-center justify-between pb-2 border-b border-[#1c1c22]">
              <h4 className="text-xs font-bold text-white uppercase tracking-wider flex items-center gap-2">
                <span>Transactions & Positions</span>
              </h4>
              <span className="text-xs font-mono text-[#D4F638]">Live PnL Engine</span>
            </div>

            {positions.length === 0 ? (
              <div className="py-8 text-center text-xs font-mono text-[#a0a0ab]">
                No active positions. Submit an order to simulate position lifecycle.
              </div>
            ) : (
              <div className="flex flex-col gap-3">
                {positions.map((pos, idx) => {
                  const isHighlighted = idx === 0;
                  return (
                    <div
                      key={pos.instrument_id}
                      className={`rounded-2xl p-4 transition-all flex flex-col sm:flex-row sm:items-center justify-between gap-3 border ${
                        isHighlighted
                          ? "bg-[#D4F638] text-black border-[#D4F638] shadow-[0_0_20px_rgba(212,246,56,0.25)]"
                          : "bg-[#141417] text-white border-[#202026]"
                      }`}
                    >
                      <div className="flex items-center gap-3">
                        <div className={`w-10 h-10 rounded-2xl flex items-center justify-center font-bold text-sm ${
                          isHighlighted ? "bg-black text-[#D4F638]" : "bg-[#202028] text-white"
                        }`}>
                          {pos.side === "LONG" ? "↑" : "↓"}
                        </div>
                        <div>
                          <strong className="text-sm block font-black">{pos.symbol}</strong>
                          <span className={`text-xs ${isHighlighted ? "text-black/80 font-bold" : "text-[#a0a0ab]"}`}>
                            {pos.quantity} Shares · Avg ₹{pos.entry_price.toFixed(2)}
                          </span>
                        </div>
                      </div>

                      <div className="flex items-center gap-4">
                        <div className="text-right">
                          <span className={`text-[10px] block uppercase font-bold ${isHighlighted ? "text-black/70" : "text-[#a0a0ab]"}`}>
                            Unrealized PnL
                          </span>
                          <strong className={`font-black text-base ${isHighlighted ? "text-black" : (pos.unrealized_pnl >= 0 ? "text-emerald-400" : "text-rose-400")}`}>
                            {pos.unrealized_pnl >= 0 ? "+" : ""}₹{pos.unrealized_pnl.toFixed(2)}
                          </strong>
                        </div>

                        {onClosePosition && (
                          <button
                            onClick={() => onClosePosition(pos.instrument_id)}
                            className={`px-3 py-1.5 rounded-full text-xs font-bold font-mono transition-all cursor-pointer ${
                              isHighlighted
                                ? "bg-black text-[#D4F638] hover:bg-black/80"
                                : "bg-[#22222c] text-white hover:bg-[#2e2e3a]"
                            }`}
                          >
                            Close Position
                          </button>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>

          {/* Filled Paper Orders */}
          <div className="bg-[#121214] border border-[#202026] rounded-3xl p-5 shadow-xl flex flex-col gap-3">
            <h4 className="text-xs font-bold text-white uppercase tracking-wider">
              Order Blotter History ({orders.length})
            </h4>

            <div className="flex flex-col gap-2">
              {orders.slice(0, 4).map((o) => (
                <div
                  key={o.order_id}
                  className="bg-[#141417] border border-[#202026] rounded-2xl p-3 flex items-center justify-between text-xs font-mono"
                >
                  <div className="flex items-center gap-2.5">
                    <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold ${
                      o.side === "BUY" ? "bg-emerald-500/15 text-emerald-400" : "bg-rose-500/15 text-rose-400"
                    }`}>
                      {o.side}
                    </span>
                    <strong className="text-white">{o.instrument_id.replace("INS_NSE_", "")}</strong>
                    <span className="text-[#a0a0ab]">x{o.quantity}</span>
                  </div>

                  <div className="flex items-center gap-3">
                    <span className="text-white font-bold">₹{o.price ? o.price.toFixed(2) : "MKT"}</span>
                    <span className="px-2 py-0.5 rounded-full bg-[#D4F638]/15 text-[#D4F638] border border-[#D4F638]/30 text-[10px] font-bold">
                      {o.status}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
