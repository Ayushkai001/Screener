/**
 * STRATLAB Strategy Studio & Simulation Types.
 * Matches backend/app/strategy/ir and execution schemas.
 */

import { AssetClass, DataQuality } from "./domain";

export type OperandKind = "price" | "indicator" | "order_flow" | "smc" | "constant";

export type ComparisonOperator =
  | ">"
  | "<"
  | ">="
  | "<="
  | "=="
  | "!="
  | "crosses_above"
  | "crosses_below"
  | "is_true"
  | "is_false"
  | "within_range"
  | "divergence_equals";

export type LogicalOp = "AND" | "OR";

export type ActionKind =
  | "ENTER_LONG"
  | "ENTER_SHORT"
  | "EXIT_LONG"
  | "EXIT_SHORT"
  | "MODIFY_STOP"
  | "SCALE_IN"
  | "SCALE_OUT";

export interface Operand {
  kind: OperandKind;
  name?: string;
  params?: Record<string, any>;
  value?: number;
  timeframe?: string;
  offset?: number;
}

export interface ConditionNode {
  type: "condition";
  left: Operand;
  operator: ComparisonOperator;
  right?: Operand;
  right2?: Operand;
  negate?: boolean;
  description?: string;
}

export interface ConditionGroup {
  type: "group";
  operator: LogicalOp;
  negate?: boolean;
  nodes: (ConditionGroup | ConditionNode)[];
}

export interface StopLossConfig {
  mode: "pct" | "atr" | "swing" | "level" | "fixed_ticks" | "none";
  value: number;
  atr_period?: number;
  level_operand?: Operand;
}

export interface TakeProfitConfig {
  mode: "pct" | "atr" | "risk_reward" | "level" | "fixed_ticks" | "none";
  value: number;
  level_operand?: Operand;
}

export interface TrailingStopConfig {
  mode: "pct" | "atr" | "step" | "none";
  activation_pct?: number;
  trail_value: number;
  atr_period?: number;
}

export interface RiskParams {
  stop_loss: StopLossConfig;
  take_profit: TakeProfitConfig;
  trailing_stop: TrailingStopConfig;
  max_hold_bars?: number;
  daily_loss_limit?: number;
}

export interface PortfolioParams {
  initial_capital: number;
  sizing_method: "percent_risk" | "fixed_quantity" | "fixed_cash" | "portfolio_percent";
  risk_pct: number;
  fixed_quantity?: number;
  fixed_cash?: number;
  max_open_positions: number;
  max_capital_allocation_pct: number;
}

export interface StrategyIR {
  version: number;
  id?: string;
  name: string;
  description?: string;
  author?: string;
  tags?: string[];
  base_timeframe: string;
  min_data_quality: DataQuality;
  entry_long?: ConditionGroup;
  entry_short?: ConditionGroup;
  exit_long?: ConditionGroup;
  exit_short?: ConditionGroup;
  risk: RiskParams;
  portfolio: PortfolioParams;
}

export interface ParameterDefinition {
  name: string;
  type: "int" | "float" | "string" | "bool";
  default: any;
  min_value?: number;
  max_value?: number;
  options?: string[];
  description?: string;
}

export interface ComponentDefinition {
  name: string;
  category: "price" | "indicator" | "order_flow" | "smc";
  display_name: string;
  description: string;
  required_feed: "candle" | "trade_ticks" | "order_book" | "footprint";
  min_data_quality: DataQuality;
  parameters: Record<string, ParameterDefinition>;
  output_type: "numeric" | "boolean" | "level";
}

export interface BacktestMetrics {
  total_trades: number;
  winning_trades: number;
  losing_trades: number;
  win_rate_pct: number;
  profit_factor: number;
  net_pnl: number;
  total_fees: number;
  max_drawdown_pct: number;
  sharpe_ratio: number;
  final_equity: number;
}

export interface ClosedTrade {
  instrument_id?: string;
  symbol: string;
  side: "LONG" | "SHORT";
  quantity?: number;
  entry_price: number;
  exit_price: number;
  entry_time_utc?: number;
  exit_time_utc?: number;
  gross_pnl?: number;
  net_pnl: number;
  total_fees: number;
  exit_reason: string;
}

export interface EquityCurvePoint {
  timestamp_utc: number;
  equity: number;
  cash: number;
  drawdown_pct: number;
}

export interface BacktestResult {
  metrics: BacktestMetrics;
  equity_curve: EquityCurvePoint[];
  closed_trades: ClosedTrade[];
}
