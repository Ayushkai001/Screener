import { useEffect, useRef, useState, useCallback } from "react";
import { FootprintBar } from "../types/domain";

export interface LiveMarketTick {
  type: "MARKET_TICK";
  instrument_id: string;
  price: number;
  quantity: number;
  aggressor: "BUY" | "SELL" | "UNKNOWN";
  timestamp_utc: number;
}

export interface LiveExecutionFill {
  type: "EXECUTION_FILL";
  fill_id: string;
  order_id: string;
  price: number;
  quantity: number;
  timestamp_utc: number;
}

interface UseMarketStreamOptions {
  url?: string;
  instrumentId: string;
  accountId?: string;
  onTick?: (tick: LiveMarketTick) => void;
  onFootprintUpdate?: (bar: FootprintBar) => void;
  onExecutionFill?: (fill: LiveExecutionFill) => void;
}

export const useMarketStream = ({
  url = "ws://localhost:8000/ws/market/stream",
  instrumentId,
  accountId = "PAPER_ACC_01",
  onTick,
  onFootprintUpdate,
  onExecutionFill,
}: UseMarketStreamOptions) => {
  const [isConnected, setIsConnected] = useState(false);
  const [latencyMs, setLatencyMs] = useState(12);
  const [tickCount, setTickCount] = useState(0);

  const socketRef = useRef<WebSocket | null>(null);
  const pingTimestampRef = useRef<number>(0);

  // Keep latest callbacks in refs to avoid reconnecting on every render
  const onTickRef = useRef(onTick);
  const onFootprintUpdateRef = useRef(onFootprintUpdate);
  const onExecutionFillRef = useRef(onExecutionFill);

  useEffect(() => {
    onTickRef.current = onTick;
    onFootprintUpdateRef.current = onFootprintUpdate;
    onExecutionFillRef.current = onExecutionFill;
  });

  // Connect to WebSocket
  useEffect(() => {
    let ws: WebSocket;
    try {
      ws = new WebSocket(url);
      socketRef.current = ws;

      ws.onopen = () => {
        setIsConnected(true);

        // Subscribe to relevant channels
        ws.send(JSON.stringify({ action: "subscribe", channel: `candles:${instrumentId}` }));
        ws.send(JSON.stringify({ action: "subscribe", channel: `footprint:${instrumentId}` }));
        ws.send(JSON.stringify({ action: "subscribe", channel: `executions:${accountId}` }));
      };

      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);

          if (data.action === "pong") {
            const rtt = Date.now() - pingTimestampRef.current;
            setLatencyMs(rtt);
          } else if (data.type === "MARKET_TICK") {
            setTickCount((prev) => prev + 1);
            if (onTickRef.current) onTickRef.current(data);
          } else if (data.type === "FOOTPRINT_UPDATE") {
            if (onFootprintUpdateRef.current) onFootprintUpdateRef.current(data.bar);
          } else if (data.type === "EXECUTION_FILL") {
            if (onExecutionFillRef.current) onExecutionFillRef.current(data);
          }
        } catch {
          // Ignore non-json frames
        }
      };

      ws.onclose = () => {
        setIsConnected(false);
      };

      ws.onerror = () => {
        setIsConnected(false);
      };
    } catch {
      setIsConnected(false);
    }

    // Ping interval for heartbeat & latency calculation
    const pingInterval = setInterval(() => {
      if (socketRef.current && socketRef.current.readyState === WebSocket.OPEN) {
        pingTimestampRef.current = Date.now();
        socketRef.current.send(JSON.stringify({ action: "ping" }));
      }
    }, 5000);

    return () => {
      clearInterval(pingInterval);
      if (socketRef.current) {
        socketRef.current.close();
      }
    };
  }, [url, instrumentId, accountId]);

  return {
    isConnected,
    latencyMs,
    tickCount,
  };
};
