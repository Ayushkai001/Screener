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
  onCancelOrder,
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
    <div className="bg-obsidian-900 border border-slate-800/90 rounded-xl p-5 shadow-2xl flex flex-col gap-6 backdrop-blur">
      {/* Desk Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between pb-3 border-b border-slate-800/80 gap-3">
        <div>
          <div className="flex items-center gap-2">
            <span className="w-2.5 h-2.5 rounded-full bg-emerald-400 shadow-glow-emerald animate-pulse" />
            <h3 className="text-base font-bold text-white tracking-tight">
              Simulated Execution Desk & Matching Engine
            </h3>
          </div>
          <p className="text-xs text-slate-400 font-mono mt-0.5">
            Queue-aware limit order modeling with Indian regulatory transaction cost calculation
          </p>
        </div>

        {/* Selected Instrument */}
        <div className="flex items-center gap-2">
          <div className="px-3 py-1 rounded-lg bg-obsidian-950 border border-slate-800 text-xs font-mono text-slate-300">
            Target: <strong className="text-emerald-400 font-bold">{selectedSymbol}</strong>
          </div>
        </div>
      </div>

      {/* Account KPI Strip */}
      <div className="grid grid-cols-2 sm:grid-cols-5 gap-3 text-xs font-mono">
        <div className="bg-obsidian-950 p-3 rounded-lg border border-slate-800">
          <span className="text-slate-500 block text-[10px] uppercase font-semibold">Net Equity</span>
          <span className="text-white font-bold text-base mt-0.5 block">
            ₹{account.equity.toLocaleString(undefined, { minimumFractionDigits: 2 })}
          </span>
        </div>

        <div className="bg-obsidian-950 p-3 rounded-lg border border-slate-800">
          <span className="text-slate-500 block text-[10px] uppercase font-semibold">Available Cash</span>
          <span className="text-slate-200 font-bold text-base mt-0.5 block">
            ₹{account.cash.toLocaleString(undefined, { minimumFractionDigits: 2 })}
          </span>
        </div>

        <div className="bg-obsidian-950 p-3 rounded-lg border border-slate-800">
          <span className="text-slate-500 block text-[10px] uppercase font-semibold">Realized PnL</span>
          <span
            className={`font-bold text-base mt-0.5 block ${
              account.realized_pnl >= 0 ? "text-emerald-400" : "text-rose-400"
            }`}
          >
            {account.realized_pnl >= 0 ? "+" : ""}₹{account.realized_pnl.toFixed(2)}
          </span>
        </div>

        <div className="bg-obsidian-950 p-3 rounded-lg border border-slate-800">
          <span className="text-slate-500 block text-[10px] uppercase font-semibold">Statutory Fees Paid</span>
          <span className="text-amber-400 font-bold text-base mt-0.5 block">
            ₹{account.total_fees.toFixed(2)}
          </span>
        </div>

        <div className="bg-obsidian-950 p-3 rounded-lg border border-slate-800">
          <span className="text-slate-500 block text-[10px] uppercase font-semibold">Open Positions</span>
          <span className="text-indigo-400 font-bold text-base mt-0.5 block">
            {account.open_positions_count} Active
          </span>
        </div>
      </div>

      {/* Order Entry Form & Order Blotter Layout */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left Column: Interactive Order Entry Pad */}
        <form
          onSubmit={handlePlaceOrder}
          className="bg-obsidian-950 border border-slate-800/90 rounded-xl p-4 flex flex-col gap-4 shadow-xl"
        >
          <div className="flex items-center justify-between border-b border-slate-800 pb-2">
            <span className="text-xs font-bold text-slate-200 uppercase tracking-wide">
              Quick Order Ticket
            </span>
            <span className="text-[10px] font-mono text-emerald-400 bg-emerald-500/10 px-2 py-0.5 rounded border border-emerald-500/30">
              Zero Slippage Mode
            </span>
          </div>

          {/* Buy / Sell Toggle Buttons */}
          <div className="grid grid-cols-2 gap-2">
            <button
              type="button"
              onClick={() => setSide("BUY")}
              className={`py-2 rounded-lg font-mono font-bold text-xs transition-all ${
                side === "BUY"
                  ? "bg-emerald-600 text-white shadow-glow-emerald"
                  : "bg-slate-900 text-slate-400 hover:text-slate-200 hover:bg-slate-800"
              }`}
            >
              BUY / LONG
            </button>
            <button
              type="button"
              onClick={() => setSide("SELL")}
              className={`py-2 rounded-lg font-mono font-bold text-xs transition-all ${
                side === "SELL"
                  ? "bg-rose-600 text-white shadow-glow-rose"
                  : "bg-slate-900 text-slate-400 hover:text-slate-200 hover:bg-slate-800"
              }`}
            >
              SELL / SHORT
            </button>
          </div>

          {/* Order Type Toggle */}
          <div className="flex flex-col gap-1 text-xs">
            <label className="text-slate-400 font-medium">Order Type</label>
            <div className="grid grid-cols-2 gap-2 font-mono">
              <button
                type="button"
                onClick={() => setOrderType("LIMIT")}
                className={`py-1.5 rounded-md text-xs font-semibold border ${
                  orderType === "LIMIT"
                    ? "bg-indigo-600 border-indigo-500 text-white shadow-glow-indigo"
                    : "bg-slate-900 border-slate-800 text-slate-400"
                }`}
              >
                Limit (Queue-Aware)
              </button>
              <button
                type="button"
                onClick={() => setOrderType("MARKET")}
                className={`py-1.5 rounded-md text-xs font-semibold border ${
                  orderType === "MARKET"
                    ? "bg-indigo-600 border-indigo-500 text-white shadow-glow-indigo"
                    : "bg-slate-900 border-slate-800 text-slate-400"
                }`}
              >
                Market (Instant)
              </button>
            </div>
          </div>

          {/* Quantity with Quick Add Pills */}
          <div className="flex flex-col gap-1.5 text-xs">
            <div className="flex items-center justify-between">
              <label className="text-slate-400 font-medium">Quantity (Shares/Lots)</label>
              <div className="flex gap-1">
                {[10, 25, 50, 100].map((q) => (
                  <button
                    key={q}
                    type="button"
                    onClick={() => handleQuickQuantity(q)}
                    className="px-1.5 py-0.5 rounded bg-slate-900 hover:bg-slate-800 border border-slate-800 text-[10px] font-mono text-slate-300"
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
              className="bg-slate-900 border border-slate-800 rounded-lg px-3 py-2 text-slate-100 font-mono text-sm focus:outline-none focus:border-indigo-500"
            />
          </div>

          {/* Price (if Limit) */}
          {orderType === "LIMIT" && (
            <div className="flex flex-col gap-1 text-xs">
              <label className="text-slate-400 font-medium">Limit Price (₹)</label>
              <input
                type="number"
                step="0.05"
                value={price}
                onChange={(e) => setPrice(parseFloat(e.target.value) || 0)}
                className="bg-slate-900 border border-slate-800 rounded-lg px-3 py-2 text-slate-100 font-mono text-sm focus:outline-none focus:border-indigo-500"
              />
            </div>
          )}

          {/* Ticket Calculations */}
          <div className="bg-slate-900/60 rounded-lg p-2.5 border border-slate-800/80 text-xs font-mono flex flex-col gap-1 text-slate-400">
            <div className="flex justify-between">
              <span>Order Notional:</span>
              <span className="text-slate-200 font-semibold">₹{orderValue.toLocaleString(undefined, { minimumFractionDigits: 2 })}</span>
            </div>
            <div className="flex justify-between text-[11px]">
              <span>Est. Statutory Charges:</span>
              <span className="text-amber-400">₹{estimatedFees.toFixed(2)}</span>
            </div>
          </div>

          {/* Submit Order Button */}
          <button
            type="submit"
            className={`w-full py-2.5 rounded-lg font-bold font-mono text-sm transition-all shadow-lg ${
              side === "BUY"
                ? "bg-emerald-600 hover:bg-emerald-500 text-white shadow-glow-emerald"
                : "bg-rose-600 hover:bg-rose-500 text-white shadow-glow-rose"
            }`}
          >
            Submit {side} Order ({quantity} @ {orderType === "LIMIT" ? `₹${price}` : "MKT"})
          </button>
        </form>

        {/* Right 2 Columns: Active Positions & Blotter */}
        <div className="lg:col-span-2 flex flex-col gap-6">
          {/* Active Positions */}
          <div className="bg-obsidian-950 border border-slate-800/90 rounded-xl p-4 shadow-xl flex flex-col gap-3">
            <h4 className="text-xs font-bold text-slate-300 uppercase tracking-wide flex items-center justify-between">
              <span>Open Portfolio Positions</span>
              <span className="text-[10px] font-mono text-slate-500">Live PnL Engine</span>
            </h4>

            {positions.length === 0 ? (
              <div className="py-6 text-center text-xs font-mono text-slate-600">
                No active positions. Submit an order to simulate position lifecycle.
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-xs font-mono text-left">
                  <thead>
                    <tr className="border-b border-slate-800 text-slate-500 text-[10px] uppercase">
                      <th className="pb-2">Symbol</th>
                      <th className="pb-2">Side</th>
                      <th className="pb-2 text-right">Qty</th>
                      <th className="pb-2 text-right">Avg Entry</th>
                      <th className="pb-2 text-right">LTP</th>
                      <th className="pb-2 text-right">Unrealized PnL</th>
                      <th className="pb-2 text-right">Action</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-800/60">
                    {positions.map((pos) => (
                      <tr key={pos.instrument_id} className="hover:bg-slate-900/50">
                        <td className="py-2.5 font-bold text-slate-200">{pos.symbol}</td>
                        <td className="py-2.5">
                          <span
                            className={`px-1.5 py-0.5 rounded text-[10px] font-bold ${
                              pos.side === "LONG"
                                ? "bg-emerald-500/20 text-emerald-400"
                                : "bg-rose-500/20 text-rose-400"
                            }`}
                          >
                            {pos.side}
                          </span>
                        </td>
                        <td className="py-2.5 text-right text-slate-300">{pos.quantity}</td>
                        <td className="py-2.5 text-right text-slate-300">₹{pos.entry_price.toFixed(2)}</td>
                        <td className="py-2.5 text-right font-bold text-slate-100">
                          ₹{pos.current_price.toFixed(2)}
                        </td>
                        <td
                          className={`py-2.5 text-right font-bold ${
                            pos.unrealized_pnl >= 0 ? "text-emerald-400" : "text-rose-400"
                          }`}
                        >
                          {pos.unrealized_pnl >= 0 ? "+" : ""}₹{pos.unrealized_pnl.toFixed(2)}
                        </td>
                        <td className="py-2.5 text-right">
                          <button
                            type="button"
                            onClick={() => onClosePosition && onClosePosition(pos.instrument_id)}
                            className="px-2 py-1 rounded bg-rose-500/20 hover:bg-rose-500/40 border border-rose-500/40 text-[10px] text-rose-300 font-semibold"
                          >
                            Close
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>

          {/* Real-time Order Blotter */}
          <div className="bg-obsidian-950 border border-slate-800/90 rounded-xl p-4 shadow-xl flex flex-col gap-3">
            <h4 className="text-xs font-bold text-slate-300 uppercase tracking-wide flex items-center justify-between">
              <span>Order Blotter & Execution Log</span>
              <span className="text-[10px] font-mono text-slate-500">{orders.length} Records</span>
            </h4>

            {orders.length === 0 ? (
              <div className="py-6 text-center text-xs font-mono text-slate-600">
                No orders submitted in current session.
              </div>
            ) : (
              <div className="overflow-x-auto max-h-56">
                <table className="w-full text-xs font-mono text-left">
                  <thead>
                    <tr className="border-b border-slate-800 text-slate-500 text-[10px] uppercase">
                      <th className="pb-2">Order ID</th>
                      <th className="pb-2">Side</th>
                      <th className="pb-2">Type</th>
                      <th className="pb-2 text-right">Qty</th>
                      <th className="pb-2 text-right">Filled</th>
                      <th className="pb-2 text-right">Price</th>
                      <th className="pb-2 text-right">Status</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-800/60">
                    {orders.map((ord) => (
                      <tr key={ord.order_id} className="hover:bg-slate-900/50">
                        <td className="py-2 text-[10px] text-slate-500">{ord.order_id}</td>
                        <td className="py-2">
                          <span
                            className={`px-1.5 py-0.2 rounded text-[10px] font-bold ${
                              ord.side === "BUY" ? "text-emerald-400" : "text-rose-400"
                            }`}
                          >
                            {ord.side}
                          </span>
                        </td>
                        <td className="py-2 text-slate-400 text-[10px]">{ord.order_type}</td>
                        <td className="py-2 text-right text-slate-300">{ord.quantity}</td>
                        <td className="py-2 text-right text-emerald-400">{ord.filled_quantity ?? ord.quantity}</td>
                        <td className="py-2 text-right text-slate-200">
                          {ord.price ? `₹${ord.price.toFixed(2)}` : "MKT"}
                        </td>
                        <td className="py-2 text-right">
                          <span
                            className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                              ord.status === "FILLED"
                                ? "bg-emerald-500/20 text-emerald-300 border border-emerald-500/40"
                                : ord.status === "PENDING"
                                ? "bg-amber-500/20 text-amber-300 border border-amber-500/40"
                                : "bg-slate-800 text-slate-400"
                            }`}
                          >
                            {ord.status}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
