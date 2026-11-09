import { useSession } from "../lib/useSession";
import type { ThemeChoice } from "../lib/theme";
import { Pill, Tag, useUi } from "./ui";

const STATUS_LABEL = {
  idle: "Not Connected",
  connecting: "Connecting",
  connected: "Connected",
  closed: "Connection Lost",
  error: "Not Connected",
} as const;

const THEMES: { id: ThemeChoice; label: string }[] = [
  { id: "system", label: "Auto" },
  { id: "light", label: "Light" },
  { id: "dark", label: "Dark" },
];

export function Header({ theme, onTheme }: { theme: ThemeChoice; onTheme: (choice: ThemeChoice) => void }) {
  const [session, state] = useSession();
  const { showCode, setShowCode } = useUi();
  const connected = state.status === "connected";

  return (
    <header className="header">
      <a className="brand" href="https://openrois.org" target="_blank" rel="noreferrer" title="openrois.org">
        <img src="/logo.svg" alt="OpenRoIS" width={28} height={28} />
        <span className="wordmark">
          OpenRoIS
          <span className="rule" />
          <span className="product">Inspector</span>
        </span>
      </a>
      <span className="eyebrow">alpha · OMG RoIS 2.0</span>

      <div className="connect">
        {state.url && <span className="mono hint">{state.url}</span>}
        <Pill status={state.status} label={STATUS_LABEL[state.status]} />
        {connected && (
          <button type="button" className="btn btn-small" onClick={() => void session.disconnect()}>
            Disconnect <Tag>disconnect</Tag>
          </button>
        )}
      </div>

      <div className="header-end">
        <label className="row hint" style={{ gap: 6, cursor: "pointer" }}>
          <input type="checkbox" checked={showCode} onChange={(e) => setShowCode(e.target.checked)} />
          SDK Calls
        </label>
        <div className="segmented" role="radiogroup" aria-label="Theme">
          {THEMES.map(({ id, label }) => (
            <button
              key={id}
              type="button"
              role="radio"
              aria-checked={theme === id}
              aria-pressed={theme === id}
              onClick={() => onTheme(id)}
            >
              {label}
            </button>
          ))}
        </div>
        <a className="btn btn-ghost btn-small" href="https://openrois.org/docs/intro" target="_blank" rel="noreferrer">
          Docs
        </a>
      </div>
    </header>
  );
}
