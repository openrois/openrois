import { useState, useEffect } from "react";
import type { RoISClient } from "@openrois/sdk";
import type { Result } from "@openrois/interfaces";

interface UseSubscribeResult {
  subscribed: boolean;
  notifications: Result[];
  error: string | null;
}

/**
 * Generic subscribe hook. Calls rois.event.subscribe on mount,
 * unsubscribes on unmount.
 *
 * The caller provides the componentRef and eventType from the
 * profile. Notifications are accumulated as they arrive.
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
    if (!client) return;
    let subId: string | null = null;
    // Set when the effect is cleaned up before the subscribe call resolves, so
    // the late subscription is released instead of leaking on the engine.
    let cancelled = false;

    client
      .subscribe(componentRef, eventType)
      .then((id) => {
        if (cancelled) {
          client.unsubscribe(id).catch(() => {});
          return;
        }
        subId = id;
        setSubscribed(true);
        setError(null);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        const message = err instanceof Error ? err.message : String(err);
        setError(message);
        setSubscribed(false);
      });

    // Listen for event notifications, keeping only those for this subscription.
    const handler = (notification: {
      params?: {
        subscribe_id?: string;
        component_ref?: string;
        event_type?: string;
        results?: Result[];
      };
    }) => {
      const params = notification.params ?? {};
      if (params.subscribe_id && subId && params.subscribe_id !== subId) return;
      if (params.event_type && params.event_type !== eventType) return;
      if (params.component_ref && params.component_ref !== componentRef) return;
      const results = params.results ?? [];
      setNotifications((prev) => [...prev, ...results].slice(-50));
    };

    client.on("rois.event.notify", handler);

    return () => {
      cancelled = true;
      client.off("rois.event.notify", handler);
      if (subId) {
        client.unsubscribe(subId).catch(() => {});
      }
      setSubscribed(false);
    };
  }, [client, componentRef, eventType]);

  return { subscribed, notifications, error };
}