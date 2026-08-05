import { useState, useCallback } from "react";
import type { RoISClient } from "@openrois/sdk";
import type { Result } from "@openrois/interfaces";

interface UseQueryResult {
  fetch: (queryType: string) => Promise<void>;
  results: Result[];
  loading: boolean;
  error: string | null;
}

/**
 * Generic query hook. Calls rois.query.query on demand.
 *
 * The caller provides the componentRef at hook creation time and
 * the queryType at call time. This avoids stale closure bugs when
 * switching between query types in the same component.
 */
export function useQuery(
  client: RoISClient | null,
  componentRef: string,
): UseQueryResult {
  const [results, setResults] = useState<Result[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetch = useCallback(async (queryType: string) => {
    if (!client) return;
    setLoading(true);
    setError(null);
    try {
      const res = await client.query(componentRef, queryType);
      setResults(res);
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : String(err);
      setError(message);
      setResults([]);
    } finally {
      setLoading(false);
    }
  }, [client, componentRef]);

  return { fetch, results, loading, error };
}