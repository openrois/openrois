import {
  RoISClient,
  allOf,
  componentRef,
  eq,
  type CommandUnitSequenceItemInput,
  type EngineProfile,
} from "@openrois/sdk";
import type {
  CompletedParams,
  CompletedStatus,
  ComponentStatus,
  NotifyErrorParams,
  NotifyEventParams,
  Parameter,
  Result,
} from "@openrois/interfaces";
import { hasStatus } from "./engines";
import { recordingWebSocket, type Frame } from "./wire";

export type ConnectionStatus = "idle" | "connecting" | "connected" | "closed" | "error";

/** A command this session sent, from its execute to its rois.command.completed. */
export interface CommandRecord {
  id: string;
  ref: string;
  type: string;
  /** The execute call that sent it, so a sequence can show its commands together. */
  batch: number;
  status: CompletedStatus | "RUNNING";
  sentAt: number;
  endedAt?: number;
}

export interface SubscriptionRecord {
  id: string;
  ref: string;
  eventType: string;
}

export interface EventRecord {
  at: number;
  ref: string;
  params: NotifyEventParams;
}

export interface ErrorRecord {
  at: number;
  params: NotifyErrorParams;
}

/** One line of the activity log. */
export interface LogEntry {
  seq: number;
  at: number;
  kind: "request" | "response" | "notification" | "failure" | "note";
  method: string;
  /** A one-line summary: a return code, a command id, an event type. */
  summary: string;
  /** The JSON-RPC message, for the raw view. Empty for a note. */
  raw: string;
  /** The JSON-RPC id that pairs a request with its response. */
  rpcId?: number | string;
}

/** The timeouts the SDK's transport takes, in milliseconds. */
export interface Timeouts {
  requestTimeout: number;
  connectTimeout: number;
}

export interface SessionState {
  url: string;
  status: ConnectionStatus;
  error: string | null;
  profile: EngineProfile | null;
  bound: ReadonlySet<string>;
  statuses: Readonly<Record<string, ComponentStatus>>;
  commands: readonly CommandRecord[];
  subscriptions: readonly SubscriptionRecord[];
  events: readonly EventRecord[];
  errors: readonly ErrorRecord[];
  log: readonly LogEntry[];
  /** How long the last get_profile took, in milliseconds. */
  profileMs: number | null;
  /** Whether the log stops recording, for reading it while traffic continues. */
  paused: boolean;
}

const LOG_LIMIT = 400;
const EVENT_LIMIT = 200;

const INITIAL: SessionState = {
  url: "",
  status: "idle",
  error: null,
  profile: null,
  bound: new Set(),
  statuses: {},
  commands: [],
  subscriptions: [],
  events: [],
  errors: [],
  log: [],
  profileMs: null,
  paused: false,
};

const URL_KEY = "openrois-inspector-url";

/** The gateway URL this browser connected to last, if storage allows. */
export function lastUrl(): string | null {
  try {
    return localStorage.getItem(URL_KEY);
  } catch {
    return null;
  }
}

/** The message of anything a call threw. */
export function errorText(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

/** A short summary of a JSON-RPC message for the log. */
function summarize(message: Record<string, unknown>): string {
  const result = message.result as Record<string, unknown> | undefined;
  const params = message.params as Record<string, unknown> | undefined;
  if (message.error) return `error ${(message.error as { message?: string }).message ?? ""}`;
  if (result) {
    const parts = [String(result.return_code ?? "")];
    if (Array.isArray(result.command_unit_list)) {
      const ids = JSON.stringify(result.command_unit_list).match(/"command_id":"([^"]+)"/g) ?? [];
      parts.push(ids.map((m) => m.slice(14, -1)).join(", "));
    }
    if (typeof result.command_id === "string") parts.push(result.command_id);
    if (typeof result.subscribe_id === "string") parts.push(result.subscribe_id);
    if (typeof result.component_ref === "string") parts.push(result.component_ref);
    return parts.filter(Boolean).join(" · ");
  }
  if (params && Array.isArray(params.command_unit_list)) {
    const refs = JSON.stringify(params.command_unit_list).match(/"command_type":"[^"]+"/g) ?? [];
    return `${refs.length} ${refs.length === 1 ? "command" : "commands"}`;
  }
  if (params) {
    const keys = ["component_ref", "command_type", "query_type", "event_type", "status", "command_id", "error_type", "subscribe_id"];
    return keys
      .filter((key) => typeof params[key] === "string" && params[key] !== "")
      .map((key) => String(params[key]))
      .join(" · ");
  }
  return "";
}

/**
 * One RoIS session of the inspector: the client, what the engine said, and the log.
 *
 * Everything the screen shows comes from here. The views subscribe with
 * useSyncExternalStore and call the methods below, which are the RoIS operations of
 * @openrois/sdk with the bookkeeping a service application does around them.
 */
export class Session {
  private state: SessionState = INITIAL;
  private readonly listeners = new Set<() => void>();
  private client: RoISClient | null = null;
  private seq = 0;
  private batch = 0;
  /** Counts connects and disconnects, so a connect that a newer call overtook gives up. */
  private generation = 0;
  private readonly pending = new Map<number | string, string>();
  /** Completions that arrived for ids this session has not recorded yet. */
  private readonly early = new Map<string, CompletedStatus>();

  subscribe = (listener: () => void): (() => void) => {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  };

  snapshot = (): SessionState => this.state;

  private set(update: Partial<SessionState>): void {
    this.state = { ...this.state, ...update };
    for (const listener of this.listeners) listener();
  }

  private append(entry: Omit<LogEntry, "seq" | "at">): void {
    if (this.state.paused) return;
    this.seq += 1;
    const log = [...this.state.log, { ...entry, seq: this.seq, at: Date.now() }];
    this.set({ log: log.length > LOG_LIMIT ? log.slice(-LOG_LIMIT) : log });
  }

  /** Add a line of the inspector's own to the log, such as a failed call. */
  note(method: string, summary: string): void {
    this.append({ kind: "failure", method, summary, raw: "" });
  }

  private onFrame = ({ direction, text }: Frame): void => {
    let message: Record<string, unknown>;
    try {
      message = JSON.parse(text) as Record<string, unknown>;
    } catch {
      return;
    }
    const raw = JSON.stringify(message, null, 2);
    if (direction === "sent") {
      const method = String(message.method ?? "");
      const rpcId = message.id as number | string | undefined;
      if (rpcId !== undefined) this.pending.set(rpcId, method);
      this.append({ kind: "request", method, summary: summarize(message), raw, rpcId });
      return;
    }
    if (message.id !== undefined && message.id !== null) {
      const method = this.pending.get(message.id as number | string) ?? "";
      this.pending.delete(message.id as number | string);
      const failed =
        message.error !== undefined ||
        (message.result as { return_code?: string } | undefined)?.return_code !== "OK";
      this.append({
        kind: failed ? "failure" : "response",
        method,
        summary: summarize(message),
        raw,
        rpcId: message.id as number | string,
      });
      return;
    }
    this.append({ kind: "notification", method: String(message.method ?? ""), summary: summarize(message), raw });
  };

  private onCompleted = ({ command_id, status }: CompletedParams): void => {
    const known = this.state.commands.some((c) => c.id === command_id);
    if (!known) {
      this.early.set(command_id, status);
      return;
    }
    this.set({
      commands: this.state.commands.map((c) =>
        c.id === command_id ? { ...c, status, endedAt: Date.now() } : c,
      ),
    });
  };

  private onEvent = (params: NotifyEventParams): void => {
    const subscription = this.state.subscriptions.find((s) => s.id === params.subscribe_id);
    const events = [...this.state.events, { at: Date.now(), ref: subscription?.ref ?? "", params }];
    this.set({ events: events.length > EVENT_LIMIT ? events.slice(-EVENT_LIMIT) : events });
  };

  private onError = (params: NotifyErrorParams): void => {
    this.set({ errors: [...this.state.errors, { at: Date.now(), params }] });
  };

  private onProfileChanged = (): void => {
    void this.refreshProfile();
  };

  private onClose = (code: number, reason: string): void => {
    this.client = null;
    this.set({
      status: "closed",
      error: `The connection closed (code ${code}${reason ? `, ${reason}` : ""}).`,
      bound: new Set(),
      subscriptions: [],
    });
  };

  private live(): RoISClient {
    if (!this.client) throw new Error("Not connected.");
    return this.client;
  }

  async connect(url: string, timeouts?: Partial<Timeouts>): Promise<void> {
    await this.disconnect();
    const generation = ++this.generation;
    this.pending.clear();
    this.early.clear();
    this.set({ ...INITIAL, url, status: "connecting", log: this.state.log });
    try {
      const client = await RoISClient.connect(url, {
        transport: { ...timeouts, webSocketFactory: recordingWebSocket(this.onFrame) },
      });
      if (generation !== this.generation) {
        await client.disconnect().catch(() => undefined);
        return;
      }
      client.on("rois.command.completed", this.onCompleted);
      client.on("rois.event.notify_event", this.onEvent);
      client.on("rois.system.notify_error", this.onError);
      client.on("rois.system.profile_changed", this.onProfileChanged);
      client.on("close", this.onClose);
      client.on("error", (error) => this.note("transport", errorText(error)));
      this.client = client;
      this.set({ status: "connected" });
      try {
        localStorage.setItem(URL_KEY, url);
      } catch {
        // Without storage, the next visit starts from the default URL again.
      }
      await this.refreshProfile();
    } catch (error) {
      if (generation !== this.generation) return;
      this.client = null;
      this.set({ status: "error", error: errorText(error) });
    }
  }

  async disconnect(): Promise<void> {
    this.generation += 1;
    const client = this.client;
    if (!client) return;
    this.client = null;
    client.off("close", this.onClose);
    try {
      await client.disconnect();
    } catch (error) {
      this.note("rois.system.disconnect", errorText(error));
    }
    this.set({ status: "idle", error: null, bound: new Set(), subscriptions: [] });
  }

  clearLog(): void {
    this.set({ log: [] });
  }

  setPaused(paused: boolean): void {
    this.set({ paused });
  }

  /**
   * Read the profile again, and forget the binds and subscriptions on components that
   * left it, since their engine took them along when it disconnected.
   */
  async refreshProfile(): Promise<void> {
    const started = performance.now();
    const profile = await this.live().getProfile();
    const present = (ref: string) => ref in profile.component_profiles;
    this.set({
      profile,
      profileMs: Math.round(performance.now() - started),
      bound: new Set([...this.state.bound].filter(present)),
      subscriptions: this.state.subscriptions.filter((s) => present(s.ref)),
    });
    const refs = Object.keys(profile.component_profiles);
    await Promise.all(refs.map((ref) => this.readStatus(ref).catch(() => undefined)));
  }

  /** Ask component_status of a component that declares it. */
  async readStatus(ref: string): Promise<void> {
    const profile = this.state.profile?.component_profiles[ref];
    if (!profile || !hasStatus(profile)) return;
    const results = await this.live().query("component_status", componentRef(ref));
    const status = results.find((r) => r.name === "status")?.value as ComponentStatus | undefined;
    if (status) this.set({ statuses: { ...this.state.statuses, [ref]: status } });
  }

  async bind(ref: string): Promise<void> {
    await this.live().bind(ref);
    this.set({ bound: new Set(this.state.bound).add(ref) });
    await this.readStatus(ref).catch(() => undefined);
  }

  async release(ref: string): Promise<void> {
    await this.live().release(ref);
    const bound = new Set(this.state.bound);
    bound.delete(ref);
    this.set({ bound });
    await this.readStatus(ref).catch(() => undefined);
  }

  getParameter(ref: string): Promise<Parameter[]> {
    return this.live().getParameter(ref);
  }

  async setParameter(ref: string, parameters: Parameter[]): Promise<string> {
    const id = await this.live().setParameter(ref, parameters);
    this.record([{ id, ref, type: "set_parameter" }]);
    return id;
  }

  /**
   * Run a command_unit_list and record each command under the id the engine gave it.
   *
   * @param steps The ref and command of every command, in the order execute() returns
   *   their ids: item by item, and branch by branch inside a group.
   */
  async execute(
    list: CommandUnitSequenceItemInput[],
    steps: { ref: string; type: string }[],
  ): Promise<string[]> {
    const ids = await this.live().execute(list);
    this.record(ids.map((id, index) => ({ id, ref: steps[index]?.ref ?? "", type: steps[index]?.type ?? "" })));
    return ids;
  }

  private record(started: { id: string; ref: string; type: string }[]): void {
    this.batch += 1;
    const now = Date.now();
    const added: CommandRecord[] = started.map(({ id, ref, type }) => {
      const status = this.early.get(id);
      this.early.delete(id);
      return status
        ? { id, ref, type, batch: this.batch, status, sentAt: now, endedAt: now }
        : { id, ref, type, batch: this.batch, status: "RUNNING", sentAt: now };
    });
    this.set({ commands: [...this.state.commands, ...added] });
  }

  /** The batch number of the most recent execute, for the sequence timeline. */
  lastBatch(): number {
    return this.batch;
  }

  getCommandResult(id: string): Promise<Result[]> {
    return this.live().getCommandResult(id);
  }

  /** Run a query on one component, with argument values in the condition. */
  query(ref: string, queryType: string, args: Record<string, string>): Promise<Result[]> {
    const parts = [componentRef(ref), ...Object.entries(args).map(([name, value]) => eq(name, value))];
    return this.live().query(queryType, parts.length > 1 ? allOf(...parts) : parts[0]);
  }

  async subscribeEvent(ref: string, eventType: string): Promise<void> {
    const id = await this.live().subscribe(eventType, componentRef(ref));
    this.set({ subscriptions: [...this.state.subscriptions, { id, ref, eventType }] });
  }

  async unsubscribe(id: string): Promise<void> {
    await this.live().unsubscribe(id);
    this.set({ subscriptions: this.state.subscriptions.filter((s) => s.id !== id) });
  }

  getEventDetail(id: string): Promise<Result[]> {
    return this.live().getEventDetail(id);
  }

  getErrorDetail(id: string): Promise<Result[]> {
    return this.live().getErrorDetail(id);
  }
}
