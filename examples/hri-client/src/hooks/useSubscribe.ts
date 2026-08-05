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

    client
      .subscribe(componentRef, eventType)
      .then((id) => {
        subId = id;
        setSubscribed(true);
        setError(null);
      })
      .catch((err: unknown) => {
        const message = err instanceof Error ? err.message : String(err);
        setError(message);
        setSubscribed(false);
      });

    // Listen for event notifications.
    const handler = (notification: {
      params?: { results?: Result[] };
    }) => {
      const results = notification.params?.results ?? [];
      setNotifications((prev) => [...prev, ...results].slice(-50));
    };

    client.on("rois.event.notify", handler);

    return () => {
      client.off("rois.event.notify", handler);
      if (subId) {
        client.unsubscribe(subId).catch(() => {});
      }
      setSubscribed(false);
    };
  }, [client, componentRef, eventType]);

  return { subscribed, notifications, error };
}