import React, { useState } from "react";
import { AssetClass, DataQuality, InstrumentMaster } from "../types/domain";

interface MarketExplorerProps {
  instruments: InstrumentMaster[];
  selectedInstrumentId: string;
  onSelectInstrument: (inst: InstrumentMaster) => void;
}

const ASSET_CLASSES: (AssetClass | "ALL")[] = [
  "ALL",
  "EQUITY",
  "FUTURES",
  "OPTIONS",
  "CRYPTO",
  "FOREX",
  "COMMODITY",
];

export const MarketExplorer: React.FC<MarketExplorerProps> = ({
  instruments,
  selectedInstrumentId,
  onSelectInstrument,
}) => {
  const [filterClass, setFilterClass] = useState<AssetClass | "ALL">("ALL");
  const [search, setSearch] = useState("");

  const filtered = instruments.filter((inst) => {
    const matchClass = filterClass === "ALL" || inst.asset_class === filterClass;
    const matchSearch =
      inst.symbol.toLowerCase().includes(search.toLowerCase()) ||
      inst.exchange.toLowerCase().includes(search.toLowerCase()) ||
      inst.instrument_id.toLowerCase().includes(search.toLowerCase());
    return matchClass && matchSearch;
  });

  return (
    <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-2xl">
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 pb-4 border-b border-slate-800">
        <div>
          <h2 className="text-xl font-bold text-slate-100 flex items-center gap-2">
            <span className="w-2.5 h-2.5 rounded-full bg-emerald-500 animate-pulse"></span>
            Market Explorer
          </h2>
          <p className="text-xs text-slate-400 mt-0.5">
            Cross-asset instrument catalog with canonical identifiers and exchange specs
          </p>
        </div>

        {/* Search */}
        <div className="relative">
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search symbol, exchange, ID..."
            className="w-64 bg-slate-950 border border-slate-700 rounded-lg px-3 py-1.5 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-indigo-500 transition-colors"
          />
        </div>
      </div>

      {/* Asset Class Filter Tabs */}
      <div className="flex flex-wrap gap-2 my-4">
        {ASSET_CLASSES.map((ac) => (
          <button
            key={ac}
            onClick={() => setFilterClass(ac)}
            className={`px-3 py-1 rounded-md text-xs font-medium transition-all ${
              filterClass === ac
                ? "bg-indigo-600 text-white shadow-md shadow-indigo-600/30"
                : "bg-slate-800/60 text-slate-400 hover:bg-slate-800 hover:text-slate-200"
            }`}
          >
            {ac}
          </button>
        ))}
      </div>

      {/* Table */}
      <div className="overflow-x-auto rounded-lg border border-slate-800">
        <table className="w-full text-left text-xs">
          <thead className="bg-slate-950/70 text-slate-400 uppercase tracking-wider text-[10px] border-b border-slate-800">
            <tr>
              <th className="py-2.5 px-3">Canonical ID</th>
              <th className="py-2.5 px-3">Symbol</th>
              <th className="py-2.5 px-3">Exchange</th>
              <th className="py-2.5 px-3">Class</th>
              <th className="py-2.5 px-3 text-right">Tick Size</th>
              <th className="py-2.5 px-3 text-right">Lot Size</th>
              <th className="py-2.5 px-3">Currency</th>
              <th className="py-2.5 px-3 text-center">Action</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-800/60">
            {filtered.length === 0 ? (
              <tr>
                <td colSpan={8} className="py-6 text-center text-slate-500">
                  No matching instruments found.
                </td>
              </tr>
            ) : (
              filtered.map((inst) => {
                const isSelected = inst.instrument_id === selectedInstrumentId;
                return (
                  <tr
                    key={inst.instrument_id}
                    className={`transition-colors ${
                      isSelected ? "bg-indigo-950/40" : "hover:bg-slate-800/30"
                    }`}
                  >
                    <td className="py-2.5 px-3 font-mono text-slate-300">
                      {inst.instrument_id}
                    </td>
                    <td className="py-2.5 px-3 font-semibold text-slate-100">
                      {inst.symbol}
                    </td>
                    <td className="py-2.5 px-3">
                      <span className="px-1.5 py-0.5 rounded bg-slate-800 text-[10px] text-slate-300 font-mono">
                        {inst.exchange}
                      </span>
                    </td>
                    <td className="py-2.5 px-3">
                      <span className="text-slate-300 font-medium">
                        {inst.asset_class}
                      </span>
                    </td>
                    <td className="py-2.5 px-3 text-right font-mono text-slate-300">
                      {inst.tick_size}
                    </td>
                    <td className="py-2.5 px-3 text-right font-mono text-slate-300">
                      {inst.lot_size}
                    </td>
                    <td className="py-2.5 px-3 text-slate-400 font-mono">
                      {inst.currency}
                    </td>
                    <td className="py-2.5 px-3 text-center">
                      <button
                        onClick={() => onSelectInstrument(inst)}
                        className={`px-3 py-1 rounded text-[11px] font-medium transition-all ${
                          isSelected
                            ? "bg-emerald-600 text-white cursor-default"
                            : "bg-slate-800 text-slate-300 hover:bg-indigo-600 hover:text-white"
                        }`}
                      >
                        {isSelected ? "Active" : "Select"}
                      </button>
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
};
