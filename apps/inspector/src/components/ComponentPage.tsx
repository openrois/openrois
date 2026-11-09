import { useCallback, useState } from "react";
import { componentTypeUrn, type HRIComponentProfile, type Parameter, type Result } from "@openrois/interfaces";
import type { CommandUnitSequenceItemInput } from "@openrois/sdk";
import { useSession } from "../lib/useSession";
import { errorText } from "../lib/session";
import { hasStatus, typeName } from "../lib/engines";
import { fromWire, toWire } from "../lib/values";
import {
  bindSnippet,
  executeSnippet,
  parameterSnippet,
  querySnippet,
  subscribeSnippet,
} from "../lib/snippets";
import { Card, CodeBlock, MethodButton, Pill, ResultsTable, Split, ValueField, clock } from "./ui";
import type { ComponentTab, View } from "../App";

/** Run an async action with its pending state and its error message. */
function useAction() {
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const run = useCallback(async (action: () => Promise<void>) => {
    setPending(true);
    setError(null);
    try {
      await action();
    } catch (e) {
      setError(errorText(e));
    } finally {
      setPending(false);
    }
  }, []);
  return { pending, error, run };
}

/** The id of the engine a client is connected to, the first part of the breadcrumb. */
function rootId(answer: { profile: { identifier?: { code?: string } } }): string {
  return answer.profile.identifier?.code ?? "";
}

const TABS: { id: ComponentTab; label: string }[] = [
  { id: "overview", label: "Overview" },
  { id: "parameters", label: "Parameters" },
  { id: "queries", label: "Queries" },
  { id: "commands", label: "Commands" },
  { id: "events", label: "Events" },
];

export function ComponentPage({
  componentRef,
  tab,
  onOpen,
}: {
  componentRef: string;
  tab: ComponentTab;
  onOpen: (view: View) => void;
}) {
  const [session, state] = useSession();
  const profile = state.profile?.component_profiles[componentRef];
  const bind = useAction();

  if (!profile) {
    return <p className="empty">{componentRef} is no longer in the engine profile.</p>;
  }
  const bound = state.bound.has(componentRef);
  const status = state.statuses[componentRef];
  const counts: Record<ComponentTab, number | null> = {
    overview: null,
    parameters: profile.parameter_profiles?.length ?? 0,
    queries: profile.query_profiles?.length ?? 0,
    commands: profile.command_profiles?.length ?? 0,
    events: profile.event_profiles?.length ?? 0,
  };

  return (
    <>
      <div className="breadcrumb">
        {[state.profile ? rootId(state.profile) : "", ...componentRef.split("/")].filter(Boolean).join(" / ")}
      </div>
      <div className="page-head">
        <div>
          <h1>{componentRef}</h1>
          <div className="sub">
            <span>{typeName(profile)}</span>
            {profile.function && <span className={`chip ${profile.function}`}>{profile.function}</span>}
            {status && <Pill status={status} />}
            {bound && <Pill status="RUNNING" label="Bound by This Session" />}
          </div>
        </div>
        <div className="actions">
          {hasStatus(profile) && (
            <MethodButton
              label="Refresh Status"
              method="query"
              onClick={() => bind.run(() => session.readStatus(componentRef))}
            />
          )}
          <MethodButton
            primary={!bound}
            small={false}
            label={bound ? "Release" : "Bind"}
            method={bound ? "release" : "bind"}
            disabled={bind.pending}
            onClick={() => bind.run(() => (bound ? session.release(componentRef) : session.bind(componentRef)))}
          />
        </div>
      </div>
      {bind.error && <p className="message bad">{bind.error}</p>}

      <div className="tabs" role="tablist">
        {TABS.map(({ id, label }) => (
          <button
            key={id}
            type="button"
            role="tab"
            aria-selected={tab === id}
            onClick={() => onOpen({ kind: "component", ref: componentRef, tab: id })}
          >
            {label}
            {counts[id] !== null && <span className="count">{counts[id]}</span>}
          </button>
        ))}
      </div>

      {tab === "overview" && <Overview componentRef={componentRef} profile={profile} />}
      {tab === "parameters" && <Parameters componentRef={componentRef} profile={profile} />}
      {tab === "queries" && <Queries componentRef={componentRef} profile={profile} />}
      {tab === "commands" && <Commands componentRef={componentRef} profile={profile} />}
      {tab === "events" && <Events componentRef={componentRef} profile={profile} />}
    </>
  );
}

function Overview({ componentRef, profile }: { componentRef: string; profile: HRIComponentProfile }) {
  const [, state] = useSession();
  const engine = componentRef.slice(0, componentRef.indexOf("/"));
  const common = (profile.sub_component_profiles ?? []).some((urn) => urn.endsWith("::RoISCommon"));
  const names = (list?: { name: string }[]) => (list ?? []).map((m) => m.name).join(", ") || "none";
  return (
    <Split>
      <div className="stack">
        <Card title="Profile">
          <dl className="kv">
            <dt>Ref</dt>
            <dd className="mono">{componentRef}</dd>
            <dt>Engine</dt>
            <dd className="mono">{engine}</dd>
            <dt>Type</dt>
            <dd className="mono">{componentTypeUrn(profile.identifier)}</dd>
            <dt>Function</dt>
            <dd>
              {profile.function ?? "none"}
              {profile.function === "actuation" && (
                <span className="hint"> · one session at a time may bind it</span>
              )}
            </dd>
            <dt>RoIS_Common</dt>
            <dd>{common ? "start, stop, suspend, resume and component_status, served by the engine" : "not included"}</dd>
            <dt>Commands</dt>
            <dd className="mono">{names(profile.command_profiles)}</dd>
            <dt>Queries</dt>
            <dd className="mono">{names(profile.query_profiles)}</dd>
            <dt>Events</dt>
            <dd className="mono">{names(profile.event_profiles)}</dd>
            <dt>Parameters</dt>
            <dd className="mono">{names(profile.parameter_profiles)}</dd>
          </dl>
        </Card>
        <Card title="How a Service Application Uses It">
          <ol className="hint" style={{ margin: 0, paddingLeft: 18 }}>
            <li>Read the profile with get_profile, as this page does.</li>
            <li>Bind the component before commands and parameters. Queries and events need no bind.</li>
            <li>Run commands with execute. Each one ends with a rois.command.completed notification.</li>
            <li>Subscribe to events, which arrive as rois.event.notify_event.</li>
          </ol>
        </Card>
      </div>
      <CodeBlock code={bindSnippet(componentRef, state.bound.has(componentRef))} />
    </Split>
  );
}

function Parameters({ componentRef, profile }: { componentRef: string; profile: HRIComponentProfile }) {
  const [session, state] = useSession();
  const params = profile.parameter_profiles ?? [];
  const [values, setValues] = useState<Record<string, string>>(() =>
    Object.fromEntries(params.map((p) => [p.name, fromWire(p.data_type_ref.code, p.default_value)])),
  );
  const [lastId, setLastId] = useState<string | null>(null);
  const read = useAction();
  const write = useAction();
  const bound = state.bound.has(componentRef);

  const wire = (): Parameter[] =>
    params
      .filter((p) => !p.read_only && (values[p.name] ?? "").trim() !== "")
      .map((p) => ({ name: p.name, data_type_ref: p.data_type_ref.code, value: toWire(p.data_type_ref.code, values[p.name]) }));

  let preview: Parameter[] = [];
  let previewError: string | null = null;
  try {
    preview = wire();
  } catch (e) {
    previewError = errorText(e);
  }
  const last = state.commands.find((c) => c.id === lastId);

  if (params.length === 0) {
    return <p className="hint">This component declares no parameters.</p>;
  }
  return (
    <Split>
      <Card
        title="Parameters"
        end={
          <>
            <MethodButton
              label="Get"
              method="get_parameter"
              disabled={!bound || read.pending}
              onClick={() =>
                read.run(async () => {
                  const current = await session.getParameter(componentRef);
                  setValues((old) => ({
                    ...old,
                    ...Object.fromEntries(current.map((p) => [p.name, fromWire(p.data_type_ref, p.value)])),
                  }));
                })
              }
            />
            <MethodButton
              primary
              label="Set"
              method="set_parameter"
              disabled={!bound || write.pending || previewError !== null || preview.length === 0}
              onClick={() => write.run(async () => setLastId(await session.setParameter(componentRef, wire())))}
            />
          </>
        }
      >
        {!bound && <p className="hint">Bind the component to read and set its parameters.</p>}
        <div className="fields">
          {params.map((p) => (
            <ValueField
              key={p.name}
              profile={p}
              value={values[p.name] ?? ""}
              onChange={(value) => setValues((old) => ({ ...old, [p.name]: value }))}
              disabled={p.read_only}
            />
          ))}
        </div>
        {(read.error || write.error || previewError) && (
          <p className="message bad">{read.error ?? write.error ?? previewError}</p>
        )}
        {last && (
          <p className="row">
            set_parameter <span className="mono">{last.id}</span> <Pill status={last.status} />
          </p>
        )}
      </Card>
      <CodeBlock code={parameterSnippet(componentRef, preview)} />
    </Split>
  );
}

function Queries({ componentRef, profile }: { componentRef: string; profile: HRIComponentProfile }) {
  const queries = profile.query_profiles ?? [];
  const [selected, setSelected] = useState(queries[0]?.name ?? "");
  const [args, setArgs] = useState<Record<string, string>>({});
  const [results, setResults] = useState<Result[] | null>(null);
  const [session] = useSession();
  const action = useAction();
  const message = queries.find((q) => q.name === selected);

  if (queries.length === 0) {
    return <p className="hint">This component declares no queries.</p>;
  }
  const filled = Object.fromEntries(Object.entries(args).filter(([, v]) => v.trim() !== ""));
  return (
    <Split>
      <div className="stack">
        <Card
          title={
            <select
              className="select"
              aria-label="Query"
              value={selected}
              onChange={(e) => {
                setSelected(e.target.value);
                setArgs({});
                setResults(null);
              }}
            >
              {queries.map((q) => (
                <option key={q.name}>{q.name}</option>
              ))}
            </select>
          }
          end={
            <MethodButton
              primary
              label="Run"
              method="query"
              disabled={action.pending}
              onClick={() => action.run(async () => setResults(await session.query(componentRef, selected, filled)))}
            />
          }
        >
          {(message?.arguments ?? []).length > 0 ? (
            <div className="fields">
              {(message?.arguments ?? []).map((arg) => (
                <ValueField
                  key={arg.name}
                  profile={arg}
                  value={args[arg.name] ?? ""}
                  onChange={(value) => setArgs((old) => ({ ...old, [arg.name]: value }))}
                />
              ))}
            </div>
          ) : (
            <p className="hint">
              No arguments. Results: {(message?.results ?? []).map((r) => r.name).join(", ") || "none"}.
            </p>
          )}
          {action.error && <p className="message bad">{action.error}</p>}
        </Card>
        {results && (
          <Card title="Results">
            <ResultsTable results={results} />
          </Card>
        )}
      </div>
      <CodeBlock code={querySnippet(componentRef, selected, filled)} />
    </Split>
  );
}

function Commands({ componentRef, profile }: { componentRef: string; profile: HRIComponentProfile }) {
  const [session, state] = useSession();
  const commands = profile.command_profiles ?? [];
  const [selected, setSelected] = useState(commands[0]?.name ?? "");
  const [args, setArgs] = useState<Record<string, string>>({});
  const [results, setResults] = useState<Record<string, Result[]>>({});
  const action = useAction();
  const message = commands.find((c) => c.name === selected);
  const bound = state.bound.has(componentRef);

  if (commands.length === 0) {
    return <p className="hint">This component declares no commands.</p>;
  }

  let list: CommandUnitSequenceItemInput[] = [];
  let listError: string | null = null;
  try {
    const wireArgs = (message?.arguments ?? [])
      .filter((a) => (args[a.name] ?? "").trim() !== "")
      .map((a) => ({ name: a.name, data_type_ref: a.data_type_ref.code, value: toWire(a.data_type_ref.code, args[a.name]) }));
    list = [{ component_ref: componentRef, command_type: selected, ...(wireArgs.length ? { arguments: wireArgs } : {}) }];
  } catch (e) {
    listError = errorText(e);
  }
  const history = state.commands.filter((c) => c.ref === componentRef).slice(-8).reverse();

  return (
    <Split>
      <div className="stack">
        <Card
          title={
            <select
              className="select"
              aria-label="Command"
              value={selected}
              onChange={(e) => {
                setSelected(e.target.value);
                setArgs({});
              }}
            >
              {commands.map((c) => (
                <option key={c.name}>{c.name}</option>
              ))}
            </select>
          }
          end={
            <MethodButton
              primary
              label="Run"
              method="execute"
              disabled={!bound || action.pending || listError !== null}
              onClick={() => action.run(async () => void (await session.execute(list, [{ ref: componentRef, type: selected }])))}
            />
          }
        >
          {!bound && <p className="hint">Bind the component to command it.</p>}
          {(message?.arguments ?? []).length > 0 ? (
            <div className="fields">
              {(message?.arguments ?? []).map((arg) => (
                <ValueField
                  key={arg.name}
                  profile={arg}
                  value={args[arg.name] ?? ""}
                  onChange={(value) => setArgs((old) => ({ ...old, [arg.name]: value }))}
                />
              ))}
            </div>
          ) : (
            <p className="hint">No arguments{message?.timeout ? `. Start timeout: ${message.timeout} ms` : ""}.</p>
          )}
          {(action.error || listError) && <p className="message bad">{action.error ?? listError}</p>}
        </Card>
        <Card title="Commands of This Session">
          {history.length === 0 ? (
            <p className="hint">None yet. A command runs until its rois.command.completed arrives.</p>
          ) : (
            <div className="timeline">
              {history.map((c) => (
                <div key={c.id}>
                  <div className="timeline-row">
                    <span className="what">
                      <strong>{c.type}</strong> <span className="id mono">{c.id}</span>{" "}
                      <span className="id">{clock(c.sentAt)}</span>
                    </span>
                    <span className="row">
                      <Pill status={c.status} />
                      {c.status !== "RUNNING" && (
                        <MethodButton
                          label="Results"
                          method="get_command_result"
                          onClick={() =>
                            action.run(async () => {
                              const r = await session.getCommandResult(c.id);
                              setResults((old) => ({ ...old, [c.id]: r }));
                            })
                          }
                        />
                      )}
                    </span>
                  </div>
                  {results[c.id] && <ResultsTable results={results[c.id]} />}
                </div>
              ))}
            </div>
          )}
        </Card>
      </div>
      <CodeBlock code={executeSnippet(list)} />
    </Split>
  );
}

function Events({ componentRef, profile }: { componentRef: string; profile: HRIComponentProfile }) {
  const [session, state] = useSession();
  const events = profile.event_profiles ?? [];
  const [details, setDetails] = useState<Record<string, Result[]>>({});
  const action = useAction();
  const received = state.events.filter((e) => e.ref === componentRef).slice(-20).reverse();

  if (events.length === 0) {
    return <p className="hint">This component declares no events.</p>;
  }
  return (
    <Split>
      <div className="stack">
        <Card title="Events">
          <table className="table">
            <tbody>
              {events.map((event) => {
                const subscription = state.subscriptions.find(
                  (s) => s.ref === componentRef && s.eventType === event.name,
                );
                return (
                  <tr key={event.name}>
                    <td>
                      <strong>{event.name}</strong>
                      <div className="field-help mono">
                        {(event.results ?? []).map((r) => `${r.name}: ${r.data_type_ref.code}`).join(", ")}
                      </div>
                    </td>
                    <td style={{ textAlign: "right" }}>
                      {subscription ? (
                        <MethodButton
                          label="Unsubscribe"
                          method="unsubscribe"
                          onClick={() => action.run(() => session.unsubscribe(subscription.id))}
                        />
                      ) : (
                        <MethodButton
                          primary
                          label="Subscribe"
                          method="subscribe"
                          onClick={() => action.run(() => session.subscribeEvent(componentRef, event.name))}
                        />
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          {action.error && <p className="message bad">{action.error}</p>}
        </Card>
        <Card title="Received">
          {received.length === 0 ? (
            <p className="hint">Subscribe to an event, and each rois.event.notify_event shows here.</p>
          ) : (
            <div className="timeline">
              {received.map(({ at, params }) => (
                <div key={params.event_id}>
                  <div className="timeline-row">
                    <span className="what">
                      <strong>{params.event_type}</strong> <span className="id">{clock(at)}</span>{" "}
                      <span className="id mono">{params.event_id}</span>
                    </span>
                    <MethodButton
                      label="Detail"
                      method="get_event_detail"
                      onClick={() =>
                        action.run(async () => {
                          const r = await session.getEventDetail(params.event_id);
                          setDetails((old) => ({ ...old, [params.event_id]: r }));
                        })
                      }
                    />
                  </div>
                  <ResultsTable results={details[params.event_id] ?? params.results ?? []} />
                </div>
              ))}
            </div>
          )}
        </Card>
      </div>
      <CodeBlock code={subscribeSnippet(componentRef, events[0].name)} />
    </Split>
  );
}
