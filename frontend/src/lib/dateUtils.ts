/**
 * Date and Time utilities for Indian Standard Time (IST, UTC+5:30)
 */

export const formatISTDate = (ts: number): string => {
  if (!ts) return '';
  const d = new Date(ts * 1000);
  return d.toLocaleDateString('en-IN', {
    timeZone: 'Asia/Kolkata',
    day: '2-digit',
    month: 'short',
    year: 'numeric',
  });
};

export const formatISTTime = (ts: number, includeSeconds = false): string => {
  if (!ts) return '';
  const d = new Date(ts * 1000);
  return d.toLocaleTimeString('en-IN', {
    timeZone: 'Asia/Kolkata',
    hour: '2-digit',
    minute: '2-digit',
    second: includeSeconds ? '2-digit' : undefined,
    hour12: false,
  });
};

export const formatISTFull = (ts: number): string => {
  if (!ts) return '';
  return `${formatISTDate(ts)} ${formatISTTime(ts, false)} IST`;
};

export const formatISTFromUTC = (utcStr: string): string => {
  if (!utcStr) return '—';
  try {
    const cleanStr = utcStr.trim().replace(' ', 'T');
    const iso = cleanStr.endsWith('Z') || cleanStr.includes('+') ? cleanStr : `${cleanStr}Z`;
    const d = new Date(iso);
    if (isNaN(d.getTime())) return utcStr;
    return (
      d.toLocaleString('en-IN', {
        timeZone: 'Asia/Kolkata',
        day: '2-digit',
        month: 'short',
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
        hour12: false,
      }) + ' IST'
    );
  } catch {
    return utcStr;
  }
};

export const getNowISTString = (): string => {
  const now = new Date();
  return (
    now.toLocaleTimeString('en-IN', {
      timeZone: 'Asia/Kolkata',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      hour12: false,
    }) + ' IST'
  );
};
