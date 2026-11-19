import React, { useState } from "react";
import { VolumeProfile } from "../types/domain";

interface VolumeProfileViewProps {
  profile: VolumeProfile | null;
}

export const VolumeProfileView: React.FC<VolumeProfileViewProps> = ({ profile }) => {
  const [hoveredPrice, setHoveredPrice] = useState<number | null>(null);

  if (!profile) {
    return (
      <div className="bg-obsidian-900 border border-slate-800 rounded-xl p-8 text-center text-slate-500 font-mono text-xs">
        No volume profile data loaded.
      </div>
    );
  }

  const entries = Object.entries(profile.bins)
    .map(([p, v]) => ({ price: parseFloat(p), volume: v }))
    .sort((a, b) => b.price - a.price);

  const maxBinVol = Math.max(...entries.map((e) => e.volume), 1);

  return (
    <div className="bg-obsidian-900 border border-slate-800/90 rounded-xl p-5 shadow-2xl flex flex-col gap-4 backdrop-blur">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between pb-3 border-b border-slate-800/80 gap-3">
        <div>
          <div className="flex items-center gap-2">
            <span className="w-2.5 h-2.5 rounded-full bg-indigo-500 shadow-glow-indigo" />
            <h3 className="text-base font-bold text-white tracking-tight">
              Session Volume Profile (70% Value Area)
            </h3>
          </div>
          <p className="text-xs text-slate-400 font-mono mt-0.5">
            {profile.instrument_id} • Session {profile.session_date}
          </p>
        </div>

        {/* Provenance Tier Badge */}
        <div className="flex items-center gap-2">
          <span
            className={`px-2.5 py-1 rounded-md text-[11px] font-mono font-semibold flex items-center gap-1.5 ${
              profile.provenance.is_estimated
                ? "bg-amber-500/10 text-amber-300 border border-amber-500/30"
                : "bg-emerald-500/10 text-emerald-300 border border-emerald-500/30 shadow-glow-emerald"
            }`}
          >
            <span>{profile.provenance.is_estimated ? "⚡ ESTIMATED PROXY" : "✓ GENUINE TICKS"}</span>
            <span className="text-[10px] text-slate-400 font-normal">
              (Level {profile.provenance.quality})
            </span>
          </span>
        </div>
      </div>

      {/* KPI Metrics Strip */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs font-mono">
        <div className="bg-obsidian-950 p-3 rounded-lg border border-amber-500/30 bg-amber-500/5">
          <span className="text-slate-400 block text-[10px] uppercase tracking-wider font-semibold">
            Point of Control (POC)
          </span>
          <span className="text-amber-400 font-bold text-base mt-0.5 block">
            ₹{profile.poc_price.toFixed(2)}
          </span>
          <span className="text-[10px] text-amber-400/80">
            {profile.poc_volume ? profile.poc_volume.toLocaleString() + " vol" : "Max volume node"}
          </span>
        </div>

        <div className="bg-obsidian-950 p-3 rounded-lg border border-indigo-500/30 bg-indigo-500/5">
          <span className="text-slate-400 block text-[10px] uppercase tracking-wider font-semibold">
            Value Area High (VAH)
          </span>
          <span className="text-indigo-400 font-bold text-base mt-0.5 block">
            ₹{profile.vah_price.toFixed(2)}
          </span>
          <span className="text-[10px] text-slate-500">Upper 70% threshold</span>
        </div>

        <div className="bg-obsidian-950 p-3 rounded-lg border border-indigo-500/30 bg-indigo-500/5">
          <span className="text-slate-400 block text-[10px] uppercase tracking-wider font-semibold">
            Value Area Low (VAL)
          </span>
          <span className="text-indigo-400 font-bold text-base mt-0.5 block">
            ₹{profile.val_price.toFixed(2)}
          </span>
          <span className="text-[10px] text-slate-500">Lower 70% threshold</span>
        </div>

        <div className="bg-obsidian-950 p-3 rounded-lg border border-slate-800">
          <span className="text-slate-400 block text-[10px] uppercase tracking-wider font-semibold">
            Total Session Volume
          </span>
          <span className="text-slate-100 font-bold text-base mt-0.5 block">
            {profile.total_volume.toLocaleString()}
          </span>
          <span className="text-[10px] text-slate-500">
            Across {entries.length} price bins
          </span>
        </div>
      </div>

      {/* Profile Horizontal Histogram Matrix */}
      <div className="max-h-96 overflow-y-auto rounded-xl border border-slate-800/80 bg-obsidian-950 p-3">
        <div className="flex flex-col gap-1">
          {entries.map((item) => {
            const isPoc = Math.abs(item.price - profile.poc_price) < 1e-4;
            const inValueArea =
              item.price >= profile.val_price && item.price <= profile.vah_price;
            const barWidthPct = (item.volume / maxBinVol) * 100;

            return (
              <div
                key={item.price}
                onMouseEnter={() => setHoveredPrice(item.price)}
                onMouseLeave={() => setHoveredPrice(null)}
                className={`group flex items-center gap-3 py-1 px-2.5 rounded-lg text-xs font-mono transition-all cursor-pointer ${
                  isPoc
                    ? "bg-amber-500/20 border border-amber-500/50 text-amber-200 shadow-glow-amber"
                    : inValueArea
                    ? "bg-indigo-950/40 text-indigo-200 border border-indigo-500/20"
                    : "text-slate-400 hover:bg-slate-900 border border-transparent"
                }`}
              >
                {/* Price Label */}
                <div className="w-16 flex items-center justify-between">
                  <span className={`font-semibold ${isPoc ? "text-amber-400 font-bold" : "text-slate-200"}`}>
                    {item.price.toFixed(1)}
                  </span>
                  {isPoc && (
                    <span className="text-[9px] px-1 rounded bg-amber-500 text-black font-extrabold ml-1">
                      POC
                    </span>
                  )}
                </div>

                {/* Histogram Visual Bar */}
                <div className="flex-1 h-4 bg-slate-900/80 rounded overflow-hidden flex items-center relative">
                  <div
                    style={{ width: `${barWidthPct}%` }}
                    className={`h-full rounded-r transition-all duration-300 ${
                      isPoc
                        ? "bg-gradient-to-r from-amber-600 to-amber-400"
                        : inValueArea
                        ? "bg-gradient-to-r from-indigo-700 to-indigo-500"
                        : "bg-slate-700/60"
                    }`}
                  />
                  {/* Subtle bar volume readout */}
                  <span className="absolute left-2 text-[10px] text-slate-300 font-bold drop-shadow">
                    {item.volume.toLocaleString()}
                  </span>
                </div>

                {/* Percentage of Session */}
                <span className="w-12 text-right text-[10px] text-slate-500">
                  {((item.volume / profile.total_volume) * 100).toFixed(1)}%
                </span>
              </div>
            );
          })}
        </div>
      </div>

      {/* Footer Info */}
      <div className="text-[11px] font-mono text-slate-500 flex justify-between items-center px-1">
        <span>VA Range: ₹{profile.val_price.toFixed(2)} — ₹{profile.vah_price.toFixed(2)} (Spread: ₹{(profile.vah_price - profile.val_price).toFixed(2)})</span>
        <span>Tick: {profile.tick_size}</span>
      </div>
    </div>
  );
};
