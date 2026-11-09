import { useState, type FormEvent } from "react";
import { useSession } from "../lib/useSession";
import { Card, Tag } from "./ui";

const EXPLAINERS = [
  {
    kicker: "Discover",
    title: "Discover Components",
    text: "Read the profile of the main HRI Engine, its child engines and every HRI Component they host.",
    methods: ["get_profile", "search"],
  },
  {
    kicker: "Read",
    title: "Read State",
    text: "Ask a component for its state and its parameters. Queries need no reservation.",
    methods: ["query", "get_parameter"],
  },
  {
    kicker: "Act",
    title: "Command and React",
    text: "Reserve a component, command it, follow each command to its end, and release it.",
    methods: ["bind", "execute", "subscribe", "release"],
  },
];

/** The first screen: where the gateway is, and what a service application does with it. */
export function ConnectScreen({ defaultUrl }: { defaultUrl: string }) {
  const [session, state] = useSession();
  const [url, setUrl] = useState(defaultUrl);
  const [requestTimeout, setRequestTimeout] = useState("30000");
  const [connectTimeout, setConnectTimeout] = useState("10000");
  const busy = state.status === "connecting";
  const failed = state.status === "error" || state.status === "closed";

  const submit = (event: FormEvent) => {
    event.preventDefault();
    void session.connect(url.trim(), {
      requestTimeout: Number(requestTimeout) || undefined,
      connectTimeout: Number(connectTimeout) || undefined,
    });
  };

  return (
    <div className="connect-screen">
      <div className="inner">
        <img className="logo" src="/logo.svg" alt="" />
        <div className="kicker" style={{ marginTop: 16 }}>
          Service application
        </div>
        <h1 style={{ fontSize: 30, letterSpacing: "-0.02em", margin: "6px 0" }}>Connect to a Gateway</h1>
        <p className="hint" style={{ fontSize: 15, maxWidth: 640 }}>
          The Inspector speaks the RoIS method catalog over JSON-RPC 2.0 and WebSocket with{" "}
          <code>@openrois/sdk</code>, as your own service application would.
        </p>

        <form className="connect-form" onSubmit={submit}>
          <input
            className="input mono"
            aria-label="Gateway endpoint"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            spellCheck={false}
            autoFocus
          />
          <button type="submit" className="btn btn-primary" disabled={busy || url.trim() === ""}>
            {busy ? "Connecting" : failed ? "Retry" : "Connect"} <Tag>connect</Tag>
          </button>
        </form>

        {failed && (
          <p className="message bad">
            Could not reach <span className="mono">{state.url}</span>. Is the compose stack running?{" "}
            <span className="mono">docker compose up --build</span>
            {state.error && <span className="field-help"> ({state.error})</span>}
          </p>
        )}

        <details className="disclosure">
          <summary>Timeouts</summary>
          <div className="row" style={{ marginTop: 8 }}>
            <label className="field">
              <span className="field-label">
                Request <span className="type">requestTimeout, ms</span>
              </span>
              <input className="input mono" value={requestTimeout} onChange={(e) => setRequestTimeout(e.target.value)} />
            </label>
            <label className="field">
              <span className="field-label">
                Connect <span className="type">connectTimeout, ms</span>
              </span>
              <input className="input mono" value={connectTimeout} onChange={(e) => setConnectTimeout(e.target.value)} />
            </label>
          </div>
        </details>

        <div className="explainers">
          {EXPLAINERS.map((e) => (
            <Card key={e.title} title={<span className="kicker">{e.kicker}</span>}>
              <h3>{e.title}</h3>
              <p className="hint" style={{ margin: 0 }}>
                {e.text}
              </p>
              <div className="tags">
                {e.methods.map((m) => (
                  <Tag key={m}>{m}</Tag>
                ))}
              </div>
            </Card>
          ))}
        </div>
      </div>
    </div>
  );
}
