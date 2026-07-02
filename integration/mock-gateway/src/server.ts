/**
 * Mock RoIS gateway: a JSON-RPC 2.0 WebSocket test double.
 *
 * This is the Week 1 skeleton. It accepts WebSocket connections, parses
 * incoming JSON-RPC 2.0 messages, and answers the two System interface
 * lifecycle methods (connect, disconnect) with a canned OK. Any other method
 * returns a JSON-RPC "method not found" error, and malformed input returns the
 * appropriate parse or invalid-request error.
 *
 * The message schemas are reused from the SDK (@openrois/sdk/jsonrpc) so the
 * mock and the real client stay on a single wire contract. Later milestones
 * add a component registry, mock components, events, queries, and async command
 * completion (see project-outline.md Weeks 2 and 3).
 *
 * Architecture: docs/architecture.md section 4 (Client SDK layer)
 * Protocol surface: project-outline.md section 6
 */

import { WebSocketServer } from "ws";
import type { RawData, WebSocket } from "ws";
import {
  JSONRPC_VERSION,
  JsonRpcErrorCode,
  JsonRpcRequestSchema,
} from "@openrois/sdk/jsonrpc";
import type {
  JsonRpcError,
  JsonRpcId,
  JsonRpcRequest,
  JsonRpcResponse,
} from "@openrois/sdk/jsonrpc";

/** Default listening port when none is supplied. */
const DEFAULT_PORT = 8765;
/** Default host: loopback only, so the mock is not exposed on the network. */
const DEFAULT_HOST = "127.0.0.1";

/** Options for {@link createMockGateway}. */
export interface MockGatewayOptions {
  /**
   * TCP port to listen on. Use 0 to bind an ephemeral port chosen by the OS,
   * which is what tests do to avoid collisions. Defaults to 8765.
   */
  port?: number;
  /** Host interface to bind. Defaults to 127.0.0.1 (loopback only). */
  host?: string;
}

/** A running mock gateway handle. */
export interface MockGateway {
  /** The underlying ws WebSocketServer. */
  readonly wss: WebSocketServer;
  /** The actual bound port, resolved even when port 0 was requested. */
  readonly port: number;
  /** Stop the server and close all connections. Resolves once closed. */
  close(): Promise<void>;
}

/**
 * Start a mock gateway and resolve once it is listening.
 *
 * The returned promise resolves after the "listening" event so the caller can
 * read the actual bound port, which matters when port 0 is used to request an
 * ephemeral port.
 */
export function createMockGateway(
  options: MockGatewayOptions = {},
): Promise<MockGateway> {
  const port = options.port ?? DEFAULT_PORT;
  const host = options.host ?? DEFAULT_HOST;

  return new Promise((resolve, reject) => {
    const wss = new WebSocketServer({ port, host });

    wss.on("connection", (socket: WebSocket) => {
      socket.on("message", (data: RawData) => {
        handleMessage(socket, data);
      });
    });

    // Reject only for startup failures, before the server is listening.
    wss.once("error", reject);

    wss.once("listening", () => {
      wss.off("error", reject);
      const address = wss.address();
      const boundPort =
        typeof address === "object" && address !== null ? address.port : port;
      resolve({
        wss,
        port: boundPort,
        close: () =>
          new Promise<void>((resolveClose, rejectClose) => {
            wss.close((err) => (err ? rejectClose(err) : resolveClose()));
          }),
      });
    });
  });
}

/**
 * Handle one incoming message: parse, validate, dispatch, respond.
 */
function handleMessage(socket: WebSocket, data: RawData): void {
  let parsed: unknown;
  try {
    parsed = JSON.parse(data.toString());
  } catch {
    // The payload was not valid JSON. Per JSON-RPC 2.0, the id cannot be
    // recovered, so the error response carries a null id.
    send(
      socket,
      errorMessage(null, JsonRpcErrorCode.ParseError, "Parse error: invalid JSON"),
    );
    return;
  }

  const request = JsonRpcRequestSchema.safeParse(parsed);
  if (!request.success) {
    // The JSON parsed but is not a well-formed JSON-RPC request. Echo back the
    // original id if the payload carried a usable one.
    send(
      socket,
      errorMessage(
        extractId(parsed),
        JsonRpcErrorCode.InvalidRequest,
        "Invalid Request: not a valid JSON-RPC 2.0 request",
      ),
    );
    return;
  }

  dispatch(socket, request.data);
}

/**
 * Route a validated request to its handler.
 *
 * The Week 1 skeleton only answers the System interface lifecycle methods.
 * Every other method is reported as not found.
 */
function dispatch(socket: WebSocket, request: JsonRpcRequest): void {
  switch (request.method) {
    case "rois.system.connect":
    case "rois.system.disconnect":
      send(socket, okResponse(request.id));
      return;
    default:
      send(
        socket,
        errorMessage(
          request.id,
          JsonRpcErrorCode.MethodNotFound,
          `Method not found: ${request.method}`,
        ),
      );
  }
}

/**
 * Best-effort extraction of a JSON-RPC id from an unvalidated payload, used to
 * correlate error responses for malformed-but-parseable requests.
 */
function extractId(payload: unknown): JsonRpcId {
  if (typeof payload === "object" && payload !== null && "id" in payload) {
    const id = (payload as { id: unknown }).id;
    if (typeof id === "string" || typeof id === "number") {
      return id;
    }
  }
  return null;
}

/** Build a success response carrying a RoIS return_code of OK. */
function okResponse(id: JsonRpcId): JsonRpcResponse {
  return {
    jsonrpc: JSONRPC_VERSION,
    id,
    result: { return_code: "OK" },
  };
}

/** Build a JSON-RPC error response. */
function errorMessage(
  id: JsonRpcId,
  code: number,
  message: string,
): JsonRpcError {
  return {
    jsonrpc: JSONRPC_VERSION,
    id,
    error: { code, message },
  };
}

/** Serialize and send a JSON-RPC message over the socket. */
function send(socket: WebSocket, message: JsonRpcResponse | JsonRpcError): void {
  socket.send(JSON.stringify(message));
}
