import { useState } from "react";
import type { RoISClient } from "@openrois/sdk";
import type { HRIComponentProfile } from "@openrois/interfaces";
import { useQuery } from "../hooks/useQuery";
import { useSubscribe } from "../hooks/useSubscribe";
import { QueryResult } from "./QueryResult";

interface ComponentPanelProps {
  client: RoISClient | null;
  componentRef: string;
  profile: HRIComponentProfile;
}

/**
 * Render one component from the engine profile.
 *
 * Shows the component name, query buttons (one per query_profiles
 * entry), command forms (one per command_profiles entry), and event
 * subscribe buttons (one per event_profiles entry). All driven by
 * the profile data. No hardcoded component refs or query types.
 */
export function ComponentPanel({ client, componentRef, profile }: ComponentPanelProps) {
  const [activeQuery, setActiveQuery] = useState<string | null>(null);
  const [activeEvent, setActiveEvent] = useState<string | null>(null);
  const [commandResult, setCommandResult] = useState<string>("");

  const queryHook = useQuery(
    client,
    componentRef,
  );

  const subscribeHook = useSubscribe(
    client,
    componentRef,
    activeEvent ?? "",
  );

  const handleQueryClick = (queryName: string) => {
    setActiveQuery(queryName);
    queryHook.fetch(queryName);
  };

  const handleCommandExecute = async (commandName: string) => {
    if (!client) return;
    try {
      const response = await client.execute(componentRef, {
        command_type: commandName,
        command_id: `cmd-${Date.now()}`,
        parameters: [],
      });
      setCommandResult(`${response.return_code} (id: ${response.command_id})`);
    } catch (err: unknown) {
      setCommandResult(`Error: ${err instanceof Error ? err.message : String(err)}`);
    }
  };

  return (
    <div className="component-panel">
      <div className="component-panel-header">
        <h3>{componentRef}</h3>
        <span className="component-type-badge">{profile.identifier.code}</span>
      </div>
      <div className="component-panel-body">
        {/* Queries */}
        {profile.query_profiles && profile.query_profiles.length > 0 && (
          <div className="section">
            <div className="section-label">Queries</div>
            <div className="button-row">
              {profile.query_profiles.map((q) => (
                <button
                  key={q.name}
                  onClick={() => handleQueryClick(q.name)}
                  className={`btn-action query ${activeQuery === q.name ? "active" : ""}`}
                >
                  {q.name}
                </button>
              ))}
            </div>
            {activeQuery && (
              <QueryResult
                results={queryHook.results}
                loading={queryHook.loading}
                error={queryHook.error}
              />
            )}
          </div>
        )}

        {/* Commands */}
        {profile.command_profiles && profile.command_profiles.length > 0 && (
          <div className="section">
            <div className="section-label">Commands</div>
            <div className="button-row">
              {profile.command_profiles.map((c) => (
                <button
                  key={c.name}
                  onClick={() => handleCommandExecute(c.name)}
                  className="btn-action command"
                >
                  {c.name}
                </button>
              ))}
            </div>
            {commandResult && (
              <div className="command-result">{commandResult}</div>
            )}
          </div>
        )}

        {/* Events */}
        {profile.event_profiles && profile.event_profiles.length > 0 && (
          <div className="section">
            <div className="section-label">Events</div>
            <div className="button-row">
              {profile.event_profiles.map((e) => (
                <button
                  key={e.name}
                  onClick={() => setActiveEvent(e.name)}
                  className={`btn-action event ${activeEvent === e.name ? "active" : ""}`}
                >
                  {e.name}
                </button>
              ))}
            </div>
            {activeEvent && (
              <div className="event-status">
                <span className={`event-badge ${subscribeHook.error ? "error" : subscribeHook.subscribed ? "subscribed" : "not-subscribed"}`}>
                  {subscribeHook.error
                    ? `Error: ${subscribeHook.error}`
                    : subscribeHook.subscribed
                      ? "Subscribed"
                      : "Not subscribed"}
                </span>
                {subscribeHook.notifications.length > 0 && (
                  <div className="notifications">
                    {subscribeHook.notifications.map((n, i) => (
                      <div key={i} className="notification">
                        {n.name}: {n.value}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}