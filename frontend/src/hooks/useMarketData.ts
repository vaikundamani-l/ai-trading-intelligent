'use client';

import { useState, useEffect, useRef, useCallback } from 'react';
import { MarketState, SignalDecision } from '@/lib/types';
import { apiFetch, getWsUrl } from '@/lib/api';

export function useMarketData(resolution = '5m') {
  const [market, setMarket] = useState<MarketState | null>(null);
  const [signal, setSignal] = useState<SignalDecision | null>(null);
  const [isConnected, setIsConnected] = useState<boolean>(false);
  const [backendAvailable, setBackendAvailable] = useState<boolean>(true);
  const [utcTime, setUtcTime] = useState<string>('');
  const [istTime, setIstTime] = useState<string>('');

  const requestVersionRef = useRef(0);
  const inFlightRequestRef = useRef<{ resolution: string; version: number } | null>(null);
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
    if (inFlightRequestRef.current?.resolution === resolution) return;
    const version = ++requestVersionRef.current;
    inFlightRequestRef.current = { resolution, version };
    try {
      const [tickerRes, signalRes] = await Promise.all([
        apiFetch<MarketState>('/api/market/ticker'),
        apiFetch<SignalDecision>(`/api/signals/current?resolution=${encodeURIComponent(resolution)}`),
      ]);

      if (version !== requestVersionRef.current) return;

      if (tickerRes.ok && tickerRes.data) {
        setMarket(tickerRes.data);
        setBackendAvailable(true);
      } else {
        setBackendAvailable(false);
      }

      if (signalRes.ok && signalRes.data) {
        setSignal(signalRes.data);
      } else {
        setSignal(null);
      }
    } catch {
      if (version === requestVersionRef.current) setBackendAvailable(false);
    } finally {
      if (inFlightRequestRef.current?.version === version) inFlightRequestRef.current = null;
    }
  }, [resolution]);

  const invalidateRequests = useCallback(() => {
    requestVersionRef.current++;
    inFlightRequestRef.current = null;
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
              if (resolution === '5m' && data.signal && (data.signal.resolution || '5m') === resolution) setSignal(data.signal);
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
      if (resolution !== '5m' || wsRef.current?.readyState !== WebSocket.OPEN) {
        fetchRestData();
      }
    }, 3000);

    return () => {
      clearTimeout(initial);
      isMounted = false;
      invalidateRequests();
      if (wsRef.current) wsRef.current.close();
      if (reconnectTimeoutRef.current) clearTimeout(reconnectTimeoutRef.current);
      clearInterval(pollInterval);
    };
  }, [fetchRestData, resolution, invalidateRequests]);

  return {
    market,
    signal: (signal?.resolution || '5m') === resolution ? signal : null,
    isConnected,
    backendAvailable,
    utcTime,
    istTime,
    refreshData: fetchRestData,
  };
}
