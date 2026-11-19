import React from "react";
import { VolumeProfile } from "../types/domain";

interface VolumeProfileViewProps {
  profile: VolumeProfile | null;
}

export const VolumeProfileView: React.FC<VolumeProfileViewProps> = ({ profile }) => {
  if (!profile) {
    return (
      <div className="bg-slate-900 border border-slate-800 rounded-xl p-8 text-center text-slate-500">
        No volume profile data loaded.
      </div>
    );
  }

  const entries = Object.entries(profile.bins)
    .map(([p, v]) => ({ price: parseFloat(p), volume: v }))
    .sort((a, b) => b.price - a.price);

  const maxBinVol = Math.max(...entries.map((e) => e.volume), 1);

  return (
    <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-2xl flex flex-col gap-4">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between pb-3 border-b border-slate-800 gap-2">
        <div>
          <h3 className="text-lg font-bold text-slate-100 flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-indigo-500"></span>
            Volume Profile (70% Value Area)
          </h3>
          <p className="text-xs text-slate-400">
            {profile.instrument_id} • Session {profile.session_date}
          </p>
        </div>

        {/* Provenance Badge */}
        <div className="flex items-center gap-2">
          <span
            className={`px-2 py-0.5 rounded text-[10px] font-mono font-semibold ${
              profile.provenance.is_estimated
                ? "bg-amber-500/10 text-amber-400 border border-amber-500/30"
                : "bg-emerald-500/10 text-emerald-400 border border-emerald-500/30"
            }`}
          >
            {profile.provenance.is_estimated ? "⚡ ESTIMATED" : "✓ GENUINE"} [Level{" "}
            {profile.provenance.quality}]
          </span>
        </div>
      </div>

      {/* Metrics Summary Strip */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs font-mono">
        <div className="bg-slate-950 p-2.5 rounded-lg border border-slate-800">
          <span className="text-slate-500 block text-[10px]">POC Price</span>
          <span className="text-amber-400 font-bold text-sm">
            {profile.poc_price.toFixed(2)}
          </span>
        </div>
        <div className="bg-slate-950 p-2.5 rounded-lg border border-slate-800">
          <span className="text-slate-500 block text-[10px]">VAH (Upper 70%)</span>
          <span className="text-indigo-400 font-bold text-sm">
            {profile.vah_price.toFixed(2)}
          </span>
        </div>
        <div className="bg-slate-950 p-2.5 rounded-lg border border-slate-800">
          <span className="text-slate-500 block text-[10px]">VAL (Lower 70%)</span>
          <span className="text-indigo-400 font-bold text-sm">
            {profile.val_price.toFixed(2)}
          </span>
        </div>
        <div className="bg-slate-950 p-2.5 rounded-lg border border-slate-800">
          <span className="text-slate-500 block text-[10px]">Total Traded Vol</span>
          <span className="text-slate-200 font-bold text-sm">
            {profile.total_volume.toLocaleString()}
          </span>
        </div>
      </div>

      {/* Profile Horizontal Histogram */}
      <div className="max-h-80 overflow-y-auto rounded-lg border border-slate-800/80 bg-slate-950/40 p-2">
        <div className="flex flex-col gap-0.5">
          {entries.map((item) => {
            const isPoc = Math.abs(item.price - profile.poc_price) < 1e-4;
            const inValueArea =
              item.price >= profile.val_price && item.price <= profile.vah_price;
            const barWidthPct = (item.volume / maxBinVol) * 100;

            return (
              <div
                key={item.price}
                className={`flex items-center gap-2 py-0.5 px-2 rounded text-[10px] font-mono transition-colors ${
                  isPoc
                    ? "bg-amber-500/20 text-amber-300 font-bold"
                    : inValueArea
                    ? "bg-indigo-950/30 text-indigo-200"
                    : "text-slate-400 hover:bg-slate-900"
                }`}
              >
                {/* Price Label */}
                <span className="w-14 text-right">{item.price.toFixed(2)}</span>

                {/* Histogram Bar */}
                <div className="flex-1 bg-slate-800/40 h-3 rounded-sm overflow-hidden flex items-center">
                  <div
                    style={{ width: `${barWidthPct}%` }}
                    className={`h-full transition-all duration-300 ${
                      isPoc
                        ? "bg-amber-400 shadow-sm shadow-amber-400/50"
                        : inValueArea
                        ? "bg-indigo-500"
                        : "bg-slate-600"
                    }`}
                  />
                </div>

                {/* Volume Count */}
                <span className="w-16 text-right text-[10px]">
                  {item.volume.toLocaleString()}
                </span>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
};
