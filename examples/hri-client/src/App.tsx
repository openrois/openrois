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

  // Group components by engine_id prefix (e.g. "kachaka_01/Navigation").
  const engineGroups = useMemo(() => {
    if (!profile?.component_ids || !profile?.component_profiles) return [];
    const map = new Map<string, { refs: string[]; profiles: HRIComponentProfile[] }>();
    profile.component_ids.forEach((id, i) => {
      const cp = profile.component_profiles![i];
      const slashIdx = id.indexOf("/");
      const engineId = slashIdx > 0 ? id.slice(0, slashIdx) : "default";
      const entry = map.get(engineId) ?? { refs: [], profiles: [] };
      entry.refs.push(id);
      entry.profiles.push(cp);
      map.set(engineId, entry);
    });
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
            <h2>{profile.identifier.code}</h2>
            {profile.identifier.authority && (
              <span className="engine-badge">{profile.identifier.authority}</span>
            )}
          </div>
          {profile.component_ids && profile.component_ids.length > 0 ? (
            profile.component_profiles && profile.component_profiles.length > 0 ? (
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
              <div className="no-profiles">
                Engine returned {profile.component_ids.length} component IDs
                but no component profiles. Use rois.command.search to
                discover components.
              </div>
            )
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