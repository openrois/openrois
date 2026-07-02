/**
 * WebSocket transport layer for the OpenRoIS SDK.
 *
 * Provides the communication bridge between the SDK's client classes
 * (SystemClient, CommandClient, QueryClient, EventClient) and the
 * gateway. Responsibilities:
 *
 *   - Establish and manage a WebSocket connection (browser or Node.js).
 *   - Serialize outgoing JSON-RPC requests and deserialize incoming messages.
 *   - Correlate responses to pending requests by matching the `id` field.
 *   - Route server-push notifications to listeners via EventEmitter.
 *   - Handle connection errors, timeouts, and unexpected disconnects.
 *
 * The transport does NOT validate the inner payload of `params` or `result`.
 * That is the responsibility of the caller, using the schemas from
 * @openrois/interfaces (e.g. DiscoverResponseSchema.parse(result)).
 *
 * Usage (both Node.js and Browser):
 *   const transport = new WebSocketTransport();
 *   await transport.connect("ws://localhost:8765");
 *   const result = await transport.send("rois.command.search", { condition: "" });
 *   transport.close();
 *
 * The transport auto-detects the environment: it uses the global WebSocket
 * in browsers and the 'ws' npm package in Node.js. A custom factory can
 * still be passed via TransportOptions.webSocketFactory if needed.
 *
 * Architecture: docs/architecture.md section 4 (Client SDK layer)
 */

// 1. Node.js built-ins
import { EventEmitter } from "node:events";

// 2. External packages
import { z } from "zod";

// 3. Local modules
import {
  JsonRpcRequestSchema,
  JsonRpcResponseSchema,
  JsonRpcErrorSchema,
  JsonRpcNotificationSchema,
  JSONRPC_VERSION,
  type JsonRpcRequest,
  type JsonRpcResponse,
  type JsonRpcError,
  type JsonRpcNotification,
  type JsonRpcId,
  type JsonRpcParams,
  type JsonRpcErrorObject,
} from "./jsonrpc";

// ---------------------------------------------------------------------------
// WebSocket abstraction
// ---------------------------------------------------------------------------

/**
 * Minimal WebSocket interface satisfied by both the browser global WebSocket
 * and the Node.js `ws` package.
 *
 * We use the property-based event handler style (onopen, onmessage, etc.)
 * because both environments support it identically. The transport assigns
 * these handlers after creating the socket.
 */
export interface WebSocketLike {
  send(data: string): void;
  close(code?: number, reason?: string): void;
  readonly readyState: number;
  onopen: ((event: { type: string }) => void) | null;
  onclose: ((event: { code: number; reason: string; type: string }) => void) | null;
  onmessage: ((event: { data: unknown; type: string }) => void) | null;
  onerror: ((event: { error?: unknown; message?: string; type: string }) => void) | null;
}

/**
 * Standard WebSocket readyState values.
 *
 * These are the same in both browser WebSocket and the `ws` package.
 */
export const WS_READY_STATE = {
  CONNECTING: 0,
  OPEN: 1,
  CLOSING: 2,
  CLOSED: 3,
} as const;

// ---------------------------------------------------------------------------
// Transport state
// ---------------------------------------------------------------------------

/**
 * Connection lifecycle states for the transport.
 *
 * State transitions:
 *   DISCONNECTED -> CONNECTING -> CONNECTED -> CLOSING -> DISCONNECTED
 *                                           -> DISCONNECTED (unexpected close)
 */
export enum TransportState {
  /** No active connection. Initial state and state after close. */
  DISCONNECTED = "DISCONNECTED",
  /** connect() has been called; waiting for the WebSocket to open. */
  CONNECTING = "CONNECTING",
  /** WebSocket is open and ready to send/receive messages. */
  CONNECTED = "CONNECTED",
  /** close() has been called; waiting for the WebSocket to finish closing. */
  CLOSING = "CLOSING",
}

// ---------------------------------------------------------------------------
// Configuration
// ---------------------------------------------------------------------------

/**
 * Options for configuring the WebSocket transport.
 */
export interface TransportOptions {
  /**
   * Maximum time in milliseconds to wait for a response to a request.
   * If the gateway does not reply within this window, the Promise returned
   * by send() rejects with a RequestTimeoutError. Default: 30000 (30s).
   */
  requestTimeout?: number;

  /**
   * Maximum time in milliseconds to wait for the WebSocket connection to
   * open during connect(). Default: 10000 (10s).
   */
  connectTimeout?: number;

  /**
   * Optional factory function that creates a WebSocket instance for a given URL.
   *
   * By default, the transport auto-detects the environment: it uses the
   * global WebSocket in browsers and require("ws") in Node.js. Override
   * this if you need custom WebSocket configuration (headers, protocols,
   * proxy settings, etc.).
   *
   * Example:
   *   webSocketFactory: (url) => new WebSocket(url, { headers: { "X-Token": "..." } })
   */
  webSocketFactory?: (url: string) => WebSocketLike;
}

/** Resolved options with defaults applied. */
interface ResolvedOptions {
  requestTimeout: number;
  connectTimeout: number;
  webSocketFactory: (url: string) => WebSocketLike;
}

/** Default timeout for request/response round-trips (30 seconds). */
const DEFAULT_REQUEST_TIMEOUT = 30_000;

/** Default timeout for the initial WebSocket connection (10 seconds). */
const DEFAULT_CONNECT_TIMEOUT = 10_000;

// ---------------------------------------------------------------------------
// Error classes
// ---------------------------------------------------------------------------

/**
 * Base error for all transport-level failures.
 *
 * Callers can catch TransportError to handle any transport problem, or catch
 * a specific subclass for finer control.
 */
export class TransportError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "TransportError";
  }
}

/**
 * Raised when the WebSocket connection cannot be established or is lost
 * unexpectedly.
 */
export class ConnectionError extends TransportError {
  /** The URL that the transport tried to connect to, if available. */
  readonly url: string;

  constructor(message: string, url: string = "") {
    super(message);
    this.name = "ConnectionError";
    this.url = url;
  }
}

/**
 * Raised when a send() call does not receive a response within the
 * configured timeout window.
 */
export class RequestTimeoutError extends TransportError {
  /** The JSON-RPC method that timed out. */
  readonly method: string;
  /** The request id that timed out. */
  readonly requestId: string;

  constructor(method: string, requestId: string, timeoutMs: number) {
    super(
      `Request timed out after ${timeoutMs}ms: ${method} (id: ${requestId})`
    );
    this.name = "RequestTimeoutError";
    this.method = method;
    this.requestId = requestId;
  }
}

/**
 * Raised when the gateway responds with a JSON-RPC error object.
 *
 * This means the gateway understood the request but could not fulfill it.
 * The error carries the structured JSON-RPC error fields so callers can
 * inspect the code and any RoIS-level ReturnCode in the data field.
 */
export class RpcError extends TransportError {
  /** The numeric JSON-RPC error code (e.g. -32601 for MethodNotFound). */
  readonly code: number;
  /** Optional additional error data from the gateway. */
  readonly data: unknown;

  constructor(errorObject: JsonRpcErrorObject) {
    super(`RPC error ${errorObject.code}: ${errorObject.message}`);
    this.name = "RpcError";
    this.code = errorObject.code;
    this.data = errorObject.data;
  }
}

// ---------------------------------------------------------------------------
// Internal types
// ---------------------------------------------------------------------------

/**
 * Tracks a single in-flight request waiting for a response.
 *
 * When a response (or error) with a matching `id` arrives, the transport
 * calls resolve or reject and clears the timeout timer.
 */
interface PendingRequest {
  resolve: (result: unknown) => void;
  reject: (error: Error) => void;
  method: string;
  timer: ReturnType<typeof setTimeout>;
}

// ---------------------------------------------------------------------------
// Transport events
// ---------------------------------------------------------------------------

/**
 * Events emitted by WebSocketTransport.
 *
 * Listen with the standard EventEmitter API:
 *   transport.on("notification", (notification) => { ... });
 *   transport.on("close", (code, reason) => { ... });
 *   transport.on("error", (error) => { ... });
 *
 * Event catalog:
 *   "notification"  - A JSON-RPC notification arrived from the gateway.
 *                     Listener receives the full JsonRpcNotification object.
 *   "close"         - The WebSocket connection closed.
 *                     Listener receives (code: number, reason: string).
 *   "error"         - A transport-level error occurred (malformed message,
 *                     WebSocket error, etc.). Listener receives (error: Error).
 *   "open"          - The WebSocket connection opened successfully.
 *
 * Notification convenience events:
 *   The transport also emits the notification's method name as a separate
 *   event. For example, a "rois.event.notify" notification triggers both
 *   the generic "notification" event and a "rois.event.notify" event.
 *   This lets higher-level clients subscribe to specific push channels:
 *     transport.on("rois.event.notify", (notification) => { ... });
 *     transport.on("rois.command.completed", (notification) => { ... });
 */

// ---------------------------------------------------------------------------
// WebSocketTransport
// ---------------------------------------------------------------------------

/**
 * Manages a single WebSocket connection to the OpenRoIS gateway.
 *
 * The transport handles the JSON-RPC 2.0 wire protocol: serialization,
 * deserialization, request/response correlation, notification routing,
 * and error handling. Higher-level SDK clients (SystemClient, CommandClient,
 * etc.) call transport.send() and subscribe to transport events.
 *
 * One transport instance manages one connection. To reconnect, close the
 * existing connection and call connect() again.
 */
export class WebSocketTransport extends EventEmitter {
  /** Current connection state. */
  private _state: TransportState = TransportState.DISCONNECTED;

  /** The underlying WebSocket instance, or null when disconnected. */
  private ws: WebSocketLike | null = null;

  /** Map of request id -> pending request awaiting a response. */
  private pending: Map<string, PendingRequest> = new Map();

  /** Counter for generating unique request ids within this connection. */
  private nextId: number = 1;

  /** Resolved configuration with defaults applied. */
  private options: ResolvedOptions;

  /** The URL this transport is connected (or connecting) to. */
  private url: string = "";

  constructor(options?: TransportOptions) {
    super();
    this.options = {
      requestTimeout: options?.requestTimeout ?? DEFAULT_REQUEST_TIMEOUT,
      connectTimeout: options?.connectTimeout ?? DEFAULT_CONNECT_TIMEOUT,
      webSocketFactory: options?.webSocketFactory ?? this.defaultWebSocketFactory,
    };
  }

  // -------------------------------------------------------------------------
  // Public API
  // -------------------------------------------------------------------------

  /** The current connection state. */
  get state(): TransportState {
    return this._state;
  }

  /**
   * Open a WebSocket connection to the gateway.
   *
   * Resolves when the connection is established and ready for messages.
   * Rejects with ConnectionError if the connection fails or times out.
   *
   * @param url - The WebSocket URL, e.g. "ws://localhost:8765" or
   *              "wss://gateway.example.com".
   */
  async connect(url: string): Promise<void> {
    // Guard: do not allow connecting when already connected or connecting.
    if (this._state !== TransportState.DISCONNECTED) {
      throw new ConnectionError(
        `Cannot connect: transport is in state ${this._state}`,
        url,
      );
    }

    this.url = url;
    this._state = TransportState.CONNECTING;

    return new Promise<void>((resolve, reject) => {
      // Start the connection timeout timer.
      const connectTimer = setTimeout(() => {
        this.cleanupSocket();
        this._state = TransportState.DISCONNECTED;
        reject(new ConnectionError(
          `Connection timed out after ${this.options.connectTimeout}ms`,
          url,
        ));
      }, this.options.connectTimeout);

      try {
        this.ws = this.options.webSocketFactory(url);
      } catch (err) {
        clearTimeout(connectTimer);
        this._state = TransportState.DISCONNECTED;
        const message = err instanceof Error ? err.message : String(err);
        reject(new ConnectionError(
          `Failed to create WebSocket: ${message}`,
          url,
        ));
        return;
      }

      // Handle successful connection.
      this.ws.onopen = () => {
        clearTimeout(connectTimer);
        this._state = TransportState.CONNECTED;
        this.emit("open");
        resolve();
      };

      // Handle connection failure (fires before onopen).
      this.ws.onerror = (event) => {
        clearTimeout(connectTimer);
        // If we are still connecting, this error means the connection failed.
        // If we are already connected, handleError takes over.
        if (this._state === TransportState.CONNECTING) {
          this.cleanupSocket();
          this._state = TransportState.DISCONNECTED;
          const detail = event.message ?? "unknown error";
          reject(new ConnectionError(
            `WebSocket connection failed: ${detail}`,
            url,
          ));
        }
      };

      // Handle unexpected close during connection attempt.
      this.ws.onclose = (event) => {
        clearTimeout(connectTimer);
        if (this._state === TransportState.CONNECTING) {
          this.cleanupSocket();
          this._state = TransportState.DISCONNECTED;
          reject(new ConnectionError(
            `WebSocket closed during connection: code ${event.code}`,
            url,
          ));
          return;
        }
        this.handleClose(event.code, event.reason);
      };

      // Wire up the message handler.
      this.ws.onmessage = (event) => {
        // Both browser WebSocket and Node.js ws deliver the payload as
        // event.data. In Node.js ws, data may be a Buffer; we convert
        // to string.
        const raw = typeof event.data === "string"
          ? event.data
          : String(event.data);
        this.handleMessage(raw);
      };
    });
  }

  /**
   * Send a JSON-RPC request to the gateway and wait for the response.
   *
   * Returns a Promise that resolves with the `result` field from the
   * success response, or rejects with:
   *   - RpcError: the gateway sent a JSON-RPC error response.
   *   - RequestTimeoutError: no response within the timeout window.
   *   - ConnectionError: the connection dropped while waiting.
   *   - TransportError: the transport is not connected.
   *
   * The caller is responsible for validating the returned result with the
   * appropriate schema from @openrois/interfaces:
   *   const result = await transport.send("rois.command.search", { condition: "" });
   *   const parsed = DiscoverResponseSchema.parse(result);
   *
   * @param method - The JSON-RPC method name, e.g. "rois.command.search".
   * @param params - Optional named parameters for the method.
   * @returns The `result` field from the gateway's success response.
   */
  async send(method: string, params?: Record<string, unknown>): Promise<unknown> {
    // Guard: must be connected to send.
    if (this._state !== TransportState.CONNECTED || !this.ws) {
      throw new TransportError(
        `Cannot send: transport is in state ${this._state}`
      );
    }

    const id = this.generateId();

    // Build the JSON-RPC request envelope.
    const request: JsonRpcRequest = {
      jsonrpc: JSONRPC_VERSION,
      id,
      method,
      ...(params !== undefined ? { params } : {}),
    };

    // Serialize and send over the wire.
    const json = JSON.stringify(request);
    this.ws.send(json);

    // Return a Promise that will be resolved or rejected when the
    // matching response arrives (or the timeout fires).
    return new Promise<unknown>((resolve, reject) => {
      // Start the request timeout timer.
      const timer = setTimeout(() => {
        this.pending.delete(id);
        reject(new RequestTimeoutError(method, id, this.options.requestTimeout));
      }, this.options.requestTimeout);

      // Store the pending request so handleMessage can resolve it.
      this.pending.set(id, { resolve, reject, method, timer });
    });
  }

  /**
   * Close the WebSocket connection.
   *
   * Any pending requests are rejected with a ConnectionError.
   * Safe to call when already disconnected (no-op).
   *
   * @param code   - WebSocket close code (default: 1000 for normal closure).
   * @param reason - Human-readable close reason.
   */
  close(code: number = 1000, reason: string = "client closed"): void {
    if (this._state === TransportState.DISCONNECTED || !this.ws) {
      return;
    }

    this._state = TransportState.CLOSING;
    this.rejectAllPending(
      new ConnectionError("Connection closed by client", this.url)
    );

    try {
      this.ws.close(code, reason);
    } catch {
      // Ignore errors from closing an already-closed socket.
    }

    this.cleanupSocket();
    this._state = TransportState.DISCONNECTED;
    this.emit("close", code, reason);
  }

  // -------------------------------------------------------------------------
  // Private: message handling
  // -------------------------------------------------------------------------

  /**
   * Process a raw message string from the WebSocket.
   *
   * Parses the JSON, classifies the message type, and dispatches to the
   * appropriate handler (response correlation or notification routing).
   */
  private handleMessage(raw: string): void {
    // Step 1: Parse the raw JSON string into a plain object.
    let parsed: unknown;
    try {
      parsed = JSON.parse(raw);
    } catch {
      this.emit("error", new TransportError(
        `Received malformed JSON from gateway: ${raw.slice(0, 200)}`
      ));
      return;
    }

    // Step 2: Classify by field presence and dispatch.
    // The JSON-RPC 2.0 spec defines the message type by which fields are present:
    //   - Has `id` + `result`       -> Success Response
    //   - Has `id` + `error`        -> Error Response
    //   - Has `method`, no `id`     -> Notification (server push)
    //   - Has `method` + `id`       -> Request (unexpected from gateway)
    if (typeof parsed !== "object" || parsed === null) {
      this.emit("error", new TransportError(
        "Received non-object JSON from gateway"
      ));
      return;
    }

    const msg = parsed as Record<string, unknown>;

    // Check for Response (success): has id and result.
    if ("id" in msg && "result" in msg) {
      this.handleResponse(msg);
      return;
    }

    // Check for Error Response: has id and error.
    if ("id" in msg && "error" in msg) {
      this.handleErrorResponse(msg);
      return;
    }

    // Check for Notification: has method but no id.
    if ("method" in msg && !("id" in msg)) {
      this.handleNotification(msg);
      return;
    }

    // Unrecognized message shape.
    this.emit("error", new TransportError(
      `Received unrecognized message shape from gateway: ${raw.slice(0, 200)}`
    ));
  }

  /**
   * Handle a success response by resolving the matching pending request.
   */
  private handleResponse(msg: Record<string, unknown>): void {
    // Validate the envelope structure.
    const parseResult = JsonRpcResponseSchema.safeParse(msg);
    if (!parseResult.success) {
      this.emit("error", new TransportError(
        `Received invalid success response: ${parseResult.error.message}`
      ));
      return;
    }

    const response = parseResult.data;
    const id = String(response.id);
    const pendingRequest = this.pending.get(id);

    if (!pendingRequest) {
      // Response for an unknown id. Could be a duplicate or a response
      // that arrived after the timeout already fired.
      this.emit("error", new TransportError(
        `Received response for unknown request id: ${id}`
      ));
      return;
    }

    // Clean up and resolve.
    clearTimeout(pendingRequest.timer);
    this.pending.delete(id);
    pendingRequest.resolve(response.result);
  }

  /**
   * Handle an error response by rejecting the matching pending request.
   */
  private handleErrorResponse(msg: Record<string, unknown>): void {
    // Validate the envelope structure.
    const parseResult = JsonRpcErrorSchema.safeParse(msg);
    if (!parseResult.success) {
      this.emit("error", new TransportError(
        `Received invalid error response: ${parseResult.error.message}`
      ));
      return;
    }

    const errorResponse = parseResult.data;
    const id = String(errorResponse.id);
    const pendingRequest = this.pending.get(id);

    if (!pendingRequest) {
      this.emit("error", new TransportError(
        `Received error response for unknown request id: ${id}`
      ));
      return;
    }

    // Clean up and reject with a structured RpcError.
    clearTimeout(pendingRequest.timer);
    this.pending.delete(id);
    pendingRequest.reject(new RpcError(errorResponse.error));
  }

  /**
   * Handle a notification by emitting it as an event.
   *
   * Emits two events:
   *   1. "notification" with the full notification object (generic catch-all).
   *   2. The method name (e.g. "rois.event.notify") for targeted listeners.
   */
  private handleNotification(msg: Record<string, unknown>): void {
    // Validate the envelope structure.
    const parseResult = JsonRpcNotificationSchema.safeParse(msg);
    if (!parseResult.success) {
      this.emit("error", new TransportError(
        `Received invalid notification: ${parseResult.error.message}`
      ));
      return;
    }

    const notification = parseResult.data;

    // Emit the generic catch-all event.
    this.emit("notification", notification);

    // Emit a method-specific event for convenience.
    // This lets callers do: transport.on("rois.event.notify", handler)
    this.emit(notification.method, notification);
  }

  // -------------------------------------------------------------------------
  // Private: connection lifecycle
  // -------------------------------------------------------------------------

  /**
   * Handle WebSocket close after the connection was established.
   *
   * If the close was not initiated by the client (i.e. the state is still
   * CONNECTED), this is an unexpected disconnect. All pending requests are
   * rejected.
   */
  private handleClose(code: number, reason: string): void {
    const wasConnected = this._state === TransportState.CONNECTED;

    this.rejectAllPending(
      new ConnectionError(
        `WebSocket closed unexpectedly: code ${code}, reason: ${reason || "none"}`,
        this.url,
      )
    );

    this.cleanupSocket();
    this._state = TransportState.DISCONNECTED;

    if (wasConnected) {
      this.emit("close", code, reason);
    }
  }

  /**
   * Reject all pending requests with the given error.
   *
   * Called on disconnect (expected or unexpected) so no Promise is left
   * hanging forever.
   */
  private rejectAllPending(error: Error): void {
    for (const [id, pending] of this.pending) {
      clearTimeout(pending.timer);
      pending.reject(error);
    }
    this.pending.clear();
  }

  /**
   * Null out the WebSocket reference and remove event handlers.
   *
   * Prevents stale handlers from firing after the transport considers
   * itself disconnected.
   */
  private cleanupSocket(): void {
    if (this.ws) {
      this.ws.onopen = null;
      this.ws.onclose = null;
      this.ws.onmessage = null;
      this.ws.onerror = null;
      this.ws = null;
    }
  }

  // -------------------------------------------------------------------------
  // Private: utilities
  // -------------------------------------------------------------------------

  /**
   * Generate a unique request id.
   *
   * Uses a simple incrementing counter prefixed with "req-". Ids are unique
   * within a single transport instance. The counter resets if you create a
   * new transport.
   */
  private generateId(): string {
    const id = `req-${this.nextId}`;
    this.nextId += 1;
    return id;
  }

  /**
   * NEW CHANGE
   */
  /**
   * Default WebSocket factory that auto-detects the environment.
   *
   * Tries in order:
   *   1. globalThis.WebSocket (browsers, Deno, Bun, or any polyfilled env)
   *   2. The 'ws' npm package (Node.js)
   *
   * If neither is available, throws a ConnectionError explaining what to install.
   *
   * Note: the require("ws") call is inside a try/catch so bundlers that
   * target the browser can mark 'ws' as external without breaking the build.
   */
  private defaultWebSocketFactory(url: string): WebSocketLike {
    // 1. Check for a global WebSocket (browser, Deno, Bun).
    if (typeof globalThis.WebSocket !== "undefined") {
      return new globalThis.WebSocket(url) as unknown as WebSocketLike;
    }

    // 2. Try the 'ws' package for Node.js.
    try {
      // Dynamic require so browser bundlers can ignore or externalize this.
      // eslint-disable-next-line @typescript-eslint/no-var-requires
      const WS = require("ws");
      return new WS(url) as unknown as WebSocketLike;
    } catch {
      throw new ConnectionError(
        "No WebSocket implementation found. If running in Node.js, " +
        "install the 'ws' package: npm install ws",
        url,
      );
    }
  }
}