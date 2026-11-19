import React, { useEffect, useRef, useState } from "react";
import { FootprintBar, PriceCluster } from "../types/domain";

interface FootprintChartProps {
  bars: FootprintBar[];
  symbol: string;
  timeframe: string;
}

export const FootprintChart: React.FC<FootprintChartProps> = ({
  bars,
  symbol,
  timeframe,
}) => {
  const [hoveredCluster, setHoveredCluster] = useState<{
    barIndex: number;
    cluster: PriceCluster;
  } | null>(null);

  if (!bars || bars.length === 0) {
    return (
      <div className="bg-slate-900 border border-slate-800 rounded-xl p-8 text-center text-slate-500">
        No footprint cluster data available for {symbol} ({timeframe}).
      </div>
    );
  }

  return (
    <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-2xl flex flex-col gap-4">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between pb-3 border-b border-slate-800 gap-2">
        <div>
          <h3 className="text-lg font-bold text-slate-100 flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-cyan-400"></span>
            Footprint Cluster Ladder (Bid × Ask)
          </h3>
          <p className="text-xs text-slate-400">
            {symbol} • {timeframe} • Diagonal Imbalances (3:1) & POC Highlight
          </p>
        </div>

        {/* Legend */}
        <div className="flex items-center gap-4 text-[11px] text-slate-400">
          <div className="flex items-center gap-1.5">
            <span className="w-2.5 h-2.5 bg-emerald-500/30 border border-emerald-500 rounded-sm"></span>
            <span>Buy Imbalance</span>
          </div>
          <div className="flex items-center gap-1.5">
            <span className="w-2.5 h-2.5 bg-rose-500/30 border border-rose-500 rounded-sm"></span>
            <span>Sell Imbalance</span>
          </div>
          <div className="flex items-center gap-1.5">
            <span className="w-2.5 h-2.5 bg-amber-500/20 border border-amber-400 rounded-sm"></span>
            <span>POC Level</span>
          </div>
        </div>
      </div>

      {/* Footprint Columns Container */}
      <div className="overflow-x-auto pb-4">
        <div className="inline-flex gap-4 min-w-full justify-start items-end py-2">
          {bars.map((bar, barIdx) => {
            const isBullish = bar.close >= bar.open;
            return (
              <div
                key={bar.timestamp_utc}
                className="flex flex-col items-center min-w-[140px] bg-slate-950/50 border border-slate-800/80 rounded-lg p-2"
              >
                {/* Candle Header: Time & Delta */}
                <div className="w-full text-center pb-2 border-b border-slate-800/60">
                  <span className="text-[10px] text-slate-400 font-mono">
                    {new Date(bar.timestamp_utc).toLocaleTimeString([], {
                      hour: "2-digit",
                      minute: "2-digit",
                    })}
                  </span>
                  <div
                    className={`text-xs font-bold font-mono ${
                      bar.delta >= 0 ? "text-emerald-400" : "text-rose-400"
                    }`}
                  >
                    Δ {bar.delta > 0 ? `+${bar.delta}` : bar.delta}
                  </div>
                </div>

                {/* Price Cluster Rows (Highest to Lowest) */}
                <div className="w-full flex flex-col gap-0.5 my-2">
                  {bar.clusters.map((cluster) => {
                    const isPoc = Math.abs(cluster.price - bar.poc_price) < 1e-4;
                    const deltaPositive = cluster.delta >= 0;
                    const isBuyImbalance = cluster.is_buy_imbalance;
                    const isSellImbalance = cluster.is_sell_imbalance;

                    return (
                      <div
                        key={cluster.price}
                        onMouseEnter={() =>
                          setHoveredCluster({ barIndex: barIdx, cluster })
                        }
                        onMouseLeave={() => setHoveredCluster(null)}
                        className={`flex items-center justify-between px-1.5 py-0.5 rounded text-[10px] font-mono transition-all cursor-pointer ${
                          isPoc
                            ? "bg-amber-500/20 border border-amber-400/80 text-amber-200"
                            : "bg-slate-900/60 hover:bg-slate-800"
                        }`}
                      >
                        {/* Bid Volume */}
                        <span
                          className={`w-10 text-right pr-1 ${
                            isSellImbalance
                              ? "bg-rose-500/30 text-rose-300 font-bold rounded-sm"
                              : "text-slate-400"
                          }`}
                        >
                          {cluster.bid_volume}
                        </span>

                        {/* Price Node */}
                        <span className="w-12 text-center font-semibold text-slate-200">
                          {cluster.price.toFixed(1)}
                        </span>

                        {/* Ask Volume */}
                        <span
                          className={`w-10 text-left pl-1 ${
                            isBuyImbalance
                              ? "bg-emerald-500/30 text-emerald-300 font-bold rounded-sm"
                              : "text-slate-400"
                          }`}
                        >
                          {cluster.ask_volume}
                        </span>
                      </div>
                    );
                  })}
                </div>

                {/* Footer: Volume & Price Boundaries */}
                <div className="w-full pt-1.5 border-t border-slate-800/60 text-[10px] text-slate-400 flex justify-between font-mono">
                  <span>Tot: {bar.volume}</span>
                  <span className="text-amber-400">POC: {bar.poc_price.toFixed(1)}</span>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Tooltip Inspector */}
      {hoveredCluster && (
        <div className="bg-slate-950 border border-slate-700 rounded-lg p-3 text-xs flex flex-wrap gap-4 font-mono">
          <div>
            <span className="text-slate-500">Price: </span>
            <span className="text-slate-200 font-bold">
              {hoveredCluster.cluster.price.toFixed(2)}
            </span>
          </div>
          <div>
            <span className="text-slate-500">Bid: </span>
            <span className="text-rose-400">{hoveredCluster.cluster.bid_volume}</span>
          </div>
          <div>
            <span className="text-slate-500">Ask: </span>
            <span className="text-emerald-400">{hoveredCluster.cluster.ask_volume}</span>
          </div>
          <div>
            <span className="text-slate-500">Delta: </span>
            <span
              className={
                hoveredCluster.cluster.delta >= 0 ? "text-emerald-400" : "text-rose-400"
              }
            >
              {hoveredCluster.cluster.delta}
            </span>
          </div>
          {hoveredCluster.cluster.is_buy_imbalance && (
            <span className="px-1.5 py-0.5 rounded bg-emerald-500/20 text-emerald-300 border border-emerald-500/40">
              ⚡ Buy Imbalance (3:1)
            </span>
          )}
          {hoveredCluster.cluster.is_sell_imbalance && (
            <span className="px-1.5 py-0.5 rounded bg-rose-500/20 text-rose-300 border border-rose-500/40">
              ⚡ Sell Imbalance (3:1)
            </span>
          )}
        </div>
      )}
    </div>
  );
};
