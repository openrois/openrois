import { useState, useMemo } from "react";
import type { HRIComponentProfile } from "@openrois/interfaces";
import { useRoISClient } from "./hooks/useRoISClient";
import { useProfile } from "./hooks/useProfile";
import { ConnectionIndicator } from "./components/ConnectionIndicator";
import { EngineGroup } from "./components/EngineGroup";
import "./App.css";

const DEFAULT_ENGINE_URL = "ws://localhost:8765";

function App() {
  const [urlInput, setUrlInput] = useState(DEFAULT_ENGINE_URL);
  const [connectedUrl, setConnectedUrl] = useState<string | null>(null);

  const { client, connected, error } = useRoISClient(connectedUrl ?? "");
  const { profile, error: profileError } = useProfile(connected ? client : null);

  // Group components by engine id, the part of each ref before the slash
  // (for example "reachy_real/head").
  const engineGroups = useMemo(() => {
    if (!profile) return [];
    const map = new Map<string, { refs: string[]; profiles: HRIComponentProfile[] }>();
    for (const ref of profile.profile.component_ids ?? []) {
      const componentProfile = profile.component_profiles[ref];
      if (!componentProfile) continue;
      const slash = ref.indexOf("/");
      const engineId = slash > 0 ? ref.slice(0, slash) : ref;
      const entry = map.get(engineId) ?? { refs: [], profiles: [] };
      entry.refs.push(ref);
      entry.profiles.push(componentProfile);
      map.set(engineId, entry);
    }
    return [...map.entries()].sort((a, b) => a[0].localeCompare(b[0]));
  }, [profile]);

  const handleConnect = () => {
    setConnectedUrl(urlInput);
  };

  const handleDisconnect = () => {
    setConnectedUrl(null);
  };

  return (
    <div className="app">
      <div className="app-header">
        <h1>OpenRoIS HRI Client</h1>
      </div>

      <div className="connection-bar">
        <input
          type="text"
          value={urlInput}
          onChange={(e) => setUrlInput(e.target.value)}
          placeholder="ws://localhost:8765"
          className="url-input"
        />
        {connected ? (
          <button onClick={handleDisconnect} className="btn btn-disconnect">
            Disconnect
          </button>
        ) : (
          <button onClick={handleConnect} className="btn btn-connect">
            Connect
          </button>
        )}
        <ConnectionIndicator connected={connected} error={error} />
      </div>

      {profileError && (
        <div className="error-message">Profile error: {profileError}</div>
      )}

      {connected && profile && (
        <div className="engine-info">
          <div className="engine-header">
            <h2>{profile.profile.identifier.code}</h2>
            {profile.profile.identifier.authority && (
              <span className="engine-badge">{profile.profile.identifier.authority}</span>
            )}
          </div>
          {engineGroups.length > 0 ? (
            <div className="engine-groups">
              {engineGroups.map(([engineId, { refs, profiles }]) => (
                <EngineGroup
                  key={engineId}
                  engineId={engineId}
                  client={client}
                  componentRefs={refs}
                  componentProfiles={profiles}
                />
              ))}
            </div>
          ) : (
            <div className="no-components">
              No components registered. Connect an adapter to the engine.
            </div>
          )}
        </div>
      )}

      {connected && !profile && !profileError && (
        <div className="loading">Loading profile...</div>
      )}
    </div>
  );
}

export default App;