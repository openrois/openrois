interface ConnectionIndicatorProps {
  connected: boolean;
  error: string | null;
}

/**
 * Colored dot + text showing the engine connection state.
 *
 * Green dot: connected. Red dot: error. Yellow dot: connecting.
 */
export function ConnectionIndicator({ connected, error }: ConnectionIndicatorProps) {
  const state = connected ? "connected" : error ? "error" : "connecting";
  const label = connected
    ? "Connected"
    : error
      ? `Error: ${error}`
      : "Connecting...";

  return (
    <div className="connection-indicator">
      <span className={`connection-dot ${state}`} />
      <span className="connection-text">{label}</span>
    </div>
  );
}