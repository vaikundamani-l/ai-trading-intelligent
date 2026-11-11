/**
 * Resilient API client for BTC Quantum Intelligence
 * Uses relative `/api` paths by default, routed via Next.js rewrites to the FastAPI backend,
 * or direct NEXT_PUBLIC_API_URL when explicitly configured.
 */

export const getApiBase = (): string => {
  if (typeof window === 'undefined') {
    return process.env.BACKEND_INTERNAL_URL || 'http://127.0.0.1:8000';
  }
  return process.env.NEXT_PUBLIC_API_URL || '';
};

export const getAuthToken = (): string | null => {
  if (typeof window === 'undefined') {
    return process.env.API_AUTH_TOKEN || null;
  }
  try {
    return localStorage.getItem('API_AUTH_TOKEN') || process.env.NEXT_PUBLIC_API_KEY || null;
  } catch {
    return null;
  }
};

export const getWsUrl = (): string => {
  const token = getAuthToken();
  const tokenParam = token ? `?token=${encodeURIComponent(token)}` : '';

  if (typeof window === 'undefined') {
    return `ws://127.0.0.1:8000/ws${tokenParam}`;
  }
  if (process.env.NEXT_PUBLIC_WS_URL) {
    const baseWs = process.env.NEXT_PUBLIC_WS_URL;
    return token ? `${baseWs}${baseWs.includes('?') ? '&' : '?'}token=${encodeURIComponent(token)}` : baseWs;
  }
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const host = window.location.hostname;
  const port = window.location.port;

  // Local Next.js dev server on port 3000 -> direct to backend on 8000
  if (port === '3000') {
    return `${protocol}//${host}:8000/ws${tokenParam}`;
  }

  // Unified production port (80, 443, reverse proxy)
  return `${protocol}//${window.location.host}/ws${tokenParam}`;
};

export async function apiFetch<T>(
  endpoint: string,
  options?: RequestInit
): Promise<{ data: T | null; error: string | null; ok: boolean }> {
  try {
    const base = getApiBase();
    const cleanEndpoint = endpoint.startsWith('/') ? endpoint : `/${endpoint}`;
    const url = `${base}${cleanEndpoint}`;

    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
      ...((options?.headers as Record<string, string>) || {}),
    };

    const token = getAuthToken();
    if (token && !headers['X-API-Key'] && !headers['Authorization']) {
      headers['X-API-Key'] = token;
    }

    const res = await fetch(url, {
      ...options,
      headers,
    });

    if (!res.ok) {
      let errorDetail = `HTTP ${res.status}`;
      try {
        const errorData = await res.json();
        errorDetail = errorData.detail || errorData.error || errorDetail;
      } catch {
        // Response was not JSON
      }
      return { data: null, error: errorDetail, ok: false };
    }

    const data = (await res.json()) as T;
    return { data, error: null, ok: true };
  } catch (caught: unknown) {
    const err = caught instanceof Error ? caught : new Error("Request failed");
    // NetworkError when backend server is down or unreachable
    const isNetwork =
      err?.name === 'TypeError' ||
      err?.message?.includes('NetworkError') ||
      err?.message?.includes('fetch');

    const msg = isNetwork
      ? 'Backend service unreachable. Verify backend is running.'
      : err?.message || 'Network request failed';

    return { data: null, error: msg, ok: false };
  }
}
