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
}

export const PaperTradingDashboard: React.FC<PaperTradingDashboardProps> = ({
  account,
  positions,
  orders,
  selectedSymbol,
  selectedInstrumentId,
  onSubmitOrder,
}) => {
  const [side, setSide] = useState<OrderSide>("BUY");
  const [orderType, setOrderType] = useState<OrderType>("LIMIT");
  const [quantity, setQuantity] = useState(50);
  const [price, setPrice] = useState(2500.0);

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
      price: orderType === "LIMIT" ? price : undefined,
      created_time_utc: Date.now(),
      updated_time_utc: Date.now(),
    });
  };

  return (
    <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-2xl flex flex-col gap-5">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between pb-3 border-b border-slate-800 gap-2">
        <div>
          <h3 className="text-lg font-bold text-slate-100 flex items-center gap-2">
            <span className="w-2.5 h-2.5 rounded-full bg-emerald-400 animate-pulse"></span>
            Paper Trading & Execution Lab
          </h3>
          <p className="text-xs text-slate-400">
            Real-time simulated order matching with queue-ahead limit modeling
          </p>
        </div>

        {/* Selected Instrument */}
        <div className="px-3 py-1 rounded bg-slate-950 border border-slate-800 text-xs font-mono text-slate-300">
          Target: <strong className="text-emerald-400">{selectedSymbol}</strong>
        </div>
      </div>

      {/* Account KPI Strip */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs font-mono">
        <div className="bg-slate-950 p-3 rounded-lg border border-slate-800">
          <span className="text-slate-500 block text-[10px]">Net Equity</span>
          <span className="text-slate-100 font-bold text-base">
            ₹{account.equity.toLocaleString(undefined, { minimumFractionDigits: 2 })}
          </span>
        </div>
        <div className="bg-slate-950 p-3 rounded-lg border border-slate-800">
          <span className="text-slate-500 block text-[10px]">Available Cash</span>
          <span className="text-slate-300 font-bold text-base">
            ₹{account.cash.toLocaleString(undefined, { minimumFractionDigits: 2 })}
          </span>
        </div>
        <div className="bg-slate-950 p-3 rounded-lg border border-slate-800">
          <span className="text-slate-500 block text-[10px]">Realized P&L</span>
          <span
            className={`font-bold text-base ${
              account.realized_pnl >= 0 ? "text-emerald-400" : "text-rose-400"
            }`}
          >
            {account.realized_pnl >= 0 ? "+" : ""}
            ₹{account.realized_pnl.toLocaleString(undefined, { minimumFractionDigits: 2 })}
          </span>
        </div>
        <div className="bg-slate-950 p-3 rounded-lg border border-slate-800">
          <span className="text-slate-500 block text-[10px]">Total Statutory Fees</span>
          <span className="text-amber-400 font-bold text-base">
            ₹{account.total_fees.toLocaleString(undefined, { minimumFractionDigits: 2 })}
          </span>
        </div>
      </div>

      {/* Order Placement Form */}
      <form
        onSubmit={handlePlaceOrder}
        className="bg-slate-950/60 border border-slate-800 rounded-lg p-3.5 flex flex-wrap items-center gap-3 text-xs"
      >
        <span className="font-semibold text-slate-300">New Order:</span>

        {/* Side toggle */}
        <div className="flex rounded border border-slate-700 overflow-hidden">
          <button
            type="button"
            onClick={() => setSide("BUY")}
            className={`px-3 py-1 font-bold ${
              side === "BUY"
                ? "bg-emerald-600 text-white"
                : "bg-slate-900 text-slate-400 hover:text-slate-200"
            }`}
          >
            BUY
          </button>
          <button
            type="button"
            onClick={() => setSide("SELL")}
            className={`px-3 py-1 font-bold ${
              side === "SELL"
                ? "bg-rose-600 text-white"
                : "bg-slate-900 text-slate-400 hover:text-slate-200"
            }`}
          >
            SELL
          </button>
        </div>

        {/* Order Type */}
        <select
          value={orderType}
          onChange={(e) => setOrderType(e.target.value as OrderType)}
          className="bg-slate-900 border border-slate-700 rounded px-2.5 py-1 text-slate-200 font-medium focus:outline-none"
        >
          <option value="MARKET">Market</option>
          <option value="LIMIT">Limit</option>
        </select>

        {/* Quantity */}
        <div className="flex items-center gap-1.5">
          <span className="text-slate-500 text-[11px]">Qty:</span>
          <input
            type="number"
            min="1"
            value={quantity}
            onChange={(e) => setQuantity(parseInt(e.target.value) || 1)}
            className="w-20 bg-slate-900 border border-slate-700 rounded px-2 py-1 text-slate-200 font-mono text-center focus:outline-none"
          />
        </div>

        {/* Limit Price */}
        {orderType === "LIMIT" && (
          <div className="flex items-center gap-1.5">
            <span className="text-slate-500 text-[11px]">Price:</span>
            <input
              type="number"
              step="0.05"
              value={price}
              onChange={(e) => setPrice(parseFloat(e.target.value) || 0)}
              className="w-24 bg-slate-900 border border-slate-700 rounded px-2 py-1 text-slate-200 font-mono text-center focus:outline-none"
            />
          </div>
        )}

        <button
          type="submit"
          className={`ml-auto px-5 py-1.5 rounded font-bold transition-all shadow-md ${
            side === "BUY"
              ? "bg-emerald-600 hover:bg-emerald-500 text-white shadow-emerald-600/30"
              : "bg-rose-600 hover:bg-rose-500 text-white shadow-rose-600/30"
          }`}
        >
          Place {side} Order
        </button>
      </form>

      {/* Active Positions Table */}
      <div className="flex flex-col gap-2">
        <h4 className="text-xs font-bold text-slate-300 uppercase tracking-wider">
          Active Positions ({positions.length})
        </h4>
        <div className="overflow-x-auto rounded-lg border border-slate-800">
          <table className="w-full text-left text-xs font-mono">
            <thead className="bg-slate-950 text-slate-400 text-[10px] uppercase border-b border-slate-800">
              <tr>
                <th className="py-2 px-3">Symbol</th>
                <th className="py-2 px-3">Side</th>
                <th className="py-2 px-3 text-right">Quantity</th>
                <th className="py-2 px-3 text-right">Entry Price</th>
                <th className="py-2 px-3 text-right">Current Price</th>
                <th className="py-2 px-3 text-right">Unrealized P&L</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/60">
              {positions.length === 0 ? (
                <tr>
                  <td colSpan={6} className="py-4 text-center text-slate-500 font-sans">
                    No active positions open.
                  </td>
                </tr>
              ) : (
                positions.map((p) => (
                  <tr key={p.instrument_id} className="hover:bg-slate-800/30">
                    <td className="py-2 px-3 font-bold text-slate-200">{p.symbol}</td>
                    <td className="py-2 px-3">
                      <span
                        className={`px-1.5 py-0.5 rounded text-[10px] font-bold ${
                          p.side === "LONG"
                            ? "bg-emerald-500/20 text-emerald-400"
                            : "bg-rose-500/20 text-rose-400"
                        }`}
                      >
                        {p.side}
                      </span>
                    </td>
                    <td className="py-2 px-3 text-right">{p.quantity}</td>
                    <td className="py-2 px-3 text-right">{p.entry_price.toFixed(2)}</td>
                    <td className="py-2 px-3 text-right">{p.current_price.toFixed(2)}</td>
                    <td
                      className={`py-2 px-3 text-right font-bold ${
                        p.unrealized_pnl >= 0 ? "text-emerald-400" : "text-rose-400"
                      }`}
                    >
                      {p.unrealized_pnl >= 0 ? "+" : ""}
                      {p.unrealized_pnl.toFixed(2)}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Order Blotter Table */}
      <div className="flex flex-col gap-2">
        <h4 className="text-xs font-bold text-slate-300 uppercase tracking-wider">
          Order Blotter ({orders.length})
        </h4>
        <div className="overflow-x-auto rounded-lg border border-slate-800">
          <table className="w-full text-left text-xs font-mono">
            <thead className="bg-slate-950 text-slate-400 text-[10px] uppercase border-b border-slate-800">
              <tr>
                <th className="py-2 px-3">Order ID</th>
                <th className="py-2 px-3">Side</th>
                <th className="py-2 px-3">Type</th>
                <th className="py-2 px-3 text-right">Price</th>
                <th className="py-2 px-3 text-right">Qty</th>
                <th className="py-2 px-3 text-center">Status</th>
                <th className="py-2 px-3 text-right">Queue Ahead</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/60">
              {orders.length === 0 ? (
                <tr>
                  <td colSpan={7} className="py-4 text-center text-slate-500 font-sans">
                    No orders placed yet.
                  </td>
                </tr>
              ) : (
                orders.map((o) => (
                  <tr key={o.order_id} className="hover:bg-slate-800/30">
                    <td className="py-2 px-3 text-slate-400">{o.order_id}</td>
                    <td className="py-2 px-3 font-bold">{o.side}</td>
                    <td className="py-2 px-3 text-slate-300">{o.order_type}</td>
                    <td className="py-2 px-3 text-right">
                      {o.price ? o.price.toFixed(2) : "MKT"}
                    </td>
                    <td className="py-2 px-3 text-right">{o.quantity}</td>
                    <td className="py-2 px-3 text-center">
                      <span
                        className={`px-1.5 py-0.5 rounded text-[10px] font-bold ${
                          o.status === "FILLED"
                            ? "bg-emerald-500/20 text-emerald-400"
                            : "bg-amber-500/20 text-amber-400"
                        }`}
                      >
                        {o.status}
                      </span>
                    </td>
                    <td className="py-2 px-3 text-right text-slate-400">
                      {o.queue_ahead_volume}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};
