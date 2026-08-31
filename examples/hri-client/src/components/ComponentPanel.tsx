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
 * Shows the component name, bind/release buttons, query buttons,
 * parameter form (set_parameter), command buttons (execute with
 * parameters), and event subscribe/unsubscribe toggle. All driven
 * by the profile data. No hardcoded component refs or query types.
 */
export function ComponentPanel({ client, componentRef, profile }: ComponentPanelProps) {
  const [activeQuery, setActiveQuery] = useState<string | null>(null);
  const [activeEvent, setActiveEvent] = useState<string | null>(null);
  const [commandResult, setCommandResult] = useState<string>("");
  const [bound, setBound] = useState(false);
  const [paramValues, setParamValues] = useState<Record<string, string>>({});

  const queryHook = useQuery(client, componentRef);
  const subscribeHook = useSubscribe(client, componentRef, activeEvent ?? "");

  // Initialize parameter values from defaults when profile loads.
  const paramProfiles = profile.parameter_profiles ?? [];
  const initParams = () => {
    const defaults: Record<string, string> = {};
    for (const p of paramProfiles) {
      defaults[p.name] = p.default_value ?? "";
    }
    setParamValues(defaults);
  };

  const handleBind = async () => {
    if (!client) return;
    try {
      await client.bind(componentRef);
      setBound(true);
      initParams();
    } catch (err: unknown) {
      setCommandResult(`Bind error: ${err instanceof Error ? err.message : String(err)}`);
    }
  };

  const handleRelease = async () => {
    if (!client) return;
    try {
      await client.release(componentRef);
      setBound(false);
    } catch (err: unknown) {
      setCommandResult(`Release error: ${err instanceof Error ? err.message : String(err)}`);
    }
  };

  const handleQueryClick = (queryName: string) => {
    setActiveQuery(queryName);
    queryHook.fetch(queryName);
  };

  const handleSetParameter = async () => {
    if (!client) return;
    try {
      const parameters = paramProfiles.map((p) => ({
        name: p.name,
        data_type_ref: p.data_type_ref?.code ?? "",
        value: paramValues[p.name] ?? "",
      }));
      await client.setParameter(componentRef, parameters);
      setCommandResult("Parameters set");
    } catch (err: unknown) {
      setCommandResult(`Set parameter error: ${err instanceof Error ? err.message : String(err)}`);
    }
  };

  const handleCommandExecute = async (commandName: string) => {
    if (!client) return;
    try {
      // For execute, pass the current parameter values.
      const parameters = commandName === "execute" && paramProfiles.length > 0
        ? paramProfiles.map((p) => ({
            name: p.name,
            data_type_ref: p.data_type_ref?.code ?? "",
            value: paramValues[p.name] ?? "",
          }))
        : [];
      const response = await client.execute(componentRef, {
        command_type: commandName,
        command_id: `cmd-${Date.now()}`,
        parameters,
      });
      setCommandResult(`${response.return_code} (id: ${response.command_id})`);
    } catch (err: unknown) {
      setCommandResult(`Error: ${err instanceof Error ? err.message : String(err)}`);
    }
  };

  const handleEventToggle = (eventName: string) => {
    if (activeEvent === eventName) {
      setActiveEvent(null);
    } else {
      setActiveEvent(eventName);
    }
  };

  const hasSetParameter = profile.command_profiles?.some((c) => c.name === "set_parameter") ?? false;

  return (
    <div className="component-panel">
      <div className="component-panel-header">
        <h3>{componentRef}</h3>
        <span className="component-type-badge">{profile.identifier.code}</span>
        {profile.command_profiles && profile.command_profiles.length > 0 && (
          <span className="bind-badge" style={{ fontSize: "0.75rem", marginLeft: "0.5rem", color: bound ? "green" : "orange" }}>
            {bound ? "Bound" : "Not bound"}
          </span>
        )}
      </div>
      <div className="component-panel-body">
        {profile.command_profiles && profile.command_profiles.length > 0 && (
          <div className="section">
            <div className="button-row">
              {!bound ? (
                <button onClick={handleBind} className="btn-action bind">Bind</button>
              ) : (
                <button onClick={handleRelease} className="btn-action release">Release</button>
              )}
            </div>
          </div>
        )}

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

        {/* Parameters (set_parameter form) */}
        {hasSetParameter && paramProfiles.length > 0 && (
          <div className="section">
            <div className="section-label">Parameters</div>
            <div className="param-form">
              {paramProfiles.map((p) => (
                <div key={p.name} className="param-row">
                  <label className="param-label">{p.name}</label>
                  <input
                    type="text"
                    className="param-input"
                    placeholder={p.default_value ?? ""}
                    value={paramValues[p.name] ?? ""}
                    onChange={(e) =>
                      setParamValues((prev) => ({ ...prev, [p.name]: e.target.value }))
                    }
                  />
                  <span className="param-type">{p.data_type_ref?.code ?? ""}</span>
                </div>
              ))}
              <button onClick={handleSetParameter} className="btn-action set-param">
                Set Parameters
              </button>
            </div>
          </div>
        )}

        {/* Commands */}
        {profile.command_profiles && profile.command_profiles.length > 0 && (
          <div className="section">
            <div className="section-label">Commands</div>
            <div className="button-row">
              {profile.command_profiles
                .filter((c) => c.name !== "set_parameter")
                .map((c) => (
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
                  onClick={() => handleEventToggle(e.name)}
                  className={`btn-action event ${activeEvent === e.name ? "active" : ""}`}
                >
                  {e.name} {activeEvent === e.name ? "✓" : ""}
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