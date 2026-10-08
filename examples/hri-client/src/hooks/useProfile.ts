import { useState, useEffect } from "react";
import type { EngineProfile, RoISClient } from "@openrois/sdk";

/**
 * Fetch the engine profile on connect, and fetch it again when the engine
 * sends rois.system.profile_changed (for example when an adapter registers
 * or disconnects).
 */
export function useProfile(client: RoISClient | null): {
  profile: EngineProfile | null;
  error: string | null;
} {
  const [profile, setProfile] = useState<EngineProfile | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);

  useEffect(() => {
    if (!client) return;
    const handler = () => setRefreshKey((k) => k + 1);
    client.on("rois.system.profile_changed", handler);
    return () => {
      client.off("rois.system.profile_changed", handler);
    };
  }, [client]);

  useEffect(() => {
    if (!client) {
      setProfile(null);
      setError(null);
      return;
    }
    client
      .getProfile()
      .then((result) => {
        setProfile(result);
        setError(null);
      })
      .catch((err: unknown) => {
        setError(err instanceof Error ? err.message : String(err));
        setProfile(null);
      });
  }, [client, refreshKey]);

  return { profile, error };
}
