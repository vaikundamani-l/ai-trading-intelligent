export interface MarketState {
  symbol: string;
  connection_status: 'LIVE' | 'DELAYED' | 'DISCONNECTED';
  exchange_status: string;
  last_update_ts: number;
  data_age_sec: number;
  last_price: number;
  mark_price: number;
  spot_price: number;
  best_bid: number;
  best_ask: number;
  bid_size: number;
  ask_size: number;
  spread: number;
  spread_bps: number;
  volume_24h: number;
  turnover_24h: number;
  change_24h_pct: number;
  funding_rate: number;
  funding_rate_pct: number;
  next_funding_countdown_sec: number;
  open_interest: number;
  oi_contracts: number;
  bids: Array<{ price: number; size: number; depth: number }>;
  asks: Array<{ price: number; size: number; depth: number }>;
  order_flow_imbalance: number;
  trade_flow_imbalance: number;
  aggressive_buy_vol: number;
  aggressive_sell_vol: number;
  weighted_mid: number;
  micro_price_dev: number;
  basis_usd: number;
  basis_bps: number;
  recent_trades: Array<{
    price: number;
    size: number;
    side: 'buy' | 'sell';
    timestamp: number;
    time_iso: string;
  }>;
  is_data_safe: boolean;
}

export interface TrendInfo {
  timeframe: string;
  direction: 'BULLISH' | 'BEARISH' | 'RANGING';
  strength: 'STRONG' | 'MODERATE' | 'WEAK' | 'NEUTRAL';
  ema9: number;
  ema21: number;
  ema50: number;
  rsi: number;
  momentum_pct: number;
  summary: string;
}

export interface CandleData {
  time: number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  ema9?: number | null;
  ema21?: number | null;
  ema50?: number | null;
  ema200?: number | null;
  vwap?: number | null;
  bb_upper?: number | null;
  bb_lower?: number | null;
  atr?: number | null;
  rsi?: number | null;
  sbr_prev_high?: number | null;
  sbr_prev_low?: number | null;
}

export interface SignalDecision {
  quality?: {grade: string; checks: {label: string; passed: boolean}[]; explanation: string; eligible_for_auto_paper: boolean};
  action: 'BUY' | 'SELL' | 'WAIT' | 'WAIT / NO TRADE' | 'HALTED / DATA UNSAFE';
  direction: number;
  strategy: string;
  status: string;
  entry_price?: number;
  stop_loss?: number;
  take_profit?: number;
  risk_reward?: number;
  gross_reward_bps?: number;
  estimated_fees_bps?: number;
  estimated_slippage_bps?: number;
  net_reward_bps?: number;
  reasons: string[];
  invalidation_risks: string[];
  market_regime?: string;
  timestamp: number;
  datetime_utc: string;
  candle_timestamp?: number;
  valid_until_ts?: number;
  research_telemetry?: Record<string, unknown>;
}

export interface HorizonForecast {
  horizon: string;
  horizon_minutes: number;
  observed_price: number;
  bullish_probability: number;
  bearish_probability: number;
  expected_move_usd: number;
  expected_volatility_pct: number;
  range_forecast: {
    lower: number;
    upper: number;
  };
  directional_bias: 'BULLISH' | 'BEARISH' | 'NEUTRAL';
  model_version: string;
  training_date: string;
  calibration_status: string;
  is_validated: boolean;
  metrics: {
    brier_score: number;
    accuracy: number;
    log_loss: number;
    test_samples: number;
  };
}

export interface AIPredictions {
  status: string;
  message?: string;
  model_version: string;
  training_date: string;
  horizons: Record<string, HorizonForecast>;
  timestamp: number;
  datetime_utc: string;
}

export interface PaperTrade {
  id: number;
  signal_id?: number;
  created_at: string;
  entry_time: string;
  exit_time?: string;
  symbol: string;
  direction: number;
  entry_price: number;
  exit_price?: number;
  stop_loss: number;
  take_profit: number;
  notional_usd: number;
  contracts: number;
  gross_bps?: number;
  fees_bps?: number;
  net_bps?: number;
  pnl_usd?: number;
  equity_after?: number;
  status: 'OPEN' | 'CLOSED';
  exit_reason?: string;
}

export interface PaperPortfolio {
  initial_equity: number;
  current_equity: number;
  peak_equity: number;
  total_return_pct: number;
  max_drawdown_pct: number;
  total_trades: number;
  winning_trades: number;
  losing_trades: number;
  win_rate_pct: number;
  profit_factor: number | null;
  average_net_expectancy_bps: number;
  losing_streak: number;
  is_cooldown_active: boolean;
  cooldown_remaining_sec: number;
  is_halted: boolean;
  halt_reason: string;
  open_position?: PaperTrade | null;
  closed_trades: PaperTrade[];
}

export interface BacktestResults {
  trades_count: number;
  start_equity: number;
  end_equity: number;
  total_return_pct: number;
  buy_and_hold_return_pct: number;
  win_rate_pct: number;
  profit_factor: number | null;
  max_drawdown_pct: number;
  avg_net_bps: number;
  trades: Array<{
    signal_utc: string;
    entry_utc: string;
    exit_utc: string;
    direction: number;
    entry: number;
    stop: number;
    target: number;
    exit: number;
    reason: string;
    holding_bars: number;
    notional_usd: number;
    gross_bps: number;
    fees_bps: number;
    net_bps: number;
    pnl_usd: number;
    equity_after: number;
  }>;
  equity_curve: Array<{ time: string; equity: number }>;
  cost_sensitivity: Array<{
    slippage_bps: number;
    net_return_pct: number;
    total_pnl_usd: number;
  }>;
  hourly_performance: Record<number, { trades: number; wins: number; pnl: number }>;
  status: string;
  error?: string;
}

export interface TimeframeTrend {
  timeframe: string;
  direction: 'BULLISH' | 'BEARISH' | 'RANGING';
  ema9?: number;
  ema21?: number;
  rsi?: number;
  last_price?: number;
  status?: string;
}

export interface LiveTrendInfo {
  timeframe: string;
  direction: 'STRONG_BULLISH' | 'BULLISH' | 'STRONG_BEARISH' | 'BEARISH' | 'RANGING';
  label: string;
  ema9: number;
  ema21: number;
  ema50?: number;
  rsi: number;
  price: number;
  momentum_pct: number;
  summary: string;
  last_updated: string;
}

