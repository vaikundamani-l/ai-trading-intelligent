'use client';

import React, { useEffect, useRef, useState, useCallback } from 'react';
import {
  createChart,
  CandlestickSeries,
  LineSeries,
  HistogramSeries,
  ColorType,
  LineStyle,
  CrosshairMode,
  IChartApi,
  ISeriesApi,
  Time,
  SeriesType,
  SeriesDataItemTypeMap,
  IPriceLine,
  TickMarkType,
  createSeriesMarkers,
  ISeriesMarkersPluginApi,
  SeriesMarker,
} from 'lightweight-charts';
import { CandleData, SignalDecision, TimeframeTrend, LiveTrendInfo, PassedSignal } from '@/lib/types';
import { apiFetch } from '@/lib/api';
import { liveCandleIndicators } from '@/lib/chartIndicators';
import { formatISTDate, formatISTTime, formatISTFull, getNowISTString } from '@/lib/dateUtils';
import { Layers, RefreshCw, TrendingUp, TrendingDown, Minus } from 'lucide-react';

interface SignalDiagnostics {
  candidate_count: number;
  qualified_count: number;
  filtered_count: number;
  filtered_reasons: Record<string, number>;
}

interface TradingViewChartProps {
  timeframe: string;
  onTimeframeChange: (tf: string) => void;
  signal: SignalDecision | null;
  lastPrice: number;
}

const TIMEFRAMES = ['1m', '3m', '5m', '15m', '30m', '1h', '4h', '1d'];

const TIMEFRAME_SECONDS: Record<string, number> = {
  '1m': 60,
  '3m': 180,
  '5m': 300,
  '15m': 900,
  '30m': 1800,
  '1h': 3600,
  '4h': 14400,
  '1d': 86400,
};

export const TradingViewChart: React.FC<TradingViewChartProps> = ({
  timeframe,
  onTimeframeChange,
  signal,
  lastPrice,
}) => {
  const chartContainerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const candleSeriesRef = useRef<ISeriesApi<'Candlestick'> | null>(null);
  const volumeSeriesRef = useRef<ISeriesApi<'Histogram'> | null>(null);

  // Lifecycle disposal guard to prevent "Object is disposed" errors
  const isDisposedRef = useRef<boolean>(false);

  // Overlay series refs
  const ema9Ref = useRef<ISeriesApi<'Line'> | null>(null);
  const ema21Ref = useRef<ISeriesApi<'Line'> | null>(null);
  const ema50Ref = useRef<ISeriesApi<'Line'> | null>(null);
  const ema200Ref = useRef<ISeriesApi<'Line'> | null>(null);
  const vwapRef = useRef<ISeriesApi<'Line'> | null>(null);
  const bbUpperRef = useRef<ISeriesApi<'Line'> | null>(null);
  const bbLowerRef = useRef<ISeriesApi<'Line'> | null>(null);
  const sbrPrevHighRef = useRef<ISeriesApi<'Line'> | null>(null);
  const sbrPrevLowRef = useRef<ISeriesApi<'Line'> | null>(null);

  // Price lines for Stop Loss and Take Profit
  const stopLineRef = useRef<IPriceLine | null>(null);
  const targetLineRef = useRef<IPriceLine | null>(null);
  const entryLineRef = useRef<IPriceLine | null>(null);

  // Series markers primitive for passed candles & live signals
  const seriesMarkersRef = useRef<ISeriesMarkersPluginApi<Time> | null>(null);
  const candlesDataRef = useRef<CandleData[]>([]);
  const selectedTimeframeRef = useRef(timeframe);
  useEffect(() => { selectedTimeframeRef.current = timeframe; }, [timeframe]);
  const isFetchingRef = useRef<boolean>(false);
  const hasFittedRef = useRef<Record<string, boolean>>({});
  const [hasCandleData, setHasCandleData] = useState(false);
  const [passedSignalsState, setPassedSignalsState] = useState<{ timeframe: string; signals: PassedSignal[] }>({ timeframe, signals: [] });
  const passedSignalsList = passedSignalsState.timeframe === timeframe ? passedSignalsState.signals : [];

  const [diagnosticsState, setDiagnosticsState] = useState<{ timeframe: string; data: SignalDiagnostics | null }>({ timeframe, data: null });
  const diagnostics = diagnosticsState.timeframe === timeframe ? diagnosticsState.data : null;

  // Active forming bar tracking
  const activeBarRef = useRef<{
    time: number;
    open: number;
    high: number;
    low: number;
    close: number;
    volume: number;
  } | null>(null);

  // Multi-timeframe trend matrix
  const [multiTrends, setMultiTrends] = useState<Record<string, TimeframeTrend>>({});

  // 1-second live trend state
  const [liveTrend, setLiveTrend] = useState<LiveTrendInfo>({
    timeframe: timeframe,
    direction: 'RANGING',
    label: 'ANALYZING',
    ema9: 0,
    ema21: 0,
    ema50: 0,
    rsi: 50,
    price: lastPrice || 0,
    momentum_pct: 0,
    summary: 'Evaluating real-time ticks...',
    last_updated: 'Just now',
  });

  // Overlay state toggles
  const [overlays, setOverlays] = useState({
    ema9: true,
    ema21: true,
    ema50: false,
    ema200: false,
    vwap: true,
    bollinger: false,
    sbrLevels: true,
    volume: true,
    signals: true,
  });

  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [atrValue, setAtrValue] = useState<number | null>(null);
  const [hoveredCandle, setHoveredCandle] = useState<CandleData | null>(null);

  const toggleOverlay = (key: keyof typeof overlays) => {
    setOverlays((prev) => ({ ...prev, [key]: !prev[key] }));
  };

  // Safe helper to update series data without throwing if chart was disposed
  const safeUpdate = <T extends SeriesType,>(series: ISeriesApi<T> | null, data: SeriesDataItemTypeMap<Time>[T]) => {
    if (isDisposedRef.current || !series) return;
    try {
      series.update(data);
    } catch {
      // Ignore disposed or out-of-order time errors gracefully
    }
  };

  // Safe helper to set entire series data
  const safeSetData = <T extends SeriesType,>(series: ISeriesApi<T> | null, data: SeriesDataItemTypeMap<Time>[T][]) => {
    if (isDisposedRef.current || !series) return;
    try {
      series.setData(data);
    } catch {
      // Ignore disposed error gracefully
    }
  };

  // Safe helper to remove a price line
  const safeRemovePriceLine = (lineRef: React.MutableRefObject<IPriceLine | null>) => {
    if (isDisposedRef.current || !candleSeriesRef.current || !lineRef.current) {
      lineRef.current = null;
      return;
    }
    try {
      candleSeriesRef.current.removePriceLine(lineRef.current);
    } catch {
      // Ignore
    }
    lineRef.current = null;
  };

  // Fetch multi-timeframe trends matrix from API
  const fetchMultiTrends = useCallback(async () => {
    try {
      const { data, ok } = await apiFetch<Record<string, TimeframeTrend>>('/api/market/trends');
      if (ok && data && !isDisposedRef.current) {
        setMultiTrends(data);
      }
    } catch {
      // Ignore network errors
    }
  }, []);

  // Poll multi-timeframe trends matrix every 4 seconds
  useEffect(() => {
    const initial = setTimeout(fetchMultiTrends, 0);
    const interval = setInterval(fetchMultiTrends, 4000);
    return () => {
      clearTimeout(initial);
      clearInterval(interval);
    };
  }, [fetchMultiTrends]);

  // Synchronize candlestick markers for passed candles & live signals
  const updateMarkers = useCallback((candlesToUse?: CandleData[]) => {
    if (isDisposedRef.current || !seriesMarkersRef.current) return;

    if (!overlays.signals) {
      try {
        seriesMarkersRef.current.setMarkers([]);
      } catch {
        // Ignore
      }
      return;
    }

    const markers: SeriesMarker<Time>[] = [];
    const sourceCandles = candlesToUse || candlesDataRef.current;

    // 1. Mark historical candles where strategy setup passed (BUY or SELL)
    for (const c of sourceCandles) {
      if (c.signal === 'BUY') {
        let tag = 'BUY';
        let color = '#10b981';
        if (c.signal_outcome === 'TARGET_HIT') {
          tag = `BUY 🎯 ${c.signal_pnl_r ?? '?'}R net`;
          color = '#10b981';
        } else if (c.signal_outcome === 'BREAKEVEN_WIN') {
          tag = `BUY 🔒 BE (+${c.signal_pnl_r ?? '0.1'}R)`;
          color = '#38bdf8';
        } else if (c.signal_outcome === 'STOP_HIT') {
          tag = `BUY 🛑 ${c.signal_pnl_r ?? '?'}R net`;
          color = '#ef4444';
        } else if (c.signal_outcome === 'TIME_EXIT') {
          tag = `BUY ⏱ ${c.signal_pnl_r ?? '?'}R net`;
          color = '#f59e0b';
        } else if (c.signal_outcome === 'ACTIVE') {
          tag = 'BUY ⏳ ACTIVE';
          color = '#06b6d4';
        }

        markers.push({
          id: `hist-buy-${c.time}`,
          time: c.time as Time,
          position: 'belowBar',
          shape: 'arrowUp',
          color,
          text: tag,
          size: 2,
        });
      } else if (c.signal === 'SELL') {
        let tag = 'SELL';
        let color = '#ef4444';
        if (c.signal_outcome === 'TARGET_HIT') {
          tag = `SELL 🎯 ${c.signal_pnl_r ?? '?'}R net`;
          color = '#10b981';
        } else if (c.signal_outcome === 'BREAKEVEN_WIN') {
          tag = `SELL 🔒 BE (+${c.signal_pnl_r ?? '0.1'}R)`;
          color = '#38bdf8';
        } else if (c.signal_outcome === 'STOP_HIT') {
          tag = `SELL 🛑 ${c.signal_pnl_r ?? '?'}R net`;
          color = '#ef4444';
        } else if (c.signal_outcome === 'TIME_EXIT') {
          tag = `SELL ⏱ ${c.signal_pnl_r ?? '?'}R net`;
          color = '#f59e0b';
        } else if (c.signal_outcome === 'ACTIVE') {
          tag = 'SELL ⏳ ACTIVE';
          color = '#06b6d4';
        }

        markers.push({
          id: `hist-sell-${c.time}`,
          time: c.time as Time,
          position: 'aboveBar',
          shape: 'arrowDown',
          color,
          text: tag,
          size: 2,
        });
      }
    }

    // 2. Mark the live trade passed (current active BUY / SELL setup)
    if (signal && (signal.resolution || '5m') === timeframe && (signal.action === 'BUY' || signal.action === 'SELL')
        && signal.valid_until_ts != null && signal.valid_until_ts > Date.now() / 1000) {
      const isLiveBuy = signal.action === 'BUY';
      const liveTime =
        signal.candle_timestamp ||
        activeBarRef.current?.time ||
        (sourceCandles.length > 0 ? sourceCandles[sourceCandles.length - 1].time : null);

      if (liveTime) {
        // If there was already a historical marker on this exact bar, remove it so live marker takes priority
        const existingIdx = markers.findIndex((m) => Number(m.time) === liveTime);
        if (existingIdx !== -1) {
          markers.splice(existingIdx, 1);
        }
        markers.push({
          id: `live-${isLiveBuy ? 'buy' : 'sell'}-${liveTime}`,
          time: liveTime as Time,
          position: isLiveBuy ? 'belowBar' : 'aboveBar',
          shape: isLiveBuy ? 'arrowUp' : 'arrowDown',
          color: isLiveBuy ? '#34d399' : '#f87171',
          text: isLiveBuy ? 'LIVE BUY ↗' : 'LIVE SELL ↘',
          size: 2,
        });
      }
    }

    // Lightweight charts requires markers to be strictly ordered by time
    markers.sort((a, b) => Number(a.time) - Number(b.time));

    try {
      seriesMarkersRef.current.setMarkers(markers);
    } catch (e) {
      console.warn('Failed to apply series markers:', e);
    }
  }, [signal, overlays.signals, timeframe]);

  const updateMarkersRef = useRef(updateMarkers);
  useEffect(() => {
    updateMarkersRef.current = updateMarkers;
  }, [updateMarkers]);

  // Update markers whenever signal or overlays.signals toggle changes
  useEffect(() => {
    updateMarkers();
  }, [updateMarkers]);

  // Fetch candles from API for the selected timeframe
  const fetchCandles = useCallback(async () => {
    if (isDisposedRef.current || isFetchingRef.current) return;
    isFetchingRef.current = true;
    setIsLoading(true);
    try {
      const { data, ok } = await apiFetch<{
        candles: CandleData[];
        trend?: import('@/lib/types').TrendInfo;
        passed_signals?: PassedSignal[];
        signal_diagnostics?: SignalDiagnostics;
      }>(`/api/market/candles?resolution=${timeframe}&limit=250`);
      if (timeframe !== selectedTimeframeRef.current) return;
      if (isDisposedRef.current || !chartRef.current || !candleSeriesRef.current) {
        setIsLoading(false);
        return;
      }

      const rawCandles: CandleData[] = ok && data?.candles ? data.candles : [];
      candlesDataRef.current = rawCandles;
      setHasCandleData(rawCandles.length > 0);
      setDiagnosticsState({ timeframe, data: data?.signal_diagnostics ?? null });
      if (data?.passed_signals) {
        setPassedSignalsState({ timeframe, signals: data.passed_signals });
      } else {
        const extracted: PassedSignal[] = rawCandles
          .filter((c) => c.signal === 'BUY' || c.signal === 'SELL')
          .map((c) => ({
            time: c.time,
            action: c.signal as 'BUY' | 'SELL',
            strategy: c.signal_strategy || 'ALPHA-5: SBR-5',
            price: c.signal_price || c.close,
            stop_loss: c.signal_stop,
            take_profit: c.signal_target,
          }));
        setPassedSignalsState({ timeframe, signals: extracted });
      }

      if (rawCandles.length === 0) {
        setIsLoading(false);
        return;
      }

      // Format for Lightweight Charts
      const formattedCandles = rawCandles.map((c) => ({
        time: c.time as Time,
        open: c.open,
        high: c.high,
        low: c.low,
        close: c.close,
      }));

      const formattedVolumes = rawCandles.map((c) => ({
        time: c.time as Time,
        value: c.volume,
        color: c.close >= c.open ? 'rgba(16, 185, 129, 0.35)' : 'rgba(239, 68, 68, 0.35)',
      }));

      safeSetData(candleSeriesRef.current, formattedCandles);
      safeSetData(volumeSeriesRef.current, formattedVolumes);

      // Overlays
      safeSetData(
        ema9Ref.current,
        rawCandles.filter((c) => c.ema9 != null).map((c) => ({ time: c.time as Time, value: c.ema9! }))
      );
      safeSetData(
        ema21Ref.current,
        rawCandles.filter((c) => c.ema21 != null).map((c) => ({ time: c.time as Time, value: c.ema21! }))
      );
      safeSetData(
        ema50Ref.current,
        rawCandles.filter((c) => c.ema50 != null).map((c) => ({ time: c.time as Time, value: c.ema50! }))
      );
      safeSetData(
        ema200Ref.current,
        rawCandles.filter((c) => c.ema200 != null).map((c) => ({ time: c.time as Time, value: c.ema200! }))
      );
      safeSetData(
        vwapRef.current,
        rawCandles.filter((c) => c.vwap != null).map((c) => ({ time: c.time as Time, value: c.vwap! }))
      );
      safeSetData(
        bbUpperRef.current,
        rawCandles.filter((c) => c.bb_upper != null).map((c) => ({ time: c.time as Time, value: c.bb_upper! }))
      );
      safeSetData(
        bbLowerRef.current,
        rawCandles.filter((c) => c.bb_lower != null).map((c) => ({ time: c.time as Time, value: c.bb_lower! }))
      );
      safeSetData(
        sbrPrevHighRef.current,
        rawCandles.filter((c) => c.sbr_prev_high != null).map((c) => ({ time: c.time as Time, value: c.sbr_prev_high! }))
      );
      safeSetData(
        sbrPrevLowRef.current,
        rawCandles.filter((c) => c.sbr_prev_low != null).map((c) => ({ time: c.time as Time, value: c.sbr_prev_low! }))
      );

      // Render markers for passed candles and active live signals
      updateMarkersRef.current(rawCandles);

      // Initialize the active forming bar tracker with the latest candle
      const lastCandle = rawCandles[rawCandles.length - 1];
      setAtrValue(lastCandle.atr ?? null);
      activeBarRef.current = {
        time: lastCandle.time,
        open: lastCandle.open,
        high: lastCandle.high,
        low: lastCandle.low,
        close: lastCandle.close,
        volume: lastCandle.volume,
      };


      // Initialize trend state from server if present
      if (data?.trend) {
        const t = data.trend;
        const timeStr = getNowISTString();
        setLiveTrend({
          timeframe,
          direction: t.direction,
          label: t.direction,
          ema9: t.ema9 || lastCandle.close,
          ema21: t.ema21 || lastCandle.close,
          ema50: t.ema50 || lastCandle.close,
          rsi: t.rsi || 50.0,
          price: lastCandle.close,
          momentum_pct: t.momentum_pct || 0,
          summary: t.summary || '',
          last_updated: timeStr,
        });
      }

      if (chartRef.current && !hasFittedRef.current[timeframe]) {
        chartRef.current.timeScale().fitContent();
        hasFittedRef.current[timeframe] = true;
      }
    } catch (err) {
      console.error('Failed to load chart candles:', err);
    } finally {
      isFetchingRef.current = false;
      if (!isDisposedRef.current) {
        setIsLoading(false);
      }
    }
  }, [timeframe]);

  const fetchCandlesRef = useRef(fetchCandles);
  useEffect(() => { fetchCandlesRef.current = fetchCandles; }, [fetchCandles]);
  useEffect(() => {
    const timer = setInterval(() => { void fetchCandles(); }, 5000);
    return () => clearInterval(timer);
  }, [fetchCandles]);

  // Real-time candle and provisional candle indicator calculation
  useEffect(() => {
    if (
      isDisposedRef.current ||
      !candleSeriesRef.current ||
      !lastPrice ||
      lastPrice <= 0 ||
      !activeBarRef.current
    ) {
      return;
    }

    const barDuration = TIMEFRAME_SECONDS[timeframe] || 300;
    const nowSec = Math.floor(Date.now() / 1000);
    let targetTime = activeBarRef.current.time;

    // Check if the current bar has completed and a new bar needs to be spawned
    if (nowSec >= activeBarRef.current.time + barDuration) {
      // Commit the last provisional close once before starting the next bar.
      const completed = activeBarRef.current;
      const existing = candlesDataRef.current.findIndex(c => c.time === completed.time);
      if (existing >= 0) candlesDataRef.current[existing] = { ...candlesDataRef.current[existing], ...completed };
      else candlesDataRef.current.push({ ...completed });
      targetTime = Math.floor(nowSec / barDuration) * barDuration;
      activeBarRef.current = {
        time: targetTime,
        open: lastPrice,
        high: lastPrice,
        low: lastPrice,
        close: lastPrice,
        volume: 0,
      };
    } else {
      activeBarRef.current.high = Math.max(activeBarRef.current.high, lastPrice);
      activeBarRef.current.low = Math.min(activeBarRef.current.low, lastPrice);
      activeBarRef.current.close = lastPrice;
    }

    safeUpdate(candleSeriesRef.current, {
      time: targetTime as Time,
      open: activeBarRef.current.open,
      high: activeBarRef.current.high,
      low: activeBarRef.current.low,
      close: activeBarRef.current.close,
    });

    const indicators = liveCandleIndicators(candlesDataRef.current, lastPrice, targetTime);
    const curEma9 = indicators.ema9;
    const curEma21 = indicators.ema21;
    const curEma50 = indicators.ema50;

    safeUpdate(ema9Ref.current, { time: targetTime as Time, value: curEma9 });
    safeUpdate(ema21Ref.current, { time: targetTime as Time, value: curEma21 });
    safeUpdate(ema50Ref.current, { time: targetTime as Time, value: curEma50 });

    // Dynamic 1-Second Trend Direction Calculation
    const openPx = activeBarRef.current.open;
    const momPct = openPx > 0 ? ((lastPrice - openPx) / openPx) * 100 : 0;
    const curRsi = indicators.rsi;

    let dir: LiveTrendInfo['direction'] = 'RANGING';
    let label = 'RANGING';
    let summary = `Consolidating: Price oscillating near EMA21 ($${curEma21.toFixed(1)})`;

    if (curEma9 > curEma21 && lastPrice > curEma21) {
      if (curRsi >= 55 || lastPrice > curEma50) {
        dir = 'STRONG_BULLISH';
        label = 'STRONG BULLISH';
        summary = `High Bullish Trend: Price ($${lastPrice.toFixed(1)}) > EMA9 ($${curEma9.toFixed(1)}) > EMA21 ($${curEma21.toFixed(1)})`;
      } else {
        dir = 'BULLISH';
        label = 'BULLISH';
        summary = `Bullish Alignment: Price holding above EMA21 ($${curEma21.toFixed(1)})`;
      }
    } else if (curEma9 < curEma21 && lastPrice < curEma21) {
      if (curRsi <= 45 || lastPrice < curEma50) {
        dir = 'STRONG_BEARISH';
        label = 'STRONG BEARISH';
        summary = `High Bearish Trend: Price ($${lastPrice.toFixed(1)}) < EMA9 ($${curEma9.toFixed(1)}) < EMA21 ($${curEma21.toFixed(1)})`;
      } else {
        dir = 'BEARISH';
        label = 'BEARISH';
        summary = `Bearish Alignment: Price pressured below EMA21 ($${curEma21.toFixed(1)})`;
      }
    }

    const timeStr = getNowISTString();

    setLiveTrend({
      timeframe,
      direction: dir,
      label,
      ema9: curEma9,
      ema21: curEma21,
      ema50: curEma50,
      rsi: curRsi,
      price: lastPrice,
      momentum_pct: momPct,
      summary,
      last_updated: timeStr,
    });
  }, [lastPrice, timeframe]);

  // Periodic 1-second clock trigger to keep IST timestamp fresh
  useEffect(() => {
    const timer = setInterval(() => {
      if (lastPrice > 0 && activeBarRef.current && !isDisposedRef.current) {
        const timeStr = getNowISTString();
        setLiveTrend((prev) => ({
          ...prev,
          price: lastPrice,
          last_updated: timeStr,
        }));
      }
    }, 1000);
    return () => clearInterval(timer);
  }, [lastPrice]);

  // Initialize Lightweight Charts
  useEffect(() => {
    if (!chartContainerRef.current) return;
    isDisposedRef.current = false;

    const chart = createChart(chartContainerRef.current, {
      width: chartContainerRef.current.clientWidth,
      height: chartContainerRef.current.clientHeight || 550,
      layout: {
        background: { type: ColorType.Solid, color: '#0b0e14' },
        textColor: '#8895a7',
        fontFamily: 'monospace',
      },
      grid: {
        vertLines: { color: 'rgba(30, 38, 56, 0.45)' },
        horzLines: { color: 'rgba(30, 38, 56, 0.45)' },
      },
      crosshair: {
        mode: CrosshairMode.Normal,
        vertLine: { color: '#06b6d4', width: 1, style: LineStyle.Dashed },
        horzLine: { color: '#06b6d4', width: 1, style: LineStyle.Dashed },
      },
      localization: {
        locale: 'en-IN',
        dateFormat: 'dd MMM yyyy',
        timeFormatter: (time: unknown) => {
          const ts = typeof time === 'number' ? time : Number(time);
          if (isNaN(ts) || !ts) return '';
          return formatISTFull(ts);
        },
      },
      timeScale: {
        borderColor: '#1e2638',
        timeVisible: true,
        secondsVisible: false,
        tickMarkFormatter: (time: unknown, tickMarkType: TickMarkType) => {
          const ts = typeof time === 'number' ? time : Number(time);
          if (isNaN(ts) || !ts) return null;
          const d = new Date(ts * 1000);
          switch (tickMarkType) {
            case TickMarkType.Year:
              return d.toLocaleDateString('en-IN', { timeZone: 'Asia/Kolkata', year: 'numeric' });
            case TickMarkType.Month:
              return d.toLocaleDateString('en-IN', { timeZone: 'Asia/Kolkata', month: 'short' });
            case TickMarkType.DayOfMonth:
              return d.toLocaleDateString('en-IN', { timeZone: 'Asia/Kolkata', day: 'numeric', month: 'short' });
            case TickMarkType.Time:
              return d.toLocaleTimeString('en-IN', { timeZone: 'Asia/Kolkata', hour: '2-digit', minute: '2-digit', hour12: false });
            case TickMarkType.TimeWithSeconds:
              return d.toLocaleTimeString('en-IN', { timeZone: 'Asia/Kolkata', hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false });
            default:
              return d.toLocaleTimeString('en-IN', { timeZone: 'Asia/Kolkata', hour: '2-digit', minute: '2-digit', hour12: false });
          }
        },
      },
      rightPriceScale: {
        borderColor: '#1e2638',
        autoScale: true,
      },
    });

    chartRef.current = chart;

    // Volume Series (bottom pane)
    const volumeSeries = chart.addSeries(HistogramSeries, {
      color: '#26a69a',
      priceFormat: { type: 'volume' },
      priceScaleId: '',
    });
    volumeSeries.priceScale().applyOptions({
      scaleMargins: { top: 0.82, bottom: 0 },
    });
    volumeSeriesRef.current = volumeSeries;

    // Candlestick Series
    const candleSeries = chart.addSeries(CandlestickSeries, {
      upColor: '#10b981',
      downColor: '#ef4444',
      borderVisible: false,
      wickUpColor: '#10b981',
      wickDownColor: '#ef4444',
    });
    candleSeriesRef.current = candleSeries;

    // Series markers primitive for passed candles & live signals
    seriesMarkersRef.current = createSeriesMarkers(candleSeries, []);

    // Overlay Lines
    ema9Ref.current = chart.addSeries(LineSeries, {
      color: '#3b82f6',
      lineWidth: 1,
      priceLineVisible: false,
      title: 'EMA 9',
    });

    ema21Ref.current = chart.addSeries(LineSeries, {
      color: '#f59e0b',
      lineWidth: 1,
      priceLineVisible: false,
      title: 'EMA 21',
    });

    ema50Ref.current = chart.addSeries(LineSeries, {
      color: '#8b5cf6',
      lineWidth: 1,
      priceLineVisible: false,
      title: 'EMA 50',
    });

    ema200Ref.current = chart.addSeries(LineSeries, {
      color: '#9ca3af',
      lineWidth: 2,
      priceLineVisible: false,
      title: 'EMA 200',
    });

    vwapRef.current = chart.addSeries(LineSeries, {
      color: '#06b6d4',
      lineWidth: 1,
      lineStyle: LineStyle.Solid,
      priceLineVisible: false,
      title: 'VWAP',
    });

    bbUpperRef.current = chart.addSeries(LineSeries, {
      color: 'rgba(59, 130, 246, 0.6)',
      lineWidth: 1,
      lineStyle: LineStyle.Dotted,
      priceLineVisible: false,
    });

    bbLowerRef.current = chart.addSeries(LineSeries, {
      color: 'rgba(59, 130, 246, 0.6)',
      lineWidth: 1,
      lineStyle: LineStyle.Dotted,
      priceLineVisible: false,
    });

    sbrPrevHighRef.current = chart.addSeries(LineSeries, {
      color: '#f43f5e',
      lineWidth: 1,
      lineStyle: LineStyle.Dashed,
      priceLineVisible: false,
      title: 'SBR Range High',
    });

    sbrPrevLowRef.current = chart.addSeries(LineSeries, {
      color: '#10b981',
      lineWidth: 1,
      lineStyle: LineStyle.Dashed,
      priceLineVisible: false,
      title: 'SBR Range Low',
    });

    // Crosshair move listener for tooltip
    chart.subscribeCrosshairMove((param) => {
      if (!param || !param.time || !param.seriesData || isDisposedRef.current) {
        setHoveredCandle(null);
        return;
      }
      const data = param.seriesData.get(candleSeries) as import('lightweight-charts').CandlestickData<Time> | undefined;
      if (data) {
        const tSec = Number(param.time);
        const matched = candlesDataRef.current.find((c) => c.time === tSec);
        setHoveredCandle({
          time: tSec,
          open: data.open,
          high: data.high,
          low: data.low,
          close: data.close,
          volume: matched?.volume ?? 0,
          signal: matched?.signal ?? null,
          signal_action: matched?.signal_action ?? null,
          signal_strategy: matched?.signal_strategy ?? null,
          signal_price: matched?.signal_price ?? null,
          signal_stop: matched?.signal_stop ?? null,
          signal_target: matched?.signal_target ?? null,
          signal_outcome: matched?.signal_outcome ?? null,
          signal_pnl_r: matched?.signal_pnl_r ?? null,
          signal_exit_price: matched?.signal_exit_price ?? null,
          signal_exit_bars: matched?.signal_exit_bars ?? null,
        });
      }
    });

    // Resize observer
    const handleResize = () => {
      if (chartContainerRef.current && chartRef.current && !isDisposedRef.current) {
        try {
          chartRef.current.applyOptions({
            width: chartContainerRef.current.clientWidth,
            height: chartContainerRef.current.clientHeight,
          });
        } catch {
          // Ignore
        }
      }
    };
    window.addEventListener('resize', handleResize);

    void fetchCandlesRef.current();

    return () => {
      isDisposedRef.current = true;
      window.removeEventListener('resize', handleResize);

      // Clean up price lines safely
      safeRemovePriceLine(stopLineRef);
      safeRemovePriceLine(targetLineRef);
      safeRemovePriceLine(entryLineRef);

      if (seriesMarkersRef.current) {
        try {
          seriesMarkersRef.current.detach();
        } catch {
          // Ignore
        }
        seriesMarkersRef.current = null;
      }

      try {
        chart.remove();
      } catch {
        // Ignore
      }

      chartRef.current = null;
      candleSeriesRef.current = null;
      volumeSeriesRef.current = null;
      ema9Ref.current = null;
      ema21Ref.current = null;
      ema50Ref.current = null;
      ema200Ref.current = null;
      vwapRef.current = null;
      bbUpperRef.current = null;
      bbLowerRef.current = null;
      sbrPrevHighRef.current = null;
      sbrPrevLowRef.current = null;
      activeBarRef.current = null;
    };
  }, []); // Chart instance created strictly once on mount

  // Fetch candles only when timeframe actively changes
  const prevTimeframeRef = useRef(timeframe);
  useEffect(() => {
    if (prevTimeframeRef.current !== timeframe) {
      prevTimeframeRef.current = timeframe;
      // Clear the previous timeframe's data and markers while the new request loads.
      candlesDataRef.current = [];
      activeBarRef.current = null;
      seriesMarkersRef.current?.setMarkers([]);
      for (const series of [candleSeriesRef.current, volumeSeriesRef.current,
        ema9Ref.current, ema21Ref.current, ema50Ref.current, ema200Ref.current,
        vwapRef.current, bbUpperRef.current, bbLowerRef.current,
        sbrPrevHighRef.current, sbrPrevLowRef.current]) series?.setData([]);
      fetchCandles();
    }
  }, [timeframe, fetchCandles]);

  // Update visibility of overlay series
  useEffect(() => {
    if (isDisposedRef.current) return;
    try {
      ema9Ref.current?.applyOptions({ visible: overlays.ema9 });
      ema21Ref.current?.applyOptions({ visible: overlays.ema21 });
      ema50Ref.current?.applyOptions({ visible: overlays.ema50 });
      ema200Ref.current?.applyOptions({ visible: overlays.ema200 });
      vwapRef.current?.applyOptions({ visible: overlays.vwap });
      bbUpperRef.current?.applyOptions({ visible: overlays.bollinger });
      bbLowerRef.current?.applyOptions({ visible: overlays.bollinger });
      sbrPrevHighRef.current?.applyOptions({ visible: overlays.sbrLevels });
      sbrPrevLowRef.current?.applyOptions({ visible: overlays.sbrLevels });
      volumeSeriesRef.current?.applyOptions({ visible: overlays.volume });
    } catch {
      // Ignore
    }
  }, [overlays]);

  // Update active price lines for Stop Loss and Take Profit
  useEffect(() => {
    if (isDisposedRef.current || !candleSeriesRef.current) return;

    safeRemovePriceLine(stopLineRef);
    safeRemovePriceLine(targetLineRef);
    safeRemovePriceLine(entryLineRef);

    if (signal && signal.action !== 'WAIT' && signal.action !== 'HALTED / DATA UNSAFE') {
      try {
        if (signal.entry_price) {
          entryLineRef.current = candleSeriesRef.current.createPriceLine({
            price: signal.entry_price,
            color: '#06b6d4',
            lineWidth: 2,
            lineStyle: LineStyle.Solid,
            axisLabelVisible: true,
            title: `ENTRY $${signal.entry_price}`,
          });
        }
        if (signal.stop_loss) {
          stopLineRef.current = candleSeriesRef.current.createPriceLine({
            price: signal.stop_loss,
            color: '#ef4444',
            lineWidth: 2,
            lineStyle: LineStyle.Dashed,
            axisLabelVisible: true,
            title: `STOP $${signal.stop_loss}`,
          });
        }
        if (signal.take_profit) {
          targetLineRef.current = candleSeriesRef.current.createPriceLine({
            price: signal.take_profit,
            color: '#10b981',
            lineWidth: 2,
            lineStyle: LineStyle.Dashed,
            axisLabelVisible: true,
            title: `TARGET $${signal.take_profit} (1.8R)`,
          });
        }
      } catch {
        // Ignore
      }
    }
  }, [signal]);

  return (
    <div className="flex flex-col h-full bg-[#0b0e14] border border-[#1e2638] rounded-xl overflow-hidden shadow-xl select-none">
      {/* 1. Unified Primary Header: Instrument, Multi-Timeframe Selector (with live trend dots) & 1s Live Trend Box */}
      <div className="h-11 min-h-[44px] max-h-[44px] px-3 bg-[#0c1017] border-b border-[#1b2333] flex items-center justify-between gap-3 overflow-x-auto no-scrollbar flex-nowrap">
        {/* Left: BTCUSD Badge + Single Unified Timeframe Selector with Live Trend Dots */}
        <div className="flex items-center gap-2 shrink-0">
          <div className="flex items-center gap-1.5 px-2 py-1 bg-[#141b29] border border-[#232e42] rounded text-xs font-mono font-bold text-white shrink-0">
            <span className="text-cyan-400">BTCUSD</span>
            <span className="text-gray-500 font-normal">|</span>
            <span className="text-gray-300">{timeframe}</span>
            <span className="text-gray-500 font-normal">|</span>
            <span className="text-amber-400 text-[10px] font-semibold tracking-wide">IST</span>
          </div>

          <div className="flex items-center gap-1 bg-[#101520] p-0.5 rounded border border-[#1e2638] shrink-0">
            {TIMEFRAMES.map((tf) => {
              const tInfo = multiTrends[tf];
              const dir = tInfo?.direction || 'RANGING';
              const isBull = dir === 'BULLISH';
              const isBear = dir === 'BEARISH';
              const isSelected = timeframe === tf;

              return (
                <button
                  key={tf}
                  onClick={() => onTimeframeChange(tf)}
                  className={`flex items-center gap-1 px-2 py-1 text-xs font-mono font-semibold rounded transition-all ${
                    isSelected
                      ? 'bg-cyan-500/20 text-cyan-300 border border-cyan-500/40 shadow-sm'
                      : 'text-gray-400 hover:text-gray-200 hover:bg-[#182030] border border-transparent'
                  }`}
                  title={`${tf} Timeframe: ${dir} (Click to switch)`}
                >
                  <span>{tf}</span>
                  <span
                    className={`w-1.5 h-1.5 rounded-full shrink-0 ${
                      isBull
                        ? 'bg-emerald-400 shadow-[0_0_5px_#10b981]'
                        : isBear
                        ? 'bg-rose-400 shadow-[0_0_5px_#f43f5e]'
                        : 'bg-amber-400'
                    }`}
                  />
                </button>
              );
            })}
          </div>
        </div>

        {/* Right: Institutional 1s Live Trend Box (Zero Layout Shift, Fixed Padding, Tabular Digits) */}
        <div className="flex items-center gap-2 shrink-0">
          <div className="flex items-center gap-2 px-2.5 py-1 rounded bg-[#131a27] border border-[#232e42] shrink-0">
            {/* Live Pulsing Dot */}
            <span className="relative flex h-2 w-2 shrink-0">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-cyan-400 opacity-75"></span>
              <span className="relative inline-flex rounded-full h-2 w-2 bg-cyan-500"></span>
            </span>

            {/* 1s Label */}
            <span className="text-[10px] font-mono text-cyan-400 font-bold uppercase tracking-wider shrink-0">
              {timeframe} Trend:
            </span>

            {/* Trend Direction Badge */}
            <span
              className={`text-xs font-mono font-bold px-2 py-0.5 rounded flex items-center gap-1 shrink-0 ${
                liveTrend.direction.includes('BULLISH')
                  ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30'
                  : liveTrend.direction.includes('BEARISH')
                  ? 'bg-rose-500/20 text-rose-400 border border-rose-500/30'
                  : 'bg-amber-500/20 text-amber-400 border border-amber-500/30'
              }`}
            >
              {liveTrend.direction.includes('BULLISH') ? (
                <TrendingUp className="w-3 h-3 shrink-0" />
              ) : liveTrend.direction.includes('BEARISH') ? (
                <TrendingDown className="w-3 h-3 shrink-0" />
              ) : (
                <Minus className="w-3 h-3 shrink-0" />
              )}
              <span>{liveTrend.label}</span>
            </span>

            {/* Live Price (Tabular Nums for Zero Width Shift) */}
            <span className="text-xs font-mono font-bold text-white tabular-nums shrink-0">
              ${liveTrend.price.toFixed(1)}
            </span>

            {/* Momentum % */}
            <span
              className={`text-xs font-mono tabular-nums shrink-0 ${
                liveTrend.momentum_pct >= 0 ? 'text-emerald-400' : 'text-rose-400'
              }`}
            >
              ({liveTrend.momentum_pct >= 0 ? '+' : ''}
              {liveTrend.momentum_pct.toFixed(2)}%)
            </span>

            <span className="text-gray-600 hidden sm:inline">|</span>

            {/* Dynamic Telemetry: EMA 9, EMA 21, RSI */}
            <div className="hidden xl:flex items-center gap-2.5 text-[11px] font-mono text-gray-400 shrink-0">
              <span>
                EMA9: <span className="text-blue-400 font-semibold tabular-nums">${liveTrend.ema9.toFixed(1)}</span>
              </span>
              <span>
                EMA21: <span className="text-amber-400 font-semibold tabular-nums">${liveTrend.ema21.toFixed(1)}</span>
              </span>
              <span>
                RSI: <span className="text-purple-400 font-semibold tabular-nums">{liveTrend.rsi.toFixed(1)}</span>
              </span>
            </div>

            <span className="text-gray-600 hidden 2xl:inline">|</span>

            {/* IST Timestamp Badge */}
            <span className="text-cyan-400 text-[10px] font-mono tabular-nums bg-cyan-950/40 border border-cyan-800/40 px-2 py-0.5 rounded hidden 2xl:inline shrink-0">
              {liveTrend.last_updated}
            </span>
          </div>
        </div>
      </div>

      {/* 2. Secondary Sub-Toolbar: OHLC Bar Inspector & Technical Indicator Toggles */}
      <div className="h-9 min-h-[36px] max-h-[36px] px-3 bg-[#0e131d] border-b border-[#161d2b] flex items-center justify-between gap-3 text-xs font-mono text-gray-400 overflow-x-auto no-scrollbar flex-nowrap">
        {/* Left: OHLC Candle Inspector */}
        <div className="flex items-center gap-3 shrink-0">
          {hoveredCandle ? (
            <div className="flex items-center gap-2.5 text-[11px]">
              <span className="text-gray-500 font-semibold">CANDLE:</span>
              <span className="text-cyan-400 font-semibold bg-cyan-950/40 px-1.5 py-0.5 rounded border border-cyan-800/40 tabular-nums">
                {formatISTDate(hoveredCandle.time)} {formatISTTime(hoveredCandle.time)} IST
              </span>
              <span>O: <span className="text-white tabular-nums">${hoveredCandle.open.toFixed(1)}</span></span>
              <span>H: <span className="text-white tabular-nums">${hoveredCandle.high.toFixed(1)}</span></span>
              <span>L: <span className="text-white tabular-nums">${hoveredCandle.low.toFixed(1)}</span></span>
              <span>
                C:{' '}
                <span
                  className={`tabular-nums font-bold ${
                    hoveredCandle.close >= hoveredCandle.open ? 'text-emerald-400' : 'text-rose-400'
                  }`}
                >
                  ${hoveredCandle.close.toFixed(1)}
                </span>
              </span>

              {/* Passed Strategy Signal Badge on hovered candle */}
              {hoveredCandle.signal && (
                <span
                  className={`px-2 py-0.5 rounded text-[10px] font-bold tracking-wide flex items-center gap-1.5 shadow-sm ${
                    hoveredCandle.signal === 'BUY'
                      ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/40 shadow-emerald-500/10'
                      : 'bg-rose-500/20 text-rose-400 border border-rose-500/40 shadow-rose-500/10'
                  }`}
                >
                  <span>{hoveredCandle.signal === 'BUY' ? '▲ BUY' : '▼ SELL'}</span>
                  {hoveredCandle.signal_outcome === 'TARGET_HIT' && (
                    <span className="px-1 py-0.2 rounded bg-emerald-500/30 text-emerald-300 font-bold border border-emerald-500/50">
                      🎯 TARGET ({hoveredCandle.signal_pnl_r ?? '?'}R net)
                    </span>
                  )}
                  {hoveredCandle.signal_outcome === 'BREAKEVEN_WIN' && (
                    <span className="px-1 py-0.2 rounded bg-sky-500/30 text-sky-300 font-bold border border-sky-500/50">
                      🔒 BREAKEVEN LOCK (+{hoveredCandle.signal_pnl_r ?? '0.1'}R net)
                    </span>
                  )}
                  {hoveredCandle.signal_outcome === 'STOP_HIT' && (
                    <span className="px-1 py-0.2 rounded bg-rose-500/30 text-rose-300 font-bold border border-rose-500/50">
                      🛑 STOPPED ({hoveredCandle.signal_pnl_r ?? '?'}R net)
                    </span>
                  )}
                  {hoveredCandle.signal_outcome === 'ACTIVE' && (
                    <span className="px-1 py-0.2 rounded bg-cyan-500/30 text-cyan-300 font-bold border border-cyan-500/50">
                      ⏳ ACTIVE
                    </span>
                  )}
                  {hoveredCandle.signal_outcome === 'TIME_EXIT' && (
                    <span className="px-1 py-0.2 rounded bg-amber-500/30 text-amber-300 font-bold border border-amber-500/50">
                      ⏱ EXIT ({hoveredCandle.signal_pnl_r ?? '?'}R net)
                    </span>
                  )}
                  {hoveredCandle.signal_price && (
                    <span className="text-white font-mono">${hoveredCandle.signal_price.toFixed(1)}</span>
                  )}
                  {hoveredCandle.signal_stop && (
                    <span className="text-rose-300 font-mono">SL ${hoveredCandle.signal_stop.toFixed(1)}</span>
                  )}
                  {hoveredCandle.signal_target && (
                    <span className="text-emerald-300 font-mono">TP ${hoveredCandle.signal_target.toFixed(1)}</span>
                  )}
                </span>
              )}
            </div>
          ) : (
            <div className="flex items-center gap-2 text-[11px]">
              <span className="text-gray-500">LIVE TICK:</span>
              <span className="text-white font-bold tabular-nums">${lastPrice.toFixed(1)}</span>
              <span className="text-gray-600">|</span>
              <span className="text-gray-400">ATR 14:</span>
              <span className="text-cyan-400 tabular-nums">
                {atrValue !== null ? `$${atrValue.toFixed(1)}` : '—'}
              </span>
              {passedSignalsList.length > 0 && (
                <>
                  <span className="text-gray-600">|</span>
                  <span className="text-emerald-400 font-semibold flex items-center gap-1.5">
                    <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
                    <span>{passedSignalsList.length} Passed Setups</span>
                    <span className="text-gray-400 font-normal">
                      ({passedSignalsList.filter(s => s.outcome === 'TARGET_HIT').length}🎯 Target · {passedSignalsList.filter(s => s.outcome === 'STOP_HIT').length}🛑 Stopped)
                    </span>
                  </span>
                </>
              )}
            </div>
          )}
        </div>

        {/* Right: Technical Overlays Toggle Bar */}
        <div className="flex items-center gap-1 text-[11px] font-mono shrink-0">
          <span className="text-gray-500 flex items-center gap-1 mr-1 text-[10px] uppercase tracking-wider">
            <Layers className="w-3 h-3" /> Overlays:
          </span>

          <button
            onClick={() => toggleOverlay('signals')}
            className={`px-1.5 py-0.5 rounded border text-[10px] font-semibold transition-all flex items-center gap-1 ${
              overlays.signals
                ? 'bg-emerald-500/20 text-emerald-300 border-emerald-500/40 shadow-[0_0_8px_rgba(16,185,129,0.2)]'
                : 'text-gray-500 border-transparent hover:text-gray-300'
            }`}
            title="Toggle Strategy Signals & Passed Candle Markers"
          >
            <span className={`w-1.5 h-1.5 rounded-full ${overlays.signals ? 'bg-emerald-400' : 'bg-gray-600'}`} />
            <span>Signals {passedSignalsList.length > 0 ? `(${passedSignalsList.length})` : ''}</span>
          </button>

          <button
            onClick={() => toggleOverlay('ema9')}
            className={`px-1.5 py-0.5 rounded border text-[10px] font-semibold transition-colors ${
              overlays.ema9
                ? 'bg-blue-500/15 text-blue-400 border-blue-500/30'
                : 'text-gray-500 border-transparent hover:text-gray-300'
            }`}
          >
            EMA 9
          </button>

          <button
            onClick={() => toggleOverlay('ema21')}
            className={`px-1.5 py-0.5 rounded border text-[10px] font-semibold transition-colors ${
              overlays.ema21
                ? 'bg-amber-500/15 text-amber-400 border-amber-500/30'
                : 'text-gray-500 border-transparent hover:text-gray-300'
            }`}
          >
            EMA 21
          </button>

          <button
            onClick={() => toggleOverlay('ema50')}
            className={`px-1.5 py-0.5 rounded border text-[10px] font-semibold transition-colors ${
              overlays.ema50
                ? 'bg-purple-500/15 text-purple-400 border-purple-500/30'
                : 'text-gray-500 border-transparent hover:text-gray-300'
            }`}
          >
            EMA 50
          </button>

          <button
            onClick={() => toggleOverlay('ema200')}
            className={`px-1.5 py-0.5 rounded border text-[10px] font-semibold transition-colors ${
              overlays.ema200
                ? 'bg-gray-400/15 text-gray-300 border-gray-400/30'
                : 'text-gray-500 border-transparent hover:text-gray-300'
            }`}
          >
            EMA 200
          </button>

          <button
            onClick={() => toggleOverlay('vwap')}
            className={`px-1.5 py-0.5 rounded border text-[10px] font-semibold transition-colors ${
              overlays.vwap
                ? 'bg-cyan-500/15 text-cyan-400 border-cyan-500/30'
                : 'text-gray-500 border-transparent hover:text-gray-300'
            }`}
          >
            VWAP
          </button>

          <button
            onClick={() => toggleOverlay('bollinger')}
            className={`px-1.5 py-0.5 rounded border text-[10px] font-semibold transition-colors ${
              overlays.bollinger
                ? 'bg-indigo-500/15 text-indigo-400 border-indigo-500/30'
                : 'text-gray-500 border-transparent hover:text-gray-300'
            }`}
          >
            BB
          </button>

          <button
            onClick={() => toggleOverlay('sbrLevels')}
            className={`px-1.5 py-0.5 rounded border text-[10px] font-semibold transition-colors ${
              overlays.sbrLevels
                ? 'bg-emerald-500/15 text-emerald-400 border-emerald-500/30'
                : 'text-gray-500 border-transparent hover:text-gray-300'
            }`}
          >
            SBR Range
          </button>

          <button
            onClick={fetchCandles}
            className="p-1 rounded text-gray-400 hover:text-white hover:bg-[#1a2233] ml-1"
            title="Refresh Candles"
          >
            <RefreshCw className={`w-3 h-3 ${isLoading ? 'animate-spin' : ''}`} />
          </button>

          <div className="flex items-center gap-1.5 pl-2 ml-1 border-l border-[#1e2638] text-[10px] text-gray-400">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
            <span className="hidden sm:inline">1s Live</span>
          </div>
        </div>
      </div>

      {diagnostics && (
        <div className="px-3 py-1.5 border-b border-[#1e2638] text-[11px] font-mono text-gray-400 flex flex-wrap gap-x-3 gap-y-1">
          <span className="text-cyan-300">{timeframe} historical signals: {diagnostics.qualified_count}</span>
          {!overlays.signals && <span className="text-amber-300">Arrows hidden — enable Signals above.</span>}
          {diagnostics.qualified_count === 0 && <span>No qualifying setups in the loaded candles.</span>}
          {diagnostics.filtered_count > 0 && (
            <span>Filtered: {diagnostics.filtered_count} · {Object.entries(diagnostics.filtered_reasons).map(([reason, count]) => `${reason}: ${count}`).join(' · ')}</span>
          )}
          {diagnostics.candidate_count === 0 && <span>Big-move volume, candle strength and momentum rules were not met.</span>}
        </div>
      )}

      {/* 4. Chart Canvas Area */}
      <div className="relative flex-1 min-h-[500px] w-full" ref={chartContainerRef}>
        {isLoading && !hasCandleData && (
          <div className="absolute inset-0 z-10 flex items-center justify-center bg-[#0b0e14]/60 backdrop-blur-sm">
            <div className="flex items-center gap-2 text-xs font-mono text-cyan-400">
              <RefreshCw className="w-4 h-4 animate-spin" />
              <span>Fetching genuine candles from Delta Exchange...</span>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
