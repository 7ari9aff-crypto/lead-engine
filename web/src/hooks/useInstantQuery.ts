import { useMemo } from "react";
import { useQuery, type UseQueryOptions, type UseQueryResult } from "@tanstack/react-query";
import { lastGoodAt, readLastGood, writeLastGood } from "@/lib/lastGood";

type Options<T> = Omit<UseQueryOptions<T, Error, T, readonly unknown[]>, "queryKey" | "queryFn"> & {
  /** Skip the localStorage seed (e.g. for huge payloads). */
  instant?: boolean;
};

/**
 * A query that paints instantly.
 *
 * First paint uses the last known-good payload from localStorage, then
 * react-query refreshes in the background (`initialDataUpdatedAt` in the past
 * makes the cached value immediately stale). The result is the "big platform"
 * behaviour: no skeleton flash on navigation, no blank state on reload — while
 * still being honest, because the data keeps refreshing and the SSE bridge
 * pushes live changes on top.
 */
export function useInstantQuery<T>(
  queryKey: readonly unknown[],
  queryFn: () => Promise<T>,
  { instant = true, ...options }: Options<T> = {}
): UseQueryResult<T, Error> {
  const storageKey = useMemo(() => queryKey, [JSON.stringify(queryKey)]); // eslint-disable-line react-hooks/exhaustive-deps
  const seed = instant ? readLastGood<T>(storageKey) : null;
  return useQuery<T, Error>({
    queryKey,
    queryFn: async () => {
      const value = await queryFn();
      if (instant) writeLastGood(storageKey, value);
      return value;
    },
    initialData: seed ?? undefined,
    initialDataUpdatedAt: instant && seed ? lastGoodAt(storageKey) : undefined,
    ...options,
  });
}
