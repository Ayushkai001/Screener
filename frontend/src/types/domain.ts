/**
 * STRATLAB Universal Domain Types.
 * Auto-synchronized with shared/schemas Python Pydantic v2 contracts.
 */

// ---------------------------------------------------------------- Provenance
export enum DataQuality {
  LEVEL_A_EXCHANGE_VERIFIED = 1,
  LEVEL_B_QUOTE_CLASSIFIED = 2,
  LEVEL_C_TICK_RULE = 3,
  LEVEL_D_OHLCV_PROXY = 4,
}

export type AggressorSide = "BUY" | "SELL" | "UNKNOWN";

export type SideMethod =
  | "EXCHANGE_FLAG"
  | "QUOTE_BBO"
  | "TICK_RULE"
  | "BVC_SYNTHETIC"
  | "UNKNOWN";

export interface ProvenanceMetadata {
  quality: DataQuality;
  side_method: SideMethod;
  source_id: string;
  confidence: number; // 0.0 - 1.0
  is_estimated: boolean;
}

// ---------------------------------------------------------------- Instrument
export type AssetClass =
  | "EQUITY"
  | "FUTURES"
  | "OPTIONS"
  | "CRYPTO"
  | "FOREX"
  | "COMMODITY"
  | "INDEX";

export type OptionType = "CE" | "PE";

export interface InstrumentMaster {
  instrument_id: string; // e.g. INS_NSE_RELIANCE
  symbol: string;
  exchange: string;
  asset_class: AssetClass;
  currency: string;
  tick_size: number;
  lot_size: number;
  multiplier: number;
  timezone: string;
  expiry?: string | null; // YYYY-MM-DD
  strike?: number | null;
  option_type?: OptionType | null;
  underlying_id?: string | null;
}

// ---------------------------------------------------------------- Market Data
export interface Candle {
  instrument_id: string;
  timestamp_utc: number; // Milliseconds Unix epoch
  timeframe: string; // "1m", "5m", "1d"
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  turnover: number;
  provenance: ProvenanceMetadata;
}

export interface TradeTick {
  instrument_id: string;
  timestamp_ns: number; // Nanoseconds UTC
  price: number;
  quantity: number;
  aggressor: AggressorSide;
  bid?: number | null;
  ask?: number | null;
  sequence_id?: number | null;
  provenance: ProvenanceMetadata;
}

export interface BookLevel {
  price: number;
  quantity: number;
  orders_count?: number | null;
}

export interface OrderBookDepth {
  instrument_id: string;
  timestamp_ns: number;
  bids: BookLevel[];
  asks: BookLevel[];
  sequence_id?: number | null;
  provenance: ProvenanceMetadata;
}

// ---------------------------------------------------------------- Order Flow
export interface PriceCluster {
  price: number;
  bid_vol?: number;
  ask_vol?: number;
  total_vol?: number;
  delta: number;
  trade_count?: number;
  imbalance_buy?: boolean;
  imbalance_sell?: boolean;
  is_poc?: boolean;
  provenance?: ProvenanceMetadata;
  // Aliases
  bid_volume?: number;
  ask_volume?: number;
  total_volume?: number;
  delta_pct?: number;
  is_buy_imbalance?: boolean;
  is_sell_imbalance?: boolean;
}

export interface FootprintBar {
  instrument_id: string;
  timeframe: string;
  open_time_utc?: number;
  close_time_utc?: number;
  timestamp_utc?: string | number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  turnover?: number;
  delta: number;
  cum_delta?: number;
  delta_min?: number;
  delta_max?: number;
  delta_finish?: number;
  clusters: Record<number, PriceCluster> | PriceCluster[];
  poc_price?: number;
  vah?: number;
  val?: number;
  value_area_high?: number;
  value_area_low?: number;
  stacked_buy_imbalances?: number[];
  stacked_sell_imbalances?: number[];
  unfinished_high?: boolean;
  unfinished_low?: boolean;
  provenance: ProvenanceMetadata;
}

export interface VolumeProfile {
  instrument_id: string;
  session_date: string;
  profile_type: "SESSION" | "FIXED_RANGE" | "DEVELOPING" | "COMPOSITE";
  start_time_utc: number;
  end_time_utc: number;
  tick_size: number;
  bins: Record<string | number, number>;
  total_volume: number;
  poc_price: number;
  poc_volume: number;
  vah_price: number;
  val_price: number;
  high_volume_nodes: number[];
  low_volume_nodes: number[];
  provenance: ProvenanceMetadata;
}

export interface CVDPoint {
  instrument_id: string;
  timestamp_utc: number;
  delta: number;
  cumulative_delta: number;
  session_reset: boolean;
  provenance: ProvenanceMetadata;
}

// ---------------------------------------------------------------- Execution
export type OrderType = "MARKET" | "LIMIT" | "STOP_LOSS" | "STOP_LIMIT";
export type OrderStatus =
  | "PENDING"
  | "QUEUED"
  | "FILLED"
  | "PARTIALLY_FILLED"
  | "CANCELLED"
  | "REJECTED";
export type OrderSide = "BUY" | "SELL";

export interface PaperOrder {
  order_id: string;
  account_id: string;
  instrument_id: string;
  side: OrderSide;
  order_type: OrderType;
  price?: number | null;
  stop_price?: number | null;
  quantity: number;
  filled_quantity: number;
  avg_fill_price?: number | null;
  status: OrderStatus;
  queue_ahead_volume: number;
  created_time_utc: number;
  updated_time_utc: number;
}

export interface PaperFill {
  fill_id: string;
  order_id: string;
  timestamp_utc: number;
  price: number;
  quantity: number;
  fee: number;
  slippage: number;
}

export interface PaperPosition {
  account_id: string;
  instrument_id: string;
  quantity: number;
  avg_entry_price: number;
  current_price: number;
  unrealized_pnl: number;
  realized_pnl: number;
  updated_time_utc: number;
}

export interface PaperAccount {
  account_id: string;
  user_id: string;
  name: string;
  currency: string;
  balance: number;
  equity: number;
  margin_used: number;
  created_time_utc: number;
}
