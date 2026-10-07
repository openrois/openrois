/**
 * The RoIS behaviour of the mock engine, without a transport.
 *
 * MockEngineCore answers every method of the RoIS method catalog for the
 * components in components.ts. The server (server.ts) validates each request
 * against the catalog before it reaches a handler here, and validates each
 * result before it goes back, so the handlers work on typed params.
 *
 * What the mock does, as an engine following the catalog would:
 *
 *   - Conditions select components by component_ref and component_type.
 *     query and subscribe go to the one component that declares the query or
 *     event type: UNSUPPORTED when none does, BAD_PARAMETER when several do.
 *   - An actuation component takes commands and parameters only from the client
 *     that bound it. Another client gets OUT_OF_RESOURCES.
 *   - The command table holds every command_id. A command_id already in it is
 *     answered with BAD_PARAMETER. Each command ends with a
 *     rois.command.completed notification, and get_command_result reads its
 *     results.
 *   - execute runs its items in order, waits each item's delay_time, and runs
 *     the commands of a ConcurrentCommands item at the same time.
 *   - Navigation start ends after a while with the reached_target event, and
 *     a stop or a second start aborts it. person_detected events arrive on a
 *     timer for every subscription. get_event_detail keeps each event until it
 *     expires.
 *
 * The mock reports no engine errors, so get_error_detail knows no error_id.
 */

import {
  COMPONENT_REF,
  COMPONENT_TYPE,
  componentTypeUrn,
  parseCondition,
} from "@openrois/interfaces";
import type {
  Argument,
  CommandUnit,
  CommandUnitSequenceItem,
  CompletedStatus,
  ComponentStatus,
  Parameter,
  Result,
  ReturnCode,
  RoISMethod,
  RoISMethodMap,
  RoISMethodSchemas,
  RoISNotification,
  RoISNotificationMap,
} from "@openrois/interfaces";
import type { z } from "zod";
import { ENGINE_ID, mockComponents, type MockComponent } from "./components";

// ---------------------------------------------------------------------------
// Public types
// ---------------------------------------------------------------------------

/** How long simulated work takes, in milliseconds. */
export interface MockEngineTiming {
  /** A command other than Navigation start. */
  commandMs: number;
  /** A Navigation start, until the robot reaches its target. */
  navigationMs: number;
  /** The interval of person_detected events for each subscription. */
  detectionIntervalMs: number;
  /** How long get_event_detail keeps an event after its notification. */
  eventLifetimeMs: number;
}

/** The timing of a mock engine started for people to watch. */
export const DEFAULT_TIMING: MockEngineTiming = {
  commandMs: 200,
  navigationMs: 3000,
  detectionIntervalMs: 5000,
  eventLifetimeMs: 60_000,
};

/** Sends a catalog notification to the client of one session. */
export type Notify = <N extends RoISNotification>(
  method: N,
  params: RoISNotificationMap[N]["params"],
) => void;

/** One connected client. */
export interface Session {
  /** Unique within the engine. Bindings and subscriptions belong to a session. */
  readonly id: string;
  /** Send this client a notification. */
  readonly notify: Notify;
}

/** The validated params of a catalog method. */
export type MethodParams<M extends RoISMethod> = RoISMethodMap[M]["params"];

/** The result a handler returns, before the result schema fills its defaults. */
export type MethodReply<M extends RoISMethod> = z.input<(typeof RoISMethodSchemas)[M]["result"]>;

// ---------------------------------------------------------------------------
// Internal state
// ---------------------------------------------------------------------------

/** A Navigation start that has not ended yet. */
interface RunningCommand {
  readonly commandId: string;
  /** End the command with a status. Ending it twice has no effect. */
  finish(status: CompletedStatus): void;
}

/** A component and what clients did to it. */
interface ComponentState extends MockComponent {
  status: ComponentStatus;
  parameters: Parameter[];
  /** The session holding the bind of an actuation component. */
  boundBy: string | null;
  running: RunningCommand | null;
}

/** An entry of the command table. */
interface CommandRecord {
  /** How the command ended, or null while it runs. */
  status: CompletedStatus | null;
  results: Result[];
}

interface Subscription {
  readonly id: string;
  readonly session: Session;
  readonly ref: string;
  readonly eventType: string;
  timer?: ReturnType<typeof setInterval>;
}

interface StoredEvent {
  readonly results: Result[];
  readonly expiresAt: number;
}

/** No property is defined for the result filters, so their condition must be empty. */
const NO_PROPERTIES: ReadonlySet<string> = new Set();

const ok = { return_code: "OK" } as const;

function failed(returnCode: ReturnCode): { return_code: ReturnCode } {
  return { return_code: returnCode };
}

function names(messages: readonly { name: string }[] | undefined): string[] {
  return (messages ?? []).map((message) => message.name);
}

// ---------------------------------------------------------------------------
// MockEngineCore
// ---------------------------------------------------------------------------

/** The state and the method handlers of one mock engine. */
export class MockEngineCore {
  private readonly components = new Map<string, ComponentState>();
  private readonly commands = new Map<string, CommandRecord>();
  private readonly subscriptions = new Map<string, Subscription>();
  private readonly events = new Map<string, StoredEvent>();
  private readonly timeouts = new Set<ReturnType<typeof setTimeout>>();
  private readonly startedAt = new Date().toISOString();
  private nextId = 1;
  private closed = false;

  constructor(private readonly timing: MockEngineTiming = DEFAULT_TIMING) {
    for (const component of mockComponents()) {
      this.components.set(component.ref, {
        ...component,
        parameters: [...component.parameters],
        status: "READY",
        boundBy: null,
        running: null,
      });
    }
  }

  /** Answer one catalog method for a session. */
  handle<M extends RoISMethod>(session: Session, method: M, params: MethodParams<M>): MethodReply<M> {
    const handler = this.handlers[method] as (session: Session, params: MethodParams<M>) => MethodReply<M>;
    return handler(session, params);
  }

  /** Release what a session held: its binds and its subscriptions. */
  closeSession(session: Session): void {
    for (const component of this.components.values()) {
      if (component.boundBy === session.id) {
        component.boundBy = null;
      }
    }
    for (const subscription of [...this.subscriptions.values()]) {
      if (subscription.session.id === session.id) {
        this.dropSubscription(subscription);
      }
    }
  }

  /** Stop every timer, so a stopped engine sends nothing more. */
  close(): void {
    this.closed = true;
    for (const timeout of this.timeouts) {
      clearTimeout(timeout);
    }
    this.timeouts.clear();
    for (const subscription of [...this.subscriptions.values()]) {
      this.dropSubscription(subscription);
    }
  }

  // -------------------------------------------------------------------------
  // Handlers
  // -------------------------------------------------------------------------

  private readonly handlers: { [M in RoISMethod]: (session: Session, params: MethodParams<M>) => MethodReply<M> } = {
    // SystemIF

    "rois.system.connect": () => ok,

    "rois.system.disconnect": (session) => {
      this.closeSession(session);
      return ok;
    },

    "rois.system.get_profile": (_session, { condition }) => {
      const selected = this.select(condition);
      if (selected === null) {
        return failed("BAD_PARAMETER");
      }
      return {
        return_code: "OK",
        profile: {
          identifier: { authority: "OpenRoIS", code: ENGINE_ID },
          component_ids: selected.map((component) => component.ref),
        },
        component_profiles: Object.fromEntries(
          selected.map((component) => [component.ref, component.profile]),
        ),
      };
    },

    "rois.system.get_error_detail": () => failed("BAD_PARAMETER"),

    // CommandIF

    "rois.command.search": (_session, { condition }) => {
      const selected = this.select(condition);
      if (selected === null) {
        return failed("BAD_PARAMETER");
      }
      return { return_code: "OK", component_ref_list: selected.map((component) => component.ref) };
    },

    "rois.command.bind": (session, { component_ref }) => {
      const component = this.components.get(component_ref);
      if (!component) {
        return failed("UNSUPPORTED");
      }
      return failed(this.bindTo(session, component));
    },

    "rois.command.bind_any": (session, { condition }) => {
      const selected = this.select(condition);
      if (selected === null) {
        return failed("BAD_PARAMETER");
      }
      if (selected.length === 0) {
        return failed("UNSUPPORTED");
      }
      const free = selected.find((component) => this.bindTo(session, component) === "OK");
      if (!free) {
        return failed("OUT_OF_RESOURCES");
      }
      return { return_code: "OK", component_ref: free.ref };
    },

    "rois.command.release": (session, { component_ref }) => {
      const component = this.components.get(component_ref);
      if (!component) {
        return failed("UNSUPPORTED");
      }
      if (component.boundBy === session.id) {
        component.boundBy = null;
      }
      return ok;
    },

    "rois.command.get_parameter": (_session, { component_ref }) => {
      const component = this.components.get(component_ref);
      if (!component) {
        return failed("UNSUPPORTED");
      }
      return { return_code: "OK", parameters: component.parameters.map((p) => ({ ...p })) };
    },

    "rois.command.set_parameter": (session, { component_ref, parameters }) => {
      const component = this.components.get(component_ref);
      if (!component) {
        return failed("UNSUPPORTED");
      }
      if (!this.holdsBind(session, component)) {
        return failed("OUT_OF_RESOURCES");
      }
      if (!this.knowsParameters(component, parameters)) {
        return failed("BAD_PARAMETER");
      }
      const commandId = `param-${this.nextId++}`;
      this.commands.set(commandId, { status: null, results: [] });
      this.store(component, parameters);
      this.after(this.timing.commandMs, () => this.complete(session, commandId, "OK"));
      return { return_code: "OK", command_id: commandId };
    },

    "rois.command.execute": (session, { command_unit_list }) => {
      const units = command_unit_list.flatMap((item) =>
        "command_list" in item ? item.command_list : [item],
      );
      if (units.length === 0) {
        return failed("BAD_PARAMETER");
      }
      const commandIds = new Set<string>();
      for (const unit of units) {
        const component = this.components.get(unit.component_ref);
        if (!component || !this.declaresCommand(component, unit.command_type)) {
          return failed("UNSUPPORTED");
        }
        if (!this.holdsBind(session, component)) {
          return failed("OUT_OF_RESOURCES");
        }
        if (unit.command_type === "set_parameter" && !this.knowsParameters(component, unit.arguments ?? [])) {
          return failed("BAD_PARAMETER");
        }
        if (this.commands.has(unit.command_id) || commandIds.has(unit.command_id)) {
          return failed("BAD_PARAMETER");
        }
        commandIds.add(unit.command_id);
      }
      for (const commandId of commandIds) {
        this.commands.set(commandId, { status: null, results: [] });
      }
      void this.runSequence(session, command_unit_list);
      return ok;
    },

    "rois.command.get_command_result": (_session, { command_id, condition }) => {
      const record = this.commands.get(command_id);
      if (!this.emptyFilter(condition) || !record) {
        return failed("BAD_PARAMETER");
      }
      return { return_code: "OK", results: record.results };
    },

    // QueryIF

    "rois.query.query": (_session, { query_type, condition }) => {
      const picked = this.pick(condition, (c) => names(c.profile.query_profiles).includes(query_type));
      if (typeof picked === "string") {
        return failed(picked);
      }
      return { return_code: "OK", results: this.answer(picked, query_type) };
    },

    // EventIF

    "rois.event.subscribe": (session, { event_type, condition }) => {
      const picked = this.pick(condition, (c) => names(c.profile.event_profiles).includes(event_type));
      if (typeof picked === "string") {
        return failed(picked);
      }
      const subscription: Subscription = {
        id: `sub-${this.nextId++}`,
        session,
        ref: picked.ref,
        eventType: event_type,
      };
      this.subscriptions.set(subscription.id, subscription);
      if (event_type === "person_detected") {
        let count = 0;
        subscription.timer = setInterval(() => {
          count = (count + 1) % 4;
          this.publish([subscription], [
            { name: "number", data_type_ref: "int", value: String(count) },
            { name: "timestamp", data_type_ref: "DateTime", value: new Date().toISOString() },
          ]);
        }, this.timing.detectionIntervalMs);
      }
      return { return_code: "OK", subscribe_id: subscription.id };
    },

    "rois.event.unsubscribe": (session, { subscribe_id }) => {
      const subscription = this.subscriptions.get(subscribe_id);
      if (subscription && subscription.session.id === session.id) {
        this.dropSubscription(subscription);
      }
      return ok;
    },

    "rois.event.get_event_detail": (_session, { event_id, condition }) => {
      const event = this.events.get(event_id);
      if (!this.emptyFilter(condition) || !event || event.expiresAt < Date.now()) {
        return failed("BAD_PARAMETER");
      }
      return { return_code: "OK", results: event.results };
    },
  };

  // -------------------------------------------------------------------------
  // Selection
  // -------------------------------------------------------------------------

  /** The components a selection condition matches, or null when it does not parse. */
  private select(condition: string): ComponentState[] | null {
    let parsed;
    try {
      parsed = parseCondition(condition);
    } catch {
      return null;
    }
    return [...this.components.values()].filter((component) =>
      parsed.matches({
        [COMPONENT_REF]: component.ref,
        [COMPONENT_TYPE]: componentTypeUrn(component.profile.identifier),
      }),
    );
  }

  /** The one component a condition selects among those that qualify, or the return code. */
  private pick(
    condition: string,
    qualifies: (component: ComponentState) => boolean,
  ): ComponentState | ReturnCode {
    const selected = this.select(condition);
    if (selected === null) {
      return "BAD_PARAMETER";
    }
    const candidates = selected.filter(qualifies);
    if (candidates.length === 0) {
      return "UNSUPPORTED";
    }
    if (candidates.length > 1) {
      return "BAD_PARAMETER";
    }
    return candidates[0];
  }

  /** Whether a result filter is empty, the only filter defined so far. */
  private emptyFilter(condition: string): boolean {
    try {
      parseCondition(condition, NO_PROPERTIES);
      return true;
    } catch {
      return false;
    }
  }

  // -------------------------------------------------------------------------
  // Bindings and parameters
  // -------------------------------------------------------------------------

  /** Only actuation components are reserved by a bind. */
  private needsBind(component: ComponentState): boolean {
    return component.profile.function === "actuation";
  }

  private holdsBind(session: Session, component: ComponentState): boolean {
    return !this.needsBind(component) || component.boundBy === session.id;
  }

  /** Bind a component to a session, returning the bind's return code. */
  private bindTo(session: Session, component: ComponentState): ReturnCode {
    if (!this.needsBind(component)) {
      return "OK";
    }
    if (component.boundBy !== null && component.boundBy !== session.id) {
      return "OUT_OF_RESOURCES";
    }
    component.boundBy = session.id;
    return "OK";
  }

  private declaresCommand(component: ComponentState, commandType: string): boolean {
    if (commandType === "set_parameter") {
      return (component.profile.parameter_profiles ?? []).length > 0;
    }
    return names(component.profile.command_profiles).includes(commandType);
  }

  private knowsParameters(component: ComponentState, parameters: readonly Argument[]): boolean {
    const known = names(component.profile.parameter_profiles);
    return parameters.every((parameter) => known.includes(parameter.name));
  }

  private store(component: ComponentState, parameters: readonly Parameter[]): void {
    for (const parameter of parameters) {
      const index = component.parameters.findIndex((p) => p.name === parameter.name);
      if (index >= 0) {
        component.parameters[index] = { ...parameter };
      } else {
        component.parameters.push({ ...parameter });
      }
    }
  }

  // -------------------------------------------------------------------------
  // Commands
  // -------------------------------------------------------------------------

  /** Run the items of an execute in order, the commands of one item at the same time. */
  private async runSequence(session: Session, items: readonly CommandUnitSequenceItem[]): Promise<void> {
    for (const item of items) {
      if (item.delay_time) {
        await this.wait(item.delay_time);
      }
      const units = "command_list" in item ? item.command_list : [item];
      await Promise.all(units.map((unit) => this.runCommand(session, unit)));
    }
  }

  private runCommand(session: Session, unit: CommandUnit): Promise<void> {
    const component = this.components.get(unit.component_ref);
    if (!component) {
      return Promise.resolve();
    }
    if (unit.command_type === "start" && component.profile.identifier.code === "Navigation") {
      return this.navigate(session, component, unit.command_id);
    }
    if (unit.command_type === "stop") {
      component.running?.finish("ABORT");
    }
    if (unit.command_type === "set_parameter") {
      this.store(component, unit.arguments ?? []);
    }
    return this.wait(this.timing.commandMs).then(() => this.complete(session, unit.command_id, "OK"));
  }

  /** Drive to the first target position. A stop or a new start aborts the drive. */
  private navigate(session: Session, component: ComponentState, commandId: string): Promise<void> {
    component.running?.finish("ABORT");
    const target = this.firstTarget(component);
    component.status = "BUSY";
    return new Promise((resolve) => {
      const finish = (status: CompletedStatus) => {
        if (component.running?.commandId !== commandId) {
          return;
        }
        if (arrival !== undefined) {
          clearTimeout(arrival);
          this.timeouts.delete(arrival);
        }
        component.running = null;
        component.status = "READY";
        const reached = status === "OK";
        this.complete(session, commandId, status, reached
          ? [{ name: "target", data_type_ref: "string", value: target }]
          : []);
        if (reached) {
          this.publish(this.subscribersOf(component.ref, "reached_target"), [
            { name: "target", data_type_ref: "string", value: target },
            { name: "is_final_target", data_type_ref: "bool", value: "true" },
          ]);
        }
        resolve();
      };
      component.running = { commandId, finish };
      const arrival = this.after(this.timing.navigationMs, () => finish("OK"));
    });
  }

  private firstTarget(component: ComponentState): string {
    const value = component.parameters.find((p) => p.name === "target_positions")?.value ?? "";
    try {
      const targets: unknown = JSON.parse(value);
      if (Array.isArray(targets) && typeof targets[0] === "string") {
        return targets[0];
      }
    } catch {
      // A value that is not a JSON list is taken as one target.
    }
    return value;
  }

  /** Record how a command ended and tell the client that sent it. */
  private complete(session: Session, commandId: string, status: CompletedStatus, results: Result[] = []): void {
    this.commands.set(commandId, { status, results });
    session.notify("rois.command.completed", { command_id: commandId, status });
  }

  // -------------------------------------------------------------------------
  // Events
  // -------------------------------------------------------------------------

  private subscribersOf(ref: string, eventType: string): Subscription[] {
    return [...this.subscriptions.values()].filter(
      (subscription) => subscription.ref === ref && subscription.eventType === eventType,
    );
  }

  /** Send one event occurrence to its subscriptions and keep it for get_event_detail. */
  private publish(subscriptions: readonly Subscription[], results: Result[]): void {
    if (subscriptions.length === 0) {
      return;
    }
    const eventId = `evt-${this.nextId++}`;
    const expiresAt = Date.now() + this.timing.eventLifetimeMs;
    this.events.set(eventId, { results, expiresAt });
    for (const subscription of subscriptions) {
      subscription.session.notify("rois.event.notify_event", {
        event_id: eventId,
        event_type: subscription.eventType,
        subscribe_id: subscription.id,
        expire: new Date(expiresAt).toISOString(),
        results,
      });
    }
  }

  private dropSubscription(subscription: Subscription): void {
    if (subscription.timer) {
      clearInterval(subscription.timer);
    }
    this.subscriptions.delete(subscription.id);
  }

  // -------------------------------------------------------------------------
  // Queries
  // -------------------------------------------------------------------------

  private answer(component: ComponentState, queryType: string): Result[] {
    const now = new Date().toISOString();
    switch (queryType) {
      case "component_status":
        return [{ name: "status", data_type_ref: "Component_Status", value: component.status }];
      case "robot_position":
        return [
          { name: "position_data", data_type_ref: "String[]", value: '["1.5,2.0,0.0"]' },
          { name: "robot_ref", data_type_ref: "RoISIdentifier[]", value: `["${ENGINE_ID}"]` },
          { name: "timestamp", data_type_ref: "DateTime", value: now },
        ];
      case "engine_status":
        return [
          { name: "operable_time", data_type_ref: "DateTime", value: this.startedAt },
          { name: "status", data_type_ref: "Component_Status", value: "READY" },
        ];
      default:
        return [];
    }
  }

  // -------------------------------------------------------------------------
  // Timers
  // -------------------------------------------------------------------------

  /** Run `action` after `ms`, unless the engine closes first. */
  private after(ms: number, action: () => void): ReturnType<typeof setTimeout> | undefined {
    if (this.closed) {
      return undefined;
    }
    const timeout = setTimeout(() => {
      this.timeouts.delete(timeout);
      action();
    }, ms);
    this.timeouts.add(timeout);
    return timeout;
  }

  /** A promise that resolves after `ms`, or never once the engine closes. */
  private wait(ms: number): Promise<void> {
    if (this.closed) {
      return new Promise(() => undefined);
    }
    return new Promise((resolve) => {
      this.after(ms, resolve);
    });
  }
}
