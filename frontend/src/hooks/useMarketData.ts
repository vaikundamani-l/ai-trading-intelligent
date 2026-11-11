'use client';

import { useState, useEffect, useRef, useCallback } from 'react';
import { MarketState, SignalDecision, AIPredictions, PaperPortfolio } from '@/lib/types';
import { apiFetch, getWsUrl } from '@/lib/api';

export function useMarketData() {
  const [market, setMarket] = useState<MarketState | null>(null);
  const [signal, setSignal] = useState<SignalDecision | null>(null);
  const [predictions, setPredictions] = useState<AIPredictions | null>(null);
  const [portfolio, setPortfolio] = useState<PaperPortfolio | null>(null);
  const [isConnected, setIsConnected] = useState<boolean>(false);
  const [backendAvailable, setBackendAvailable] = useState<boolean>(true);
  const [utcTime, setUtcTime] = useState<string>('');
  const [istTime, setIstTime] = useState<string>('');

  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null);

  // Time updater: keeps UTC and IST clocks synchronized
  useEffect(() => {
    const updateClocks = () => {
      const now = new Date();
      setUtcTime(
        now.toLocaleTimeString('en-US', {
          timeZone: 'UTC',
          hour12: false,
          hour: '2-digit',
          minute: '2-digit',
          second: '2-digit',
        }) + ' UTC'
      );
      setIstTime(
        now.toLocaleTimeString('en-US', {
          timeZone: 'Asia/Kolkata',
          hour12: false,
          hour: '2-digit',
          minute: '2-digit',
          second: '2-digit',
        }) + ' IST'
      );
    };
    updateClocks();
    const interval = setInterval(updateClocks, 1000);
    return () => clearInterval(interval);
  }, []);

  // REST Fallback fetcher using resilient apiFetch
  const fetchRestData = useCallback(async () => {
    try {
      const [tickerRes, signalRes, predsRes, portRes] = await Promise.all([
        apiFetch<MarketState>('/api/market/ticker'),
        apiFetch<SignalDecision>('/api/signals/current'),
        apiFetch<AIPredictions>('/api/predictions'),
        apiFetch<PaperPortfolio>('/api/paper-trade/portfolio'),
      ]);

      if (tickerRes.ok && tickerRes.data) {
        setMarket(tickerRes.data);
        setBackendAvailable(true);
      } else {
        setBackendAvailable(false);
      }

      if (signalRes.ok && signalRes.data) {
        setSignal(signalRes.data);
      }
      if (predsRes.ok && predsRes.data) {
        setPredictions(predsRes.data);
      }
      if (portRes.ok && portRes.data) {
        setPortfolio(portRes.data);
      }
    } catch {
      setBackendAvailable(false);
    }
  }, []);

  // WebSocket Connection
  useEffect(() => {
    let isMounted = true;

    const connectWebSocket = () => {
      if (!isMounted) return;
      try {
        const wsUrl = getWsUrl();
        const ws = new WebSocket(wsUrl);
        wsRef.current = ws;

        ws.onopen = () => {
          if (!isMounted) return;
          setIsConnected(true);
          setBackendAvailable(true);
        };

        ws.onmessage = (event) => {
          if (!isMounted) return;
          try {
            const data = JSON.parse(event.data);
            if (data.type === 'REALTIME_TICK' || data.type === 'INITIAL_STATE') {
              if (data.market) setMarket(data.market);
              if (data.signal) setSignal(data.signal);
              if (data.predictions) setPredictions(data.predictions);
              if (data.portfolio) setPortfolio(data.portfolio);
              setBackendAvailable(true);
            }
          } catch {
            // Ignore parse errors on malformed frames
          }
        };

        ws.onerror = () => {
          // Fall back gracefully to REST without throwing unhandled exceptions
          setIsConnected(false);
        };

        ws.onclose = () => {
          if (!isMounted) return;
          setIsConnected(false);
          reconnectTimeoutRef.current = setTimeout(connectWebSocket, 3000);
        };
      } catch {
        setIsConnected(false);
        reconnectTimeoutRef.current = setTimeout(connectWebSocket, 4000);
      }
    };

    const initial = setTimeout(fetchRestData, 0);
    connectWebSocket();

    const pollInterval = setInterval(() => {
      if (wsRef.current?.readyState !== WebSocket.OPEN) {
        fetchRestData();
      }
    }, 3000);

    return () => {
      clearTimeout(initial);
      isMounted = false;
      if (wsRef.current) wsRef.current.close();
      if (reconnectTimeoutRef.current) clearTimeout(reconnectTimeoutRef.current);
      clearInterval(pollInterval);
    };
  }, [fetchRestData]);

  return {
    market,
    signal,
    predictions,
    portfolio,
    isConnected,
    backendAvailable,
    utcTime,
    istTime,
    refreshData: fetchRestData,
  };
}
