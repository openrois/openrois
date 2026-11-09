import { useEffect, useRef, useState, type ReactNode } from "react";
import type { Result } from "@openrois/interfaces";
import { useSession } from "../lib/useSession";
import { errorText, type LogEntry } from "../lib/session";
import { Frame, MethodButton, Pill, ResultsTable, clock } from "./ui";

const ARROW: Record<LogEntry["kind"], string> = {
  request: "→",
  response: "←",
  notification: "◆",
  failure: "✕",
  note: "·",
};

type Kind = "all" | "requests" | "notifications" | "failures";

const KINDS: { id: Kind; label: string }[] = [
  { id: "all", label: "All" },
  { id: "requests", label: "Requests" },
  { id: "notifications", label: "Notifications" },
  { id: "failures", label: "Failures" },
];

const OF_KIND: Record<Kind, (entry: LogEntry) => boolean> = {
  all: () => true,
  requests: (e) => e.kind === "request" || e.kind === "response",
  notifications: (e) => e.kind === "notification",
  failures: (e) => e.kind === "failure",
};

/** One line of the log: a frame, or in Pair view a request with its response. */
interface Row {
  key: number;
  entry: LogEntry;
  response?: LogEntry;
}

function rows(log: readonly LogEntry[], paired: boolean): Row[] {
  if (!paired) return log.map((entry) => ({ key: entry.seq, entry }));
  const responses = new Map<number | string, LogEntry>();
  for (const entry of log) {
    if ((entry.kind === "response" || entry.kind === "failure") && entry.rpcId !== undefined) {
      responses.set(entry.rpcId, entry);
    }
  }
  return log
    .filter((entry) => !((entry.kind === "response" || entry.kind === "failure") && entry.rpcId !== undefined))
    .map((entry) => ({
      key: entry.seq,
      entry,
      response: entry.rpcId !== undefined ? responses.get(entry.rpcId) : undefined,
    }));
}

function exportJsonl(log: readonly LogEntry[]): void {
  const lines = log
    .filter((e) => e.raw !== "")
    .map((e) => JSON.stringify({ at: new Date(e.at).toISOString(), kind: e.kind, message: JSON.parse(e.raw) }));
  const blob = new Blob([lines.join("\n") + "\n"], { type: "application/jsonl" });
  const link = document.createElement("a");
  link.href = URL.createObjectURL(blob);
  link.download = `openrois-inspector-${new Date().toISOString().replace(/[:.]/g, "-")}.jsonl`;
  link.click();
  URL.revokeObjectURL(link.href);
}

/** The notify_error behind a log row, with its detail on request. */
function ErrorDetail({ entry }: { entry: LogEntry }) {
  const [session] = useSession();
  const [detail, setDetail] = useState<Result[] | string | null>(null);
  const errorId = (JSON.parse(entry.raw) as { params?: { error_id?: string } }).params?.error_id;
  if (!errorId) return null;
  return (
    <div style={{ padding: "8px 0" }}>
      <MethodButton
        label="Read Detail"
        method="get_error_detail"
        onClick={() =>
          session
            .getErrorDetail(errorId)
            .then(setDetail)
            .catch((e) => setDetail(errorText(e)))
        }
      />
      {typeof detail === "string" && <p className="message bad">{detail}</p>}
      {Array.isArray(detail) && <ResultsTable results={detail} />}
    </div>
  );
}

/**
 * Every JSON-RPC message of the session, in order: what the SDK sent, what the
 * gateway answered and the notifications it pushed. A row opens to the raw message.
 */
export function ActivityLog({
  open,
  onOpen,
  query,
  onQuery,
}: {
  open: boolean;
  onOpen: (open: boolean) => void;
  query: string;
  onQuery: (query: string) => void;
}) {
  const [session, state] = useSession();
  const [kind, setKind] = useState<Kind>("all");
  const [paired, setPaired] = useState(true);
  const [expanded, setExpanded] = useState<number | null>(null);
  const body = useRef<HTMLDivElement>(null);
  const stick = useRef(true);
  const q = query.trim().toLowerCase();
  const shown = rows(state.log, paired).filter(
    ({ entry, response }) =>
      OF_KIND[kind](entry) &&
      (q === "" ||
        `${entry.method} ${entry.summary} ${entry.raw} ${response?.summary ?? ""}`.toLowerCase().includes(q)),
  );
  const errors = state.errors.length;

  useEffect(() => {
    const el = body.current;
    if (el && stick.current) el.scrollTop = el.scrollHeight;
  }, [shown.length]);

  useEffect(() => {
    const close = (e: KeyboardEvent) => {
      if (e.key === "Escape") setExpanded(null);
    };
    window.addEventListener("keydown", close);
    return () => window.removeEventListener("keydown", close);
  }, []);

  return (
    <section className={`log${open ? "" : " collapsed"}`} aria-label="Activity">
      <header className="log-head">
        <button type="button" className="btn btn-ghost btn-small" onClick={() => onOpen(!open)} aria-expanded={open}>
          {open ? "▾" : "▸"}
        </button>
        <h2>Activity</h2>
        <span className="hint">{state.log.length} messages</span>
        {state.paused && <Pill status="WARNING" label="Paused" />}
        {errors > 0 && <Pill status="ERROR" label={`${errors} notify_error`} />}
        <div className="end">
          <input
            className="input mono"
            type="search"
            placeholder="Filter"
            aria-label="Filter the log"
            value={query}
            onChange={(e) => onQuery(e.target.value)}
            style={{ padding: "3px 8px", width: 160 }}
          />
          <div className="segmented" role="group" aria-label="Kind">
            {KINDS.map(({ id, label }) => (
              <button key={id} type="button" aria-pressed={kind === id} onClick={() => setKind(id)}>
                {label}
              </button>
            ))}
          </div>
          <div className="segmented" role="group" aria-label="Layout">
            <button type="button" aria-pressed={paired} onClick={() => setPaired(true)} title="A request with its response">
              Pair
            </button>
            <button type="button" aria-pressed={!paired} onClick={() => setPaired(false)} title="Every frame">
              Flat
            </button>
          </div>
          <button type="button" className="btn btn-ghost btn-small" onClick={() => session.setPaused(!state.paused)}>
            {state.paused ? "Resume" : "Pause"}
          </button>
          <button type="button" className="btn btn-ghost btn-small" onClick={() => exportJsonl(state.log)}>
            Export .jsonl
          </button>
          <button type="button" className="btn btn-ghost btn-small" onClick={() => session.clearLog()}>
            Clear
          </button>
        </div>
      </header>
      {open && (
        <div
          className="log-body"
          ref={body}
          onScroll={(e) => {
            const el = e.currentTarget;
            stick.current = el.scrollHeight - el.scrollTop - el.clientHeight < 24;
          }}
        >
          {shown.length === 0 && <div className="empty">Messages appear here as the session runs.</div>}
          {shown.map(({ key, entry, response }) => {
            const isOpen = expanded === key;
            const detail: ReactNode = isOpen && (
                <div style={{ padding: "6px 16px 12px" }}>
                  <Frame caption={`${entry.method} · ${entry.kind}`} text={entry.raw || entry.summary} />
                  {response && (
                    <div style={{ marginTop: 8 }}>
                      <Frame caption={`${response.method} · ${response.kind}`} text={response.raw} />
                    </div>
                  )}
                  {entry.method === "rois.system.notify_error" && <ErrorDetail entry={entry} />}
                </div>
            );
            return (
              <div key={key}>
                <div
                  className="log-row"
                  role="button"
                  tabIndex={0}
                  aria-expanded={isOpen}
                  onClick={() => setExpanded(isOpen ? null : key)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === " ") setExpanded(isOpen ? null : key);
                  }}
                >
                  <span className="time">{clock(entry.at)}</span>
                  <span className={`arrow ${response ? response.kind : entry.kind}`}>
                    {response ? "⇄" : ARROW[entry.kind]}
                  </span>
                  <span>{entry.method || "inspector"}</span>
                  <span className="summary">
                    {entry.summary}
                    {response && ` → ${response.summary}`}
                  </span>
                </div>
                {detail}
              </div>
            );
          })}
        </div>
      )}
    </section>
  );
}
