/**
 * The mock RoIS engine's WebSocket server: JSON-RPC 2.0 over WebSocket.
 *
 * Each message goes through the same checks a catalog engine runs:
 *
 *   - JSON that does not parse          → PARSE_ERROR, with a null id
 *   - an object that is not a request   → INVALID_REQUEST
 *   - a method outside the catalog      → METHOD_NOT_FOUND (rois.stream.* included)
 *   - params that fail the catalog model → INVALID_PARAMS, with the issues as data
 *
 * A valid request goes to MockEngineCore (engine.ts), and its result is
 * validated against the catalog's result model before it is sent. A RoIS
 * failure travels as a normal result whose return_code is not OK. A message
 * without an id is a notification from the client and gets no reply, as
 * JSON-RPC 2.0 requires.
 *
 * The JSON-RPC envelope schemas come from the SDK (@openrois/sdk/jsonrpc) and
 * the method catalog from @openrois/interfaces, so the mock and the clients
 * share one wire contract.
 */

import { WebSocketServer } from "ws";
import type { RawData, WebSocket } from "ws";
import { RoISMethodSchemas } from "@openrois/interfaces";
import type { RoISMethod } from "@openrois/interfaces";
import {
  JSONRPC_VERSION,
  JsonRpcErrorCode,
  JsonRpcRequestSchema,
} from "@openrois/sdk/jsonrpc";
import type { JsonRpcError, JsonRpcId, JsonRpcResponse } from "@openrois/sdk/jsonrpc";
import {
  DEFAULT_TIMING,
  MockEngineCore,
  type MethodParams,
  type MockEngineTiming,
  type Session,
} from "./engine";

/** Default listening port when none is supplied. */
const DEFAULT_PORT = 8765;
/** Default host: loopback only, so the mock is not exposed on the network. */
const DEFAULT_HOST = "127.0.0.1";

/** Options for {@link createMockEngine}. */
export interface MockEngineOptions {
  /**
   * TCP port to listen on. Use 0 to bind an ephemeral port chosen by the OS,
   * which is what tests do to avoid collisions. Defaults to 8765.
   */
  port?: number;
  /** Host interface to bind. Defaults to 127.0.0.1 (loopback only). */
  host?: string;
  /** How long simulated work takes. Tests shorten it. */
  timing?: Partial<MockEngineTiming>;
}

/** A running mock engine handle. */
export interface MockEngine {
  /** The underlying ws WebSocketServer. */
  readonly wss: WebSocketServer;
  /** The actual bound port, resolved even when port 0 was requested. */
  readonly port: number;
  /** Stop the engine and close every connection. Resolves once closed. */
  close(): Promise<void>;
}

/**
 * Start a mock engine and resolve once it is listening.
 *
 * Every engine has its own components, bindings, commands and subscriptions,
 * so several engines can run in one process.
 */
export function createMockEngine(options: MockEngineOptions = {}): Promise<MockEngine> {
  const port = options.port ?? DEFAULT_PORT;
  const host = options.host ?? DEFAULT_HOST;
  const core = new MockEngineCore({ ...DEFAULT_TIMING, ...options.timing });
  let nextSession = 1;

  return new Promise((resolve, reject) => {
    const wss = new WebSocketServer({ port, host });

    wss.on("connection", (socket: WebSocket) => {
      const session: Session = {
        id: `session-${nextSession++}`,
        notify: (method, params) => {
          if (socket.readyState === socket.OPEN) {
            socket.send(JSON.stringify({ jsonrpc: JSONRPC_VERSION, method, params }));
          }
        },
      };
      socket.on("message", (data: RawData) => handleMessage(core, session, socket, data));
      socket.on("close", () => core.closeSession(session));
    });

    // Reject only for startup failures, before the server is listening.
    wss.once("error", reject);

    wss.once("listening", () => {
      wss.off("error", reject);
      const address = wss.address();
      const boundPort = typeof address === "object" && address !== null ? address.port : port;
      resolve({
        wss,
        port: boundPort,
        close: () =>
          new Promise<void>((resolveClose, rejectClose) => {
            core.close();
            for (const client of wss.clients) {
              client.terminate();
            }
            wss.close((err) => (err ? rejectClose(err) : resolveClose()));
          }),
      });
    });
  });
}

/** Parse, validate, dispatch and answer one message. */
function handleMessage(core: MockEngineCore, session: Session, socket: WebSocket, data: RawData): void {
  let payload: unknown;
  try {
    payload = JSON.parse(data.toString());
  } catch {
    send(socket, errorMessage(null, JsonRpcErrorCode.PARSE_ERROR, "Parse error: invalid JSON"));
    return;
  }

  if (isNotification(payload)) {
    return;
  }

  const request = JsonRpcRequestSchema.safeParse(payload);
  if (!request.success) {
    send(
      socket,
      errorMessage(
        extractId(payload),
        JsonRpcErrorCode.INVALID_REQUEST,
        "Invalid Request: not a valid JSON-RPC 2.0 request",
      ),
    );
    return;
  }
  const { id, method, params } = request.data;

  if (!isCatalogMethod(method)) {
    send(socket, errorMessage(id, JsonRpcErrorCode.METHOD_NOT_FOUND, `Method not found: ${method}`));
    return;
  }

  const schemas = RoISMethodSchemas[method];
  const parsed = schemas.params.safeParse(params ?? {});
  if (!parsed.success) {
    const issues = parsed.error.issues.map((issue) => ({
      path: issue.path.join("."),
      message: issue.message,
    }));
    send(
      socket,
      errorMessage(id, JsonRpcErrorCode.INVALID_PARAMS, `Invalid params for ${method}`, issues),
    );
    return;
  }

  let result: unknown;
  try {
    const reply = core.handle(session, method, parsed.data as MethodParams<RoISMethod>);
    result = schemas.result.parse(reply);
  } catch (error) {
    const detail = error instanceof Error ? error.message : String(error);
    send(socket, errorMessage(id, JsonRpcErrorCode.INTERNAL_ERROR, `Internal error: ${detail}`));
    return;
  }
  send(socket, resultMessage(id, result));
}

function isCatalogMethod(method: string): method is RoISMethod {
  return Object.prototype.hasOwnProperty.call(RoISMethodSchemas, method);
}

/** A JSON-RPC notification: an object with a method and no id. */
function isNotification(payload: unknown): boolean {
  return (
    typeof payload === "object" &&
    payload !== null &&
    !Array.isArray(payload) &&
    "method" in payload &&
    !("id" in payload)
  );
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

function resultMessage(id: JsonRpcId, result: unknown): JsonRpcResponse {
  return { jsonrpc: JSONRPC_VERSION, id, result };
}

function errorMessage(id: JsonRpcId, code: number, message: string, data?: unknown): JsonRpcError {
  return {
    jsonrpc: JSONRPC_VERSION,
    id,
    error: { code, message, ...(data !== undefined ? { data } : {}) },
  };
}

function send(socket: WebSocket, message: JsonRpcResponse | JsonRpcError): void {
  socket.send(JSON.stringify(message));
}
