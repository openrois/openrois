/**
 * Unit tests for jsonrpc.ts -- JSON-RPC 2.0 message type validation.
 *
 * Coverage goals (fill in assertions as you implement):
 *   - Valid messages parse without error.
 *   - Invalid / malformed messages are rejected by Zod.
 *   - Round-trip: serialize to JSON, parse back, schema still accepts it.
 *   - Edge cases from the JSON-RPC 2.0 spec (null id, missing params, etc.)
 *
 * All test fixtures use field names from the canonical JSON Schema files in
 * interfaces/schema/ so the tests validate real RoIS payloads, not made-up ones.
 *
 * Run with: npx vitest run
 */

import { describe, it, expect } from "vitest";
import {
  JsonRpcRequestSchema,
  JsonRpcResponseSchema,
  JsonRpcErrorSchema,
  JsonRpcNotificationSchema,
  JsonRpcErrorObjectSchema,
  JsonRpcErrorCode,
  JSONRPC_VERSION,
  RoISNamespace,
  type JsonRpcRequest,
  type JsonRpcResponse,
  type JsonRpcError,
  type JsonRpcNotification,
  type RoISMethod,
} from "../src/jsonrpc";

// ---------------------------------------------------------------------------
// Fixtures -- minimal valid objects using real schema field names
// ---------------------------------------------------------------------------

// Request: rois.command.search -> params matches DiscoverRequest.schema.json
// DiscoverRequest has: { condition: string (default "") }
const searchRequest: JsonRpcRequest = {
  jsonrpc: "2.0",
  id: "req-001",
  method: "rois.command.search",
  params: { condition: "" },
};

// Request: rois.query.query -> params matches QueryRequest.schema.json
// QueryRequest has: { component_ref, query_type, condition? }
const queryRequest: JsonRpcRequest = {
  jsonrpc: "2.0",
  id: "req-002",
  method: "rois.query.query",
  params: {
    component_ref: "PersonDetection_0",
    query_type: "component_status",
  },
};

// Request: rois.command.execute -> params matches CommandRequest.schema.json
// CommandRequest has: { component_ref, command_type, command_id, arguments?, parameters?, command_unit_sequence? }
const executeRequest: JsonRpcRequest = {
  jsonrpc: "2.0",
  id: "req-003",
  method: "rois.command.execute",
  params: {
    component_ref: "Navigation_0",
    command_type: "set_parameter",
    command_id: "cmd-nav-001",
    parameters: [
      { name: "target_positions", data_type_ref: "string[]", value: '["3.0,1.5,0.0"]' },
      { name: "time_limit", data_type_ref: "int", value: "30" },
      { name: "routing_policy", data_type_ref: "string", value: "time" },
    ],
  },
};

// Request: rois.event.subscribe -> params matches SubscribeRequest.schema.json
// SubscribeRequest has: { component_ref, event_type, condition? }
const subscribeRequest: JsonRpcRequest = {
  jsonrpc: "2.0",
  id: "req-004",
  method: "rois.event.subscribe",
  params: {
    component_ref: "PersonDetection_0",
    event_type: "person_detected",
    condition: "",
  },
};

// Response: result matches DiscoverResponse.schema.json
// DiscoverResponse has: { return_code (default "OK"), component_ref_list }
const searchResponse: JsonRpcResponse = {
  jsonrpc: "2.0",
  id: "req-001",
  result: {
    return_code: "OK",
    component_ref_list: ["PersonDetection_0", "Navigation_0", "SystemInformation_0"],
  },
};

// Response: result matches QueryResponse.schema.json
// QueryResponse has: { return_code, results: Result[] }
// where Result is: { name, data_type_ref, value }
const queryResponse: JsonRpcResponse = {
  jsonrpc: "2.0",
  id: "req-002",
  result: {
    return_code: "OK",
    results: [
      { name: "status", data_type_ref: "ComponentStatus", value: "READY" },
    ],
  },
};

// Response: result matches InvokeResponse.schema.json
// InvokeResponse has: { return_code, command_id, results? }
const invokeResponse: JsonRpcResponse = {
  jsonrpc: "2.0",
  id: "req-003",
  result: {
    return_code: "OK",
    command_id: "cmd-nav-001",
    results: [],
  },
};

// Response: result matches SubscribeResponse.schema.json
// SubscribeResponse has: { return_code, subscribe_id }
const subscribeResponse: JsonRpcResponse = {
  jsonrpc: "2.0",
  id: "req-004",
  result: {
    return_code: "OK",
    subscribe_id: "sub-pd-001",
  },
};

// Error response: method not found
const methodNotFoundError: JsonRpcError = {
  jsonrpc: "2.0",
  id: "req-099",
  error: {
    code: JsonRpcErrorCode.MethodNotFound,
    message: "Method not found: rois.command.fly",
  },
};

// Error response: RoIS-level bad parameter (carried in data)
const badParameterError: JsonRpcError = {
  jsonrpc: "2.0",
  id: "req-005",
  error: {
    code: JsonRpcErrorCode.InvalidParams,
    message: "Invalid component_ref",
    data: { return_code: "BAD_PARAMETER" },
  },
};

// Notification: rois.event.notify -> params matches EventEnvelope.schema.json
// EventEnvelope has: { event_id, event_type, subscribe_id?, component_ref?, expire?,
//                      payload: Result[], error_type?, completed_status?, stream_status?, component_status? }
const personDetectedNotification: JsonRpcNotification = {
  jsonrpc: "2.0",
  method: "rois.event.notify",
  params: {
    event_id: "evt-001",
    event_type: "person_detected",
    subscribe_id: "sub-pd-001",
    component_ref: "PersonDetection_0",
    payload: [
      { name: "timestamp", data_type_ref: "DateTime", value: "2026-06-25T10:30:00Z" },
      { name: "number", data_type_ref: "int", value: "2" },
    ],
  },
};

// Notification: rois.command.completed -> params matches CompletedEvent.schema.json
// CompletedEvent has: { command_id, status: CompletedStatus }
const commandCompletedNotification: JsonRpcNotification = {
  jsonrpc: "2.0",
  method: "rois.command.completed",
  params: {
    command_id: "cmd-nav-001",
    status: "OK",
  },
};

// Notification: rois.system.notify_error -> params matches NotifyErrorEvent.schema.json
// NotifyErrorEvent has: { error_id, error_type: ErrorType }
const notifyErrorNotification: JsonRpcNotification = {
  jsonrpc: "2.0",
  method: "rois.system.notify_error",
  params: {
    error_id: "err-001",
    error_type: "COMPONENT_NOT_RESPONDING",
  },
};

// ---------------------------------------------------------------------------
// JsonRpcRequest
// ---------------------------------------------------------------------------

describe("JsonRpcRequestSchema", () => {
  it("accepts a search request (DiscoverRequest params)", () => {
    const result = JsonRpcRequestSchema.safeParse(searchRequest);
    expect(result.success).toBe(true);
  });

  it("accepts a query request (QueryRequest params)", () => {
    const result = JsonRpcRequestSchema.safeParse(queryRequest);
    expect(result.success).toBe(true);
  });

  it("accepts an execute request (CommandRequest params)", () => {
    const result = JsonRpcRequestSchema.safeParse(executeRequest);
    expect(result.success).toBe(true);
  });

  it("accepts a subscribe request (SubscribeRequest params)", () => {
    const result = JsonRpcRequestSchema.safeParse(subscribeRequest);
    expect(result.success).toBe(true);
  });

  it("accepts a request with numeric id", () => {
    const result = JsonRpcRequestSchema.safeParse({ ...searchRequest, id: 42 });
    expect(result.success).toBe(true);
  });

  it("accepts a connect request with no params (params is optional)", () => {
    const result = JsonRpcRequestSchema.safeParse({
      jsonrpc: "2.0",
      id: "req-connect",
      method: "rois.system.connect",
    });
    expect(result.success).toBe(true);
  });

  it("rejects a request with wrong jsonrpc version", () => {
    const result = JsonRpcRequestSchema.safeParse({ ...searchRequest, jsonrpc: "1.0" });
    expect(result.success).toBe(false);
  });

  it("rejects a request with missing method", () => {
    const { method: _omit, ...noMethod } = searchRequest;
    const result = JsonRpcRequestSchema.safeParse(noMethod);
    expect(result.success).toBe(false);
  });

  it("rejects a request with empty-string method", () => {
    const result = JsonRpcRequestSchema.safeParse({ ...searchRequest, method: "" });
    expect(result.success).toBe(false);
  });

  it("rejects a request with missing id (would be a Notification)", () => {
    const { id: _omit, ...noId } = searchRequest;
    const result = JsonRpcRequestSchema.safeParse(noId);
    expect(result.success).toBe(false);
  });

  it("round-trips through JSON.stringify / JSON.parse", () => {
    const json = JSON.stringify(executeRequest);
    const parsed = JSON.parse(json);
    const result = JsonRpcRequestSchema.safeParse(parsed);
    expect(result.success).toBe(true);
    if (result.success) {
      expect(result.data.method).toBe("rois.command.execute");
      expect(result.data.id).toBe("req-003");
    }
  });

  it("accepts positional array params for spec compliance", () => {
    const result = JsonRpcRequestSchema.safeParse({
      jsonrpc: "2.0",
      id: "req-pos",
      method: "rois.command.search",
      params: [""],
    });
    expect(result.success).toBe(true);
  });

  it("rejects a request with unexpected extra fields (strict validation)", () => {
    const result = JsonRpcRequestSchema.safeParse({
      ...searchRequest,
      result: { return_code: "OK" }, // result does not belong on a Request
    });
    expect(result.success).toBe(false);
  });
});

// ---------------------------------------------------------------------------
// JsonRpcResponse (success)
// ---------------------------------------------------------------------------

describe("JsonRpcResponseSchema", () => {
  it("accepts a search response (DiscoverResponse result)", () => {
    const result = JsonRpcResponseSchema.safeParse(searchResponse);
    expect(result.success).toBe(true);
  });

  it("accepts a query response (QueryResponse result)", () => {
    const result = JsonRpcResponseSchema.safeParse(queryResponse);
    expect(result.success).toBe(true);
  });

  it("accepts an invoke response (InvokeResponse result)", () => {
    const result = JsonRpcResponseSchema.safeParse(invokeResponse);
    expect(result.success).toBe(true);
  });

  it("accepts a subscribe response (SubscribeResponse result)", () => {
    const result = JsonRpcResponseSchema.safeParse(subscribeResponse);
    expect(result.success).toBe(true);
  });

  it("accepts a response where result is null (some methods return nothing)", () => {
    const result = JsonRpcResponseSchema.safeParse({ ...searchResponse, result: null });
    expect(result.success).toBe(true);
  });

  it("rejects a response with wrong jsonrpc version", () => {
    const result = JsonRpcResponseSchema.safeParse({ ...searchResponse, jsonrpc: "1.0" });
    expect(result.success).toBe(false);
  });

  it("rejects a response with missing id", () => {
    const { id: _omit, ...noId } = searchResponse;
    const result = JsonRpcResponseSchema.safeParse(noId);
    expect(result.success).toBe(false);
  });

  it("round-trips through JSON.stringify / JSON.parse", () => {
    const json = JSON.stringify(searchResponse);
    const parsed = JSON.parse(json);
    const result = JsonRpcResponseSchema.safeParse(parsed);
    expect(result.success).toBe(true);
    if (result.success) {
      expect(result.data.id).toBe("req-001");
    }
  });

  it("rejects a response with unexpected extra fields (strict validation)", () => {
    const result = JsonRpcResponseSchema.safeParse({
      ...searchResponse,
      method: "rois.command.search", // method does not belong on a Response
    });
    expect(result.success).toBe(false);
  });
});

// ---------------------------------------------------------------------------
// JsonRpcError (failure response)
// ---------------------------------------------------------------------------

describe("JsonRpcErrorSchema", () => {
  it("accepts an error with a standard MethodNotFound code", () => {
    const result = JsonRpcErrorSchema.safeParse(methodNotFoundError);
    expect(result.success).toBe(true);
  });

  it("accepts an error carrying RoIS return_code in data field", () => {
    const result = JsonRpcErrorSchema.safeParse(badParameterError);
    expect(result.success).toBe(true);
  });

  it("accepts a null id (parse-error case where original id is unknown)", () => {
    const parseError: JsonRpcError = {
      jsonrpc: "2.0",
      id: null,
      error: {
        code: JsonRpcErrorCode.ParseError,
        message: "Invalid JSON",
      },
    };
    const result = JsonRpcErrorSchema.safeParse(parseError);
    expect(result.success).toBe(true);
  });

  it("rejects an error with a non-integer error code", () => {
    const result = JsonRpcErrorSchema.safeParse({
      ...methodNotFoundError,
      error: { ...methodNotFoundError.error, code: -32601.5 },
    });
    expect(result.success).toBe(false);
  });

  it("rejects an error with missing error.message", () => {
    const result = JsonRpcErrorSchema.safeParse({
      ...methodNotFoundError,
      error: { code: JsonRpcErrorCode.InternalError },
    });
    expect(result.success).toBe(false);
  });

  it("round-trips through JSON.stringify / JSON.parse", () => {
    const json = JSON.stringify(badParameterError);
    const parsed = JSON.parse(json);
    const result = JsonRpcErrorSchema.safeParse(parsed);
    expect(result.success).toBe(true);
    if (result.success) {
      expect(result.data.error.code).toBe(JsonRpcErrorCode.InvalidParams);
    }
  });

  // TODO: The spec says a response MUST NOT have both `result` and `error`.
  // Current schemas validate each shape independently. Enforcing mutual
  // exclusion requires a discriminated union or a refine() on a parent schema.
  it.todo("(known gap) rejects a message that has both result and error fields");
});

// ---------------------------------------------------------------------------
// JsonRpcNotification (server-to-client push, no id)
// ---------------------------------------------------------------------------

describe("JsonRpcNotificationSchema", () => {
  it("accepts a person_detected event notification (EventEnvelope params)", () => {
    const result = JsonRpcNotificationSchema.safeParse(personDetectedNotification);
    expect(result.success).toBe(true);
  });

  it("accepts a command completed notification (CompletedEvent params)", () => {
    const result = JsonRpcNotificationSchema.safeParse(commandCompletedNotification);
    expect(result.success).toBe(true);
  });

  it("accepts a notify_error notification (NotifyErrorEvent params)", () => {
    const result = JsonRpcNotificationSchema.safeParse(notifyErrorNotification);
    expect(result.success).toBe(true);
  });

  it("accepts a notification with no params (params is optional)", () => {
    const result = JsonRpcNotificationSchema.safeParse({
      jsonrpc: "2.0",
      method: "rois.system.notify_error",
    });
    expect(result.success).toBe(true);
  });

  it("rejects a notification with wrong jsonrpc version", () => {
    const result = JsonRpcNotificationSchema.safeParse({
      ...personDetectedNotification,
      jsonrpc: "1.0",
    });
    expect(result.success).toBe(false);
  });

  it("rejects a notification with missing method", () => {
    const { method: _omit, ...noMethod } = personDetectedNotification;
    const result = JsonRpcNotificationSchema.safeParse(noMethod);
    expect(result.success).toBe(false);
  });

  it("round-trips through JSON.stringify / JSON.parse", () => {
    const json = JSON.stringify(personDetectedNotification);
    const parsed = JSON.parse(json);
    const result = JsonRpcNotificationSchema.safeParse(parsed);
    expect(result.success).toBe(true);
    if (result.success) {
      expect(result.data.method).toBe("rois.event.notify");
    }
  });

  it("rejects a notification with an extra id field (strict validation)", () => {
    // With .strict(), an `id` field is rejected. This is correct behavior:
    // if a message has `method` + `id`, it is a Request, not a Notification.
    // The router should parse it as a Request, not silently accept it here.
    const result = JsonRpcNotificationSchema.safeParse({
      ...personDetectedNotification,
      id: "should-not-be-here",
    });
    expect(result.success).toBe(false);
  });
});

// ---------------------------------------------------------------------------
// JsonRpcErrorObject (shared sub-schema)
// ---------------------------------------------------------------------------

describe("JsonRpcErrorObjectSchema", () => {
  it("accepts all standard error codes defined in JsonRpcErrorCode", () => {
    const standardCodes = [
      JsonRpcErrorCode.ParseError,
      JsonRpcErrorCode.InvalidRequest,
      JsonRpcErrorCode.MethodNotFound,
      JsonRpcErrorCode.InvalidParams,
      JsonRpcErrorCode.InternalError,
    ];
    for (const code of standardCodes) {
      const result = JsonRpcErrorObjectSchema.safeParse({ code, message: "test" });
      expect(result.success).toBe(true);
    }
  });

  it("accepts gateway-defined error codes in the reserved range", () => {
    const result = JsonRpcErrorObjectSchema.safeParse({ code: -32000, message: "gateway timeout" });
    expect(result.success).toBe(true);
  });

  it("accepts application-defined error codes outside the reserved range", () => {
    const result = JsonRpcErrorObjectSchema.safeParse({ code: -31000, message: "app error" });
    expect(result.success).toBe(true);
  });

  it("accepts a data field carrying RoIS ReturnCode", () => {
    const result = JsonRpcErrorObjectSchema.safeParse({
      code: JsonRpcErrorCode.InvalidParams,
      message: "Component not found",
      data: { return_code: "UNSUPPORTED", component_ref: "UnknownComponent_0" },
    });
    expect(result.success).toBe(true);
  });
});

// ---------------------------------------------------------------------------
// RoIS namespace constants and method type
// ---------------------------------------------------------------------------

describe("RoISNamespace", () => {
  it('has the five interface namespaces matching the architecture', () => {
    expect(RoISNamespace.System).toBe("rois.system");
    expect(RoISNamespace.Command).toBe("rois.command");
    expect(RoISNamespace.Query).toBe("rois.query");
    expect(RoISNamespace.Event).toBe("rois.event");
    expect(RoISNamespace.Stream).toBe("rois.stream");
  });
});

describe("RoISMethod type", () => {
  // Compile-time check: assigning known method strings to the union type
  // should not cause a type error. This test verifies that the constant
  // literals are assignable.
  it("accepts known RoIS method strings at compile time", () => {
    const methods: RoISMethod[] = [
      "rois.system.connect",
      "rois.system.disconnect",
      "rois.system.get_profile",
      "rois.system.get_error_detail",
      "rois.system.notify_error",
      "rois.command.search",
      "rois.command.bind",
      "rois.command.bind_any",
      "rois.command.release",
      "rois.command.get_parameter",
      "rois.command.set_parameter",
      "rois.command.execute",
      "rois.command.get_command_result",
      "rois.command.completed",
      "rois.query.query",
      "rois.event.subscribe",
      "rois.event.unsubscribe",
      "rois.event.get_event_detail",
      "rois.event.notify",
      "rois.stream.connect_stream",
      "rois.stream.disconnect_stream",
      "rois.stream.suspend_stream",
      "rois.stream.resume_stream",
      "rois.stream.query_stream_status",
      "rois.stream.notify_status",
    ];
    expect(methods.length).toBe(25);
  });
});

// ---------------------------------------------------------------------------
// Cross-cutting
// ---------------------------------------------------------------------------

describe("JSONRPC_VERSION", () => {
  it('equals the string "2.0"', () => {
    expect(JSONRPC_VERSION).toBe("2.0");
  });
});