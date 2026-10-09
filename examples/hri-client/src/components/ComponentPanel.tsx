import { useEffect, useState } from "react";
import type { RoISClient } from "@openrois/sdk";
import type { CompletedParams, HRIComponentProfile } from "@openrois/interfaces";
import { useQuery } from "../hooks/useQuery";
import { useSubscribe } from "../hooks/useSubscribe";
import { QueryResult } from "./QueryResult";

interface ComponentPanelProps {
  client: RoISClient | null;
  componentRef: string;
  profile: HRIComponentProfile;
}

/** The last command sent from this panel, and how it ended. */
interface CommandState {
  name: string;
  commandId: string;
  status: string;
}

/**
 * Render one component from the engine profile.
 *
 * Shows the component's queries, parameters, commands and events, all taken
 * from its profile, with bind and release for an actuation component. Nothing
 * here is specific to a component type.
 */
export function ComponentPanel({ client, componentRef, profile }: ComponentPanelProps) {
  const [activeQuery, setActiveQuery] = useState<string | null>(null);
  const [activeEvent, setActiveEvent] = useState<string | null>(null);
  const [message, setMessage] = useState<string>("");
  const [lastCommand, setLastCommand] = useState<CommandState | null>(null);
  const [bound, setBound] = useState(false);

  const paramProfiles = profile.parameter_profiles ?? [];
  const commandProfiles = profile.command_profiles ?? [];
  const queryProfiles = profile.query_profiles ?? [];
  const eventProfiles = profile.event_profiles ?? [];
  const isActuation = profile.function === "actuation";

  const [paramValues, setParamValues] = useState<Record<string, string>>(() =>
    Object.fromEntries(paramProfiles.map((p) => [p.name, p.default_value])),
  );

  const queryHook = useQuery(client, componentRef);
  const subscribeHook = useSubscribe(client, componentRef, activeEvent ?? "");

  // Each command ends with a rois.command.completed notification. Show how the
  // last command sent from this panel ended.
  useEffect(() => {
    if (!client || !lastCommand) return;
    const handler = (params: CompletedParams) => {
      if (params.command_id !== lastCommand.commandId) return;
      setLastCommand((current) =>
        current?.commandId === params.command_id ? { ...current, status: params.status } : current,
      );
    };
    client.on("rois.command.completed", handler);
    return () => {
      client.off("rois.command.completed", handler);
    };
  }, [client, lastCommand]);

  const errorText = (err: unknown) => (err instanceof Error ? err.message : String(err));

  const handleBind = async () => {
    if (!client) return;
    try {
      await client.bind(componentRef);
      setBound(true);
      setMessage("");
    } catch (err: unknown) {
      setMessage(`Bind error: ${errorText(err)}`);
    }
  };

  const handleRelease = async () => {
    if (!client) return;
    try {
      await client.release(componentRef);
      setBound(false);
      setMessage("");
    } catch (err: unknown) {
      setMessage(`Release error: ${errorText(err)}`);
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
        data_type_ref: p.data_type_ref.code,
        value: paramValues[p.name] ?? "",
      }));
      const commandId = await client.setParameter(componentRef, parameters);
      setLastCommand({ name: "set_parameter", commandId, status: "running" });
      setMessage("");
    } catch (err: unknown) {
      setMessage(`Set parameter error: ${errorText(err)}`);
    }
  };

  const handleCommand = async (commandName: string) => {
    if (!client) return;
    try {
      const [commandId] = await client.execute([
        { component_ref: componentRef, command_type: commandName },
      ]);
      setLastCommand({ name: commandName, commandId, status: "running" });
      setMessage("");
    } catch (err: unknown) {
      setMessage(`${commandName} error: ${errorText(err)}`);
    }
  };

  const handleEventToggle = (eventName: string) => {
    setActiveEvent(activeEvent === eventName ? null : eventName);
  };

  return (
    <div className="component-panel">
      <div className="component-panel-header">
        <h3>{componentRef}</h3>
        <span className="component-type-badge">{profile.identifier.code}</span>
        {isActuation && (
          <span className={`bind-badge ${bound ? "bound" : "unbound"}`}>
            {bound ? "Bound" : "Not bound"}
          </span>
        )}
      </div>
      <div className="component-panel-body">
        {isActuation && (
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
        {queryProfiles.length > 0 && (
          <div className="section">
            <div className="section-label">Queries</div>
            <div className="button-row">
              {queryProfiles.map((q) => (
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

        {/* Parameters */}
        {paramProfiles.length > 0 && (
          <div className="section">
            <div className="section-label">Parameters</div>
            <div className="param-form">
              {paramProfiles.map((p) => (
                <div key={p.name} className="param-row">
                  <label className="param-label" title={p.description}>{p.name}</label>
                  <input
                    type="text"
                    className="param-input"
                    placeholder={p.default_value}
                    value={paramValues[p.name] ?? ""}
                    onChange={(e) =>
                      setParamValues((prev) => ({ ...prev, [p.name]: e.target.value }))
                    }
                  />
                  <span className="param-type">{p.data_type_ref.code}</span>
                </div>
              ))}
              <button onClick={handleSetParameter} className="btn-action set-param">
                Set Parameters
              </button>
            </div>
          </div>
        )}

        {/* Commands */}
        {commandProfiles.length > 0 && (
          <div className="section">
            <div className="section-label">Commands</div>
            <div className="button-row">
              {commandProfiles.map((c) => (
                <button
                  key={c.name}
                  onClick={() => handleCommand(c.name)}
                  className="btn-action command"
                >
                  {c.name}
                </button>
              ))}
            </div>
          </div>
        )}

        {(lastCommand || message) && (
          <div className="command-result">
            {message ||
              (lastCommand &&
                `${lastCommand.name}: ${lastCommand.status} (id: ${lastCommand.commandId})`)}
          </div>
        )}

        {/* Events */}
        {eventProfiles.length > 0 && (
          <div className="section">
            <div className="section-label">Events</div>
            <div className="button-row">
              {eventProfiles.map((e) => (
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
                <span
                  className={`event-badge ${
                    subscribeHook.error ? "error" : subscribeHook.subscribed ? "subscribed" : "not-subscribed"
                  }`}
                >
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
