import { useState, useEffect } from "react";
import { RoISClient } from "@openrois/sdk";
import type { CompletedParams } from "@openrois/interfaces";

/** Where the connection to the engine stands. */
export type ConnectionState = "idle" | "connecting" | "connected" | "error";

/** How each command of this session ended, by command_id. */
export type CommandStatuses = ReadonlyMap<string, CompletedParams["status"]>;

interface UseRoISClientResult {
  client: RoISClient | null;
  state: ConnectionState;
  error: string | null;
  commandStatuses: CommandStatuses;
}

const NO_STATUSES: CommandStatuses = new Map();

/**
 * Connect to a RoIS engine while a URL is given, and disconnect when it is null.
 *
 * Each new attempt number connects again, so a Connect button retries the same
 * URL. No auto-reconnect: when the engine closes the connection, the state turns
 * to error with the close code, and the user connects again.
 *
 * A command can end before the reply that names it reaches the caller, so
 * completions are recorded from connect on, and a panel reads its command's status
 * by id. A listener added after execute() would miss those.
 */
export function useRoISClient(url: string | null, attempt: number): UseRoISClientResult {
  const [client, setClient] = useState<RoISClient | null>(null);
  const [state, setState] = useState<ConnectionState>("idle");
  const [error, setError] = useState<string | null>(null);
  const [commandStatuses, setCommandStatuses] = useState<CommandStatuses>(NO_STATUSES);

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
    const onCompleted = ({ command_id, status }: CompletedParams) => {
      setCommandStatuses((known) => new Map(known).set(command_id, status));
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
        c.on("rois.command.completed", onCompleted);
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
        current.off("rois.command.completed", onCompleted);
        current.disconnect().catch(() => {});
      }
      setClient(null);
      setState("idle");
      setError(null);
      setCommandStatuses(NO_STATUSES);
    };
  }, [url, attempt]);

  return { client, state, error, commandStatuses };
}
