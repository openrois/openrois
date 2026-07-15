/**
 * RoISClient: top-level client for the OpenRoIS TypeScript SDK.
 *
 * Wraps the WebSocket transport and JSON-RPC protocol into a clean,
 * high-level API that mirrors the five RoIS interfaces:
 *
 *   SystemIF  -> connect, disconnect, getProfile, getErrorDetail
 *   CommandIF -> search, bind, bindAny, release, getParameter,
 *                setParameter, execute, getCommandResult
 *   QueryIF   -> query
 *   EventIF   -> subscribe, unsubscribe, getEventDetail
 *   Streaming -> (deferred, not in scope for Week 1-2)
 *
 * Usage:
 *   import { RoISClient } from "@openrois/sdk";
 *
 *   const client = await RoISClient.connect("wss://gateway.example.com", {
 *     token: await getAccessToken(),
 *   });
 *
 *   // Search for available components
 *   const components = await client.search();
 *
 *   // Query a component's status
 *   const status = await client.query("PersonDetection_0", "component_status");
 *
 *   // Subscribe to events
 *   const subId = await client.subscribe("PersonDetection_0", "person_detected");
 *   client.on("person_detected", (event) => {
 *     console.log(`${event.params.number} people detected`);
 *   });
 *
 *   // Navigate
 *   const cmdId = await client.execute("Navigation_0", {
 *     target_positions: ["3.0,1.5,0.0"],
 *     time_limit: 30,
 *   });
 *
 *   await client.disconnect();
 *
 * Architecture: docs/architecture.md section 4 (Client SDK layer)
 */

// 1. Node.js built-ins
import { EventEmitter } from "node:events";

// 2. External packages
// (zod is not used directly in this module. Schemas are imported from
// @openrois/interfaces, which re-exports zod-based schemas.)

// 3. Internal packages (@openrois/*)
import {
  DiscoverResponseSchema,
  InvokeResponseSchema,
  QueryResponseSchema,
  SubscribeResponseSchema,
  ReturnCodeSchema,
} from "@openrois/interfaces";

import type {
  DiscoverResponse,
  InvokeResponse,
  QueryResponse,
  SubscribeResponse,
  ReturnCode,
  Result,
} from "@openrois/interfaces";

// 4. Local modules
import {
  WebSocketTransport,
  TransportError,
  ConnectionError,
  RpcError,
  type TransportOptions,
} from "./transport";

// ---------------------------------------------------------------------------
// Configuration
// ---------------------------------------------------------------------------

/**
 * Options for creating a RoISClient connection.
 */
export interface ClientOptions {
  /**
   * Authentication token for the gateway (e.g. a JWT or bearer token).
   *
   * The token is NOT sent in the `rois.system.connect` message params.
   * Auth is a transport-layer concern. A custom `webSocketFactory` in
   * `transport.webSocketFactory` can read this token from the
   * `ClientOptions` and attach it to the WebSocket upgrade request
   * (e.g. as an `Authorization` header or query parameter).
   *
   * The client itself does not use this field. It is here so callers
   * can pass it through to a custom factory in a type-safe way.
   */
  token?: string;

  /**
   * Transport-level options (timeouts, WebSocket factory).
   * Passed through to the underlying WebSocketTransport.
   */
  transport?: TransportOptions;
}

// ---------------------------------------------------------------------------
// Error classes
// ---------------------------------------------------------------------------

/**
 * Raised when a RoIS operation returns a non-OK ReturnCode.
 *
 * Carries the structured ReturnCode so callers can inspect and handle
 * specific failure modes (BAD_PARAMETER, UNSUPPORTED, TIMEOUT, etc.).
 */
export class RoISError extends Error {
  /** The ReturnCode from the gateway response. */
  // (BAD_PARAMETER, UNSUPPORTED, OUT_OF_RESOURCES, TIMEOUT) 
  // and the method name that failed.
  readonly returnCode: ReturnCode;

  /** The RoIS method that failed. */
  //Ex: socket died
  readonly method: string;

  constructor(returnCode: ReturnCode, method: string, detail?: string) {
    const message = detail
      ? `${method} failed with ${returnCode}: ${detail}`
      : `${method} failed with ${returnCode}`;
    super(message);
    this.name = "RoISError";
    this.returnCode = returnCode;
    this.method = method;
  }
}

// ---------------------------------------------------------------------------
// RoISClient
// ---------------------------------------------------------------------------

/**
 * High-level client for communicating with an OpenRoIS gateway.
 *
 * The client manages the WebSocket connection, serializes RoIS operations
 * into JSON-RPC requests, validates responses against the canonical schemas,
 * and routes async notifications to event listeners.
 *
 * Use the static RoISClient.connect() factory to create an instance.
 * Do not call the constructor directly.
 *
 * Events emitted:
 *   "notification"              - Any server-push notification (generic).
 *   "rois.event.notify"         - Component event (person_detected, reached_target, etc.).
 *   "rois.command.completed"    - A command finished executing.
 *   "rois.system.notify_error"  - The gateway reported an error.
 *   "close"                     - The connection was lost.
 *   "error"                     - A transport-level error occurred.
 */
export class RoISClient extends EventEmitter {
  /** The underlying transport managing the WebSocket connection. */
  private transport: WebSocketTransport;

  /** Says whether the client has completed the RoIS system.connect handshake. */
  private connected: boolean = false;

  /**
   * The underlying transport managing the WebSocket connection.
   *
   * Exposed so that interface-specific clients (SystemClient, CommandClient,
   * etc.) can be constructed over the same connection without re-opening it.
   */
  get getTransport(): WebSocketTransport {
    return this.transport;
  }

  // -----------------------------------------------------------------------
  // Construction (private -- use RoISClient.connect() instead)
  // -----------------------------------------------------------------------

  /**
   * Private constructor. Use RoISClient.connect() to create a client.
   *
   * The constructor wires up event forwarding from the transport so
   * callers can listen on the client directly.
   */
  private constructor(transport: WebSocketTransport) {
    super();
    this.transport = transport;
    this.forwardTransportEvents();
  }

  // -----------------------------------------------------------------------
  // Static factory
  // -----------------------------------------------------------------------

  /**
   * Connect to an OpenRoIS gateway and return a ready-to-use client.
   *
   * This is the primary entry point for the SDK. It:
   *   1. Creates a WebSocketTransport.
   *   2. Opens the WebSocket connection to the gateway.
   *   3. Sends rois.system.connect with empty params and validates the
   *      response. The bearer token, if any, is passed at the transport
   *      layer (WebSocket upgrade headers or query params), not in the
   *      message params. This keeps auth as a transport concern.
   *   4. Returns a connected RoISClient instance.
   *
   * @param url     - Gateway WebSocket URL, e.g. "wss://gateway.example.com".
   * @param options - Transport configuration. The `token` field, if
   *   provided, is available to a custom `webSocketFactory` but is NOT
   *   sent in the `rois.system.connect` message params.
   * @returns A connected RoISClient ready for RoIS operations.
   *
   * @throws ConnectionError if the WebSocket connection fails.
   * @throws RoISError if the gateway returns a non-OK return code for
   *   the `rois.system.connect` handshake.
   */
  static async connect(
    url: string,
    options?: ClientOptions,
  ): Promise<RoISClient> {

    // Step 1: Create the transport with any caller-provided options.
    const transport = new WebSocketTransport(options?.transport);

    // Step 2: Open the WebSocket connection.
    // The bearer token, if any, is passed at the transport layer via
    // the webSocketFactory (e.g. as a query param or upgrade header).
    await transport.connect(url);

    // Step 3: Create the client.
    const client = new RoISClient(transport);

    // Step 4: Perform the RoIS system.connect handshake.
    // Send rois.system.connect with empty params. The token is NOT in
    // the message. Auth happened at the transport layer.
    const result = await transport.send("rois.system.connect");
    const parsed = result as Record<string, unknown>;
    const returnCode = ReturnCodeSchema.parse(parsed.return_code);
    if (returnCode !== "OK") {
      throw new RoISError(returnCode, "rois.system.connect");
    }

    client.connected = true;
    return client;
  }

  // -----------------------------------------------------------------------
  // SystemIF operations
  // -----------------------------------------------------------------------

  /**
   * Disconnect from the gateway.
   *
   * Closes the WebSocket connection directly. No `rois.system.disconnect`
   * message is sent. The gateway is expected to detect the WebSocket close
   * and clean up the session. Safe to call multiple times.
   */
  async disconnect(): Promise<void> {
    if (!this.connected) {
      return;
    }

    // TODO: send rois.system.disconnect and await acknowledgment.
    // For now, we just close the transport directly.

    this.connected = false;
    this.transport.close();
  }

  /**
   * Retrieve the gateway's HRI Engine profile.
   *
   * The profile describes all available components, their capabilities,
   * and supported operations. This is the aggregated profile from all
   * sub-engines behind the gateway.
   *
   * Maps to: rois.system.get_profile
   *
   * @returns The HRI Engine profile (XML string).
   *
   * TODO: define the response type once the profile schema is finalized.
   */
  async getProfile(): Promise<unknown> {
    this.ensureConnected("getProfile");
    const result = await this.transport.send("rois.system.get_profile");
    // TODO: validate with a profile response schema.
    return result;
  }

  /**
   * Get detailed information about a specific error.
   *
   * Maps to: rois.system.get_error_detail
   *
   * @param errorId - The error identifier from a notify_error event.
   * @returns Error details from the gateway.
   *
   * TODO: define the response type once the error detail schema is finalized.
   */
  async getErrorDetail(errorId: string): Promise<unknown> {
    this.ensureConnected("getErrorDetail");
    const result = await this.transport.send(
      "rois.system.get_error_detail",
      { error_id: errorId },
    );
    // TODO: validate with an error detail response schema.
    return result;
  }

  // -----------------------------------------------------------------------
  // CommandIF operations
  // -----------------------------------------------------------------------

  /**
   * Search for components matching a condition.
   *
   * Returns a list of component_ref identifiers that can be passed to
   * bind(), query(), or subscribe().
   *
   * Maps to: rois.command.search
   * Request schema:  DiscoverRequest  { condition }
   * Response schema: DiscoverResponse { return_code, component_ref_list }
   *
   * @param condition - ISO 19143 filter expression. Empty string returns all.
   * @returns List of matching component_ref identifiers.
   */
  async search(condition: string = ""): Promise<string[]> {
    this.ensureConnected("search");

    const result = await this.transport.send(
      "rois.command.search",
      { condition },
    );

    // Validate the response with the canonical schema.
    const parsed = DiscoverResponseSchema.parse(result);
    this.checkReturnCode(parsed.return_code, "rois.command.search");

    return parsed.component_ref_list ?? [];
  }

  /**
   * Reserve a specific component for exclusive use.
   *
   * The bind/execute/release pattern is the standard way to interact with
   * components. After binding, you can set parameters, execute commands,
   * and receive events from the component. Call release() when done.
   *
   * Maps to: rois.command.bind
   *
   * @param componentRef - The component_ref from search() results.
   * @returns The ReturnCode from the gateway.
   *
   * TODO: consider returning a ComponentProxy that wraps the component_ref
   * and provides start(), stop(), execute(), on() methods directly.
   */
  async bind(componentRef: string): Promise<ReturnCode> {
    this.ensureConnected("bind");

    const result = await this.transport.send(
      "rois.command.bind",
      { component_ref: componentRef },
    );

    // TODO: validate with a bind-specific response schema if one exists.
    // For now, extract the return_code field.
    const parsed = result as Record<string, unknown>;
    const returnCode = ReturnCodeSchema.parse(parsed.return_code);
    this.checkReturnCode(returnCode, "rois.command.bind");

    return returnCode;
  }

  /**
   * Reserve any component matching a condition.
   *
   * Like bind(), but the gateway picks the best available component
   * instead of the caller specifying one.
   *
   * Maps to: rois.command.bind_any
   *
   * @param condition - Filter expression to match candidate components.
   * @returns The component_ref of the bound component.
   *
   * TODO: define the response type (likely includes the chosen component_ref).
   */
  async bindAny(condition: string): Promise<string> {
    this.ensureConnected("bindAny");

    const result = await this.transport.send(
      "rois.command.bind_any",
      { condition },
    );

    // TODO: validate with the proper response schema.
    const parsed = result as Record<string, unknown>;
    return parsed.component_ref as string;
  }

  /**
   * Release a previously bound component.
   *
   * Frees the component for other applications. Any active subscriptions
   * or in-progress commands on this component should be cleaned up first.
   *
   * Maps to: rois.command.release
   *
   * @param componentRef - The component_ref to release.
   * @returns The ReturnCode from the gateway.
   */
  async release(componentRef: string): Promise<ReturnCode> {
    this.ensureConnected("release");

    const result = await this.transport.send(
      "rois.command.release",
      { component_ref: componentRef },
    );

    const parsed = result as Record<string, unknown>;
    const returnCode = ReturnCodeSchema.parse(parsed.return_code);
    return returnCode;
  }

  /**
   * Get current parameter values for a bound component.
   *
   * Maps to: rois.command.get_parameter
   *
   * @param componentRef - The component_ref to query.
   * @returns The parameter results (component-specific shape).
   */
  async getParameter(componentRef: string): Promise<Result[]> {
    this.ensureConnected("getParameter");

    const result = await this.transport.send(
      "rois.command.get_parameter",
      { component_ref: componentRef },
    );

    // TODO: validate with a get_parameter response schema.
    const parsed = result as Record<string, unknown>;
    this.checkReturnCode(
      ReturnCodeSchema.parse(parsed.return_code),
      "rois.command.get_parameter",
    );

    return (parsed.results as Result[]) ?? [];
  }

  /**
   * Set parameter values on a bound component.
   *
   * For example, setting navigation targets:
   *   await client.setParameter("Navigation_0", [
   *     { name: "target_positions", data_type_ref: "string[]", value: '["3.0,1.5,0.0"]' },
   *     { name: "time_limit", data_type_ref: "int", value: "30" },
   *   ]);
   *
   * Maps to: rois.command.set_parameter
   *
   * @param componentRef - The component_ref to configure.
   * @param parameters   - Named parameters to set.
   * @returns The InvokeResponse with return_code and command_id.
   */
  async setParameter(
    componentRef: string,
    parameters: Record<string, unknown>[],
  ): Promise<InvokeResponse> {
    this.ensureConnected("setParameter");

    const result = await this.transport.send(
      "rois.command.set_parameter",
      { component_ref: componentRef, parameters },
    );

    const parsed = InvokeResponseSchema.parse(result);
    this.checkReturnCode(parsed.return_code, "rois.command.set_parameter");

    return parsed;
  }

  /**
   * Execute a command on a bound component.
   *
   * Commands run asynchronously. This method returns immediately with a
   * command_id. Listen for "rois.command.completed" events to know when
   * the command finishes:
   *
   *   const cmdId = await client.execute("Navigation_0", { ... });
   *   client.on("rois.command.completed", (notification) => {
   *     if (notification.params.command_id === cmdId) {
   *       console.log("Navigation complete:", notification.params.status);
   *     }
   *   });
   *
   * Maps to: rois.command.execute
   *
   * @param componentRef - The component_ref to command.
   * @param params       - Command parameters (component-specific).
   * @returns The InvokeResponse with return_code and command_id.
   */
  async execute(
    componentRef: string,
    params: Record<string, unknown>,
  ): Promise<InvokeResponse> {
    this.ensureConnected("execute");

    const result = await this.transport.send(
      "rois.command.execute",
      { component_ref: componentRef, ...params },
    );

    const parsed = InvokeResponseSchema.parse(result);
    this.checkReturnCode(parsed.return_code, "rois.command.execute");

    return parsed;
  }

  /**
   * Get the result of a completed command.
   *
   * Call this after receiving a "rois.command.completed" notification
   * for the given command_id.
   *
   * Maps to: rois.command.get_command_result
   *
   * @param commandId - The command_id from execute() or a completed event.
   * @returns The command results (component-specific shape).
   */
  async getCommandResult(commandId: string): Promise<Result[]> {
    this.ensureConnected("getCommandResult");

    const result = await this.transport.send(
      "rois.command.get_command_result",
      { command_id: commandId },
    );

    // TODO: validate with a command result response schema.
    const parsed = result as Record<string, unknown>;
    this.checkReturnCode(
      ReturnCodeSchema.parse(parsed.return_code),
      "rois.command.get_command_result",
    );

    return (parsed.results as Result[]) ?? [];
  }

  // -----------------------------------------------------------------------
  // QueryIF operations
  // -----------------------------------------------------------------------

  /**
   * Run a SYNCHRONOUS query on a component.
   *
   * Queries return immediately with the requested data (unlike commands,
   * which run asynchronously). Common query types include:
   *   "component_status" - returns the current ComponentStatus
   *   "robot_position"   - returns position data (SystemInformation)
   *   "engine_status"    - returns engine status (SystemInformation)
   *
   * Maps to: rois.query.query
   * Request schema:  QueryRequest  { component_ref, query_type, condition }
   * Response schema: QueryResponse { return_code, results }
   *
   * @param componentRef - The component_ref to query.
   * @param queryType    - The query operation name.
   * @param condition    - Optional filter expression.
   * @returns The query results as an array of Result objects.
   */
  async query(
    componentRef: string,
    queryType: string,
    condition: string = "",
  ): Promise<Result[]> {
    this.ensureConnected("query");

    const result = await this.transport.send(
      "rois.query.query",
      { component_ref: componentRef, query_type: queryType, condition },
    );

    const parsed = QueryResponseSchema.parse(result);
    this.checkReturnCode(parsed.return_code, "rois.query.query");

    return parsed.results ?? [];
  }

  // -----------------------------------------------------------------------
  // EventIF operations
  // -----------------------------------------------------------------------

  /**
   * Subscribe to events from a component.
   *
   * After subscribing, the gateway pushes notifications to the SDK
   * whenever the event fires. Listen for them with:
   *   client.on("rois.event.notify", handler)
   *
   * Maps to: rois.event.subscribe
   * Request schema:  SubscribeRequest  { component_ref, event_type, condition }
   * Response schema: SubscribeResponse { return_code, subscribe_id }
   *
   * @param componentRef - The component_ref to subscribe to.
   * @param eventType    - Event type name, e.g. "person_detected".
   * @param condition    - Optional filter expression.
   * @returns The subscribe_id for this subscription (use to unsubscribe).
   */
  async subscribe(
    componentRef: string,
    eventType: string,
    condition: string = "",
  ): Promise<string> {
    this.ensureConnected("subscribe");

    const result = await this.transport.send(
      "rois.event.subscribe",
      { component_ref: componentRef, event_type: eventType, condition },
    );

    const parsed = SubscribeResponseSchema.parse(result);
    this.checkReturnCode(parsed.return_code, "rois.event.subscribe");

    return parsed.subscribe_id;
  }

  /**
   * Cancel an event subscription.
   *
   * Maps to: rois.event.unsubscribe
   *
   * @param subscribeId - The subscribe_id returned by subscribe().
   * @returns The ReturnCode from the gateway.
   */
  async unsubscribe(subscribeId: string): Promise<ReturnCode> {
    this.ensureConnected("unsubscribe");

    const result = await this.transport.send(
      "rois.event.unsubscribe",
      { subscribe_id: subscribeId },
    );

    const parsed = result as Record<string, unknown>;
    return ReturnCodeSchema.parse(parsed.return_code);
  }

  /**
   * Get detailed information about a specific event.
   *
   * Maps to: rois.event.get_event_detail
   *
   * @param eventId - The event_id from a notification.
   * @returns Event details (component-specific shape).
   *
   * TODO: define the response type once the event detail schema is finalized.
   */
  async getEventDetail(eventId: string): Promise<unknown> {
    this.ensureConnected("getEventDetail");

    const result = await this.transport.send(
      "rois.event.get_event_detail",
      { event_id: eventId },
    );

    // TODO: validate with an event detail response schema.
    return result;
  }

  // -----------------------------------------------------------------------
  // Private: event forwarding
  // -----------------------------------------------------------------------

  /**
   * Forward transport events to the client so callers can listen on
   * the client directly instead of reaching into the transport.
   *
   * This means callers can do:
   *   client.on("rois.event.notify", handler)
   * instead of:
   *   client.transport.on("rois.event.notify", handler)
   */
  private forwardTransportEvents(): void {
    // Forward all notifications.
    this.transport.on("notification", (notification) => {
      this.emit("notification", notification);
    });

    // Forward method-specific notification events.
    this.transport.on("rois.event.notify", (notification) => {
      this.emit("rois.event.notify", notification);

      // Also emit the specific event_type for convenience.
      // This lets callers do: client.on("person_detected", handler)
      const params = notification.params as Record<string, unknown> | undefined;
      if (params?.event_type && typeof params.event_type === "string") {
        this.emit(params.event_type, notification);
      }
    });

    this.transport.on("rois.command.completed", (notification) => {
      this.emit("rois.command.completed", notification);
    });

    this.transport.on("rois.system.notify_error", (notification) => {
      this.emit("rois.system.notify_error", notification);
    });

    // Forward connection lifecycle events.
    this.transport.on("close", (code: number, reason: string) => {
      this.connected = false;
      this.emit("close", code, reason);
    });

    this.transport.on("error", (error: Error) => {
      this.emit("error", error);
    });
  }

  // -----------------------------------------------------------------------
  // Private: helpers
  // -----------------------------------------------------------------------

  /**
   * Guard that throws if the client is not connected.
   *
   * Called at the top of every public method to give a clear error
   * message instead of a confusing transport-level failure.
   */
  private ensureConnected(operation: string): void {
    if (!this.connected) {
      throw new TransportError(
        `Cannot call ${operation}: client is not connected`
      );
    }
  }

  /**
   * Check a ReturnCode and throw a RoISError if it is not OK.
   *
   * Called after parsing every gateway response. This centralizes the
   * error-checking pattern so individual methods don't repeat it.
   */
  private checkReturnCode(returnCode: ReturnCode, method: string): void {
    if (returnCode !== "OK") {
      throw new RoISError(returnCode, method);
    }
  }
}