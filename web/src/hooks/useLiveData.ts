import { useEffect, useRef, useState, useCallback } from "react";

/** Live-polling hook with exponential backoff on consecutive errors. */
export function useLiveData<T>(
  fetcher: () => Promise<T>,
  intervalMs = 5000
): { data: T | null; error: Error | null; loading: boolean; refresh: () => Promise<void> } {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const [loading, setLoading] = useState(true);
  const fetcherRef = useRef(fetcher);
  const mountedRef = useRef(false);
  const inFlightRef = useRef(false);
  const failuresRef = useRef(0);
  fetcherRef.current = fetcher;

  const refresh = useCallback(async () => {
    if (!mountedRef.current || inFlightRef.current) return;
    inFlightRef.current = true;
    try {
      const v = await fetcherRef.current();
      if (mountedRef.current) {
        setData(v);
        setError(null);
      }
      failuresRef.current = 0;
    } catch (error: unknown) {
      failuresRef.current += 1;
      if (mountedRef.current) {
        setError(error instanceof Error ? error : new Error(String(error)));
      }
    } finally {
      inFlightRef.current = false;
      if (mountedRef.current) setLoading(false);
    }
  }, []);

  useEffect(() => {
    mountedRef.current = true;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const backoff = () => intervalMs * Math.min(2 ** failuresRef.current, 8);
    const tick = () => {
      void refresh().finally(() => {
        if (!mountedRef.current) return;
        timer = setTimeout(tick, backoff());
      });
    };
    void refresh().finally(() => {
      if (mountedRef.current) timer = setTimeout(tick, backoff());
    });
    return () => {
      mountedRef.current = false;
      if (timer) clearTimeout(timer);
    };
  }, [intervalMs, refresh]);

  return { data, error, loading, refresh };
}