import { useState } from "react";
import { useRoISClient } from "./hooks/useRoISClient";
import { useProfile } from "./hooks/useProfile";
import { ConnectionIndicator } from "./components/ConnectionIndicator";
import { ComponentPanel } from "./components/ComponentPanel";
import "./App.css";

const DEFAULT_ENGINE_URL = "ws://localhost:8765";

function App() {
  const [urlInput, setUrlInput] = useState(DEFAULT_ENGINE_URL);
  const [connectedUrl, setConnectedUrl] = useState<string | null>(null);

  const { client, connected, error } = useRoISClient(connectedUrl ?? "");
  const { profile, error: profileError } = useProfile(connected ? client : null);

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
            <div className="component-grid">
              {profile.component_profiles && profile.component_profiles.length > 0 ? (
                profile.component_profiles.map((cp, i) => {
                  const ref = profile.component_ids![i] ?? cp.name;
                  return (
                    <ComponentPanel
                      key={ref}
                      client={client}
                      componentRef={ref}
                      profile={cp}
                    />
                  );
                })
              ) : (
                <div className="no-profiles">
                  Engine returned {profile.component_ids.length} component IDs
                  but no component profiles. Use rois.command.search to
                  discover components.
                </div>
              )}
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