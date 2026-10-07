/**
 * RoISClient: the client of the OpenRoIS TypeScript SDK.
 *
 * One method per operation of the RoIS method catalog, named after the IDL
 * operation and taking its `in` parameters in IDL order:
 *
 *   System   connect, disconnect, getProfile, getErrorDetail
 *   Command  search, bind, bindAny, release, getParameter, setParameter,
 *            execute, getCommandResult
 *   Query    query
 *   Event    subscribe, unsubscribe, getEventDetail
 *
 * Streaming is not modelled yet (planned).
 *
 * Every call goes through one path that validates the params and the result
 * against the catalog schemas from @openrois/interfaces and turns a return code
 * other than OK into a RoISError. Notifications from the engine are validated
 * the same way before listeners receive their params.
 *
 * Usage:
 *   import { RoISClient, componentRef } from "@openrois/sdk";
 *
 *   const client = await RoISClient.connect("ws://localhost:8765");
 *   const { profile, component_profiles } = await client.getProfile();
 *
 *   const head = componentRef("reachy_real/head");
 *   const status = await client.query("component_status", head);
 *
 *   client.on("rois.event.notify_event", (params) => console.log(params.event_type));
 *   const subscribeId = await client.subscribe("person_detected", head);
 *
 *   await client.bind("reachy_real/head");
 *   const [commandId] = await client.execute([
 *     { component_ref: "reachy_real/head", command_type: "start" },
 *   ]);
 *
 *   await client.disconnect();
 *
 * Wire binding: docs/rois-reference.md section 17.
 */

// 1. Node.js built-ins
import { EventEmitter } from "events";

// 2. External packages
import type { z } from "zod";

// 3. Internal packages (@openrois/*)
import {
  RoISMethods,
  RoISMethodSchemas,
  RoISNotifications,
  RoISNotificationSchemas,
} from "@openrois/interfaces";

import type {
  CommandUnitSchema,
  ConcurrentCommandsSchema,
  HRIComponentProfile,
  HRIEngineProfileType,
  NotifyEventParams,
  Parameter,
  Result,
  ReturnCode,
  RoISMethod,
  RoISMethodMap,
  RoISNotification,
  RoISNotificationMap,
} from "@openrois/interfaces";

// 4. Local modules
import {
  WebSocketTransport,
  TransportError,
  type TransportOptions,
} from "./transport";
import type { JsonRpcNotification } from "./jsonrpc";

export {
  COMPONENT_REF,
  COMPONENT_TYPE,
  allOf,
  componentRef,
  componentType,
  componentTypeUrn,
  eq,
  like,
  quote,
  type ComponentTypeIdentifier,
} from "./condition";
export {
  ConnectionError,
  RequestTimeoutError,
  RpcError,
  TransportError,
  type TransportOptions,
} from "./transport";

// ---------------------------------------------------------------------------
// Configuration
// ---------------------------------------------------------------------------

/** Options for RoISClient.connect(). */
export interface ClientOptions {
  /** Transport options: timeouts and a custom WebSocket factory. */
  transport?: TransportOptions;
}

// ---------------------------------------------------------------------------
// Public types
// ---------------------------------------------------------------------------

/** The get_profile result of an engine that answered OK. */
export interface EngineProfile {
  /** The engine profile, as HRIEngineProfileType in XML-Profiles.xsd defines it. */
  profile: HRIEngineProfileType;
  /**
   * The profile of every component in `profile.component_ids`, keyed by fully
   * qualified ref. An OpenRoIS extension (docs/rois-reference.md section 17.3).
   */
  component_profiles: Record<string, HRIComponentProfile>;
}

/**
 * One command for execute(): a CommandUnit whose `command_id` may be left out.
 * The client then names the command with a UUID.
 */
export type CommandUnitInput = Omit<z.input<typeof CommandUnitSchema>, "command_id"> & {
  command_id?: string;
};

/** Commands for execute() that run at the same time. */
export type ConcurrentCommandsInput = Omit<
  z.input<typeof ConcurrentCommandsSchema>,
  "command_list"
> & {
  command_list: CommandUnitInput[];
};

/** One item of the command_unit_list that execute() takes. */
export type CommandUnitSequenceItemInput = CommandUnitInput | ConcurrentCommandsInput;

/** The params a listener receives for each catalog notification. */
export type NotificationParams<N extends RoISNotification> = RoISNotificationMap[N]["params"];

/**
 * The listener arguments of every event the client emits under a fixed name.
 * Event types, such as "person_detected", come on top of these.
 */
export type RoISClientEvents = {
  [N in RoISNotification]: [params: NotificationParams<N>];
} & {
  notification: [notification: JsonRpcNotification];
  close: [code: number, reason: string];
  error: [error: Error];
};

// ---------------------------------------------------------------------------
// Errors
// ---------------------------------------------------------------------------

/**
 * Raised when a RoIS operation returns a code other than OK.
 *
 * A RoIS failure is a normal result on the wire, so this error carries the
 * return code for callers to branch on (BAD_PARAMETER, UNSUPPORTED,
 * OUT_OF_RESOURCES, TIMEOUT, ERROR).
 */
export class RoISError extends Error {
  /** The return code of the result. */
  readonly returnCode: ReturnCode;

  /** The JSON-RPC method that returned it. */
  readonly method: string;

  constructor(returnCode: ReturnCode, method: string) {
    super(`${method} failed with ${returnCode}`);
    this.name = "RoISError";
    this.returnCode = returnCode;
    this.method = method;
  }
}

// ---------------------------------------------------------------------------
// Internal helpers
// ---------------------------------------------------------------------------

/** The params a caller passes for a catalog method, before defaults apply. */
type MethodParams<M extends RoISMethod> = z.input<(typeof RoISMethodSchemas)[M]["params"]>;

/** The validated result of a catalog method. */
type MethodResult<M extends RoISMethod> = RoISMethodMap[M]["result"];

/**
 * The schemas of one catalog method, typed for that method. The catalog map is
 * a record of different schema types, which TypeScript cannot index with a
 * generic key and still call, so call() reads its entry through this view.
 */
interface MethodSchema<M extends RoISMethod> {
  params: z.ZodType<RoISMethodMap[M]["params"], MethodParams<M>>;
  result: z.ZodType<MethodResult<M>>;
}

/**
 * A listener of any event. Its parameters are `never` so that a listener with
 * any parameter list fits, which the typed overloads then narrow.
 */
type AnyListener = (...args: never[]) => void;

/** Event names the client emits itself, which an event type must not shadow. */
const RESERVED_EVENTS: ReadonlySet<string> = new Set(["notification", "close", "error"]);

/** Name a command. RoIS has the application name each command (IDL CommandMessage). */
function newCommandId(): string {
  return globalThis.crypto.randomUUID();
}

// ---------------------------------------------------------------------------
// RoISClient
// ---------------------------------------------------------------------------

/**
 * A connection to an OpenRoIS engine, with one method per RoIS operation.
 *
 * Create it with RoISClient.connect().
 *
 * Events:
 *   "rois.event.notify_event"     NotifyEventParams, for every event of a subscription
 *   <event_type>                  NotifyEventParams, the same events under their type,
 *                                 for example "person_detected"
 *   "rois.command.completed"      CompletedParams, when a command ends
 *   "rois.system.notify_error"    NotifyErrorParams, when the engine reports an error
 *   "rois.system.profile_changed" ProfileChangedParams, when components join or leave
 *   "notification"                The JSON-RPC envelope of every notification,
 *                                 including methods outside the catalog
 *   "close"                       (code, reason) when the connection closes
 *   "error"                       Error, for transport faults and notifications whose
 *                                 params fail validation
 */
export class RoISClient extends EventEmitter {
  /** The WebSocket transport this client sends on. */
  private readonly wire: WebSocketTransport;

  /** Whether the connect handshake succeeded and disconnect has not run. */
  private connected: boolean = false;

  private constructor(wire: WebSocketTransport) {
    super();
    this.wire = wire;
    this.forwardTransportEvents();
  }

  /**
   * The underlying transport, for JSON-RPC methods outside the catalog. The
   * client does not validate what is sent through it.
   */
  get transport(): WebSocketTransport {
    return this.wire;
  }

  // -----------------------------------------------------------------------
  // Typed listeners
  // -----------------------------------------------------------------------

  /**
   * Listen for an event. A catalog notification passes its validated params,
   * and any other name is an event type, such as "person_detected", which
   * passes the NotifyEventParams of each event of that type.
   */
  override on<E extends keyof RoISClientEvents>(
    event: E,
    listener: (...args: RoISClientEvents[E]) => void,
  ): this;
  override on(event: string, listener: (params: NotifyEventParams) => void): this;
  override on(event: string, listener: AnyListener): this {
    return super.on(event, listener as (...args: unknown[]) => void);
  }

  /** Listen for the next occurrence of an event. */
  override once<E extends keyof RoISClientEvents>(
    event: E,
    listener: (...args: RoISClientEvents[E]) => void,
  ): this;
  override once(event: string, listener: (params: NotifyEventParams) => void): this;
  override once(event: string, listener: AnyListener): this {
    return super.once(event, listener as (...args: unknown[]) => void);
  }

  /** Remove a listener added with on() or once(). */
  override off<E extends keyof RoISClientEvents>(
    event: E,
    listener: (...args: RoISClientEvents[E]) => void,
  ): this;
  override off(event: string, listener: (params: NotifyEventParams) => void): this;
  override off(event: string, listener: AnyListener): this {
    return super.off(event, listener as (...args: unknown[]) => void);
  }

  // -----------------------------------------------------------------------
  // SystemIF
  // -----------------------------------------------------------------------

  /**
   * Open a connection to an engine and run rois.system.connect.
   *
   * @param url - The engine's WebSocket URL, for example "ws://localhost:8765".
   * @throws ConnectionError if the WebSocket cannot be opened.
   * @throws RoISError if the engine answers connect with a code other than OK.
   */
  static async connect(url: string, options?: ClientOptions): Promise<RoISClient> {
    const wire = new WebSocketTransport(options?.transport);
    await wire.connect(url);
    const client = new RoISClient(wire);
    try {
      await client.request(RoISMethods.Connect, {});
    } catch (error) {
      wire.close();
      throw error;
    }
    client.connected = true;
    return client;
  }

  /**
   * Run rois.system.disconnect and close the connection. The connection closes
   * even when the engine answers with an error. Safe to call more than once.
   */
  async disconnect(): Promise<void> {
    if (!this.connected) {
      return;
    }
    try {
      await this.call(RoISMethods.Disconnect, {});
    } finally {
      this.connected = false;
      this.wire.close();
    }
  }

  /**
   * Read the engine profile and the profiles of its components.
   *
   * @param condition - Selects the components the profile lists. Empty lists all.
   */
  async getProfile(condition: string = ""): Promise<EngineProfile> {
    const result = await this.call(RoISMethods.GetProfile, { condition });
    if (result.profile === null) {
      throw new TransportError("rois.system.get_profile returned OK without a profile");
    }
    return {
      profile: result.profile as HRIEngineProfileType,
      component_profiles: result.component_profiles ?? {},
    };
  }

  /**
   * Read the details of an error from a rois.system.notify_error notification.
   *
   * @param condition - Filter on the results. Must be empty for now.
   */
  async getErrorDetail(errorId: string, condition: string = ""): Promise<Result[]> {
    const result = await this.call(RoISMethods.GetErrorDetail, {
      error_id: errorId,
      condition,
    });
    return result.results ?? [];
  }

  // -----------------------------------------------------------------------
  // CommandIF
  // -----------------------------------------------------------------------

  /**
   * Find components.
   *
   * @param condition - Selects the components. Empty matches every component.
   * @returns Their fully qualified refs.
   */
  async search(condition: string = ""): Promise<string[]> {
    const result = await this.call(RoISMethods.Search, { condition });
    return result.component_ref_list ?? [];
  }

  /** Reserve a component for this client. */
  async bind(componentRef: string): Promise<void> {
    await this.call(RoISMethods.Bind, { component_ref: componentRef });
  }

  /**
   * Reserve one of the components a condition selects, chosen by the engine.
   *
   * @returns The ref of the reserved component.
   */
  async bindAny(condition: string = ""): Promise<string> {
    const result = await this.call(RoISMethods.BindAny, { condition });
    return result.component_ref;
  }

  /** Release a component reserved with bind() or bindAny(). */
  async release(componentRef: string): Promise<void> {
    await this.call(RoISMethods.Release, { component_ref: componentRef });
  }

  /** Read the current value of every parameter of a component. */
  async getParameter(componentRef: string): Promise<Parameter[]> {
    const result = await this.call(RoISMethods.GetParameter, {
      component_ref: componentRef,
    });
    return result.parameters ?? [];
  }

  /**
   * Set parameters of a component.
   *
   * @returns The command_id the engine assigned to the change. Its
   *   rois.command.completed notification reports when the change took effect.
   */
  async setParameter(componentRef: string, parameters: Parameter[]): Promise<string> {
    const result = await this.call(RoISMethods.SetParameter, {
      component_ref: componentRef,
      parameters,
    });
    return result.command_id;
  }

  /**
   * Run commands in order. A ConcurrentCommands item runs its commands at the
   * same time.
   *
   * The engine answers as soon as it accepts the commands. Each command then
   * ends with a rois.command.completed notification carrying its command_id,
   * and getCommandResult() reads its results.
   *
   * @param commandUnitList - The commands. A command without a command_id is
   *   named with a UUID.
   * @returns The command_id of every command, in the order the list gives them,
   *   with the commands of a ConcurrentCommands item in their list order.
   */
  async execute(commandUnitList: CommandUnitSequenceItemInput[]): Promise<string[]> {
    const commandIds: string[] = [];
    const named = (unit: CommandUnitInput) => {
      const command_id = unit.command_id ?? newCommandId();
      commandIds.push(command_id);
      return { ...unit, command_id };
    };
    const command_unit_list = commandUnitList.map((item) =>
      "command_list" in item
        ? { ...item, command_list: item.command_list.map(named) }
        : named(item),
    );
    await this.call(RoISMethods.Execute, { command_unit_list });
    return commandIds;
  }

  /**
   * Read the results of a command.
   *
   * @param condition - Filter on the results. Must be empty for now.
   */
  async getCommandResult(commandId: string, condition: string = ""): Promise<Result[]> {
    const result = await this.call(RoISMethods.GetCommandResult, {
      command_id: commandId,
      condition,
    });
    return result.results ?? [];
  }

  // -----------------------------------------------------------------------
  // QueryIF
  // -----------------------------------------------------------------------

  /**
   * Run a query and wait for its results.
   *
   * The engine sends the query to the one component that declares `queryType`
   * and matches the condition. It returns UNSUPPORTED when none does, and
   * BAD_PARAMETER when several do.
   *
   * @param queryType - The query name from a component profile, for example
   *   "component_status".
   * @param condition - Selects the component, for example
   *   componentRef("reachy_real/head").
   */
  async query(queryType: string, condition: string = ""): Promise<Result[]> {
    const result = await this.call(RoISMethods.Query, {
      query_type: queryType,
      condition,
    });
    return result.results ?? [];
  }

  // -----------------------------------------------------------------------
  // EventIF
  // -----------------------------------------------------------------------

  /**
   * Subscribe to an event. Its occurrences arrive as rois.event.notify_event
   * notifications, and under their event type.
   *
   * The engine subscribes to the one component that declares `eventType` and
   * matches the condition, with the same rules as query().
   *
   * @returns The subscribe_id, for unsubscribe().
   */
  async subscribe(eventType: string, condition: string = ""): Promise<string> {
    const result = await this.call(RoISMethods.Subscribe, {
      event_type: eventType,
      condition,
    });
    return result.subscribe_id;
  }

  /**
   * Cancel a subscription. The engine ignores an id it does not know, as RoIS
   * requires.
   */
  async unsubscribe(subscribeId: string): Promise<void> {
    await this.call(RoISMethods.Unsubscribe, { subscribe_id: subscribeId });
  }

  /**
   * Read the payload of an event until it expires.
   *
   * @param condition - Filter on the results. Must be empty for now.
   */
  async getEventDetail(eventId: string, condition: string = ""): Promise<Result[]> {
    const result = await this.call(RoISMethods.GetEventDetail, {
      event_id: eventId,
      condition,
    });
    return result.results ?? [];
  }

  // -----------------------------------------------------------------------
  // Private: calls
  // -----------------------------------------------------------------------

  /** Run a catalog method on a connected client. */
  private async call<M extends RoISMethod>(
    method: M,
    params: MethodParams<M>,
  ): Promise<MethodResult<M>> {
    if (!this.connected) {
      throw new TransportError(`Cannot call ${method}: client is not connected`);
    }
    return this.request(method, params);
  }

  /**
   * Validate the params, send the request, validate the result and check its
   * return code. Invalid params throw before anything is sent, and a result
   * that does not match the catalog throws instead of reaching the caller.
   */
  private async request<M extends RoISMethod>(
    method: M,
    params: MethodParams<M>,
  ): Promise<MethodResult<M>> {
    const schema = RoISMethodSchemas[method] as unknown as MethodSchema<M>;
    const validParams = schema.params.parse(params) as Record<string, unknown>;
    const raw = await this.wire.send(method, validParams);
    const result = schema.result.parse(raw);
    const returnCode = (result as { return_code: ReturnCode }).return_code;
    if (returnCode !== "OK") {
      throw new RoISError(returnCode, method);
    }
    return result;
  }

  // -----------------------------------------------------------------------
  // Private: notifications
  // -----------------------------------------------------------------------

  /**
   * Re-emit what the transport receives. Catalog notifications are validated
   * and emitted with their params. Methods outside the catalog reach listeners
   * through the generic "notification" event only.
   */
  private forwardTransportEvents(): void {
    this.wire.on("notification", (notification: JsonRpcNotification) => {
      this.emit("notification", notification);
      if (notification.method in RoISNotificationSchemas) {
        this.dispatchNotification(notification.method as RoISNotification, notification.params);
      }
    });

    this.wire.on("close", (code: number, reason: string) => {
      this.connected = false;
      this.emit("close", code, reason);
    });

    this.wire.on("error", (error: Error) => {
      this.emit("error", error);
    });
  }

  /** Validate a catalog notification and emit its params. */
  private dispatchNotification(method: RoISNotification, rawParams: unknown): void {
    const parsed = RoISNotificationSchemas[method].params.safeParse(rawParams ?? {});
    if (!parsed.success) {
      this.emit(
        "error",
        new TransportError(`Invalid params in ${method} notification: ${parsed.error.message}`),
      );
      return;
    }
    this.emit(method, parsed.data);

    // An event also goes out under its own type, so a caller can listen for
    // "person_detected" directly. Names the client already uses are skipped.
    if (method === RoISNotifications.NotifyEvent) {
      const eventType = (parsed.data as NotificationParams<"rois.event.notify_event">).event_type;
      if (!RESERVED_EVENTS.has(eventType) && !eventType.startsWith("rois.")) {
        this.emit(eventType, parsed.data);
      }
    }
  }
}
