import React, { useCallback, useRef, useState } from "react";
import { DataQuality } from "../types/domain";
import {
  ActionKind,
  ComparisonOperator,
  ConditionGroup,
  ConditionNode,
  LogicalOp,
  Operand,
  OperandKind,
  StrategyIR,
} from "../types/strategy";

// ---------------------------------------------------------------- Node Data Contracts

export type NodeType =
  | "FEED"
  | "CALCULATION"
  | "CONDITION"
  | "LOGIC_GATE"
  | "RISK"
  | "ACTION";

export interface GraphPort {
  id: string;
  name: string;
  type: "price" | "value" | "boolean" | "trigger" | "risk";
  direction: "input" | "output";
}

export interface GraphNode {
  id: string;
  type: NodeType;
  title: string;
  x: number;
  y: number;
  inputs: GraphPort[];
  outputs: GraphPort[];
  config: Record<string, any>;
}

export interface GraphEdge {
  id: string;
  fromNodeId: string;
  fromPortId: string;
  toNodeId: string;
  toPortId: string;
}

interface StrategyGraphStudioProps {
  onRunBacktest: (strategy: StrategyIR) => void;
  onCompileStrategy: (strategy: StrategyIR) => Promise<{
    highest_required_quality: string;
    required_feeds: string[];
  } | null>;
}

// Default initial nodes forming a complete Breakout & Order Flow Strategy
const INITIAL_NODES: GraphNode[] = [
  {
    id: "node_feed",
    type: "FEED",
    title: "Market Feed",
    x: 40,
    y: 100,
    inputs: [],
    outputs: [{ id: "feed_out", name: "Market Stream", type: "price", direction: "output" }],
    config: { symbol: "RELIANCE", timeframe: "5m", exchange: "NSE" },
  },
  {
    id: "node_ema",
    type: "CALCULATION",
    title: "EMA(20)",
    x: 280,
    y: 60,
    inputs: [{ id: "calc_in", name: "Price In", type: "price", direction: "input" }],
    outputs: [{ id: "calc_out", name: "EMA Value", type: "value", direction: "output" }],
    config: { category: "indicator", name: "ema", period: 20 },
  },
  {
    id: "node_delta",
    type: "CALCULATION",
    title: "Bar Delta",
    x: 280,
    y: 260,
    inputs: [{ id: "calc_in", name: "Feed In", type: "price", direction: "input" }],
    outputs: [{ id: "calc_out", name: "Delta Vol", type: "value", direction: "output" }],
    config: { category: "order_flow", name: "bar_delta" },
  },
  {
    id: "node_cond_ema",
    type: "CONDITION",
    title: "Close > EMA",
    x: 520,
    y: 60,
    inputs: [
      { id: "left_in", name: "Left (Close)", type: "value", direction: "input" },
      { id: "right_in", name: "Right (EMA)", type: "value", direction: "input" },
    ],
    outputs: [{ id: "cond_out", name: "Pass", type: "boolean", direction: "output" }],
    config: { operator: ">", leftKind: "price", leftName: "close" },
  },
  {
    id: "node_cond_delta",
    type: "CONDITION",
    title: "Delta > 0",
    x: 520,
    y: 260,
    inputs: [
      { id: "left_in", name: "Left (Delta)", type: "value", direction: "input" },
      { id: "right_in", name: "Right (Constant)", type: "value", direction: "input" },
    ],
    outputs: [{ id: "cond_out", name: "Pass", type: "boolean", direction: "output" }],
    config: { operator: ">", rightConst: 0 },
  },
  {
    id: "node_gate",
    type: "LOGIC_GATE",
    title: "AND Gate",
    x: 760,
    y: 160,
    inputs: [
      { id: "sig_1", name: "Signal 1", type: "boolean", direction: "input" },
      { id: "sig_2", name: "Signal 2", type: "boolean", direction: "input" },
    ],
    outputs: [{ id: "gate_out", name: "Trigger", type: "trigger", direction: "output" }],
    config: { operator: "AND" },
  },
  {
    id: "node_risk",
    type: "RISK",
    title: "Risk Engine",
    x: 980,
    y: 140,
    inputs: [{ id: "trig_in", name: "Trigger", type: "trigger", direction: "input" }],
    outputs: [{ id: "risk_out", name: "Order Profile", type: "risk", direction: "output" }],
    config: { stopLossPct: 2.0, takeProfitPct: 4.0, sizingPct: 1.0 },
  },
  {
    id: "node_action",
    type: "ACTION",
    title: "Enter Long Action",
    x: 1220,
    y: 140,
    inputs: [{ id: "action_in", name: "Profile", type: "risk", direction: "input" }],
    outputs: [],
    config: { action: "ENTER_LONG", orderType: "MARKET" },
  },
];

const INITIAL_EDGES: GraphEdge[] = [
  { id: "e1", fromNodeId: "node_feed", fromPortId: "feed_out", toNodeId: "node_ema", toPortId: "calc_in" },
  { id: "e2", fromNodeId: "node_feed", fromPortId: "feed_out", toNodeId: "node_delta", toPortId: "calc_in" },
  { id: "e3", fromNodeId: "node_ema", fromPortId: "calc_out", toNodeId: "node_cond_ema", toPortId: "right_in" },
  { id: "e4", fromNodeId: "node_delta", fromPortId: "calc_out", toNodeId: "node_cond_delta", toPortId: "left_in" },
  { id: "e5", fromNodeId: "node_cond_ema", fromPortId: "cond_out", toNodeId: "node_gate", toPortId: "sig_1" },
  { id: "e6", fromNodeId: "node_cond_delta", fromPortId: "cond_out", toNodeId: "node_gate", toPortId: "sig_2" },
  { id: "e7", fromNodeId: "node_gate", fromPortId: "gate_out", toNodeId: "node_risk", toPortId: "trig_in" },
  { id: "e8", fromNodeId: "node_risk", fromPortId: "risk_out", toNodeId: "node_action", toPortId: "action_in" },
];

export const StrategyGraphStudio: React.FC<StrategyGraphStudioProps> = ({
  onRunBacktest,
  onCompileStrategy,
}) => {
  const [nodes, setNodes] = useState<GraphNode[]>(INITIAL_NODES);
  const [edges, setEdges] = useState<GraphEdge[]>(INITIAL_EDGES);

  // Canvas viewport translation & zoom
  const [pan, setPan] = useState({ x: 20, y: 30 });
  const [zoom, setZoom] = useState(0.9);

  // Dragging state
  const [draggingNodeId, setDraggingNodeId] = useState<string | null>(null);
  const [isPanning, setIsPanning] = useState(false);
  const dragRef = useRef<{ startX: number; startY: number; initialNodeX: number; initialNodeY: number }>({
    startX: 0,
    startY: 0,
    initialNodeX: 0,
    initialNodeY: 0,
  });

  // Wiring / Edge connection state
  const [connectingPort, setConnectingPort] = useState<{
    nodeId: string;
    portId: string;
    direction: "input" | "output";
    type: string;
  } | null>(null);
  const [mousePos, setMousePos] = useState({ x: 0, y: 0 });

  // Compilation feedback
  const [compileResult, setCompileResult] = useState<{
    highest_required_quality: string;
    required_feeds: string[];
  } | null>(null);
  const [compiling, setCompiling] = useState(false);

  // Compile the visual Graph DAG into unified StrategyIR
  const compileGraphToIR = useCallback((): StrategyIR => {
    // 1. Locate Feed Node
    const feedNode = nodes.find((n) => n.type === "FEED");
    const timeframe = feedNode?.config.timeframe || "5m";

    // 2. Locate Risk Node
    const riskNode = nodes.find((n) => n.type === "RISK");
    const stopLossPct = riskNode?.config.stopLossPct ?? 2.0;
    const takeProfitPct = riskNode?.config.takeProfitPct ?? 4.0;
    const sizingPct = riskNode?.config.sizingPct ?? 1.0;

    // 3. Locate Action Node
    const actionNode = nodes.find((n) => n.type === "ACTION");
    const actionKind: ActionKind = actionNode?.config.action || "ENTER_LONG";

    // 4. Construct Condition Nodes
    const conditionNodes: ConditionNode[] = [];
    const conditionGraphNodes = nodes.filter((n) => n.type === "CONDITION");

    for (const cNode of conditionGraphNodes) {
      // Trace incoming edges to left and right ports
      const leftEdge = edges.find((e) => e.toNodeId === cNode.id && e.toPortId === "left_in");
      const rightEdge = edges.find((e) => e.toNodeId === cNode.id && e.toPortId === "right_in");

      let leftOp: Operand = { kind: "price", name: "close" };
      let rightOp: Operand = { kind: "constant", value: cNode.config.rightConst ?? 0 };

      if (leftEdge) {
        const sourceNode = nodes.find((n) => n.id === leftEdge.fromNodeId);
        if (sourceNode?.type === "CALCULATION") {
          leftOp = {
            kind: sourceNode.config.category === "order_flow" ? "order_flow" : "indicator",
            name: sourceNode.config.name,
            params: sourceNode.config.period ? { period: sourceNode.config.period } : {},
          };
        }
      }

      if (rightEdge) {
        const sourceNode = nodes.find((n) => n.id === rightEdge.fromNodeId);
        if (sourceNode?.type === "CALCULATION") {
          rightOp = {
            kind: sourceNode.config.category === "order_flow" ? "order_flow" : "indicator",
            name: sourceNode.config.name,
            params: sourceNode.config.period ? { period: sourceNode.config.period } : {},
          };
        }
      }

      conditionNodes.push({
        type: "condition",
        left: leftOp,
        operator: (cNode.config.operator as ComparisonOperator) || ">",
        right: rightOp,
      });
    }

    return {
      version: 1,
      name: "Visual Graph Strategy",
      base_timeframe: timeframe,
      min_data_quality: DataQuality.LEVEL_D_OHLCV_PROXY,
      entry_long: {
        type: "group",
        operator: "AND",
        nodes: conditionNodes,
      },
      risk: {
        stop_loss: { mode: "pct", value: stopLossPct },
        take_profit: { mode: "pct", value: takeProfitPct },
        trailing_stop: { mode: "none", trail_value: 0 },
      },
      portfolio: {
        initial_capital: 100_000,
        sizing_method: "percent_risk",
        risk_pct: sizingPct,
        max_open_positions: 5,
        max_capital_allocation_pct: 100,
      },
    };
  }, [nodes, edges]);

  // Handle Compile Validation
  const handleCompile = async () => {
    setCompiling(true);
    const ir = compileGraphToIR();
    const res = await onCompileStrategy(ir);
    setCompileResult(res);
    setCompiling(false);
  };

  const handleRunBacktest = () => {
    const ir = compileGraphToIR();
    onRunBacktest(ir);
  };

  // Node Dragging Mechanics
  const handleNodeMouseDown = (e: React.MouseEvent, nodeId: string) => {
    e.stopPropagation();
    setDraggingNodeId(nodeId);
    const targetNode = nodes.find((n) => n.id === nodeId);
    if (!targetNode) return;
    dragRef.current = {
      startX: e.clientX,
      startY: e.clientY,
      initialNodeX: targetNode.x,
      initialNodeY: targetNode.y,
    };
  };

  const handleCanvasMouseDown = (e: React.MouseEvent) => {
    setIsPanning(true);
    dragRef.current = {
      startX: e.clientX,
      startY: e.clientY,
      initialNodeX: pan.x,
      initialNodeY: pan.y,
    };
  };

  const handleMouseMove = (e: React.MouseEvent) => {
    const canvasRect = e.currentTarget.getBoundingClientRect();
    const currentMouseX = (e.clientX - canvasRect.left - pan.x) / zoom;
    const currentMouseY = (e.clientY - canvasRect.top - pan.y) / zoom;
    setMousePos({ x: currentMouseX, y: currentMouseY });

    if (draggingNodeId) {
      const dx = (e.clientX - dragRef.current.startX) / zoom;
      const dy = (e.clientY - dragRef.current.startY) / zoom;
      setNodes((prev) =>
        prev.map((n) =>
          n.id === draggingNodeId
            ? { ...n, x: dragRef.current.initialNodeX + dx, y: dragRef.current.initialNodeY + dy }
            : n
        )
      );
    } else if (isPanning) {
      const dx = e.clientX - dragRef.current.startX;
      const dy = e.clientY - dragRef.current.startY;
      setPan({ x: dragRef.current.initialNodeX + dx, y: dragRef.current.initialNodeY + dy });
    }
  };

  const handleMouseUp = () => {
    setDraggingNodeId(null);
    setIsPanning(false);
    setConnectingPort(null);
  };

  // Port Connection Mechanics
  const handlePortMouseDown = (e: React.MouseEvent, nodeId: string, port: GraphPort) => {
    e.stopPropagation();
    setConnectingPort({
      nodeId,
      portId: port.id,
      direction: port.direction,
      type: port.type,
    });
  };

  const handlePortMouseUp = (e: React.MouseEvent, targetNodeId: string, targetPort: GraphPort) => {
    e.stopPropagation();
    if (!connectingPort) return;
    if (connectingPort.nodeId === targetNodeId) return; // Disallow self-connection

    // Validate input <-> output connection
    if (connectingPort.direction === "output" && targetPort.direction === "input") {
      const newEdge: GraphEdge = {
        id: `edge_${Date.now()}`,
        fromNodeId: connectingPort.nodeId,
        fromPortId: connectingPort.portId,
        toNodeId: targetNodeId,
        toPortId: targetPort.id,
      };
      setEdges((prev) => [...prev.filter((edge) => !(edge.toNodeId === targetNodeId && edge.toPortId === targetPort.id)), newEdge]);
    } else if (connectingPort.direction === "input" && targetPort.direction === "output") {
      const newEdge: GraphEdge = {
        id: `edge_${Date.now()}`,
        fromNodeId: targetNodeId,
        fromPortId: targetPort.id,
        toNodeId: connectingPort.nodeId,
        toPortId: connectingPort.portId,
      };
      setEdges((prev) => [...prev.filter((edge) => !(edge.toNodeId === connectingPort.nodeId && edge.toPortId === connectingPort.portId)), newEdge]);
    }
    setConnectingPort(null);
  };

  // Add Node Helper
  const addNode = (type: NodeType) => {
    const id = `node_${Date.now()}`;
    const newX = (-pan.x + 100) / zoom;
    const newY = (-pan.y + 100) / zoom;

    let newNode: GraphNode;
    if (type === "CALCULATION") {
      newNode = {
        id,
        type,
        title: "RSI(14)",
        x: newX,
        y: newY,
        inputs: [{ id: "calc_in", name: "Price In", type: "price", direction: "input" }],
        outputs: [{ id: "calc_out", name: "RSI Value", type: "value", direction: "output" }],
        config: { category: "indicator", name: "rsi", period: 14 },
      };
    } else if (type === "CONDITION") {
      newNode = {
        id,
        type,
        title: "Value > Threshold",
        x: newX,
        y: newY,
        inputs: [
          { id: "left_in", name: "Left Value", type: "value", direction: "input" },
          { id: "right_in", name: "Right Value", type: "value", direction: "input" },
        ],
        outputs: [{ id: "cond_out", name: "Pass", type: "boolean", direction: "output" }],
        config: { operator: ">", rightConst: 50 },
      };
    } else {
      newNode = {
        id,
        type,
        title: "Logic Gate",
        x: newX,
        y: newY,
        inputs: [
          { id: "sig_1", name: "Signal 1", type: "boolean", direction: "input" },
          { id: "sig_2", name: "Signal 2", type: "boolean", direction: "input" },
        ],
        outputs: [{ id: "gate_out", name: "Trigger", type: "trigger", direction: "output" }],
        config: { operator: "AND" },
      };
    }
    setNodes([...nodes, newNode]);
  };

  const deleteNode = (nodeId: string) => {
    setNodes(nodes.filter((n) => n.id !== nodeId));
    setEdges(edges.filter((e) => e.fromNodeId !== nodeId && e.toNodeId !== nodeId));
  };

  return (
    <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-2xl flex flex-col gap-4 select-none">
      {/* Studio Header & Top Bar */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between pb-3 border-b border-slate-800 gap-2">
        <div>
          <h3 className="text-lg font-bold text-slate-100 flex items-center gap-2">
            <span className="w-2.5 h-2.5 rounded-full bg-violet-400 animate-pulse"></span>
            Node-Based Visual Strategy Graph (React Flow Canvas)
          </h3>
          <p className="text-xs text-slate-400">
            Assemble multi-market algorithms by wiring data feeds, order flow metrics, and risk parameters
          </p>
        </div>

        {/* Node Drawer & Action Buttons */}
        <div className="flex items-center gap-2">
          <div className="flex items-center gap-1 bg-slate-950 p-1 rounded-lg border border-slate-800 text-xs">
            <span className="text-[10px] text-slate-500 px-1.5 font-bold uppercase">Add:</span>
            <button
              onClick={() => addNode("CALCULATION")}
              className="px-2 py-0.5 rounded bg-slate-800 hover:bg-slate-700 text-slate-200 text-[11px]"
            >
              + Indicator
            </button>
            <button
              onClick={() => addNode("CONDITION")}
              className="px-2 py-0.5 rounded bg-slate-800 hover:bg-slate-700 text-slate-200 text-[11px]"
            >
              + Condition
            </button>
            <button
              onClick={() => addNode("LOGIC_GATE")}
              className="px-2 py-0.5 rounded bg-slate-800 hover:bg-slate-700 text-slate-200 text-[11px]"
            >
              + Gate
            </button>
          </div>

          <button
            onClick={handleCompile}
            disabled={compiling}
            className="px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-semibold border border-slate-700"
          >
            {compiling ? "Validating..." : "Compile Graph"}
          </button>

          <button
            onClick={handleRunBacktest}
            className="px-4 py-1.5 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-bold shadow-md shadow-indigo-600/30 flex items-center gap-1.5"
          >
            <span>▶</span>
            <span>Backtest Graph</span>
          </button>
        </div>
      </div>

      {/* Compiler Provenance Diagnostic Banner */}
      {compileResult && (
        <div className="bg-slate-950 border border-indigo-900/60 rounded-lg p-2.5 text-xs flex flex-wrap items-center justify-between gap-2 font-mono">
          <div className="flex items-center gap-3">
            <span className="text-emerald-400 font-bold">✓ Strategy Graph Verified</span>
            <span className="text-slate-400">
              Required Provenance: <strong className="text-indigo-300">{compileResult.highest_required_quality}</strong>
            </span>
            <span className="text-slate-400">
              Data Feeds: <strong className="text-cyan-300">{compileResult.required_feeds.join(", ")}</strong>
            </span>
          </div>
        </div>
      )}

      {/* Interactive Infinite Canvas */}
      <div
        onMouseDown={handleCanvasMouseDown}
        onMouseMove={handleMouseMove}
        onMouseUp={handleMouseUp}
        className="relative w-full h-[580px] bg-slate-950 rounded-xl overflow-hidden border border-slate-800 cursor-grab active:cursor-grabbing"
      >
        {/* Background Dot Grid */}
        <div
          className="absolute inset-0 opacity-15 pointer-events-none"
          style={{
            backgroundImage: "radial-gradient(#94a3b8 1px, transparent 1px)",
            backgroundSize: `${20 * zoom}px ${20 * zoom}px`,
            backgroundPosition: `${pan.x}px ${pan.y}px`,
          }}
        />

        {/* Scaled & Translated World Layer */}
        <div
          style={{
            transform: `translate(${pan.x}px, ${pan.y}px) scale(${zoom})`,
            transformOrigin: "0 0",
          }}
          className="absolute inset-0 w-full h-full pointer-events-none"
        >
          {/* SVG Connection Edges Layer */}
          <svg className="absolute inset-0 w-[5000px] h-[5000px] overflow-visible pointer-events-none z-10">
            {edges.map((edge) => {
              const fromNode = nodes.find((n) => n.id === edge.fromNodeId);
              const toNode = nodes.find((n) => n.id === edge.toNodeId);
              if (!fromNode || !toNode) return null;

              // Compute port positions relative to nodes (nodes width = 180px)
              const fromIdx = fromNode.outputs.findIndex((p) => p.id === edge.fromPortId);
              const toIdx = toNode.inputs.findIndex((p) => p.id === edge.toPortId);

              const startX = fromNode.x + 180;
              const startY = fromNode.y + 45 + (fromIdx >= 0 ? fromIdx * 24 : 0);
              const endX = toNode.x;
              const endY = toNode.y + 45 + (toIdx >= 0 ? toIdx * 24 : 0);

              const controlDist = Math.max(40, Math.abs(endX - startX) * 0.5);

              return (
                <g key={edge.id}>
                  {/* Outer glow line */}
                  <path
                    d={`M ${startX} ${startY} C ${startX + controlDist} ${startY}, ${endX - controlDist} ${endY}, ${endX} ${endY}`}
                    stroke="rgba(99, 102, 241, 0.2)"
                    strokeWidth="6"
                    fill="none"
                  />
                  {/* Core connection curve */}
                  <path
                    d={`M ${startX} ${startY} C ${startX + controlDist} ${startY}, ${endX - controlDist} ${endY}, ${endX} ${endY}`}
                    stroke="#6366f1"
                    strokeWidth="2.5"
                    fill="none"
                  />
                </g>
              );
            })}

            {/* In-flight connecting wire */}
            {connectingPort && (
              <path
                d={`M ${
                  connectingPort.direction === "output"
                    ? (nodes.find((n) => n.id === connectingPort.nodeId)?.x || 0) + 180
                    : nodes.find((n) => n.id === connectingPort.nodeId)?.x || 0
                } ${
                  (nodes.find((n) => n.id === connectingPort.nodeId)?.y || 0) + 45
                } C ${mousePos.x} ${mousePos.y}, ${mousePos.x} ${mousePos.y}, ${mousePos.x} ${mousePos.y}`}
                stroke="#a855f7"
                strokeWidth="2.5"
                strokeDasharray="4,4"
                fill="none"
              />
            )}
          </svg>

          {/* Draggable Graph Nodes */}
          {nodes.map((node) => {
            return (
              <div
                key={node.id}
                style={{
                  left: `${node.x}px`,
                  top: `${node.y}px`,
                  width: "180px",
                }}
                onMouseDown={(e) => handleNodeMouseDown(e, node.id)}
                className={`absolute pointer-events-auto rounded-xl border bg-slate-900/95 backdrop-blur shadow-xl transition-shadow z-20 flex flex-col ${
                  draggingNodeId === node.id
                    ? "border-indigo-400 shadow-indigo-500/20 shadow-2xl cursor-grabbing"
                    : "border-slate-800 hover:border-slate-700 cursor-grab"
                }`}
              >
                {/* Node Title Bar */}
                <div className="px-3 py-2 border-b border-slate-800/80 bg-slate-950/70 rounded-t-xl flex items-center justify-between">
                  <div className="flex items-center gap-1.5">
                    <span
                      className={`w-2 h-2 rounded-full ${
                        node.type === "FEED"
                          ? "bg-cyan-400"
                          : node.type === "CALCULATION"
                          ? "bg-indigo-400"
                          : node.type === "CONDITION"
                          ? "bg-amber-400"
                          : node.type === "LOGIC_GATE"
                          ? "bg-purple-400"
                          : node.type === "RISK"
                          ? "bg-rose-400"
                          : "bg-emerald-400"
                      }`}
                    />
                    <span className="text-xs font-bold text-slate-200 tracking-tight">{node.title}</span>
                  </div>
                  {node.type !== "FEED" && node.type !== "ACTION" && (
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        deleteNode(node.id);
                      }}
                      className="text-slate-600 hover:text-rose-400 text-xs px-1"
                    >
                      ✕
                    </button>
                  )}
                </div>

                {/* Ports Section */}
                <div className="p-2.5 flex flex-col gap-2 text-[10px] font-mono">
                  {/* Inputs */}
                  {node.inputs.map((port) => (
                    <div key={port.id} className="flex items-center gap-1.5 -ml-4">
                      <div
                        onMouseDown={(e) => handlePortMouseDown(e, node.id, port)}
                        onMouseUp={(e) => handlePortMouseUp(e, node.id, port)}
                        className="w-3 h-3 rounded-full bg-slate-800 border-2 border-indigo-400 hover:bg-indigo-400 cursor-pointer transition-colors"
                      />
                      <span className="text-slate-400">{port.name}</span>
                    </div>
                  ))}

                  {/* Outputs */}
                  {node.outputs.map((port) => (
                    <div key={port.id} className="flex items-center justify-end gap-1.5 -mr-4">
                      <span className="text-slate-400">{port.name}</span>
                      <div
                        onMouseDown={(e) => handlePortMouseDown(e, node.id, port)}
                        onMouseUp={(e) => handlePortMouseUp(e, node.id, port)}
                        className="w-3 h-3 rounded-full bg-slate-800 border-2 border-emerald-400 hover:bg-emerald-400 cursor-pointer transition-colors"
                      />
                    </div>
                  ))}

                  {/* Inline Node Param Controls */}
                  {node.type === "FEED" && (
                    <div className="text-[10px] text-slate-400 flex flex-col gap-0.5 mt-1 border-t border-slate-800/60 pt-1">
                      <span>Symbol: <strong>{node.config.symbol}</strong></span>
                      <span>Timeframe: <strong>{node.config.timeframe}</strong></span>
                    </div>
                  )}

                  {node.type === "CALCULATION" && node.config.period && (
                    <div className="flex items-center justify-between text-[10px] mt-1 border-t border-slate-800/60 pt-1">
                      <span className="text-slate-500">Period:</span>
                      <input
                        type="number"
                        value={node.config.period}
                        onChange={(e) => {
                          const val = parseInt(e.target.value) || 14;
                          setNodes(nodes.map((n) => (n.id === node.id ? { ...n, config: { ...n.config, period: val } } : n)));
                        }}
                        className="w-12 bg-slate-950 border border-slate-700 rounded px-1 text-right text-slate-200"
                      />
                    </div>
                  )}

                  {node.type === "CONDITION" && (
                    <div className="flex items-center justify-between text-[10px] mt-1 border-t border-slate-800/60 pt-1">
                      <span className="text-slate-500">Operator:</span>
                      <span className="text-amber-300 font-bold">{node.config.operator}</span>
                    </div>
                  )}

                  {node.type === "RISK" && (
                    <div className="text-[10px] text-slate-400 flex flex-col gap-0.5 mt-1 border-t border-slate-800/60 pt-1">
                      <span className="text-rose-400">SL: {node.config.stopLossPct}%</span>
                      <span className="text-emerald-400">TP: {node.config.takeProfitPct}%</span>
                    </div>
                  )}
                </div>
              </div>
            );
          })}
        </div>

        {/* Viewport Floating Info */}
        <div className="absolute bottom-3 left-3 bg-slate-900/80 border border-slate-800 rounded-lg px-2.5 py-1 text-[10px] font-mono text-slate-500 pointer-events-none">
          Nodes: {nodes.length} • Edges: {edges.length} • Pan: ({Math.round(pan.x)}, {Math.round(pan.y)})
        </div>
      </div>
    </div>
  );
};
