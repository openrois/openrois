import { useState, useEffect, useRef } from "react";
import { RoISClient } from "@openrois/sdk";

interface UseRoISClientResult {
  client: RoISClient | null;
  connected: boolean;
  error: string | null;
}

/**
 * Connect to a RoIS engine on mount, disconnect on unmount.
 *
 * No auto-reconnect. If the connection drops, the error state is set
 * and the user must reconnect manually.
 */
export function useRoISClient(url: string): UseRoISClientResult {
  const [client, setClient] = useState<RoISClient | null>(null);
  const [connected, setConnected] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const clientRef = useRef<RoISClient | null>(null);

  useEffect(() => {
    let cancelled = false;
    RoISClient.connect(url)
      .then((c) => {
        if (cancelled) {
          c.disconnect();
          return;
        }
        clientRef.current = c;
        setClient(c);
        setConnected(true);
        setError(null);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        const message = err instanceof Error ? err.message : String(err);
        setError(message);
        setConnected(false);
      });
    return () => {
      cancelled = true;
      if (clientRef.current) {
        clientRef.current.disconnect();
        clientRef.current = null;
      }
      setClient(null);
      setConnected(false);
    };
  }, [url]);

  return { client, connected, error };
}