/**
 * WebSocket transport layer for the OpenRoIS SDK.
 *
 * Carries the JSON-RPC messages between RoISClient and an engine.
 * Responsibilities:
 *
 *   - Establish and manage a WebSocket connection (browser or Node.js).
 *   - Serialize outgoing JSON-RPC requests and deserialize incoming messages.
 *   - Correlate responses to pending requests by matching the `id` field.
 *   - Route server-push notifications to listeners.
 *   - Handle connection errors, timeouts, and unexpected disconnects.
 *
 * The transport does NOT validate the inner payload of `params` or `result`.
 * RoISClient does that with the catalog schemas from @openrois/interfaces
 * (RoISMethodSchemas and RoISNotificationSchemas).
 *
 * Usage (both Node.js and Browser):
 *   const transport = new WebSocketTransport();
 *   await transport.connect("ws://localhost:8765");
 *   const result = await transport.send("rois.command.search", { condition: "" });
 *   transport.close();
 *
 * The transport uses the global WebSocket, which browsers and Node.js 22 both
 * have. TransportOptions.webSocketFactory replaces it, for example to pass
 * headers with the `ws` package.
 *
 * Architecture: docs/architecture.md section 4 (Client SDK layer)
 */

import { TypedEmitter } from "./emitter";
import {
  JsonRpcResponseSchema,
  JsonRpcErrorSchema,
  JsonRpcNotificationSchema,
  JSONRPC_VERSION,
  type JsonRpcRequest,
  type JsonRpcErrorObject,
  type JsonRpcNotification,
} from "./jsonrpc";

// ---------------------------------------------------------------------------
// WebSocket abstraction
// ---------------------------------------------------------------------------

/**
 * Minimal WebSocket interface satisfied by the global WebSocket of browsers and
 * Node.js, and by the `ws` package.
 *
 * We use the property-based event handler style (onopen, onmessage, etc.)
 * because all of them support it identically. The transport assigns these
 * handlers after creating the socket.
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
  /** connect() has been called, and the WebSocket has not opened yet. */
  CONNECTING = "CONNECTING",
  /** WebSocket is open and ready to send/receive messages. */
  CONNECTED = "CONNECTED",
  /** close() has been called, and the WebSocket has not finished closing yet. */
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
   * By default, the transport uses the global WebSocket. Override this if you
   * need custom WebSocket configuration (headers, protocols, proxy settings,
   * etc.) or run somewhere that has no global WebSocket.
   *
   * Example (Node.js, `ws` package):
   *   webSocketFactory: (url) =>
   *     new WebSocket(url, { perMessageDeflate: false }) as unknown as WebSocketLike
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

/** The most bytes of UTF-8 that a close frame has room for as its reason. */
const MAX_CLOSE_REASON_BYTES = 123;

/** Open a socket with the global WebSocket of the runtime. */
function globalWebSocketFactory(url: string): WebSocketLike {
  // Read through a narrow type so that the published types need no DOM library.
  const { WebSocket } = globalThis as { WebSocket?: new (url: string) => WebSocketLike };
  if (WebSocket === undefined) {
    throw new Error("This runtime has no global WebSocket. Pass a webSocketFactory.");
  }
  return new WebSocket(url);
}

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
 * Raised when the engine responds with a JSON-RPC error object.
 *
 * This reports a protocol fault: unparseable JSON, an invalid request, an
 * unknown method, params that fail validation, or an internal error. A RoIS
 * failure is not an RpcError: it is a normal result with a return_code other
 * than OK, which RoISClient raises as a RoISError.
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
 * The events of WebSocketTransport, with their listener arguments.
 *
 *   "open"          - The WebSocket connection opened successfully.
 *   "notification"  - A JSON-RPC notification arrived from the gateway, with any
 *                     method, in or outside the catalog.
 *   "close"         - The WebSocket connection closed.
 *   "error"         - A message from the gateway could not be used.
 */
export type TransportEvents = {
  open: [];
  notification: [notification: JsonRpcNotification];
  close: [code: number, reason: string];
  error: [error: Error];
};

// ---------------------------------------------------------------------------
// WebSocketTransport
// ---------------------------------------------------------------------------

/**
 * Manages a single WebSocket connection to the OpenRoIS gateway.
 *
 * The transport handles the JSON-RPC 2.0 wire protocol: serialization,
 * deserialization, request/response correlation, notification routing,
 * and error handling. RoISClient calls transport.send() and listens to the
 * transport events.
 *
 * One transport instance manages one connection. To reconnect, close the
 * existing connection and call connect() again.
 */
export class WebSocketTransport extends TypedEmitter<TransportEvents> {
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

  /** Ends the connect() that is in progress, or null when none is. */
  private abortConnect: ((message: string) => void) | null = null;

  constructor(options?: TransportOptions) {
    super();
    this.options = {
      requestTimeout: options?.requestTimeout ?? DEFAULT_REQUEST_TIMEOUT,
      connectTimeout: options?.connectTimeout ?? DEFAULT_CONNECT_TIMEOUT,
      webSocketFactory: options?.webSocketFactory ?? globalWebSocketFactory,
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
   * Rejects with ConnectionError if the connection fails or times out, or if
   * close() runs first.
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
      let socket: WebSocketLike;
      try {
        socket = this.options.webSocketFactory(url);
      } catch (err) {
        this._state = TransportState.DISCONNECTED;
        const message = err instanceof Error ? err.message : String(err);
        reject(new ConnectionError(
          `Failed to create WebSocket: ${message}`,
          url,
        ));
        return;
      }
      this.ws = socket;

      // Every way out of the attempt stops its timer, so the timer can never act on a
      // connection that a later connect() opened.
      const fail = (message: string): void => {
        clearTimeout(connectTimer);
        this.abortConnect = null;
        this.cleanupSocket();
        this._state = TransportState.DISCONNECTED;
        reject(new ConnectionError(message, url));
      };

      // Close it as well, or the handshake can still finish after the caller gave up,
      // and leave an open connection that nothing holds.
      const abort = (message: string): void => {
        fail(message);
        try {
          socket.close();
        } catch {
          // Ignore errors from closing a socket that is failing on its own.
        }
      };

      // Start the connection timeout timer.
      const connectTimer = setTimeout(() => {
        abort(`Connection timed out after ${this.options.connectTimeout}ms`);
      }, this.options.connectTimeout);
      this.abortConnect = abort;

      // Handle successful connection.
      socket.onopen = () => {
        clearTimeout(connectTimer);
        this.abortConnect = null;
        this._state = TransportState.CONNECTED;
        this.emit("open");
        resolve();
      };

      // Handle connection failure (fires before onopen). After the connection
      // opened, a socket error says nothing that the close event after it does not.
      socket.onerror = (event) => {
        if (this._state === TransportState.CONNECTING) {
          fail(`WebSocket connection failed: ${event.message ?? "unknown error"}`);
        }
      };

      // Handle unexpected close during connection attempt.
      socket.onclose = (event) => {
        if (this._state === TransportState.CONNECTING) {
          fail(`WebSocket closed during connection: code ${event.code}`);
          return;
        }
        this.handleClose(event.code, event.reason);
      };

      // Wire up the message handler.
      socket.onmessage = (event) => {
        // Every implementation delivers the payload as event.data. In the
        // `ws` package a binary frame arrives as a Buffer, so we convert it.
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
   * catalog schema for the method:
   *   const result = await transport.send("rois.command.search", { condition: "" });
   *   const parsed = RoISMethodSchemas["rois.command.search"].result.parse(result);
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
   * During connect(), this ends the attempt instead: connect() rejects with a
   * ConnectionError and no "close" event fires, because no connection opened.
   *
   * @param code   - WebSocket close code (default: 1000 for normal closure): 1000, or
   *                 3000 to 4999, which is what the WebSocket API lets a client send.
   * @param reason - Human-readable close reason, at most 123 bytes of UTF-8.
   * @throws TransportError for any other code or reason, in every state, and a
   *         connection stays open.
   */
  close(code: number = 1000, reason: string = "client closed"): void {
    // Checked here for every kind of socket. The global WebSocket throws on these, but
    // the `ws` package can throw halfway, with a socket that neither works nor closes.
    if (code !== 1000 && !(code >= 3000 && code <= 4999)) {
      throw new TransportError(`Cannot close with code ${code}: use 1000, or 3000 to 4999`);
    }
    if (new TextEncoder().encode(reason).length > MAX_CLOSE_REASON_BYTES) {
      throw new TransportError(
        `Cannot close with this reason: it is over ${MAX_CLOSE_REASON_BYTES} bytes of UTF-8`
      );
    }

    if (this._state === TransportState.DISCONNECTED || !this.ws) {
      return;
    }

    if (this.abortConnect) {
      this.abortConnect("Connection closed by client");
      return;
    }

    // First, so that a socket that throws leaves the transport as it was, and nothing
    // reports a close that never happened.
    this.ws.close(code, reason);

    this._state = TransportState.CLOSING;
    this.rejectAllPending(
      new ConnectionError("Connection closed by client", this.url)
    );

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
   * Handle a notification by emitting it as an event. It goes out only as
   * "notification", never under its method name, because a server could then
   * fake the "close" event by naming a notification after it.
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

    this.emit("notification", parseResult.data);
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
    for (const pending of this.pending.values()) {
      clearTimeout(pending.timer);
      pending.reject(error);
    }
    this.pending.clear();
  }

  /**
   * Null out the WebSocket reference and remove event handlers.
   *
   * Prevents stale handlers from firing after the transport considers
   * itself disconnected. The error handler stays as a no-op, because the `ws`
   * package throws a late socket error that has no handler, and it raises one
   * when a socket closes before its handshake ends.
   */
  private cleanupSocket(): void {
    if (this.ws) {
      this.ws.onopen = null;
      this.ws.onclose = null;
      this.ws.onmessage = null;
      this.ws.onerror = () => {};
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
}
