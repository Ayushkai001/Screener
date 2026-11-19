import React, { useCallback, useEffect, useRef, useState } from "react";
import { DataQuality, FootprintBar, PriceCluster } from "../types/domain";

interface CanvasFootprintChartProps {
  bars: FootprintBar[];
  symbol: string;
  timeframe: string;
  tickSize?: number;
}

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
  useEffect(() => {
    if (!bars || bars.length === 0 || !containerRef.current) return;
    const width = containerRef.current.clientWidth || 800;
    const height = containerRef.current.clientHeight || 500;

    // Center on the latest bar's POC price
    const latestBar = bars[bars.length - 1];
    const initialPanX = width - bars.length * viewport.barWidth - 100;
    const initialPanY = height / 2;

    setViewport((prev) => ({
      ...prev,
      panX: Math.min(20, initialPanX),
      panY: initialPanY,
    }));
  }, [bars, symbol]);

  // Main Canvas Rendering Loop
  const render = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const dpr = window.devicePixelRatio || 1;
    const width = canvas.width / dpr;
    const height = canvas.height / dpr;

    // Clear background
    ctx.fillStyle = "#020617"; // slate-950
    ctx.fillRect(0, 0, width, height);

    if (!bars || bars.length === 0) {
      ctx.fillStyle = "#64748b";
      ctx.font = "14px Inter, sans-serif";
      ctx.textAlign = "center";
      ctx.fillText("No footprint data loaded", width / 2, height / 2);
      return;
    }

    const { barWidth, cellHeight, panX, panY } = viewport;

    // Reference price for vertical coordinates (midpoint of all bars)
    const allPrices = bars.flatMap((b) => b.clusters.map((c) => c.price));
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

    ctx.strokeStyle = "rgba(30, 41, 59, 0.5)"; // slate-800
    ctx.lineWidth = 1;
    ctx.fillStyle = "#64748b"; // slate-500
    ctx.font = "10px monospace";
    ctx.textAlign = "right";

    const firstGridPrice = Math.floor(minVisiblePrice / gridPriceStep) * gridPriceStep;
    for (let p = firstGridPrice; p <= maxVisiblePrice; p += gridPriceStep) {
      const y = priceToY(p);
      ctx.beginPath();
      ctx.moveTo(0, y);
      ctx.lineTo(width - 65, y);
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
      ctx.strokeStyle = isBullish ? "rgba(16, 185, 129, 0.4)" : "rgba(244, 63, 94, 0.4)";
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.moveTo(barCenter, highY);
      ctx.lineTo(barCenter, lowY);
      ctx.stroke();

      // Draw 70% Value Area Box Bracket
      const vahY = priceToY(bar.value_area_high);
      const valY = priceToY(bar.value_area_low);
      ctx.fillStyle = "rgba(99, 102, 241, 0.05)"; // subtle indigo tint
      ctx.fillRect(barX + 2, vahY, barWidth - 4, Math.abs(valY - vahY));
      ctx.strokeStyle = "rgba(99, 102, 241, 0.35)";
      ctx.setLineDash([3, 3]);
      ctx.strokeRect(barX + 2, vahY, barWidth - 4, Math.abs(valY - vahY));
      ctx.setLineDash([]); // Reset dashed lines

      // Sort clusters descending by price (top to bottom)
      const sortedClusters = [...bar.clusters].sort((a, b) => b.price - a.price);

      sortedClusters.forEach((cluster) => {
        const cellY = priceToY(cluster.price) - cellHeight / 2;
        const cellW = barWidth - 8;
        const cellX = barX + 4;
        const halfW = cellW / 2;

        const isPoc = Math.abs(cluster.price - bar.poc_price) < 1e-4;

        // Base cell background
        ctx.fillStyle = isPoc ? "rgba(245, 158, 11, 0.15)" : "rgba(15, 23, 42, 0.8)";
        ctx.fillRect(cellX, cellY, cellW, cellHeight - 1);

        // Highlight Diagonal Imbalances:
        // Buy Imbalance: Ask volume > 3x lower-bid -> right cell highlight
        if (cluster.is_buy_imbalance) {
          ctx.fillStyle = "rgba(16, 185, 129, 0.35)";
          ctx.fillRect(cellX + halfW, cellY, halfW, cellHeight - 1);
        }

        // Sell Imbalance: Bid volume > 3x higher-ask -> left cell highlight
        if (cluster.is_sell_imbalance) {
          ctx.fillStyle = "rgba(244, 63, 94, 0.35)";
          ctx.fillRect(cellX, cellY, halfW, cellHeight - 1);
        }

        // POC Gold Outline
        if (isPoc) {
          ctx.strokeStyle = "#f59e0b"; // amber-500
          ctx.lineWidth = 1.5;
          ctx.strokeRect(cellX, cellY, cellW, cellHeight - 1);
        } else {
          ctx.strokeStyle = "rgba(30, 41, 59, 0.6)";
          ctx.lineWidth = 0.5;
          ctx.strokeRect(cellX, cellY, cellW, cellHeight - 1);
        }

        // Render Bid Volume (Left half)
        ctx.font = cluster.is_sell_imbalance ? "bold 10px monospace" : "10px monospace";
        ctx.fillStyle = cluster.is_sell_imbalance ? "#fda4af" : "#94a3b8";
        ctx.textAlign = "right";
        ctx.fillText(cluster.bid_volume.toString(), cellX + halfW - 6, cellY + cellHeight / 2 + 3);

        // Center Divider Line
        ctx.strokeStyle = "rgba(51, 65, 85, 0.5)";
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.moveTo(cellX + halfW, cellY);
        ctx.lineTo(cellX + halfW, cellY + cellHeight - 1);
        ctx.stroke();

        // Render Ask Volume (Right half)
        ctx.font = cluster.is_buy_imbalance ? "bold 10px monospace" : "10px monospace";
        ctx.fillStyle = cluster.is_buy_imbalance ? "#6ee7b7" : "#cbd5e1";
        ctx.textAlign = "left";
        ctx.fillText(cluster.ask_volume.toString(), cellX + halfW + 6, cellY + cellHeight / 2 + 3);
      });

      // Bottom Bar Metrics Strip (Delta, Volume, Time)
      const footerY = height - 45;
      ctx.fillStyle = "rgba(15, 23, 42, 0.9)";
      ctx.fillRect(barX + 2, footerY, barWidth - 4, 40);
      ctx.strokeStyle = "rgba(51, 65, 85, 0.6)";
      ctx.strokeRect(barX + 2, footerY, barWidth - 4, 40);

      // Delta
      const deltaColor = bar.delta >= 0 ? "#10b981" : "#f43f5e";
      ctx.font = "bold 11px monospace";
      ctx.fillStyle = deltaColor;
      ctx.textAlign = "center";
      ctx.fillText(`Δ ${bar.delta > 0 ? "+" : ""}${bar.delta}`, barCenter, footerY + 14);

      // Total Volume
      ctx.font = "9px monospace";
      ctx.fillStyle = "#94a3b8";
      ctx.fillText(`Vol: ${bar.volume}`, barCenter, footerY + 26);

      // Time
      const timeStr = new Date(bar.timestamp_utc).toLocaleTimeString([], {
        hour: "2-digit",
        minute: "2-digit",
      });
      ctx.fillStyle = "#64748b";
      ctx.fillText(timeStr, barCenter, footerY + 37);
    });

    // 3. Right-Hand Pinned Price Scale Axis Strip
    ctx.fillStyle = "rgba(15, 23, 42, 0.95)";
    ctx.fillRect(width - 65, 0, 65, height);
    ctx.strokeStyle = "#334155";
    ctx.beginPath();
    ctx.moveTo(width - 65, 0);
    ctx.lineTo(width - 65, height);
    ctx.stroke();

    // Re-draw scale numbers over pinned strip
    ctx.fillStyle = "#cbd5e1";
    ctx.font = "10px monospace";
    ctx.textAlign = "right";
    for (let p = firstGridPrice; p <= maxVisiblePrice; p += gridPriceStep) {
      const y = priceToY(p);
      ctx.fillText(p.toFixed(2), width - 8, y + 3);
    }

    // 4. Interactive Crosshair Lines
    if (hoverInfo) {
      ctx.strokeStyle = "rgba(148, 163, 184, 0.4)";
      ctx.lineWidth = 1;
      ctx.setLineDash([4, 4]);

      // Horizontal cursor price line
      ctx.beginPath();
      ctx.moveTo(0, hoverInfo.screenY);
      ctx.lineTo(width - 65, hoverInfo.screenY);
      ctx.stroke();

      // Vertical cursor bar line
      ctx.beginPath();
      ctx.moveTo(hoverInfo.screenX, 0);
      ctx.lineTo(hoverInfo.screenX, height - 45);
      ctx.stroke();
      ctx.setLineDash([]);

      // Pinned Price Tag on Right Axis
      ctx.fillStyle = "#4f46e5"; // Indigo banner
      ctx.fillRect(width - 64, hoverInfo.screenY - 9, 63, 18);
      ctx.fillStyle = "#ffffff";
      ctx.font = "bold 10px monospace";
      ctx.textAlign = "right";
      ctx.fillText(hoverInfo.price.toFixed(2), width - 8, hoverInfo.screenY + 3);
    }
  }, [bars, viewport, tickSize, hoverInfo]);

  // Handle Resize & Canvas Pixel Ratio
  useEffect(() => {
    const handleResize = () => {
      const canvas = canvasRef.current;
      const container = containerRef.current;
      if (!canvas || !container) return;

      const dpr = window.devicePixelRatio || 1;
      const w = container.clientWidth;
      const h = container.clientHeight;

      canvas.width = w * dpr;
      canvas.height = h * dpr;
      canvas.style.width = `${w}px`;
      canvas.style.height = `${h}px`;

      const ctx = canvas.getContext("2d");
      if (ctx) {
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

  // Mouse Interaction: Panning & Hover
  const handleMouseDown = (e: React.MouseEvent) => {
    setIsDragging(true);
    dragStartRef.current = {
      x: e.clientX,
      y: e.clientY,
      panX: viewport.panX,
      panY: viewport.panY,
    };
  };

  const handleMouseMove = (e: React.MouseEvent) => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const rect = canvas.getBoundingClientRect();
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
      // Hover hit-testing
      const { barWidth, cellHeight, panX, panY } = viewport;
      const allPrices = bars.flatMap((b) => b.clusters.map((c) => c.price));
      const refPrice = allPrices.length > 0 ? (Math.max(...allPrices) + Math.min(...allPrices)) / 2 : 2500.0;
      const hoveredPrice = refPrice - ((mouseY - panY) / cellHeight) * tickSize;
      const hoveredBarIdx = Math.floor((mouseX - panX) / barWidth);

      if (hoveredBarIdx >= 0 && hoveredBarIdx < bars.length) {
        const targetBar = bars[hoveredBarIdx];
        // Find closest cluster
        const closestCluster = targetBar.clusters.reduce((prev, curr) =>
          Math.abs(curr.price - hoveredPrice) < Math.abs(prev.price - hoveredPrice) ? curr : prev
        , targetBar.clusters[0]);

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

  // Zooming on Wheel
  const handleWheel = (e: React.WheelEvent) => {
    e.preventDefault();
    const zoomFactor = e.deltaY < 0 ? 1.08 : 0.92;

    if (e.shiftKey) {
      // Horizontal pan with shift-wheel
      setViewport((prev) => ({ ...prev, panX: prev.panX - e.deltaY }));
    } else {
      // Zoom both cell height and bar width
      setViewport((prev) => ({
        ...prev,
        cellHeight: Math.max(12, Math.min(50, prev.cellHeight * zoomFactor)),
        barWidth: Math.max(80, Math.min(260, prev.barWidth * zoomFactor)),
      }));
    }
  };

  const resetView = () => {
    if (!containerRef.current || bars.length === 0) return;
    const w = containerRef.current.clientWidth;
    const h = containerRef.current.clientHeight;
    setViewport({
      barWidth: 140,
      cellHeight: 22,
      panX: w - bars.length * 140 - 100,
      panY: h / 2,
    });
  };

  return (
    <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-2xl flex flex-col gap-4">
      {/* Top Header & Toolbar */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between pb-3 border-b border-slate-800 gap-2">
        <div>
          <h3 className="text-lg font-bold text-slate-100 flex items-center gap-2">
            <span className="w-2.5 h-2.5 rounded-full bg-cyan-400 animate-pulse"></span>
            Hardware-Accelerated Canvas Footprint (Bid × Ask)
          </h3>
          <p className="text-xs text-slate-400">
            {symbol} • {timeframe} • 60 FPS Pan & Zoom • 3:1 Diagonal Imbalances & POC
          </p>
        </div>

        {/* Controls & Badges */}
        <div className="flex items-center gap-3 text-xs">
          <div className="flex items-center gap-2 text-[11px] text-slate-400">
            <span className="flex items-center gap-1">
              <span className="w-2 h-2 rounded-sm bg-emerald-500/60"></span> Buy Imbalance
            </span>
            <span className="flex items-center gap-1">
              <span className="w-2 h-2 rounded-sm bg-rose-500/60"></span> Sell Imbalance
            </span>
            <span className="flex items-center gap-1">
              <span className="w-2 h-2 rounded-sm border border-amber-400 bg-amber-500/30"></span> POC
            </span>
          </div>

          <button
            onClick={resetView}
            className="px-2.5 py-1 bg-slate-800 hover:bg-slate-700 text-slate-200 rounded border border-slate-700 font-mono text-[11px] transition-colors"
          >
            Reset View
          </button>
        </div>
      </div>

      {/* Canvas Viewport Container */}
      <div
        ref={containerRef}
        onWheel={handleWheel}
        className="relative w-full h-[520px] rounded-lg overflow-hidden border border-slate-800 select-none bg-slate-950 cursor-crosshair"
      >
        <canvas
          ref={canvasRef}
          onMouseDown={handleMouseDown}
          onMouseMove={handleMouseMove}
          onMouseUp={handleMouseUp}
          onMouseLeave={handleMouseUp}
          className="absolute inset-0 block"
        />

        {/* Floating Tooltip Inspector */}
        {hoverInfo && hoverInfo.cluster && (
          <div
            style={{
              left: Math.min(hoverInfo.screenX + 15, (containerRef.current?.clientWidth || 800) - 220),
              top: Math.max(10, hoverInfo.screenY - 80),
            }}
            className="pointer-events-none absolute z-20 bg-slate-900/95 border border-indigo-500/60 rounded-lg p-2.5 text-[11px] font-mono shadow-2xl backdrop-blur flex flex-col gap-1 min-w-[200px]"
          >
            <div className="text-slate-300 font-bold border-b border-slate-800 pb-1 flex justify-between">
              <span>Price: ₹{hoverInfo.cluster.price.toFixed(2)}</span>
              <span className={hoverInfo.cluster.delta >= 0 ? "text-emerald-400" : "text-rose-400"}>
                Δ {hoverInfo.cluster.delta}
              </span>
            </div>
            <div className="flex justify-between text-slate-400">
              <span>Bid Volume:</span>
              <span className="text-rose-300 font-semibold">{hoverInfo.cluster.bid_volume}</span>
            </div>
            <div className="flex justify-between text-slate-400">
              <span>Ask Volume:</span>
              <span className="text-emerald-300 font-semibold">{hoverInfo.cluster.ask_volume}</span>
            </div>
            <div className="flex justify-between text-slate-400">
              <span>Total Cluster Vol:</span>
              <span className="text-slate-200">{hoverInfo.cluster.total_volume}</span>
            </div>
            {hoverInfo.cluster.is_buy_imbalance && (
              <div className="mt-0.5 text-center px-1.5 py-0.5 bg-emerald-500/20 text-emerald-300 border border-emerald-500/40 rounded text-[10px] font-bold">
                ⚡ 3:1 Buy Imbalance
              </div>
            )}
            {hoverInfo.cluster.is_sell_imbalance && (
              <div className="mt-0.5 text-center px-1.5 py-0.5 bg-rose-500/20 text-rose-300 border border-rose-500/40 rounded text-[10px] font-bold">
                ⚡ 3:1 Sell Imbalance
              </div>
            )}
          </div>
        )}
      </div>

      <div className="text-[11px] text-slate-500 font-mono flex items-center justify-between">
        <span>💡 Drag to pan horizontally and vertically • Scroll wheel to zoom price / bar scale</span>
        <span>Resolution: 60 FPS Canvas</span>
      </div>
    </div>
  );
};
