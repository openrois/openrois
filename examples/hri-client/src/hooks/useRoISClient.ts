import { useState, useEffect } from "react";
import { RoISClient } from "@openrois/sdk";

/** Where the connection to the engine stands. */
export type ConnectionState = "idle" | "connecting" | "connected" | "error";

interface UseRoISClientResult {
  client: RoISClient | null;
  state: ConnectionState;
  error: string | null;
}

/**
 * Connect to a RoIS engine while a URL is given, and disconnect when it is null.
 *
 * Each new attempt number connects again, so a Connect button retries the same
 * URL. No auto-reconnect: when the engine closes the connection, the state turns
 * to error with the close code, and the user connects again.
 */
export function useRoISClient(url: string | null, attempt: number): UseRoISClientResult {
  const [client, setClient] = useState<RoISClient | null>(null);
  const [state, setState] = useState<ConnectionState>("idle");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!url) {
      return;
    }
    let cancelled = false;
    let current: RoISClient | null = null;

    const onClose = (code: number, reason: string) => {
      setClient(null);
      setState("error");
      setError(`The connection closed (code ${code}${reason ? `, ${reason}` : ""})`);
    };
    // The client's event emitter throws on an "error" event nobody listens to,
    // such as a notification that does not fit its schema.
    const onError = (err: Error) => {
      console.warn("RoIS client:", err.message);
    };

    setState("connecting");
    setError(null);
    RoISClient.connect(url)
      .then((c) => {
        if (cancelled) {
          c.disconnect().catch(() => {});
          return;
        }
        current = c;
        c.on("close", onClose);
        c.on("error", onError);
        setClient(c);
        setState("connected");
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setState("error");
        setError(err instanceof Error ? err.message : String(err));
      });

    return () => {
      cancelled = true;
      if (current) {
        current.off("close", onClose);
        current.disconnect().catch(() => {});
      }
      setClient(null);
      setState("idle");
      setError(null);
    };
  }, [url, attempt]);

  return { client, state, error };
}
