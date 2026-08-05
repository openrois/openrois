import { useState, useEffect } from "react";
import type { RoISClient } from "@openrois/sdk";
import type { HRIEngineProfileType } from "@openrois/interfaces";

/**
 * Fetch the HRI Engine Profile on connect.
 *
 * Calls rois.system.get_profile and returns the parsed profile,
 * including component_profiles (if the engine supports them).
 */
export function useProfile(client: RoISClient | null): {
  profile: HRIEngineProfileType | null;
  error: string | null;
} {
  const [profile, setProfile] = useState<HRIEngineProfileType | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!client) return;
    client
      .getProfile()
      .then((result) => {
        // RoISClient.getProfile() returns the raw response: { return_code, profile }.
        // Extract the profile field from it.
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
  }, [client]);

  return { profile, error };
}