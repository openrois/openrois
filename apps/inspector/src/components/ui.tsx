import { createContext, useContext, useState, type ButtonHTMLAttributes, type ReactNode } from "react";
import type { ParameterProfile, Result } from "@openrois/interfaces";
import { inputKind, showResult } from "../lib/values";

/** The pill class of a component status, a completed status or a connection status. */
export function tone(status: string): "ok" | "warn" | "bad" | "idle" | "run" {
  switch (status) {
    case "READY":
    case "OK":
    case "connected":
      return "ok";
    case "BUSY":
    case "WARNING":
    case "ABORT":
    case "TIMEOUT":
    case "connecting":
      return "warn";
    case "ERROR":
    case "OUT_OF_RESOURCES":
    case "error":
    case "closed":
      return "bad";
    case "RUNNING":
      return "run";
    default:
      return "idle";
  }
}

export function Pill({ status, label }: { status: string; label?: string }) {
  return <span className={`pill ${tone(status)}`}>{label ?? status}</span>;
}

export function Card({
  title,
  end,
  children,
  className = "",
}: {
  title: ReactNode;
  end?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={`card ${className}`}>
      <header className="card-head">
        <h3>{title}</h3>
        {end && <div className="end">{end}</div>}
      </header>
      <div className="card-body">{children}</div>
    </section>
  );
}

/** A RoIS method or a data type, set as code next to a human label. */
export function Tag({ children }: { children: ReactNode }) {
  return <span className="tag">{children}</span>;
}

/** A button that calls one RoIS operation, labelled with the operation's name. */
export function MethodButton({
  label,
  method,
  primary,
  small = true,
  ...rest
}: {
  label: string;
  method: string;
  primary?: boolean;
  small?: boolean;
} & Omit<ButtonHTMLAttributes<HTMLButtonElement>, "children">) {
  return (
    <button
      type="button"
      className={`btn${primary ? " btn-primary" : ""}${small ? " btn-small" : ""}`}
      {...rest}
    >
      {label} <Tag>{method}</Tag>
    </button>
  );
}

function useCopy(text: string): [boolean, () => void] {
  const [copied, setCopied] = useState(false);
  const copy = () => {
    navigator.clipboard
      ?.writeText(text)
      .then(() => {
        setCopied(true);
        setTimeout(() => setCopied(false), 1200);
      })
      .catch(() => undefined);
  };
  return [copied, copy];
}

/** The window frame of openrois.org: three dots, a caption, and code. */
export function Frame({ caption, text, end }: { caption: string; text: string; end?: ReactNode }) {
  const [copied, copy] = useCopy(text);
  return (
    <div className="frame">
      <div className="frame-bar">
        <i />
        <i />
        <i />
        <span className="caption">{caption}</span>
        <span className="end row">
          {end}
          <button type="button" className="btn btn-ghost btn-small" onClick={copy}>
            {copied ? "Copied" : "Copy"}
          </button>
        </span>
      </div>
      <pre>{text}</pre>
    </div>
  );
}

/** What the views share beyond the session: the SDK-calls toggle and the log query. */
export interface UiState {
  showCode: boolean;
  setShowCode: (show: boolean) => void;
  /** Filter the activity log to one method or component and open it. */
  showInTraffic: (query: string) => void;
}

export const UiContext = createContext<UiState>({
  showCode: false,
  setShowCode: () => undefined,
  showInTraffic: () => undefined,
});

export function useUi(): UiState {
  return useContext(UiContext);
}

/** The @openrois/sdk calls of a view, shown when "SDK Calls" is on. */
export function CodeBlock({ code, title = "With @openrois/sdk" }: { code: string; title?: string }) {
  const { showCode } = useUi();
  if (!showCode) return null;
  return <Frame caption={title} text={code} />;
}

/** The two-column layout of a view, one column while the SDK calls are hidden. */
export function Split({ children }: { children: ReactNode }) {
  const { showCode } = useUi();
  return <div className={showCode ? "grid" : "grid single"}>{children}</div>;
}

/** An input for a value of a profile type: a list, a boolean, a number or text. */
export function ValueField({
  profile,
  value,
  onChange,
  disabled,
}: {
  profile: ParameterProfile;
  value: string;
  onChange: (value: string) => void;
  disabled?: boolean;
}) {
  const type = profile.data_type_ref.code;
  const kind = inputKind(type);
  const id = `field-${profile.name}`;
  let input: ReactNode;
  if (kind === "list") {
    input = (
      <textarea
        id={id}
        className="textarea"
        value={value}
        rows={2}
        placeholder="One item per line"
        onChange={(e) => onChange(e.target.value)}
        disabled={disabled}
      />
    );
  } else if (kind === "boolean") {
    input = (
      <select id={id} className="select" value={value} onChange={(e) => onChange(e.target.value)} disabled={disabled}>
        <option value="">—</option>
        <option value="true">true</option>
        <option value="false">false</option>
      </select>
    );
  } else {
    input = (
      <input
        id={id}
        className="input mono"
        inputMode={kind === "number" ? "decimal" : undefined}
        value={value}
        placeholder={profile.default_value ?? ""}
        onChange={(e) => onChange(e.target.value)}
        disabled={disabled}
      />
    );
  }
  return (
    <div className="field">
      <label className="field-label" htmlFor={id}>
        {profile.name}
        <span className="type">{type}</span>
        {profile.read_only && <span className="chip">read only</span>}
      </label>
      {input}
      {profile.description && <span className="field-help">{profile.description}</span>}
    </div>
  );
}

export function ResultsTable({ results }: { results: Result[] }) {
  if (results.length === 0) {
    return <p className="hint">No results.</p>;
  }
  return (
    <table className="table">
      <thead>
        <tr>
          <th>Name</th>
          <th>Type</th>
          <th>Value</th>
        </tr>
      </thead>
      <tbody>
        {results.map((result) => (
          <tr key={result.name}>
            <td>{result.name}</td>
            <td className="mono">{result.data_type_ref}</td>
            <td className="mono">{showResult(result)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

/** Text for a time, in the local clock, to the millisecond. */
export function clock(at: number): string {
  const d = new Date(at);
  return `${d.toLocaleTimeString([], { hour12: false })}.${String(d.getMilliseconds()).padStart(3, "0")}`;
}
