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
 * A streaming component is driven with these same methods. Carrying its media
 * is planned.
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
 *   const statuses = new Map<string, string>();
 *   client.on("rois.command.completed", ({ command_id, status }) => {
 *     statuses.set(command_id, status);
 *   });
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

// 1. External packages
import type { z } from "zod";

// 2. Internal packages (@openrois/*)
import {
  RoISMethods,
  RoISMethodSchemas,
  RoISNotificationSchemas,
} from "@openrois/interfaces";

import type {
  CommandUnitSchema,
  ConcurrentCommandsSchema,
  HRIComponentProfile,
  HRIEngineProfileType,
  Parameter,
  Result,
  ReturnCode,
  RoISMethod,
  RoISMethodMap,
  RoISNotification,
  RoISNotificationMap,
} from "@openrois/interfaces";

// 3. Local modules
import { TypedEmitter } from "./emitter";
import {
  WebSocketTransport,
  TransportError,
  type TransportOptions,
} from "./transport";

// The condition builders, so a client needs no second import to write conditions.
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
} from "@openrois/interfaces";
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
 * One command for execute(): a CommandUnit without its `command_id`, which the
 * engine assigns (spec 8.2.2.2).
 */
export type CommandUnitInput = Omit<z.input<typeof CommandUnitSchema>, "command_id">;

/**
 * Commands for execute() in branches that run at the same time. Each branch runs
 * its commands in order, and the next item waits for every branch.
 */
export type ConcurrentCommandsInput = Omit<
  z.input<typeof ConcurrentCommandsSchema>,
  "branch_list"
> & {
  branch_list: { command_list: CommandUnitInput[] }[];
};

/** One item of the command_unit_list that execute() takes. */
export type CommandUnitSequenceItemInput = CommandUnitInput | ConcurrentCommandsInput;

/** The params a listener receives for each catalog notification. */
export type NotificationParams<N extends RoISNotification> = RoISNotificationMap[N]["params"];

/** The listener arguments of every event the client emits. */
export type RoISClientEvents = {
  [N in RoISNotification]: [params: NotificationParams<N>];
} & {
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

// ---------------------------------------------------------------------------
// RoISClient
// ---------------------------------------------------------------------------

/**
 * A connection to an OpenRoIS engine, with one method per RoIS operation.
 *
 * Create it with RoISClient.connect(). One client is one session: bindings and
 * subscriptions end with it, and nothing reconnects by itself.
 *
 * Listen with on() and off():
 *   "rois.event.notify_event"     NotifyEventParams, for every event of a subscription
 *   "rois.command.completed"      CompletedParams, when a command ends
 *   "rois.system.notify_error"    NotifyErrorParams, when the engine reports an error
 *   "rois.system.profile_changed" ProfileChangedParams, when components join or leave
 *   "close"                       (code, reason) when the connection closes
 *   "error"                       Error, for a message that cannot be used or a listener
 *                                 that throws. With no listener it goes to the console.
 */
export class RoISClient extends TypedEmitter<RoISClientEvents> {
  /** The WebSocket transport this client sends on. */
  private readonly wire: WebSocketTransport;

  /** Whether the connect handshake succeeded and disconnect has not run. */
  private connected: boolean = false;

  /** The disconnect in flight, which overlapping callers share. */
  private disconnecting: Promise<void> | null = null;

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
   * even when the engine answers with an error. Safe to call more than once. Calls
   * that overlap send one rois.system.disconnect and share its outcome.
   */
  async disconnect(): Promise<void> {
    this.disconnecting ??= this.endSession().finally(() => {
      this.disconnecting = null;
    });
    return this.disconnecting;
  }

  /** Run disconnect() when a block declared with `await using` ends. */
  async [Symbol.asyncDispose](): Promise<void> {
    await this.disconnect();
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
   * Run commands in order. A ConcurrentCommands item runs its branches at the
   * same time, and each branch runs its commands in order.
   *
   * The engine answers as soon as it accepts the commands, with the command_id
   * it assigned to each one. Each command then ends with a
   * rois.command.completed notification carrying that command_id, which
   * arrives after the answer, and getCommandResult() reads its results.
   *
   * @param commandUnitList - The commands, without command ids.
   * @returns The command_id the engine assigned to every command, in the order
   *   the list gives them, with the commands of a ConcurrentCommands item branch
   *   by branch.
   */
  async execute(commandUnitList: CommandUnitSequenceItemInput[]): Promise<string[]> {
    const result = await this.call(RoISMethods.Execute, { command_unit_list: commandUnitList });
    return (result.command_unit_list ?? []).flatMap((item) =>
      "branch_list" in item
        ? item.branch_list.flatMap((branch) => branch.command_list.map((unit) => unit.command_id))
        : [item.command_id],
    );
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
   * notifications, which carry the subscribe_id this returns.
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

  /** The work of disconnect(), once for all the calls that overlap. */
  private async endSession(): Promise<void> {
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
   * and emitted with their params. Methods outside the catalog stay on the
   * transport's "notification" event.
   */
  private forwardTransportEvents(): void {
    this.wire.on("notification", ({ method, params }) => {
      if (Object.hasOwn(RoISNotificationSchemas, method)) {
        this.dispatchNotification(method as RoISNotification, params);
      }
    });

    this.wire.on("close", (code, reason) => {
      this.connected = false;
      this.emit("close", code, reason);
    });

    this.wire.on("error", (error) => {
      this.emit("error", error);
    });
  }

  /** Validate a catalog notification and emit its params. */
  private dispatchNotification<N extends RoISNotification>(method: N, rawParams: unknown): void {
    const parsed = RoISNotificationSchemas[method].params.safeParse(rawParams ?? {});
    if (!parsed.success) {
      this.emit(
        "error",
        new TransportError(`Invalid params in ${method} notification: ${parsed.error.message}`),
      );
      return;
    }
    this.emit(method, ...([parsed.data] as unknown as RoISClientEvents[N]));
  }
}
