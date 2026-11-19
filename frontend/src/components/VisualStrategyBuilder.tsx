import React, { useState } from "react";
import { DataQuality } from "../types/domain";
import {
  ComparisonOperator,
  ConditionNode,
  Operand,
  OperandKind,
  StrategyIR,
} from "../types/strategy";

interface VisualStrategyBuilderProps {
  onRunBacktest: (strategy: StrategyIR) => void;
  onCompileStrategy: (strategy: StrategyIR) => Promise<{
    highest_required_quality: string;
    required_feeds: string[];
  } | null>;
}

export const VisualStrategyBuilder: React.FC<VisualStrategyBuilderProps> = ({
  onRunBacktest,
  onCompileStrategy,
}) => {
  const [strategyName, setStrategyName] = useState("Order Flow Momentum");
  const [timeframe, setTimeframe] = useState("5m");
  const [stopLossPct, setStopLossPct] = useState(2.0);
  const [takeProfitPct, setTakeProfitPct] = useState(4.0);

  // Condition blocks for Long Entry
  const [conditions, setConditions] = useState<ConditionNode[]>([
    {
      type: "condition",
      left: { kind: "price", name: "close" },
      operator: ">",
      right: { kind: "indicator", name: "ema", params: { period: 20 } },
    },
    {
      type: "condition",
      left: { kind: "order_flow", name: "bar_delta" },
      operator: ">",
      right: { kind: "constant", value: 0 },
    },
  ]);

  const [compileResult, setCompileResult] = useState<{
    highest_required_quality: string;
    required_feeds: string[];
  } | null>(null);

  const [compiling, setCompiling] = useState(false);

  const addCondition = () => {
    setConditions([
      ...conditions,
      {
        type: "condition",
        left: { kind: "price", name: "close" },
        operator: ">",
        right: { kind: "constant", value: 100 },
      },
    ]);
  };

  const removeCondition = (index: number) => {
    setConditions(conditions.filter((_, i) => i !== index));
  };

  const updateCondition = (index: number, updated: ConditionNode) => {
    const next = [...conditions];
    next[index] = updated;
    setConditions(next);
  };

  const buildCurrentIR = (): StrategyIR => {
    return {
      version: 1,
      name: strategyName,
      base_timeframe: timeframe,
      min_data_quality: DataQuality.LEVEL_D_OHLCV_PROXY,
      entry_long: {
        type: "group",
        operator: "AND",
        nodes: conditions,
      },
      risk: {
        stop_loss: { mode: "pct", value: stopLossPct },
        take_profit: { mode: "pct", value: takeProfitPct },
        trailing_stop: { mode: "none", trail_value: 0 },
      },
      portfolio: {
        initial_capital: 100_000,
        sizing_method: "percent_risk",
        risk_pct: 1.0,
        max_open_positions: 3,
        max_capital_allocation_pct: 100,
      },
    };
  };

  const handleCompile = async () => {
    setCompiling(true);
    const res = await onCompileStrategy(buildCurrentIR());
    setCompileResult(res);
    setCompiling(false);
  };

  const handleRun = () => {
    onRunBacktest(buildCurrentIR());
  };

  return (
    <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-2xl flex flex-col gap-5">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between pb-3 border-b border-slate-800 gap-2">
        <div>
          <h3 className="text-lg font-bold text-slate-100 flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-violet-500"></span>
            Strategy Studio (Visual Blocks)
          </h3>
          <p className="text-xs text-slate-400">
            Design multi-market entry/exit triggers with strict data provenance validation
          </p>
        </div>

        {/* Global Strategy Meta */}
        <div className="flex items-center gap-2">
          <input
            type="text"
            value={strategyName}
            onChange={(e) => setStrategyName(e.target.value)}
            className="bg-slate-950 border border-slate-700 rounded px-2.5 py-1 text-xs text-slate-200 focus:outline-none focus:border-indigo-500"
            placeholder="Strategy Name"
          />
          <select
            value={timeframe}
            onChange={(e) => setTimeframe(e.target.value)}
            className="bg-slate-950 border border-slate-700 rounded px-2 py-1 text-xs text-slate-300 focus:outline-none"
          >
            <option value="1m">1m</option>
            <option value="5m">5m</option>
            <option value="15m">15m</option>
            <option value="1h">1h</option>
            <option value="1d">1d</option>
          </select>
        </div>
      </div>

      {/* Condition Blocks Canvas */}
      <div className="flex flex-col gap-2">
        <label className="text-xs font-semibold text-slate-300">
          Long Entry Rules (All conditions must be satisfied — AND):
        </label>

        {conditions.map((cond, idx) => (
          <div
            key={idx}
            className="flex flex-wrap items-center gap-2 bg-slate-950/70 border border-slate-800 p-2.5 rounded-lg text-xs"
          >
            <span className="w-6 h-6 rounded bg-slate-800 text-slate-400 flex items-center justify-center font-mono font-bold text-[11px]">
              {idx + 1}
            </span>

            {/* Left Operand Kind & Name */}
            <select
              value={cond.left.name || "close"}
              onChange={(e) => {
                const val = e.target.value;
                const kind: OperandKind =
                  val === "close" || val === "open"
                    ? "price"
                    : val === "ema" || val === "rsi"
                    ? "indicator"
                    : "order_flow";
                updateCondition(idx, {
                  ...cond,
                  left: { kind, name: val, params: val === "ema" ? { period: 20 } : {} },
                });
              }}
              className="bg-slate-900 border border-slate-700 text-slate-200 rounded px-2 py-1 focus:outline-none font-mono"
            >
              <option value="close">Price: Close</option>
              <option value="open">Price: Open</option>
              <option value="ema">Indicator: EMA(20)</option>
              <option value="rsi">Indicator: RSI(14)</option>
              <option value="bar_delta">Order Flow: Bar Delta</option>
              <option value="cvd">Order Flow: CVD</option>
              <option value="footprint_stacked_imbalance_buy">
                Footprint: Stacked Buy Imbalances
              </option>
            </select>

            {/* Operator */}
            <select
              value={cond.operator}
              onChange={(e) =>
                updateCondition(idx, {
                  ...cond,
                  operator: e.target.value as ComparisonOperator,
                })
              }
              className="bg-slate-900 border border-indigo-500/50 text-indigo-300 font-bold rounded px-2 py-1 focus:outline-none"
            >
              <option value=">">&gt; (Greater)</option>
              <option value="<">&lt; (Less)</option>
              <option value=">=">&gt;= (Greater or Equal)</option>
              <option value="<=">&lt;= (Less or Equal)</option>
              <option value="==">== (Equals)</option>
              <option value="crosses_above">Crosses Above</option>
              <option value="crosses_below">Crosses Below</option>
            </select>

            {/* Right Operand */}
            {cond.right?.kind === "constant" ? (
              <input
                type="number"
                value={cond.right.value ?? 0}
                onChange={(e) =>
                  updateCondition(idx, {
                    ...cond,
                    right: { kind: "constant", value: parseFloat(e.target.value) || 0 },
                  })
                }
                className="w-24 bg-slate-900 border border-slate-700 rounded px-2 py-1 text-slate-200 font-mono focus:outline-none"
              />
            ) : (
              <select
                value={cond.right?.name || "ema"}
                onChange={(e) => {
                  const val = e.target.value;
                  if (val === "constant") {
                    updateCondition(idx, {
                      ...cond,
                      right: { kind: "constant", value: 0 },
                    });
                  } else {
                    updateCondition(idx, {
                      ...cond,
                      right: {
                        kind: val === "close" ? "price" : "indicator",
                        name: val,
                        params: { period: 20 },
                      },
                    });
                  }
                }}
                className="bg-slate-900 border border-slate-700 text-slate-200 rounded px-2 py-1 focus:outline-none font-mono"
              >
                <option value="ema">Indicator: EMA(20)</option>
                <option value="close">Price: Close</option>
                <option value="constant">Fixed Constant Value</option>
              </select>
            )}

            {/* Delete button */}
            <button
              onClick={() => removeCondition(idx)}
              className="ml-auto text-slate-500 hover:text-rose-400 font-bold px-2 py-1"
            >
              ✕
            </button>
          </div>
        ))}

        <button
          onClick={addCondition}
          className="self-start text-xs font-medium text-indigo-400 hover:text-indigo-300 py-1 flex items-center gap-1"
        >
          + Add Condition Block
        </button>
      </div>

      {/* Risk Controls Strip */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 pt-2 border-t border-slate-800">
        <div className="bg-slate-950 p-3 rounded-lg border border-slate-800">
          <label className="text-[11px] text-slate-400 block mb-1">
            Stop Loss (% from Entry)
          </label>
          <input
            type="number"
            step="0.5"
            value={stopLossPct}
            onChange={(e) => setStopLossPct(parseFloat(e.target.value) || 1.0)}
            className="w-full bg-slate-900 border border-slate-700 rounded px-2 py-1 text-xs text-rose-400 font-mono font-bold focus:outline-none"
          />
        </div>
        <div className="bg-slate-950 p-3 rounded-lg border border-slate-800">
          <label className="text-[11px] text-slate-400 block mb-1">
            Take Profit (% from Entry)
          </label>
          <input
            type="number"
            step="0.5"
            value={takeProfitPct}
            onChange={(e) => setTakeProfitPct(parseFloat(e.target.value) || 2.0)}
            className="w-full bg-slate-900 border border-slate-700 rounded px-2 py-1 text-xs text-emerald-400 font-mono font-bold focus:outline-none"
          />
        </div>
      </div>

      {/* Compilation Diagnostics Bar */}
      {compileResult && (
        <div className="bg-slate-950 border border-indigo-900/50 rounded-lg p-3 text-xs flex flex-wrap items-center justify-between gap-2">
          <div className="flex items-center gap-3">
            <span className="text-emerald-400 font-bold">✓ IR Compiled Successfully</span>
            <span className="text-slate-400">
              Min Provenance:{" "}
              <strong className="text-indigo-300 font-mono">
                {compileResult.highest_required_quality}
              </strong>
            </span>
            <span className="text-slate-400">
              Required Feeds:{" "}
              <strong className="text-indigo-300 font-mono">
                {compileResult.required_feeds.join(", ")}
              </strong>
            </span>
          </div>
        </div>
      )}

      {/* Actions */}
      <div className="flex items-center gap-3 pt-2">
        <button
          onClick={handleCompile}
          disabled={compiling}
          className="px-4 py-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-semibold transition-all border border-slate-700"
        >
          {compiling ? "Validating..." : "Compile & Verify Provenance"}
        </button>

        <button
          onClick={handleRun}
          className="px-5 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-bold shadow-lg shadow-indigo-600/30 transition-all flex items-center gap-2"
        >
          <span>▶</span>
          <span>Run Backtest Simulation</span>
        </button>
      </div>
    </div>
  );
};
