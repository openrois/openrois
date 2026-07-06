/**
 * Mock RoIS gateway: a JSON-RPC 2.0 WebSocket test double.
 *
 * Accepts WebSocket connections, parses incoming JSON-RPC 2.0 messages, and
 * answers the System interface methods (connect, disconnect, get_profile,
 * get_error_detail) and the full Command interface (search, bind, bind_any,
 * release, set_parameter, get_parameter, execute, get_command_result) against
 * an in-memory component registry. Any other method returns a JSON-RPC
 * "method not found" error, and malformed input returns the appropriate parse
 * or invalid-request error.
 *
 * The message schemas are reused from the SDK (@openrois/sdk/jsonrpc) so the
 * mock and the real client stay on a single wire contract. Later milestones
 * add mock components, events, queries, and async command completion (see
 * project-outline.md Weeks 3 and beyond).
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
import { ComponentRegistry } from "./registry";
import type { Parameter } from "@openrois/interfaces";

/** Shared component registry for all connections (global bind state). */
const registry = new ComponentRegistry();

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
 * Handles the System interface lifecycle methods (connect, disconnect) and
 * the two System query operations (get_profile, get_error_detail) with canned
 * data. Handles the full Command interface (search, bind, bind_any, release,
 * get_parameter, set_parameter, execute, get_command_result) against the
 * in-memory component registry. Every other method is reported as not found.
 */
function dispatch(socket: WebSocket, request: JsonRpcRequest): void {
  switch (request.method) {
    case "rois.system.connect":
    case "rois.system.disconnect":
      send(socket, okResponse(request.id));
      return;

    case "rois.system.get_profile":
      send(socket, resultResponse(request.id, {
        return_code: "OK",
        profile: registry.getProfile(),
      }));
      return;

    case "rois.system.get_error_detail": {
      const params = namedParams(request);
      const errorId = asString(params.error_id);
      const { returnCode, results } = registry.getErrorDetail(errorId);
      send(socket, resultResponse(request.id, {
        return_code: returnCode,
        results,
      }));
      return;
    }

    case "rois.command.search": {
      const params = namedParams(request);
      send(socket, resultResponse(request.id, {
        return_code: "OK",
        component_ref_list: registry.search(
          typeof params.condition === "string" ? params.condition : "",
        ),
      }));
      return;
    }

    case "rois.command.bind": {
      const params = namedParams(request);
      const ref = asString(params.component_ref);
      send(socket, resultResponse(request.id, {
        return_code: registry.bind(ref),
      }));
      return;
    }

    case "rois.command.bind_any": {
      const params = namedParams(request);
      const condition =
        typeof params.condition === "string" ? params.condition : "";
      const { returnCode, componentRef } = registry.bindAny(condition);
      send(socket, resultResponse(request.id, {
        return_code: returnCode,
        component_ref: componentRef,
      }));
      return;
    }

    case "rois.command.release": {
      const params = namedParams(request);
      const ref = asString(params.component_ref);
      send(socket, resultResponse(request.id, {
        return_code: registry.release(ref),
      }));
      return;
    }

    case "rois.command.set_parameter": {
      const params = namedParams(request);
      const ref = asString(params.component_ref);
      // Validate that parameters is an array before passing to the registry.
      // The registry merges by name, so a non-array is a protocol error.
      if (!Array.isArray(params.parameters)) {
        send(socket, resultResponse(request.id, {
          return_code: "BAD_PARAMETER",
          command_id: "",
        }));
        return;
      }
      const parameters = asParameterArray(params.parameters);
      send(socket, resultResponse(request.id, {
        return_code: registry.setParameter(ref, parameters),
        command_id: "",
      }));
      return;
    }

    case "rois.command.get_parameter": {
      const params = namedParams(request);
      const ref = asString(params.component_ref);
      const names = asStringArray(params.names);
      const { returnCode, parameters } = registry.getParameter(ref, names);
      send(socket, resultResponse(request.id, {
        return_code: returnCode,
        parameters,
      }));
      return;
    }

    case "rois.command.execute": {
      const params = namedParams(request);
      const ref = asString(params.component_ref);
      const { returnCode, commandId } = registry.execute(ref);
      send(socket, resultResponse(request.id, {
        return_code: returnCode,
        command_id: commandId,
      }));
      return;
    }

    case "rois.command.get_command_result": {
      const params = namedParams(request);
      const commandId = asString(params.command_id);
      const { returnCode, results } = registry.getCommandResult(commandId);
      send(socket, resultResponse(request.id, {
        return_code: returnCode,
        results,
      }));
      return;
    }

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

/** Build a success response with an arbitrary result object. */
function resultResponse(id: JsonRpcId, result: Record<string, unknown>): JsonRpcResponse {
  return {
    jsonrpc: JSONRPC_VERSION,
    id,
    result,
  };
}

/**
 * Extract the named-params object from a validated request.
 *
 * The JSON-RPC spec allows array (positional) params, but OpenRoIS always uses
 * objects. If params is missing or an array, return an empty record so callers
 * get undefined for every key (which they handle via asString/asParameterArray).
 */
function namedParams(request: JsonRpcRequest): Record<string, unknown> {
  if (request.params && !Array.isArray(request.params)) {
    return request.params as Record<string, unknown>;
  }
  return {};
}

/** Safely coerce an unknown value to string, defaulting to empty string. */
function asString(value: unknown): string {
  return typeof value === "string" ? value : "";
}

/**
 * Safely coerce an unknown value to an array of strings, defaulting to an
 * empty array. Non-string elements are coerced to string.
 */
function asStringArray(value: unknown): string[] {
  if (!Array.isArray(value)) {
    return [];
  }
  return value.map((v) => String(v));
}

/**
 * Safely coerce an unknown value to a Parameter array.
 *
 * Performs a shallow shape check (name, data_type_ref, value must be strings).
 * Values that do not match are dropped. This keeps the mock lenient: it does
 * not reject malformed params with a JSON-RPC error, it just ignores bad
 * entries. The real gateway would validate strictly.
 */
function asParameterArray(value: unknown): Parameter[] {
  if (!Array.isArray(value)) {
    return [];
  }
  return value.filter(isParameter) as Parameter[];
}

/** Runtime guard for the Parameter shape: { name, data_type_ref, value }. */
function isParameter(v: unknown): v is Parameter {
  if (typeof v !== "object" || v === null) return false;
  const obj = v as Record<string, unknown>;
  return (
    typeof obj.name === "string" &&
    typeof obj.data_type_ref === "string" &&
    typeof obj.value === "string"
  );
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
