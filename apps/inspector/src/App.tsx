import { useCallback, useEffect, useMemo, useState } from "react";
import { Session, lastUrl } from "./lib/session";
import { SessionContext, useSession } from "./lib/useSession";
import { useTheme } from "./lib/theme";
import { Header } from "./components/Header";
import { Sidebar } from "./components/Sidebar";
import { ComponentPage } from "./components/ComponentPage";
import { SequencePage } from "./components/SequencePage";
import { ActivityLog } from "./components/ActivityLog";
import { ConnectScreen } from "./components/ConnectScreen";
import { Footer } from "./components/Footer";
import { Welcome } from "./components/Welcome";
import { UiContext, type UiState } from "./components/ui";

export type ComponentTab = "overview" | "parameters" | "queries" | "commands" | "events";

export type View =
  | { kind: "welcome" }
  | { kind: "sequence"; example?: boolean }
  | { kind: "component"; ref: string; tab: ComponentTab };

const PARAMS = new URLSearchParams(window.location.search);
const CODE_KEY = "openrois-inspector-sdk-calls";

/**
 * The gateway URL to start with: ?url= in the address, then the last one this browser
 * used, then the build setting, then the gateway of `docker compose up` on this machine.
 */
function defaultUrl(): string {
  return PARAMS.get("url") || lastUrl() || import.meta.env.VITE_GATEWAY_URL || "ws://localhost:8765";
}

function storedShowCode(): boolean {
  try {
    return localStorage.getItem(CODE_KEY) === "1";
  } catch {
    return false;
  }
}

function Shell() {
  const [session, state] = useSession();
  const [theme, setTheme] = useTheme();
  const [view, setView] = useState<View>({ kind: "welcome" });
  const [logOpen, setLogOpen] = useState(true);
  const [logQuery, setLogQuery] = useState("");
  const [showCode, setShowCodeState] = useState(storedShowCode);
  const url = useMemo(defaultUrl, []);

  // ?autoconnect=1 connects on load, so a quickstart link is one click.
  useEffect(() => {
    if (PARAMS.get("autoconnect") === "1") void session.connect(url);
    return () => void session.disconnect();
  }, [session, url]);

  const setShowCode = useCallback((show: boolean) => {
    setShowCodeState(show);
    try {
      localStorage.setItem(CODE_KEY, show ? "1" : "0");
    } catch {
      // The toggle still applies to this visit.
    }
  }, []);

  const ui: UiState = useMemo(
    () => ({
      showCode,
      setShowCode,
      showInTraffic: (query: string) => {
        setLogQuery(query);
        setLogOpen(true);
      },
    }),
    [showCode, setShowCode],
  );

  // A component that left the profile, with its engine, takes the view back to the start.
  const shown =
    view.kind === "component" && state.profile && !state.profile.component_profiles[view.ref]
      ? ({ kind: "welcome" } as const)
      : view;
  const lost = state.status === "closed" && state.profile !== null;
  const ready = state.profile !== null && (state.status === "connected" || lost);

  return (
    <UiContext.Provider value={ui}>
      <div className="shell">
        <Header theme={theme} onTheme={setTheme} />
        {lost && (
          <div className="banner" role="alert">
            The connection to the gateway was lost. Binds and subscriptions ended with it.
            <button type="button" className="btn btn-small" onClick={() => void session.connect(state.url)}>
              Reconnect
            </button>
          </div>
        )}
        {ready ? (
          <>
            <div className="body">
              <Sidebar view={shown} onOpen={setView} />
              <main className="main">
                {shown.kind === "welcome" && <Welcome onOpen={setView} />}
                {shown.kind === "sequence" && <SequencePage key={shown.example ? "example" : "blank"} example={shown.example} />}
                {shown.kind === "component" && (
                  <ComponentPage key={shown.ref} componentRef={shown.ref} tab={shown.tab} onOpen={setView} />
                )}
              </main>
            </div>
            <ActivityLog open={logOpen} onOpen={setLogOpen} query={logQuery} onQuery={setLogQuery} />
          </>
        ) : (
          <main className="main" style={{ padding: 0, flex: 1 }}>
            <ConnectScreen defaultUrl={url} />
          </main>
        )}
        <Footer />
      </div>
    </UiContext.Provider>
  );
}

export default function App() {
  const session = useMemo(() => new Session(), []);
  return (
    <SessionContext.Provider value={session}>
      <Shell />
    </SessionContext.Provider>
  );
}
