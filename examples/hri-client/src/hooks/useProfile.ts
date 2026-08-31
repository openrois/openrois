import { useState, useEffect } from "react";
import type { RoISClient } from "@openrois/sdk";
import type { HRIEngineProfileType } from "@openrois/interfaces";

/**
 * Fetch the HRI Engine Profile on connect, and re-fetch when
 * the engine broadcasts a profile_changed notification (e.g.
 * when an adapter registers or disconnects).
 */
export function useProfile(client: RoISClient | null): {
  profile: HRIEngineProfileType | null;
  error: string | null;
} {
  const [profile, setProfile] = useState<HRIEngineProfileType | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);

  // Listen for profile_changed notifications from the engine.
  // The SDK emits method-name events for all JSON-RPC notifications.
  useEffect(() => {
    if (!client) return;
    const handler = () => setRefreshKey((k) => k + 1);
    client.on("rois.system.profile_changed", handler);
    return () => {
      client.off("rois.system.profile_changed", handler);
    };
  }, [client]);

  // Fetch (or re-fetch) the profile.
  useEffect(() => {
    if (!client) return;
    client
      .getProfile()
      .then((result) => {
        const raw = result as { return_code?: string; profile?: HRIEngineProfileType };
        if (raw.return_code && raw.return_code !== "OK") {
          setError(`get_profile returned ${raw.return_code}`);
          setProfile(null);
          return;
        }
        setProfile(raw.profile ?? null);
        setError(null);
      })
      .catch((err: unknown) => {
        const message = err instanceof Error ? err.message : String(err);
        setError(message);
        setProfile(null);
      });
  }, [client, refreshKey]);

  return { profile, error };
}