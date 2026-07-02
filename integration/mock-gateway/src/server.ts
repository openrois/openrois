/**
 * Mock RoIS gateway: a JSON-RPC 2.0 WebSocket test double.
 *
 * Accepts WebSocket connections, parses incoming JSON-RPC 2.0 messages, and
 * answers the System interface methods: connect, disconnect (canned OK),
 * get_profile (canned HRI_Engine_Profile), and get_error_detail (canned
 * Result[] keyed by error_id). Any other method returns a JSON-RPC "method
 * not found" error, and malformed input returns the appropriate parse or
 * invalid-request error.
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

import type { 
  HRIEngineProfileType, 
  Result 
} from "@openrois/interfaces";

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
 * Answers the System interface lifecycle methods (connect, disconnect) and
 * the two System query operations (get_profile, get_error_detail) with canned
 * data. Every other method is reported as not found.
 */
function dispatch(socket: WebSocket, request: JsonRpcRequest): void {
  switch (request.method) {
    case "rois.system.connect":
    case "rois.system.disconnect":
      send(socket, okResponse(request.id));
      return;

    //New Additions
    case "rois.system.get_profile":
      send(socket, profileResponse(request.id, request.params));
      return;
    case "rois.system.get_error_detail":
      send(socket, errorDetailResponse(request.id, request.params));
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

// ---------------------------------------------------------------------------
// Canned HRI Engine Profile
// ---------------------------------------------------------------------------

/**
 * A canned HRI_Engine_Profile returned by rois.system.get_profile.
 *
 * Describes a mock gateway hosting three components (PersonDetection,
 * Navigation, SystemInformation) with a nested perception sub-engine. The
 * condition filter is accepted but not evaluated — the mock always returns
 * the full profile.
 */
const CANNED_ENGINE_PROFILE: HRIEngineProfileType = {
  identifier: {
    authority: "OMG",
    code: "MockGateway",
    codebook_ref: "",
    version: "2.0",
  },
  sub_profiles: [
    {
      identifier: {
        authority: "OMG",
        code: "PerceptionSubEngine",
        codebook_ref: "",
        version: "2.0",
      },
      component_ids: ["PersonDetection_0"],
    },
  ],
  component_ids: ["PersonDetection_0", "Navigation_0", "SystemInformation_0"],
  parameter_profiles: [],
};

/**
 * Canned error details keyed by error_id.
 *
 * The mock gateway recognizes a small set of known error IDs and returns
 * descriptive Result arrays. Unknown error IDs return an empty result list
 * with return_code OK (the error was found but has no extra detail).
 */
const CANNED_ERROR_DETAILS: Record<string, Result[]> = {
  "err-001": [
    {
      name: "component_ref",
      data_type_ref: "string",
      value: "robot-a1/Navigation",
    },
    {
      name: "description",
      data_type_ref: "string",
      value: "Navigation action timed out after 30s",
    },
  ],
  "err-002": [
    {
      name: "component_ref",
      data_type_ref: "string",
      value: "PersonDetection_0",
    },
    {
      name: "description",
      data_type_ref: "string",
      value: "Component internal error: model failed to load",
    },
  ],
};

// ---------------------------------------------------------------------------
// Response builders for System query operations
// ---------------------------------------------------------------------------

/**
 * Build a get_profile success response.
 *
 * The condition parameter is accepted but not evaluated — the mock always
 * returns the full canned profile.
 */
function profileResponse(id: JsonRpcId, _params: unknown): JsonRpcResponse {
  return {
    jsonrpc: JSONRPC_VERSION,
    id,
    result: {
      return_code: "OK",
      profile: CANNED_ENGINE_PROFILE,
    },
  };
}

/**
 * Build a get_error_detail success response.
 *
 * Looks up the error_id in the canned details table. Unknown IDs return an
 * empty results array with return_code OK.
 */
function errorDetailResponse(id: JsonRpcId, params: unknown): JsonRpcResponse {
  const errorId =
    typeof params === "object" && params !== null && "error_id" in params
      ? String((params as { error_id: unknown }).error_id)
      : "";

  const results = CANNED_ERROR_DETAILS[errorId] ?? [];

  return {
    jsonrpc: JSONRPC_VERSION,
    id,
    result: {
      return_code: "OK",
      results,
    },
  };
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
