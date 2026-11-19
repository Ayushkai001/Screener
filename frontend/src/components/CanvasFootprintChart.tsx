import React, { useCallback, useEffect, useRef, useState } from "react";
import { FootprintBar, PriceCluster } from "../types/domain";

interface CanvasFootprintChartProps {
  bars: FootprintBar[];
  symbol: string;
  timeframe: string;
  tickSize?: number;
}

type ClusterRenderMode = "bidxask" | "delta" | "volume";

interface HoverInfo {
  barIndex: number;
  bar: FootprintBar;
  cluster?: PriceCluster;
  price: number;
  screenX: number;
  screenY: number;
}

export const CanvasFootprintChart: React.FC<CanvasFootprintChartProps> = ({
  bars,
  symbol,
  timeframe,
  tickSize = 0.5,
}) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);

  // Settings & Modes
  const [renderMode, setRenderMode] = useState<ClusterRenderMode>("bidxask");
  const [imbalanceRatio, setImbalanceRatio] = useState<number>(3.0);
  const [showValueArea, setShowValueArea] = useState<boolean>(true);
  const [showPocRays, setShowPocRays] = useState<boolean>(true);
  const [showImbalances, setShowImbalances] = useState<boolean>(true);

  // Viewport transforms (pan & zoom)
  const [viewport, setViewport] = useState({
    barWidth: 140, // pixels per bar
    cellHeight: 22, // pixels per price row
    panX: 40,
    panY: 0,
  });

  const [isDragging, setIsDragging] = useState(false);
  const dragStartRef = useRef<{ x: number; y: number; panX: number; panY: number }>({
    x: 0,
    y: 0,
    panX: 0,
    panY: 0,
  });

  const [hoverInfo, setHoverInfo] = useState<HoverInfo | null>(null);

  // Auto-center viewport on initial load or symbol change
  const autoFitView = useCallback(() => {
    if (!bars || bars.length === 0 || !containerRef.current) return;
    const width = containerRef.current.clientWidth || 800;
    const height = containerRef.current.clientHeight || 500;

    const initialPanX = Math.max(20, width - bars.length * viewport.barWidth - 100);
    const initialPanY = height / 2;

    setViewport((prev) => ({
      ...prev,
      panX: initialPanX,
      panY: initialPanY,
      barWidth: 140,
      cellHeight: 22,
    }));
  }, [bars, viewport.barWidth]);

  useEffect(() => {
    autoFitView();
  }, [bars, symbol, autoFitView]);

  // Main Canvas Rendering Loop
  const render = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const dpr = window.devicePixelRatio || 1;
    const width = canvas.width / dpr;
    const height = canvas.height / dpr;

    // Clear background with deep obsidian tone
    ctx.fillStyle = "#04070d";
    ctx.fillRect(0, 0, width, height);

    if (!bars || bars.length === 0) {
      ctx.fillStyle = "#64748b";
      ctx.font = "14px Inter, sans-serif";
      ctx.textAlign = "center";
      ctx.fillText("No footprint data loaded for " + symbol, width / 2, height / 2);
      return;
    }

    const { barWidth, cellHeight, panX, panY } = viewport;

    // Reference price for vertical coordinates (midpoint of all bars)
    const allPrices = bars.flatMap((b) =>
      (Array.isArray(b.clusters) ? b.clusters : Object.values(b.clusters)).map((c) => c.price)
    );
    const refPrice = allPrices.length > 0 ? (Math.max(...allPrices) + Math.min(...allPrices)) / 2 : 2500.0;

    const priceToY = (price: number): number => {
      return panY - ((price - refPrice) / tickSize) * cellHeight;
    };

    const yToPrice = (y: number): number => {
      return refPrice - ((y - panY) / cellHeight) * tickSize;
    };

    // 1. Draw horizontal background price gridlines
    const minVisiblePrice = yToPrice(height);
    const maxVisiblePrice = yToPrice(0);
    const gridPriceStep = tickSize * Math.max(1, Math.round(50 / cellHeight));

    ctx.strokeStyle = "rgba(30, 41, 59, 0.4)";
    ctx.lineWidth = 1;
    ctx.fillStyle = "#64748b";
    ctx.font = "10px JetBrains Mono, monospace";
    ctx.textAlign = "right";

    const firstGridPrice = Math.floor(minVisiblePrice / gridPriceStep) * gridPriceStep;
    for (let p = firstGridPrice; p <= maxVisiblePrice; p += gridPriceStep) {
      const y = priceToY(p);
      ctx.beginPath();
      ctx.moveTo(0, y);
      ctx.lineTo(width - 70, y);
      ctx.stroke();

      // Right-hand price scale label
      ctx.fillText(p.toFixed(2), width - 8, y + 3);
    }

    // 2. Draw Footprint Bars
    bars.forEach((bar, barIdx) => {
      const barX = panX + barIdx * barWidth;

      // Skip off-screen bars (frustum culling)
      if (barX + barWidth < 0 || barX > width) return;

      const barCenter = barX + barWidth / 2;
      const isBullish = bar.close >= bar.open;

      // Draw Thin High-Low Wick behind clusters
      const highY = priceToY(bar.high);
      const lowY = priceToY(bar.low);
      ctx.strokeStyle = isBullish ? "rgba(16, 185, 129, 0.5)" : "rgba(244, 63, 94, 0.5)";
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.moveTo(barCenter, highY);
      ctx.lineTo(barCenter, lowY);
      ctx.stroke();

      // Draw 70% Value Area Box Bracket
      if (showValueArea) {
        const vah = bar.vah ?? bar.value_area_high ?? bar.high;
        const val = bar.val ?? bar.value_area_low ?? bar.low;
        const vahY = priceToY(vah);
        const valY = priceToY(val);
        ctx.fillStyle = "rgba(99, 102, 241, 0.06)";
        ctx.fillRect(barX + 2, vahY, barWidth - 4, Math.abs(valY - vahY));
        ctx.strokeStyle = "rgba(99, 102, 241, 0.4)";
        ctx.setLineDash([4, 4]);
        ctx.strokeRect(barX + 2, vahY, barWidth - 4, Math.abs(valY - vahY));
        ctx.setLineDash([]);
      }

      // Sort clusters descending by price (top to bottom)
      const clusterList: PriceCluster[] = Array.isArray(bar.clusters)
        ? bar.clusters
        : Object.values(bar.clusters);
      const sortedClusters = [...clusterList].sort((a, b) => b.price - a.price);

      sortedClusters.forEach((cluster) => {
        const cellY = priceToY(cluster.price) - cellHeight / 2;
        const cellW = barWidth - 8;
        const cellX = barX + 4;
        const halfW = cellW / 2;

        const isPoc = bar.poc_price ? Math.abs(cluster.price - bar.poc_price) < 1e-4 : false;
        const isBuyImbalance = cluster.imbalance_buy ?? cluster.is_buy_imbalance ?? false;
        const isSellImbalance = cluster.imbalance_sell ?? cluster.is_sell_imbalance ?? false;
        const bidVal = cluster.bid_vol ?? cluster.bid_volume ?? 0;
        const askVal = cluster.ask_vol ?? cluster.ask_volume ?? 0;
        const totalVal = cluster.total_vol ?? cluster.total_volume ?? (bidVal + askVal);
        const deltaVal = cluster.delta ?? (askVal - bidVal);

        // Base cell background
        ctx.fillStyle = isPoc ? "rgba(245, 158, 11, 0.18)" : "rgba(11, 16, 26, 0.85)";
        ctx.fillRect(cellX, cellY, cellW, cellHeight - 1);

        if (renderMode === "bidxask") {
          // Classic Bid x Ask Footprint
          if (showImbalances && isBuyImbalance) {
            ctx.fillStyle = "rgba(16, 185, 129, 0.35)";
            ctx.fillRect(cellX + halfW, cellY, halfW, cellHeight - 1);
          }

          if (showImbalances && isSellImbalance) {
            ctx.fillStyle = "rgba(244, 63, 94, 0.35)";
            ctx.fillRect(cellX, cellY, halfW, cellHeight - 1);
          }

          // Center Divider Line
          ctx.strokeStyle = "rgba(51, 65, 85, 0.4)";
          ctx.lineWidth = 1;
          ctx.beginPath();
          ctx.moveTo(cellX + halfW, cellY);
          ctx.lineTo(cellX + halfW, cellY + cellHeight - 1);
          ctx.stroke();

          // Bid Volume (Left half)
          ctx.font = isSellImbalance ? "bold 10px JetBrains Mono, monospace" : "10px JetBrains Mono, monospace";
          ctx.fillStyle = isSellImbalance ? "#fca5a5" : "#94a3b8";
          ctx.textAlign = "right";
          ctx.fillText(bidVal.toString(), cellX + halfW - 6, cellY + cellHeight / 2 + 3);

          // Ask Volume (Right half)
          ctx.font = isBuyImbalance ? "bold 10px JetBrains Mono, monospace" : "10px JetBrains Mono, monospace";
          ctx.fillStyle = isBuyImbalance ? "#6ee7b7" : "#cbd5e1";
          ctx.textAlign = "left";
          ctx.fillText(askVal.toString(), cellX + halfW + 6, cellY + cellHeight / 2 + 3);
        } else if (renderMode === "delta") {
          // Net Delta Mode
          const deltaPct = totalVal > 0 ? deltaVal / totalVal : 0;
          const barFillW = Math.min(halfW, Math.abs(deltaPct) * halfW);

          if (deltaVal >= 0) {
            ctx.fillStyle = "rgba(16, 185, 129, 0.4)";
            ctx.fillRect(cellX + halfW, cellY, barFillW, cellHeight - 1);
          } else {
            ctx.fillStyle = "rgba(244, 63, 94, 0.4)";
            ctx.fillRect(cellX + halfW - barFillW, cellY, barFillW, cellHeight - 1);
          }

          ctx.font = "bold 10px JetBrains Mono, monospace";
          ctx.fillStyle = deltaVal >= 0 ? "#34d399" : "#fb7185";
          ctx.textAlign = "center";
          ctx.fillText(`${deltaVal > 0 ? "+" : ""}${deltaVal}`, cellX + halfW, cellY + cellHeight / 2 + 3);
        } else {
          // Volume Profile Mode
          const maxVolInBar = Math.max(...clusterList.map((c) => c.total_vol ?? (c.bid_vol ?? 0) + (c.ask_vol ?? 0)), 1);
          const barW = (totalVal / maxVolInBar) * (cellW - 8);

          ctx.fillStyle = isPoc ? "rgba(245, 158, 11, 0.35)" : "rgba(99, 102, 241, 0.25)";
          ctx.fillRect(cellX + 4, cellY, barW, cellHeight - 1);

          ctx.font = "10px JetBrains Mono, monospace";
          ctx.fillStyle = isPoc ? "#fcd34d" : "#e2e8f0";
          ctx.textAlign = "left";
          ctx.fillText(`${totalVal} (${cluster.price.toFixed(1)})`, cellX + 8, cellY + cellHeight / 2 + 3);
        }

        // POC Gold Outline
        if (isPoc) {
          ctx.strokeStyle = "#f59e0b";
          ctx.lineWidth = 1.5;
          ctx.strokeRect(cellX, cellY, cellW, cellHeight - 1);

          // Extend POC Ray to right edge if toggled and latest bar
          if (showPocRays && barIdx === bars.length - 1) {
            ctx.strokeStyle = "rgba(245, 158, 11, 0.75)";
            ctx.lineWidth = 1;
            ctx.setLineDash([4, 2]);
            ctx.beginPath();
            ctx.moveTo(cellX + cellW, cellY + cellHeight / 2);
            ctx.lineTo(width - 70, cellY + cellHeight / 2);
            ctx.stroke();
            ctx.setLineDash([]);
          }
        } else {
          ctx.strokeStyle = "rgba(30, 41, 59, 0.5)";
          ctx.lineWidth = 0.5;
          ctx.strokeRect(cellX, cellY, cellW, cellHeight - 1);
        }
      });

      // Bottom Bar Metrics Strip (Delta, Volume, Time)
      const footerY = height - 52;
      ctx.fillStyle = "rgba(7, 11, 18, 0.95)";
      ctx.fillRect(barX + 2, footerY, barWidth - 4, 46);
      ctx.strokeStyle = "rgba(30, 41, 59, 0.8)";
      ctx.strokeRect(barX + 2, footerY, barWidth - 4, 46);

      // Delta
      const deltaColor = bar.delta >= 0 ? "#10b981" : "#f43f5e";
      ctx.font = "bold 11px JetBrains Mono, monospace";
      ctx.fillStyle = deltaColor;
      ctx.textAlign = "center";
      ctx.fillText(`Δ ${bar.delta > 0 ? "+" : ""}${bar.delta}`, barCenter, footerY + 14);

      // Total Volume
      ctx.font = "9px JetBrains Mono, monospace";
      ctx.fillStyle = "#94a3b8";
      ctx.fillText(`Vol: ${bar.volume.toLocaleString()}`, barCenter, footerY + 28);

      // Time
      const barTs = bar.timestamp_utc || bar.open_time_utc || Date.now();
      const timeStr = new Date(barTs).toLocaleTimeString([], {
        hour: "2-digit",
        minute: "2-digit",
      });
      ctx.fillStyle = "#64748b";
      ctx.fillText(timeStr, barCenter, footerY + 41);
    });

    // 3. Crosshair HUD Lines & Pinned Axis Badges
    if (hoverInfo) {
      const { screenX, screenY, price } = hoverInfo;

      ctx.strokeStyle = "rgba(148, 163, 184, 0.4)";
      ctx.lineWidth = 1;
      ctx.setLineDash([3, 3]);

      // Vertical line
      ctx.beginPath();
      ctx.moveTo(screenX, 0);
      ctx.lineTo(screenX, height - 52);
      ctx.stroke();

      // Horizontal line
      ctx.beginPath();
      ctx.moveTo(0, screenY);
      ctx.lineTo(width - 70, screenY);
      ctx.stroke();
      ctx.setLineDash([]);

      // Pinned Right Price Pill
      ctx.fillStyle = "#6366f1";
      ctx.fillRect(width - 70, screenY - 10, 70, 20);
      ctx.fillStyle = "#ffffff";
      ctx.font = "bold 10px JetBrains Mono, monospace";
      ctx.textAlign = "center";
      ctx.fillText(price.toFixed(2), width - 35, screenY + 4);
    }

    // 4. Right-Hand Pinned Price Scale Axis Strip
    ctx.fillStyle = "#070b12";
    ctx.fillRect(width - 70, 0, 70, height);
    ctx.strokeStyle = "#1e293b";
    ctx.beginPath();
    ctx.moveTo(width - 70, 0);
    ctx.lineTo(width - 70, height);
    ctx.stroke();

    // Re-draw scale numbers over pinned strip
    ctx.fillStyle = "#94a3b8";
    ctx.font = "10px JetBrains Mono, monospace";
    ctx.textAlign = "right";
    for (let p = firstGridPrice; p <= maxVisiblePrice; p += gridPriceStep) {
      const y = priceToY(p);
      if (y > 10 && y < height - 60) {
        ctx.fillText(p.toFixed(2), width - 8, y + 3);
      }
    }
  }, [
    bars,
    symbol,
    viewport,
    tickSize,
    hoverInfo,
    renderMode,
    showValueArea,
    showPocRays,
    showImbalances,
  ]);

  // Handle Resize and High-DPI Canvas Rendering
  useEffect(() => {
    const handleResize = () => {
      const canvas = canvasRef.current;
      const container = containerRef.current;
      if (!canvas || !container) return;

      const dpr = window.devicePixelRatio || 1;
      const width = container.clientWidth || 800;
      const height = container.clientHeight || 520;

      canvas.width = width * dpr;
      canvas.height = height * dpr;
      canvas.style.width = `${width}px`;
      canvas.style.height = `${height}px`;

      const ctx = canvas.getContext("2d");
      if (ctx) {
        ctx.resetTransform();
        ctx.scale(dpr, dpr);
      }
      render();
    };

    handleResize();
    window.addEventListener("resize", handleResize);
    return () => window.removeEventListener("resize", handleResize);
  }, [render]);

  useEffect(() => {
    render();
  }, [render]);

  // Mouse Interactivity (Pan & Zoom)
  const handleWheel = (e: React.WheelEvent) => {
    e.preventDefault();
    const zoomFactor = e.deltaY < 0 ? 1.08 : 0.92;

    setViewport((prev) => ({
      ...prev,
      barWidth: Math.max(90, Math.min(300, prev.barWidth * (e.shiftKey ? zoomFactor : 1))),
      cellHeight: Math.max(14, Math.min(48, prev.cellHeight * (!e.shiftKey ? zoomFactor : 1))),
    }));
  };

  const handleMouseDown = (e: React.MouseEvent) => {
    if (e.button !== 0) return;
    setIsDragging(true);
    dragStartRef.current = {
      x: e.clientX,
      y: e.clientY,
      panX: viewport.panX,
      panY: viewport.panY,
    };
  };

  const handleMouseMove = (e: React.MouseEvent) => {
    const rect = canvasRef.current?.getBoundingClientRect();
    if (!rect) return;
    const mouseX = e.clientX - rect.left;
    const mouseY = e.clientY - rect.top;

    if (isDragging) {
      const deltaX = e.clientX - dragStartRef.current.x;
      const deltaY = e.clientY - dragStartRef.current.y;
      setViewport((prev) => ({
        ...prev,
        panX: dragStartRef.current.panX + deltaX,
        panY: dragStartRef.current.panY + deltaY,
      }));
    } else {
      const { barWidth, cellHeight, panX, panY } = viewport;
      const allPrices = bars.flatMap((b) =>
        (Array.isArray(b.clusters) ? b.clusters : Object.values(b.clusters)).map((c) => c.price)
      );
      const refPrice = allPrices.length > 0 ? (Math.max(...allPrices) + Math.min(...allPrices)) / 2 : 2500.0;
      const hoveredPrice = refPrice - ((mouseY - panY) / cellHeight) * tickSize;
      const hoveredBarIdx = Math.floor((mouseX - panX) / barWidth);

      if (hoveredBarIdx >= 0 && hoveredBarIdx < bars.length) {
        const targetBar = bars[hoveredBarIdx];
        const clusterList: PriceCluster[] = Array.isArray(targetBar.clusters)
          ? targetBar.clusters
          : Object.values(targetBar.clusters);
        const closestCluster = clusterList.length > 0
          ? clusterList.reduce((prev, curr) =>
              Math.abs(curr.price - hoveredPrice) < Math.abs(prev.price - hoveredPrice) ? curr : prev
            , clusterList[0])
          : undefined;

        setHoverInfo({
          barIndex: hoveredBarIdx,
          bar: targetBar,
          cluster: closestCluster,
          price: Math.round(hoveredPrice / tickSize) * tickSize,
          screenX: mouseX,
          screenY: mouseY,
        });
      } else {
        setHoverInfo(null);
      }
    }
  };

  const handleMouseUp = () => {
    setIsDragging(false);
  };

  return (
    <div className="flex flex-col gap-2.5 w-full select-none">
      {/* Institutional Toolbar Ribbon */}
      <div className="flex flex-wrap items-center justify-between gap-3 bg-obsidian-900 border border-slate-800/90 rounded-xl px-4 py-2.5 shadow-xl backdrop-blur">
        {/* Left: Mode Selectors */}
        <div className="flex items-center gap-2">
          <div className="flex rounded-lg bg-obsidian-950 p-0.5 border border-slate-800 text-xs font-mono">
            <button
              onClick={() => setRenderMode("bidxask")}
              className={`px-3 py-1 rounded-md font-semibold transition-all ${
                renderMode === "bidxask"
                  ? "bg-indigo-600 text-white shadow-glow-indigo"
                  : "text-slate-400 hover:text-slate-200"
              }`}
            >
              Bid × Ask
            </button>
            <button
              onClick={() => setRenderMode("delta")}
              className={`px-3 py-1 rounded-md font-semibold transition-all ${
                renderMode === "delta"
                  ? "bg-indigo-600 text-white shadow-glow-indigo"
                  : "text-slate-400 hover:text-slate-200"
              }`}
            >
              Delta Profile
            </button>
            <button
              onClick={() => setRenderMode("volume")}
              className={`px-3 py-1 rounded-md font-semibold transition-all ${
                renderMode === "volume"
                  ? "bg-indigo-600 text-white shadow-glow-indigo"
                  : "text-slate-400 hover:text-slate-200"
              }`}
            >
              Volume Profile
            </button>
          </div>

          <div className="h-4 w-px bg-slate-800" />

          {/* Imbalance Ratio */}
          <div className="flex items-center gap-1.5 text-xs font-mono text-slate-400">
            <span>Imb:</span>
            <select
              value={imbalanceRatio}
              onChange={(e) => setImbalanceRatio(parseFloat(e.target.value))}
              className="bg-obsidian-950 border border-slate-800 text-slate-200 text-xs rounded px-2 py-1 focus:outline-none focus:border-indigo-500"
            >
              <option value="2.5">2.5 : 1 (Sensitive)</option>
              <option value="3.0">3.0 : 1 (Standard)</option>
              <option value="4.0">4.0 : 1 (Strict)</option>
            </select>
          </div>
        </div>

        {/* Center: Overlays Toggles */}
        <div className="flex items-center gap-2 text-xs font-mono">
          <button
            onClick={() => setShowValueArea(!showValueArea)}
            className={`px-2.5 py-1 rounded border text-[11px] font-semibold transition-all ${
              showValueArea
                ? "bg-indigo-500/15 border-indigo-500/40 text-indigo-300"
                : "bg-obsidian-950 border-slate-800 text-slate-500"
            }`}
          >
            VA 70%
          </button>
          <button
            onClick={() => setShowPocRays(!showPocRays)}
            className={`px-2.5 py-1 rounded border text-[11px] font-semibold transition-all ${
              showPocRays
                ? "bg-amber-500/15 border-amber-500/40 text-amber-300"
                : "bg-obsidian-950 border-slate-800 text-slate-500"
            }`}
          >
            POC Rays
          </button>
          <button
            onClick={() => setShowImbalances(!showImbalances)}
            className={`px-2.5 py-1 rounded border text-[11px] font-semibold transition-all ${
              showImbalances
                ? "bg-emerald-500/15 border-emerald-500/40 text-emerald-300"
                : "bg-obsidian-950 border-slate-800 text-slate-500"
            }`}
          >
            Imbalances
          </button>
        </div>

        {/* Right: Zoom & Fit Controls */}
        <div className="flex items-center gap-1.5 text-xs font-mono">
          <button
            onClick={() => setViewport((prev) => ({ ...prev, barWidth: Math.min(300, prev.barWidth + 20) }))}
            className="w-7 h-7 rounded bg-obsidian-950 border border-slate-800 hover:border-slate-700 text-slate-300 flex items-center justify-center font-bold"
            title="Widen Bars"
          >
            +
          </button>
          <button
            onClick={() => setViewport((prev) => ({ ...prev, barWidth: Math.max(90, prev.barWidth - 20) }))}
            className="w-7 h-7 rounded bg-obsidian-950 border border-slate-800 hover:border-slate-700 text-slate-300 flex items-center justify-center font-bold"
            title="Narrow Bars"
          >
            -
          </button>
          <button
            onClick={autoFitView}
            className="px-2.5 py-1 rounded bg-obsidian-950 border border-slate-800 hover:border-indigo-500 text-slate-300 text-[11px]"
            title="Reset View"
          >
            Auto Fit
          </button>
        </div>
      </div>

      {/* Main Interactive Canvas Surface */}
      <div
        ref={containerRef}
        className="relative w-full h-[540px] bg-obsidian-950 border border-slate-800/90 rounded-xl overflow-hidden shadow-2xl cursor-crosshair"
      >
        <canvas
          ref={canvasRef}
          onWheel={handleWheel}
          onMouseDown={handleMouseDown}
          onMouseMove={handleMouseMove}
          onMouseUp={handleMouseUp}
          onMouseLeave={handleMouseUp}
          className="absolute inset-0 block w-full h-full"
        />

        {/* Active Crosshair HUD Bar (Top Center) */}
        {hoverInfo && (
          <div className="pointer-events-none absolute top-3 left-4 right-20 z-20 flex items-center justify-between bg-obsidian-900/90 border border-slate-800 rounded-lg px-4 py-1.5 text-xs font-mono backdrop-blur shadow-lg">
            <div className="flex items-center gap-3">
              <span className="text-slate-400">Price:</span>
              <strong className="text-white text-sm">₹{hoverInfo.price.toFixed(2)}</strong>
              {hoverInfo.cluster && (
                <>
                  <span className="text-slate-600">|</span>
                  <span className="text-slate-400">Bid:</span>
                  <span className="text-rose-400 font-semibold">{hoverInfo.cluster.bid_vol ?? hoverInfo.cluster.bid_volume ?? 0}</span>
                  <span className="text-slate-400">Ask:</span>
                  <span className="text-emerald-400 font-semibold">{hoverInfo.cluster.ask_vol ?? hoverInfo.cluster.ask_volume ?? 0}</span>
                  <span className="text-slate-600">|</span>
                  <span className="text-slate-400">Delta:</span>
                  <span className={hoverInfo.cluster.delta >= 0 ? "text-emerald-400 font-bold" : "text-rose-400 font-bold"}>
                    {hoverInfo.cluster.delta > 0 ? "+" : ""}{hoverInfo.cluster.delta}
                  </span>
                </>
              )}
            </div>

            <div className="flex items-center gap-3 text-[11px]">
              <span className="text-slate-500">Bar Vol:</span>
              <span className="text-slate-300 font-semibold">{hoverInfo.bar.volume.toLocaleString()}</span>
              <span className="text-slate-500">Bar Delta:</span>
              <span className={hoverInfo.bar.delta >= 0 ? "text-emerald-400 font-semibold" : "text-rose-400 font-semibold"}>
                {hoverInfo.bar.delta > 0 ? "+" : ""}{hoverInfo.bar.delta}
              </span>
            </div>
          </div>
        )}
      </div>

      {/* Footer Hotkey & Navigation Hints */}
      <div className="flex items-center justify-between text-[11px] font-mono text-slate-500 px-2">
        <div className="flex items-center gap-3">
          <span>💡 <strong className="text-slate-400">Drag</strong> to pan</span>
          <span>• <strong className="text-slate-400">Wheel</strong> to zoom price rows</span>
          <span>• <strong className="text-slate-400">Shift + Wheel</strong> to zoom candle width</span>
        </div>
        <div className="flex items-center gap-2">
          <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
          <span className="text-slate-400">{symbol} • {timeframe} • Tick: {tickSize}</span>
        </div>
      </div>
    </div>
  );
};
