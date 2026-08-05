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
import { ComponentRegistry } from "./registry";

/** Shared component registry for all connections (global bind state). */
const registry = new ComponentRegistry();

import type {
  Result,
  Parameter,
} from "@openrois/interfaces";

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
}

/** A running mock engine handle. */
export interface MockEngine {
  /** The underlying ws WebSocketServer. */
  readonly wss: WebSocketServer;
  /** The actual bound port, resolved even when port 0 was requested. */
  readonly port: number;
  /** Stop the server and close all connections. Resolves once closed. */
  close(): Promise<void>;
}

/**
 * Start a mock engine and resolve once it is listening.
 *
 * The returned promise resolves after the "listening" event so the caller can
 * read the actual bound port, which matters when port 0 is used to request an
 * ephemeral port.
 */
export function createMockEngine(
  options: MockEngineOptions = {},
): Promise<MockEngine> {
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
 * data. Handles the full Command interface (search, bind, bind_any, release,
 * get_parameter, set_parameter, execute, get_command_result), the Query
 * interface (query), and the Event interface (subscribe, unsubscribe,
 * get_event_detail) against an in-memory component registry. Every other
 * method is reported as not found.
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
    case "rois.system.get_error_detail":
      send(socket, errorDetailResponse(request.id, request.params));
      return;
      
    // Command interface

    // case "rois.command.search":
    //   send(socket, searchResponse(request.id, request.params));
    //   return;

    // case "rois.command.bind":
    //   send(socket, bindResponse(request.id, request.params));
    //   return;
    case "rois.command.bind_any":
      send(socket, bindAnyResponse(request.id, request.params));
      return;
    // case "rois.command.release":
    //   send(socket, releaseResponse(request.id, request.params));
    //   return;
    // case "rois.command.get_parameter":
    //   send(socket, getParameterResponse(request.id, request.params));
    //   return;
    // case "rois.command.set_parameter":
    //   send(socket, setParameterResponse(request.id, request.params));
    //   return;
    case "rois.command.execute":
      send(socket, executeResponse(request.id, request.params));
      return;
    case "rois.command.get_command_result":
      send(socket, getCommandResultResponse(request.id, request.params));
      return;

    // Query interface
    case "rois.query.query":
      send(socket, queryResponse(request.id, request.params));
      return;

    // Event interface
    case "rois.event.subscribe":
      send(socket, subscribeResponse(request.id, request.params));
      return;
    case "rois.event.unsubscribe":
      send(socket, unsubscribeResponse(request.id, request.params));
      return;
    case "rois.event.get_event_detail":
      send(socket, getEventDetailResponse(request.id, request.params));
      return;

    case "rois.command.search": {
      const params = namedParams(request);
      send(socket, resultResponse(request.id, {
        return_code: "OK",
        component_ref_list: registry.search(typeof params.condition === "string" ? params.condition : ""),
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
      const { returnCode, parameters } = registry.getParameter(ref);
      send(socket, resultResponse(request.id, {
        return_code: returnCode,
        parameters,
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

// ---------------------------------------------------------------------------
// Canned HRI Engine Profile
// ---------------------------------------------------------------------------

/**
 * Canned error details keyed by error_id.
 *
 * The mock engine recognizes a small set of known error IDs and returns
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

// ---------------------------------------------------------------------------
// Component registry
// ---------------------------------------------------------------------------

/**
 * A registered component in the mock gateway.
 *
 * Each component has a ref, a human-readable name, and a parameter store
 * (name -> Parameter) that set_parameter updates and get_parameter reads.
 */
interface MockComponent {
  /** The component_ref identifier (e.g. "PersonDetection_0"). */
  ref: string;
  /** Human-readable component name. */
  name: string;
  /** Current parameter values, keyed by parameter name. */
  parameters: Map<string, Parameter>;
}

/**
 * The in-memory component registry.
 *
 * Pre-populated with three components matching the canned engine profile:
 * PersonDetection_0, Navigation_0, and SystemInformation_0. Each starts with
 * a set of default parameters.
 */
const COMPONENT_REGISTRY: Map<string, MockComponent> = createComponentRegistry();

/**
 * Create the initial component registry with default parameters.
 */
function createComponentRegistry(): Map<string, MockComponent> {
  const registry = new Map<string, MockComponent>();

  registry.set("PersonDetection_0", {
    ref: "PersonDetection_0",
    name: "PersonDetection",
    parameters: new Map<string, Parameter>([
      ["confidence_threshold", {
        name: "confidence_threshold",
        data_type_ref: "float",
        value: "0.5",
      }],
      ["model_name", {
        name: "model_name",
        data_type_ref: "string",
        value: "yolov8n",
      }],
    ]),
  });

  registry.set("Navigation_0", {
    ref: "Navigation_0",
    name: "Navigation",
    parameters: new Map<string, Parameter>([
      ["target_positions", {
        name: "target_positions",
        data_type_ref: "string[]",
        value: "[]",
      }],
      ["time_limit", {
        name: "time_limit",
        data_type_ref: "int",
        value: "30",
      }],
      ["routing_policy", {
        name: "routing_policy",
        data_type_ref: "string",
        value: "time",
      }],
    ]),
  });

  registry.set("SystemInformation_0", {
    ref: "SystemInformation_0",
    name: "SystemInformation",
    parameters: new Map<string, Parameter>([
      ["robot_position", {
        name: "robot_position",
        data_type_ref: "string",
        value: "0.0,0.0,0.0",
      }],
      ["battery_level", {
        name: "battery_level",
        data_type_ref: "int",
        value: "85",
      }],
    ]),
  });

  return registry;
}

/**
 * Extract a string param from the JSON-RPC params object.
 */
function paramStr(params: unknown, key: string): string {
  if (typeof params === "object" && params !== null && key in params) {
    return String((params as Record<string, unknown>)[key]);
  }
  return "";
}

/**
 * Extract an array-of-strings param from the JSON-RPC params object.
 */
function paramStrArray(params: unknown, key: string): string[] {
  if (typeof params === "object" && params !== null && key in params) {
    const val = (params as Record<string, unknown>)[key];
    if (Array.isArray(val)) {
      return val.map((v) => String(v));
    }
  }
  return [];
}

// ---------------------------------------------------------------------------
// Response builders for Command operations
// ---------------------------------------------------------------------------

/**
 * Build a search (discover) response.
 *
 * The condition filter is accepted but not evaluated — the mock always
 * returns all registered component_refs.
 */
function searchResponse(id: JsonRpcId, _params: unknown): JsonRpcResponse {
  const componentRefList = Array.from(COMPONENT_REGISTRY.keys());
  return {
    jsonrpc: JSONRPC_VERSION,
    id,
    result: {
      return_code: "OK",
      component_ref_list: componentRefList,
    },
  };
}

/**
 * Build a bind response.
 *
 * Returns OK if the component exists, UNSUPPORTED if it does not.
 */
function bindResponse(id: JsonRpcId, params: unknown): JsonRpcResponse {
  const componentRef = paramStr(params, "component_ref");

  if (!COMPONENT_REGISTRY.has(componentRef)) {
    return {
      jsonrpc: JSONRPC_VERSION,
      id,
      result: { return_code: "UNSUPPORTED" },
    };
  }

  return {
    jsonrpc: JSONRPC_VERSION,
    id,
    result: { return_code: "OK" },
  };
}

/**
 * Build a release response.
 *
 * Returns OK if the component exists, UNSUPPORTED if it does not.
 */
function releaseResponse(id: JsonRpcId, params: unknown): JsonRpcResponse {
  const componentRef = paramStr(params, "component_ref");

  if (!COMPONENT_REGISTRY.has(componentRef)) {
    return {
      jsonrpc: JSONRPC_VERSION,
      id,
      result: { return_code: "UNSUPPORTED" },
    };
  }

  return {
    jsonrpc: JSONRPC_VERSION,
    id,
    result: { return_code: "OK" },
  };
}

/**
 * Build a get_parameter response.
 *
 * If `names` is provided, only those parameters are returned. If `names` is
 * empty or omitted, all parameters for the component are returned.
 * Returns UNSUPPORTED if the component does not exist.
 */
function getParameterResponse(id: JsonRpcId, params: unknown): JsonRpcResponse {
  const componentRef = paramStr(params, "component_ref");
  const names = paramStrArray(params, "names");

  const component = COMPONENT_REGISTRY.get(componentRef);
  if (!component) {
    return {
      jsonrpc: JSONRPC_VERSION,
      id,
      result: { return_code: "UNSUPPORTED", results: [] },
    };
  }

  let values: Parameter[];
  if (names.length > 0) {
    values = names
      .map((n) => component.parameters.get(n))
      .filter((p): p is Parameter => p !== undefined);
  } else {
    values = Array.from(component.parameters.values());
  }

  // Convert Parameter[] to Result[] (same shape: name, data_type_ref, value).
  const results: Result[] = values.map((p) => ({
    name: p.name,
    data_type_ref: p.data_type_ref,
    value: p.value,
  }));

  return {
    jsonrpc: JSONRPC_VERSION,
    id,
    result: {
      return_code: "OK",
      results,
    },
  };
}

/**
 * Build a set_parameter response.
 *
 * Updates the component's parameter store with the provided values.
 * Returns OK with an empty command_id on success, UNSUPPORTED if the
 * component does not exist, BAD_PARAMETER if a parameter has no name.
 */
function setParameterResponse(id: JsonRpcId, params: unknown): JsonRpcResponse {
  const componentRef = paramStr(params, "component_ref");

  const component = COMPONENT_REGISTRY.get(componentRef);
  if (!component) {
    return {
      jsonrpc: JSONRPC_VERSION,
      id,
      result: { return_code: "UNSUPPORTED", command_id: "" },
    };
  }

  // Extract the parameters array from the request.
  let rawParameters: unknown;
  if (typeof params === "object" && params !== null && "parameters" in params) {
    rawParameters = (params as Record<string, unknown>).parameters;
  }

  if (!Array.isArray(rawParameters)) {
    return {
      jsonrpc: JSONRPC_VERSION,
      id,
      result: { return_code: "BAD_PARAMETER", command_id: "" },
    };
  }

  // Update the component's parameter store.
  for (const raw of rawParameters) {
    if (typeof raw !== "object" || raw === null || !("name" in raw)) {
      return {
        jsonrpc: JSONRPC_VERSION,
        id,
        result: { return_code: "BAD_PARAMETER", command_id: "" },
      };
    }

    const param = raw as Parameter;
    component.parameters.set(param.name, {
      name: param.name,
      data_type_ref: param.data_type_ref ?? "string",
      value: param.value ?? "",
    });
  }

  return {
    jsonrpc: JSONRPC_VERSION,
    id,
    result: {
      return_code: "OK",
      command_id: "",
    },
  };
}

/**
 * Build a bind_any response.
 *
 * The condition filter is accepted but not evaluated — the mock returns the
 * first registered component. If no components are registered, returns
 * OUT_OF_RESOURCES.
 */
function bindAnyResponse(id: JsonRpcId, _params: unknown): JsonRpcResponse {
  const firstRef = COMPONENT_REGISTRY.keys().next();
  if (firstRef.done) {
    return {
      jsonrpc: JSONRPC_VERSION,
      id,
      result: { return_code: "OUT_OF_RESOURCES", component_ref: "" },
    };
  }

  return {
    jsonrpc: JSONRPC_VERSION,
    id,
    result: {
      return_code: "OK",
      component_ref: firstRef.value,
    },
  };
}

/**
 * Build an execute response.
 *
 * Returns OK with a generated command_id. The mock does not actually execute
 * anything — it acknowledges the command immediately. The caller should listen
 * for "rois.command.completed" notifications (not yet implemented in the mock).
 * Returns UNSUPPORTED if the component does not exist.
 */
function executeResponse(id: JsonRpcId, params: unknown): JsonRpcResponse {
  const componentRef = paramStr(params, "component_ref");

  if (!COMPONENT_REGISTRY.has(componentRef)) {
    return {
      jsonrpc: JSONRPC_VERSION,
      id,
      result: { return_code: "UNSUPPORTED", command_id: "" },
    };
  }

  // Generate a simple command_id based on a counter.
  const commandId = `cmd-${Date.now()}-${Math.floor(Math.random() * 10000)}`;

  return {
    jsonrpc: JSONRPC_VERSION,
    id,
    result: {
      return_code: "OK",
      command_id: commandId,
      results: [],
    },
  };
}

/**
 * Build a get_command_result response.
 *
 * The mock does not track command execution, so it returns an empty results
 * array with return_code OK for any command_id.
 */
function getCommandResultResponse(id: JsonRpcId, _params: unknown): JsonRpcResponse {
  return {
    jsonrpc: JSONRPC_VERSION,
    id,
    result: {
      return_code: "OK",
      results: [],
    },
  };
}

// ---------------------------------------------------------------------------
// Response builders for Query operations
// ---------------------------------------------------------------------------

/**
 * Canned query results for SystemInformation_0.
 *
 * The mock gateway answers "robot_position" and "engine_status" queries for
 * the SystemInformation component. Other query types on SystemInformation
 * return UNSUPPORTED. Queries on unknown components return UNSUPPORTED.
 */
const CANNED_QUERY_RESULTS: Record<string, Record<string, Result[]>> = {
  SystemInformation_0: {
    robot_position: [
      { name: "position", data_type_ref: "string", value: "1.5,2.0,0.0" },
      { name: "orientation", data_type_ref: "string", value: "0.0,0.0,0.0,1.0" },
      { name: "timestamp", data_type_ref: "DateTime", value: "2026-07-08T12:00:00Z" },
    ],
    engine_status: [
      { name: "status", data_type_ref: "ComponentStatus", value: "READY" },
      { name: "uptime", data_type_ref: "int", value: "3600" },
    ],
    component_status: [
      { name: "status", data_type_ref: "ComponentStatus", value: "READY" },
    ],
  },
  PersonDetection_0: {
    component_status: [
      { name: "status", data_type_ref: "ComponentStatus", value: "READY" },
    ],
  },
  Navigation_0: {
    component_status: [
      { name: "status", data_type_ref: "ComponentStatus", value: "BUSY" },
    ],
  },
};

/**
 * Build a query response.
 *
 * Looks up the component_ref and query_type in the canned query results table.
 * Returns UNSUPPORTED if the component or query type is not recognized.
 */
function queryResponse(id: JsonRpcId, params: unknown): JsonRpcResponse {
  const componentRef = paramStr(params, "component_ref");
  const queryType = paramStr(params, "query_type");

  const componentQueries = CANNED_QUERY_RESULTS[componentRef];
  if (!componentQueries) {
    return {
      jsonrpc: JSONRPC_VERSION,
      id,
      result: { return_code: "UNSUPPORTED", results: [] },
    };
  }

  const results = componentQueries[queryType];
  if (!results) {
    return {
      jsonrpc: JSONRPC_VERSION,
      id,
      result: { return_code: "UNSUPPORTED", results: [] },
    };
  }

  return {
    jsonrpc: JSONRPC_VERSION,
    id,
    result: {
      return_code: "OK",
      results,
    },
  };
}

// ---------------------------------------------------------------------------
// Response builders for Event operations
// ---------------------------------------------------------------------------

/**
 * In-memory subscription registry.
 *
 * Maps subscribe_id to the subscription details (component_ref, event_type).
 * Used to track active subscriptions and support unsubscribe.
 */
const SUBSCRIPTION_REGISTRY: Map<string, { componentRef: string; eventType: string }> =
  new Map();

/** Counter for generating unique subscribe_ids. */
let subscriptionCounter = 0;

/**
 * Build a subscribe response.
 *
 * Registers the subscription in the in-memory registry and returns a unique
 * subscribe_id. Returns UNSUPPORTED if the component does not exist.
 */
function subscribeResponse(id: JsonRpcId, params: unknown): JsonRpcResponse {
  const componentRef = paramStr(params, "component_ref");
  const eventType = paramStr(params, "event_type");

  if (!COMPONENT_REGISTRY.has(componentRef)) {
    return {
      jsonrpc: JSONRPC_VERSION,
      id,
      result: { return_code: "UNSUPPORTED", subscribe_id: "" },
    };
  }

  const subscribeId = `sub-${++subscriptionCounter}`;
  SUBSCRIPTION_REGISTRY.set(subscribeId, { componentRef, eventType });

  return {
    jsonrpc: JSONRPC_VERSION,
    id,
    result: {
      return_code: "OK",
      subscribe_id: subscribeId,
    },
  };
}

/**
 * Build an unsubscribe response.
 *
 * Removes the subscription from the registry. Per the RoIS spec, duplicate
 * unsubscribe requests are silently ignored (return OK).
 */
function unsubscribeResponse(id: JsonRpcId, params: unknown): JsonRpcResponse {
  const subscribeId = paramStr(params, "subscribe_id");
  SUBSCRIPTION_REGISTRY.delete(subscribeId);

  return {
    jsonrpc: JSONRPC_VERSION,
    id,
    result: { return_code: "OK" },
  };
}

/**
 * Canned event details keyed by event_id.
 *
 * The mock gateway recognizes a small set of known event IDs and returns
 * descriptive Result arrays. Unknown event IDs return an empty result list
 * with return_code OK.
 */
const CANNED_EVENT_DETAILS: Record<string, Result[]> = {
  "evt-001": [
    { name: "number", data_type_ref: "int", value: "3" },
    { name: "timestamp", data_type_ref: "DateTime", value: "2026-07-08T12:00:00Z" },
  ],
  "evt-002": [
    { name: "number", data_type_ref: "int", value: "1" },
    { name: "timestamp", data_type_ref: "DateTime", value: "2026-07-08T12:01:00Z" },
  ],
};

/**
 * Build a get_event_detail response.
 *
 * Looks up the event_id in the canned details table. Unknown IDs return an
 * empty results array with return_code OK.
 */
function getEventDetailResponse(id: JsonRpcId, params: unknown): JsonRpcResponse {
  const eventId = paramStr(params, "event_id");
  const results = CANNED_EVENT_DETAILS[eventId] ?? [];

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
