type IndicatorCandle = {
  time: number;
  close: number;
};

// Recompute the provisional last candle from completed candle closes. Ticks
// within one candle replace its close; they never become extra EMA periods.
export function liveCandleIndicators(candles: IndicatorCandle[], price: number, barTime: number) {
  const closes = candles.filter(c => c.time < barTime).map(c => c.close);
  const ema = (period: number) => {
    const k = 2 / (period + 1);
    let value = closes[0] ?? price;
    for (const close of closes.slice(1)) value = k * close + (1 - k) * value;
    return k * price + (1 - k) * value;
  };
  const recent = [...closes.slice(-14), price];
  let gains = 0;
  let losses = 0;
  for (let i = 1; i < recent.length; i++) {
    const delta = recent[i] - recent[i - 1];
    gains += Math.max(0, delta);
    losses += Math.max(0, -delta);
  }
  const rsi = gains + losses === 0 ? 50 : 100 * gains / (gains + losses);
  return { ema9: ema(9), ema21: ema(21), ema50: ema(50), rsi };
}
