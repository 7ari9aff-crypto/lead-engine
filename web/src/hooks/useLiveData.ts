import { useEffect, useRef, useState, useCallback } from "react";

/** Lightweight live-polling hook with backoff on errors. */
export function useLiveData<T>(
  fetcher: () => Promise<T>,
  intervalMs = 5000
): { data: T | null; error: Error | null; loading: boolean; refresh: () => Promise<void> } {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const [loading, setLoading] = useState(true);
  const ref = useRef(fetcher);
  ref.current = fetcher;

  const refresh = useCallback(async () => {
    try {
      const v = await ref.current();
      setData(v);
      setError(null);
    } catch (e: any) {
      setError(e);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
    const id = setInterval(refresh, intervalMs);
    return () => clearInterval(id);
  }, [intervalMs, refresh]);

  return { data, error, loading, refresh };
}
