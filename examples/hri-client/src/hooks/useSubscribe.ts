import { useState, useEffect } from "react";
import { componentRef as selectRef, type RoISClient } from "@openrois/sdk";
import type { NotifyEventParams, Result } from "@openrois/interfaces";

interface UseSubscribeResult {
  subscribed: boolean;
  notifications: Result[];
  error: string | null;
}

/**
 * Subscribe to one event type of one component while the hook is mounted.
 *
 * The component is selected by its ref. The payload of every event of this
 * subscription is kept, up to the last 50 results.
 */
export function useSubscribe(
  client: RoISClient | null,
  componentRef: string,
  eventType: string,
): UseSubscribeResult {
  const [subscribed, setSubscribed] = useState(false);
  const [notifications, setNotifications] = useState<Result[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!client || !eventType) return;
    let subscribeId: string | null = null;
    // Set when the effect is cleaned up before subscribe resolves, so the late
    // subscription is released instead of left open on the engine.
    let cancelled = false;

    const handler = (params: NotifyEventParams) => {
      if (params.subscribe_id !== subscribeId) return;
      setNotifications((prev) => [...prev, ...(params.results ?? [])].slice(-50));
    };
    client.on("rois.event.notify_event", handler);

    client
      .subscribe(eventType, selectRef(componentRef))
      .then((id) => {
        if (cancelled) {
          client.unsubscribe(id).catch(() => {});
          return;
        }
        subscribeId = id;
        setSubscribed(true);
        setError(null);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : String(err));
        setSubscribed(false);
      });

    return () => {
      cancelled = true;
      client.off("rois.event.notify_event", handler);
      if (subscribeId) {
        client.unsubscribe(subscribeId).catch(() => {});
      }
      setSubscribed(false);
    };
  }, [client, componentRef, eventType]);

  return { subscribed, notifications, error };
}
