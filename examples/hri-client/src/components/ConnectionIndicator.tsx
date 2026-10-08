import type { ConnectionState } from "../hooks/useRoISClient";

interface ConnectionIndicatorProps {
  state: ConnectionState;
  error: string | null;
}

const LABELS: Record<Exclude<ConnectionState, "error">, string> = {
  idle: "Not connected",
  connecting: "Connecting...",
  connected: "Connected",
};

/**
 * Colored dot + text showing the engine connection state.
 *
 * Green dot: connected. Red dot: error. Yellow dot: connecting. Grey dot: not
 * connected.
 */
export function ConnectionIndicator({ state, error }: ConnectionIndicatorProps) {
  const label = state === "error" ? `Error: ${error ?? "unknown"}` : LABELS[state];

  return (
    <div className="connection-indicator">
      <span className={`connection-dot ${state}`} />
      <span className="connection-text">{label}</span>
    </div>
  );
}
