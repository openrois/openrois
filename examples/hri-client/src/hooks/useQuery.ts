import { useState, useCallback } from "react";
import { componentRef as selectRef, type RoISClient } from "@openrois/sdk";
import type { Result } from "@openrois/interfaces";

interface UseQueryResult {
  fetch: (queryType: string) => Promise<void>;
  results: Result[];
  loading: boolean;
  error: string | null;
}

/**
 * Run rois.query.query on demand, on the component the ref selects.
 *
 * The caller provides the componentRef at hook creation time and the
 * queryType at call time, which avoids stale closures when switching between
 * query types in the same component.
 */
export function useQuery(client: RoISClient | null, componentRef: string): UseQueryResult {
  const [results, setResults] = useState<Result[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetch = useCallback(
    async (queryType: string) => {
      if (!client) return;
      setLoading(true);
      setError(null);
      try {
        setResults(await client.query(queryType, selectRef(componentRef)));
      } catch (err: unknown) {
        setError(err instanceof Error ? err.message : String(err));
        setResults([]);
      } finally {
        setLoading(false);
      }
    },
    [client, componentRef],
  );

  return { fetch, results, loading, error };
}
