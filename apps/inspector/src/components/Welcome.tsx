import { useEffect, useRef, useState } from "react";
import type { Result } from "@openrois/interfaces";
import { useSession } from "../lib/useSession";
import { errorText } from "../lib/session";
import { allComponents, engineTree } from "../lib/engines";
import { connectSnippet } from "../lib/snippets";
import { Card, CodeBlock, MethodButton, Pill, ResultsTable, Tag, clock, useUi } from "./ui";
import type { View } from "../App";

/** The first component of a RoIS type, such as "Navigation", in the profile. */
function firstOfType(profiles: Record<string, { identifier: { code: string } }>, type: string): string | null {
  return Object.keys(profiles).find((ref) => profiles[ref].identifier.code === type) ?? null;
}

function TrafficLink({ query }: { query: string }) {
  const { showInTraffic } = useUi();
  return (
    <button type="button" className="btn btn-ghost btn-small" onClick={() => showInTraffic(query)}>
      Show in Traffic →
    </button>
  );
}

function ReadPosition({ componentRef }: { componentRef: string }) {
  const [session] = useSession();
  const [results, setResults] = useState<Result[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  return (
    <Card title="Read the Position" end={<TrafficLink query="rois.query.query" />}>
      <p className="hint" style={{ marginTop: 0 }}>
        Ask <span className="mono">{componentRef}</span> where the robot is. A query needs no reservation.
      </p>
      <MethodButton
        primary
        label="Run Query"
        method="query"
        onClick={() =>
          session
            .query(componentRef, "robot_position", {})
            .then(setResults)
            .catch((e) => setError(errorText(e)))
        }
      />
      {error && <p className="message bad">{error}</p>}
      {results && <ResultsTable results={results} />}
    </Card>
  );
}

function WatchPeople({ componentRef }: { componentRef: string }) {
  const [session, state] = useSession();
  const [error, setError] = useState<string | null>(null);
  const subscription = state.subscriptions.find((s) => s.ref === componentRef && s.eventType === "person_detected");
  const events = state.events.filter((e) => subscription && e.params.subscribe_id === subscription.id).slice(-3).reverse();
  return (
    <Card title="Watch for People" end={<TrafficLink query="notify_event" />}>
      <p className="hint" style={{ marginTop: 0 }}>
        Subscribe to <span className="mono">person_detected</span> on <span className="mono">{componentRef}</span>. Each
        detection arrives as a notification.
      </p>
      {subscription ? (
        <MethodButton
          label="Unsubscribe"
          method="unsubscribe"
          onClick={() => session.unsubscribe(subscription.id).catch((e) => setError(errorText(e)))}
        />
      ) : (
        <MethodButton
          primary
          label="Subscribe"
          method="subscribe"
          onClick={() => session.subscribeEvent(componentRef, "person_detected").catch((e) => setError(errorText(e)))}
        />
      )}
      {subscription && (
        <p className="hint">
          subscribe_id <span className="mono">{subscription.id}</span>
        </p>
      )}
      {error && <p className="message bad">{error}</p>}
      {events.map(({ at, params }) => (
        <div key={params.event_id} className="timeline-row" style={{ marginTop: 6 }}>
          <span className="what">
            <strong>{params.event_type}</strong> <span className="id">{clock(at)}</span>
          </span>
          <span className="mono hint">
            {(params.results ?? []).map((r) => `${r.name}=${r.value}`).join(" ")}
          </span>
        </div>
      ))}
    </Card>
  );
}

function DriveToTarget({ componentRef }: { componentRef: string }) {
  const [session, state] = useSession();
  const [commandId, setCommandId] = useState<string | null>(null);
  const [subscribeId, setSubscribeId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [now, setNow] = useState(Date.now());
  const bound = state.bound.has(componentRef);
  const command = state.commands.find((c) => c.id === commandId);
  const running = command?.status === "RUNNING";
  const arrived = state.events.filter((e) => subscribeId && e.params.subscribe_id === subscribeId);
  const subscribed = useRef<string | null>(null);

  useEffect(() => {
    if (!running) return;
    const timer = setInterval(() => setNow(Date.now()), 100);
    return () => clearInterval(timer);
  }, [running]);

  // The step listens for reached_target only while its command runs.
  useEffect(() => {
    if (command && command.status !== "RUNNING" && subscribed.current) {
      const id = subscribed.current;
      subscribed.current = null;
      void session.unsubscribe(id).catch(() => undefined);
    }
  }, [command, session]);

  const start = async () => {
    setError(null);
    try {
      await session.subscribeEvent(componentRef, "reached_target");
      const sub = session.snapshot().subscriptions.find((s) => s.ref === componentRef && s.eventType === "reached_target");
      subscribed.current = sub?.id ?? null;
      setSubscribeId(sub?.id ?? null);
      const [id] = await session.execute([{ component_ref: componentRef, command_type: "start" }], [
        { ref: componentRef, type: "start" },
      ]);
      setCommandId(id);
    } catch (e) {
      setError(errorText(e));
    }
  };

  return (
    <Card title="Drive to a Target" end={<TrafficLink query="rois.command" />}>
      <p className="hint" style={{ marginTop: 0 }}>
        Reserve <span className="mono">{componentRef}</span>, command it, and release it. The command ends with{" "}
        <span className="mono">completed</span>, after <span className="mono">reached_target</span>.
      </p>
      <div className="steps-inline">
        <MethodButton
          primary={!bound}
          label="1 · Bind"
          method="bind"
          disabled={bound}
          onClick={() => session.bind(componentRef).catch((e) => setError(errorText(e)))}
        />
        <MethodButton primary={bound && !running} label="2 · Start" method="execute" disabled={!bound || running} onClick={start} />
        <MethodButton
          label="3 · Release"
          method="release"
          disabled={!bound || running}
          onClick={() => session.release(componentRef).catch((e) => setError(errorText(e)))}
        />
      </div>
      {error && <p className="message bad">{error}</p>}
      {arrived.map(({ params }) => (
        <div key={params.event_id} className="timeline-row" style={{ marginTop: 6 }}>
          <span className="what">
            <strong>reached_target</strong>
          </span>
          <span className="mono hint">{(params.results ?? []).map((r) => `${r.name}=${r.value}`).join(" ")}</span>
        </div>
      ))}
      {command && (
        <div className="timeline-row" style={{ marginTop: 6 }}>
          <span className="what">
            <strong>start</strong> <span className="id mono">{command.id}</span>
          </span>
          <span className="row">
            <span className="id">{((command.endedAt ?? now) - command.sentAt).toString()} ms</span>
            <Pill status={command.status} label={command.status === "RUNNING" ? "Pending" : command.status} />
          </span>
        </div>
      )}
    </Card>
  );
}

/** The overview: the main HRI Engine, the session, and guided first steps. */
export function Welcome({ onOpen }: { onOpen: (view: View) => void }) {
  const [session, state] = useSession();
  const [details, setDetails] = useState<Record<string, Result[] | string>>({});
  if (!state.profile) return null;
  const tree = engineTree(state.profile);
  const profiles = state.profile.component_profiles;
  const children = countEngines(tree) - 1;
  const components = allComponents(tree).length;
  const info = firstOfType(profiles, "SystemInformation");
  const people = firstOfType(profiles, "PersonDetection");
  const navigation = firstOfType(profiles, "Navigation");

  return (
    <div className="stack">
      <Card title={<span className="kicker">Main HRI Engine</span>} className="accent-top">
        <h2 style={{ margin: "0 0 10px", fontSize: 20 }}>
          You are connected to <span className="mono">{tree.id}</span>, the main HRI Engine
        </h2>
        <ul className="checks">
          <li>
            Connected to <span className="mono">{state.url}</span> <Tag>connect</Tag>
          </li>
          <li>
            Profile loaded: {children} child {children === 1 ? "engine" : "engines"}, {components} HRI Components{" "}
            <Tag>get_profile</Tag>
          </li>
          <li>
            Listening for <Tag>completed</Tag> <Tag>notify_event</Tag> <Tag>notify_error</Tag> <Tag>profile_changed</Tag>
          </li>
        </ul>
      </Card>

      <div className="kicker" style={{ marginTop: 6 }}>
        Try This
      </div>
      <div className="try">
        {info && <ReadPosition componentRef={info} />}
        {people && <WatchPeople componentRef={people} />}
        {navigation && <DriveToTarget componentRef={navigation} />}
        <Card
          title="Build a Sequence →"
          className="clickable"
          end={<TrafficLink query="rois.command.execute" />}
        >
          <div
            role="button"
            tabIndex={0}
            onClick={() => onOpen({ kind: "sequence", example: true })}
            onKeyDown={(e) => e.key === "Enter" && onOpen({ kind: "sequence", example: true })}
          >
            <p className="hint" style={{ marginTop: 0 }}>
              One <span className="mono">execute</span> with a command, then a concurrent group of two branches. One
              branch fails on purpose, so you can see how a failure ends its branch.
            </p>
            <span className="btn btn-small">Open the Example</span>
          </div>
        </Card>
      </div>

      {state.errors.length > 0 && (
        <Card title="Errors the Engine Reported">
          <div className="timeline">
            {[...state.errors].reverse().map(({ at, params }) => (
              <div key={params.error_id}>
                <div className="timeline-row">
                  <span className="what">
                    <Pill status="ERROR" label={params.error_type} /> <span className="id mono">{params.error_id}</span>{" "}
                    <span className="id">{clock(at)}</span>
                  </span>
                  <MethodButton
                    label="Detail"
                    method="get_error_detail"
                    onClick={() =>
                      session
                        .getErrorDetail(params.error_id)
                        .then((r) => setDetails((old) => ({ ...old, [params.error_id]: r })))
                        .catch((e) => setDetails((old) => ({ ...old, [params.error_id]: errorText(e) })))
                    }
                  />
                </div>
                {typeof details[params.error_id] === "string" && (
                  <p className="message bad">{details[params.error_id] as string}</p>
                )}
                {Array.isArray(details[params.error_id]) && (
                  <ResultsTable results={details[params.error_id] as Result[]} />
                )}
              </div>
            ))}
          </div>
        </Card>
      )}

      <CodeBlock code={connectSnippet(state.url)} title="Connect with @openrois/sdk" />
    </div>
  );
}

function countEngines(node: { children: { children: unknown[] }[] }): number {
  return 1 + node.children.reduce((n, child) => n + countEngines(child as { children: { children: unknown[] }[] }), 0);
}
