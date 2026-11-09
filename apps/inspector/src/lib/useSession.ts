import { createContext, useContext, useSyncExternalStore } from "react";
import type { Session, SessionState } from "./session";

export const SessionContext = createContext<Session | null>(null);

/** The session of the inspector, and its state, kept current. */
export function useSession(): [Session, SessionState] {
  const session = useContext(SessionContext);
  if (!session) throw new Error("useSession outside SessionContext");
  const state = useSyncExternalStore(session.subscribe, session.snapshot);
  return [session, state];
}
