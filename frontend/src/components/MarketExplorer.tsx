import React, { useState } from "react";
import { AssetClass, InstrumentMaster } from "../types/domain";

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

const ASSET_COLORS: Record<string, string> = {
  EQUITY: "bg-cyan-500/15 text-cyan-300 border-cyan-500/30",
  FUTURES: "bg-indigo-500/15 text-indigo-300 border-indigo-500/30",
  OPTIONS: "bg-purple-500/15 text-purple-300 border-purple-500/30",
  CRYPTO: "bg-amber-500/15 text-amber-300 border-amber-500/30",
  FOREX: "bg-emerald-500/15 text-emerald-300 border-emerald-500/30",
  COMMODITY: "bg-orange-500/15 text-orange-300 border-orange-500/30",
};

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
    <div className="bg-obsidian-900 border border-slate-800/90 rounded-xl p-5 shadow-2xl backdrop-blur">
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 pb-4 border-b border-slate-800/80">
        <div>
          <div className="flex items-center gap-2">
            <span className="w-2.5 h-2.5 rounded-full bg-cyan-400 shadow-glow-indigo animate-pulse" />
            <h2 className="text-base font-bold text-white tracking-tight">
              Global Instrument Catalog & Multi-Asset Master
            </h2>
          </div>
          <p className="text-xs text-slate-400 font-mono mt-0.5">
            Canonical identifiers, lot sizes, tick specifications, and derivative contract metadata
          </p>
        </div>

        {/* Search */}
        <div className="relative">
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search symbol, exchange, ID..."
            className="w-72 bg-obsidian-950 border border-slate-800 rounded-lg px-3 py-1.5 text-xs text-slate-100 placeholder-slate-500 focus:outline-none focus:border-indigo-500 transition-colors font-mono"
          />
        </div>
      </div>

      {/* Asset Class Filter Tabs */}
      <div className="flex flex-wrap gap-2 my-4">
        {ASSET_CLASSES.map((ac) => (
          <button
            key={ac}
            onClick={() => setFilterClass(ac)}
            className={`px-3 py-1 rounded-md text-xs font-mono font-medium transition-all ${
              filterClass === ac
                ? "bg-indigo-600 text-white shadow-glow-indigo font-bold"
                : "bg-obsidian-950 text-slate-400 hover:bg-slate-800 hover:text-slate-200 border border-slate-800"
            }`}
          >
            {ac}
          </button>
        ))}
      </div>

      {/* Table */}
      <div className="overflow-x-auto rounded-xl border border-slate-800/90 bg-obsidian-950">
        <table className="w-full text-left text-xs font-mono">
          <thead className="bg-obsidian-900 text-slate-400 uppercase tracking-wider text-[10px] border-b border-slate-800">
            <tr>
              <th className="py-2.5 px-3">Canonical ID</th>
              <th className="py-2.5 px-3">Symbol</th>
              <th className="py-2.5 px-3">Exchange</th>
              <th className="py-2.5 px-3">Asset Class</th>
              <th className="py-2.5 px-3 text-right">Tick Size</th>
              <th className="py-2.5 px-3 text-right">Lot Size</th>
              <th className="py-2.5 px-3">Currency</th>
              <th className="py-2.5 px-3 text-center">Action</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-800/60">
            {filtered.length === 0 ? (
              <tr>
                <td colSpan={8} className="py-8 text-center text-slate-500">
                  No matching instruments found for query "{search}".
                </td>
              </tr>
            ) : (
              filtered.map((inst) => {
                const isSelected = inst.instrument_id === selectedInstrumentId;
                const classBadge = ASSET_COLORS[inst.asset_class] || "bg-slate-800 text-slate-300";

                return (
                  <tr
                    key={inst.instrument_id}
                    className={`transition-colors ${
                      isSelected ? "bg-indigo-950/40" : "hover:bg-slate-900/60"
                    }`}
                  >
                    <td className="py-2.5 px-3 text-slate-400">
                      {inst.instrument_id}
                    </td>
                    <td className="py-2.5 px-3 font-bold text-white">
                      {inst.symbol}
                    </td>
                    <td className="py-2.5 px-3">
                      <span className="px-1.5 py-0.5 rounded bg-slate-900 border border-slate-800 text-[10px] text-slate-300">
                        {inst.exchange}
                      </span>
                    </td>
                    <td className="py-2.5 px-3">
                      <span className={`px-2 py-0.5 rounded text-[10px] font-semibold border ${classBadge}`}>
                        {inst.asset_class}
                      </span>
                    </td>
                    <td className="py-2.5 px-3 text-right text-slate-300">
                      {inst.tick_size}
                    </td>
                    <td className="py-2.5 px-3 text-right text-slate-300">
                      {inst.lot_size}
                    </td>
                    <td className="py-2.5 px-3 text-slate-400">
                      {inst.currency}
                    </td>
                    <td className="py-2.5 px-3 text-center">
                      <button
                        onClick={() => onSelectInstrument(inst)}
                        className={`px-3 py-1 rounded-md text-[11px] font-bold transition-all ${
                          isSelected
                            ? "bg-emerald-600 text-white shadow-glow-emerald cursor-default"
                            : "bg-slate-800 hover:bg-indigo-600 text-slate-200 hover:text-white"
                        }`}
                      >
                        {isSelected ? "Active" : "Load Chart"}
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
