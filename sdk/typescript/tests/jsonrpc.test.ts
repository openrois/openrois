/**
 * Unit tests for jsonrpc.ts -- JSON-RPC 2.0 message type validation.
 *
 * Coverage goals (fill in assertions as you implement):
 *   - Valid messages parse without error.
 *   - Invalid / malformed messages are rejected by Zod.
 *   - Round-trip: serialize to JSON, parse back, schema still accepts it.
 *   - Edge cases from the JSON-RPC 2.0 spec (null id, missing params, etc.)
 *
 * The fixtures carry params and results that the method catalog accepts, so the
 * envelopes are checked with real RoIS payloads.
 *
 * Run with: npx vitest run
 */

import { describe, it, expect } from "vitest";
import {
  JsonRpcErrorCode as CatalogJsonRpcErrorCode,
  RoISMethodSchemas,
  RoISNotificationSchemas,
  type RoISMethod,
  type RoISNotification,
} from "@openrois/interfaces";
import {
  JsonRpcRequestSchema,
  JsonRpcResponseSchema,
  JsonRpcErrorSchema,
  JsonRpcNotificationSchema,
  JsonRpcErrorObjectSchema,
  JsonRpcErrorCode,
  JSONRPC_VERSION,
  type JsonRpcRequest,
  type JsonRpcResponse,
  type JsonRpcError,
  type JsonRpcNotification,
} from "../src/jsonrpc";

// ---------------------------------------------------------------------------
// Fixtures: envelopes whose params and results are real catalog payloads
// ---------------------------------------------------------------------------

const searchRequest: JsonRpcRequest = {
  jsonrpc: "2.0",
  id: "req-001",
  method: "rois.command.search",
  params: { condition: "" },
};

const queryRequest: JsonRpcRequest = {
  jsonrpc: "2.0",
  id: "req-002",
  method: "rois.query.query",
  params: {
    query_type: "component_status",
    condition: "component_ref = 'reachy_real/head'",
  },
};

const executeRequest: JsonRpcRequest = {
  jsonrpc: "2.0",
  id: "req-003",
  method: "rois.command.execute",
  params: {
    command_unit_list: [
      { component_ref: "reachy_real/head", command_type: "start", command_id: "nod-1" },
      {
        command_list: [
          { component_ref: "reachy_real/head", command_type: "stop", command_id: "nod-2" },
          { component_ref: "reachy_sim/head", command_type: "stop", command_id: "nod-3" },
        ],
        delay_time: 500,
      },
    ],
  },
};

const subscribeRequest: JsonRpcRequest = {
  jsonrpc: "2.0",
  id: "req-004",
  method: "rois.event.subscribe",
  params: {
    event_type: "person_detected",
    condition: "component_ref = 'reachy_real/camera'",
  },
};

const searchResponse: JsonRpcResponse = {
  jsonrpc: "2.0",
  id: "req-001",
  result: {
    return_code: "OK",
    component_ref_list: ["reachy_real/head", "reachy_sim/head", "reachy_real/camera"],
  },
};

const queryResponse: JsonRpcResponse = {
  jsonrpc: "2.0",
  id: "req-002",
  result: {
    return_code: "OK",
    results: [{ name: "status", data_type_ref: "ComponentStatus", value: "READY" }],
  },
};

const executeResponse: JsonRpcResponse = {
  jsonrpc: "2.0",
  id: "req-003",
  result: { return_code: "OK" },
};

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
    code: JsonRpcErrorCode.METHOD_NOT_FOUND,
    message: "Method not found: rois.stream.connect_stream",
  },
};

// Error response: params that fail validation, with engine-defined data
const invalidParamsError: JsonRpcError = {
  jsonrpc: "2.0",
  id: "req-005",
  error: {
    code: JsonRpcErrorCode.INVALID_PARAMS,
    message: "Invalid params for rois.command.bind",
    data: { field: "component_ref", issue: "required" },
  },
};

const personDetectedNotification: JsonRpcNotification = {
  jsonrpc: "2.0",
  method: "rois.event.notify_event",
  params: {
    event_id: "evt-001",
    event_type: "person_detected",
    subscribe_id: "sub-pd-001",
    expire: "",
    results: [
      { name: "timestamp", data_type_ref: "DateTime", value: "2026-06-25T10:30:00Z" },
      { name: "number", data_type_ref: "int", value: "2" },
    ],
  },
};

const commandCompletedNotification: JsonRpcNotification = {
  jsonrpc: "2.0",
  method: "rois.command.completed",
  params: {
    command_id: "nod-1",
    status: "OK",
  },
};

const notifyErrorNotification: JsonRpcNotification = {
  jsonrpc: "2.0",
  method: "rois.system.notify_error",
  params: {
    error_id: "err-001",
    error_type: "COMPONENT_NOT_RESPONDING",
  },
};

describe("fixtures", () => {
  it("carry params and results that the catalog accepts", () => {
    const requests = [searchRequest, queryRequest, executeRequest, subscribeRequest];
    const responses = [searchResponse, queryResponse, executeResponse, subscribeResponse];
    requests.forEach((request, index) => {
      const schemas = RoISMethodSchemas[request.method as RoISMethod];
      expect(schemas.params.safeParse(request.params).success).toBe(true);
      expect(schemas.result.safeParse(responses[index].result).success).toBe(true);
    });
    for (const notification of [
      personDetectedNotification,
      commandCompletedNotification,
      notifyErrorNotification,
    ]) {
      const schemas = RoISNotificationSchemas[notification.method as RoISNotification];
      expect(schemas.params.safeParse(notification.params).success).toBe(true);
    }
  });
});

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

  it("accepts an execute response", () => {
    const result = JsonRpcResponseSchema.safeParse(executeResponse);
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

  it("accepts an error carrying engine-defined data", () => {
    const result = JsonRpcErrorSchema.safeParse(invalidParamsError);
    expect(result.success).toBe(true);
  });

  it("accepts a null id (parse-error case where original id is unknown)", () => {
    const parseError: JsonRpcError = {
      jsonrpc: "2.0",
      id: null,
      error: {
        code: JsonRpcErrorCode.PARSE_ERROR,
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
      error: { code: JsonRpcErrorCode.INTERNAL_ERROR },
    });
    expect(result.success).toBe(false);
  });

  it("round-trips through JSON.stringify / JSON.parse", () => {
    const json = JSON.stringify(invalidParamsError);
    const parsed = JSON.parse(json);
    const result = JsonRpcErrorSchema.safeParse(parsed);
    expect(result.success).toBe(true);
    if (result.success) {
      expect(result.data.error.code).toBe(JsonRpcErrorCode.INVALID_PARAMS);
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
      expect(result.data.method).toBe("rois.event.notify_event");
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
      JsonRpcErrorCode.PARSE_ERROR,
      JsonRpcErrorCode.INVALID_REQUEST,
      JsonRpcErrorCode.METHOD_NOT_FOUND,
      JsonRpcErrorCode.INVALID_PARAMS,
      JsonRpcErrorCode.INTERNAL_ERROR,
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

  it("accepts an engine-defined data field", () => {
    const result = JsonRpcErrorObjectSchema.safeParse({
      code: JsonRpcErrorCode.INVALID_PARAMS,
      message: "Invalid params for rois.query.query",
      data: { field: "query_type", issue: "required" },
    });
    expect(result.success).toBe(true);
  });
});

// ---------------------------------------------------------------------------
// JSON-RPC error codes
// ---------------------------------------------------------------------------

describe("JsonRpcErrorCode", () => {
  it("is the catalog's table of JSON-RPC 2.0 codes", () => {
    expect(JsonRpcErrorCode).toBe(CatalogJsonRpcErrorCode);
    expect(JsonRpcErrorCode.PARSE_ERROR).toBe(-32700);
    expect(JsonRpcErrorCode.INVALID_REQUEST).toBe(-32600);
    expect(JsonRpcErrorCode.METHOD_NOT_FOUND).toBe(-32601);
    expect(JsonRpcErrorCode.INVALID_PARAMS).toBe(-32602);
    expect(JsonRpcErrorCode.INTERNAL_ERROR).toBe(-32603);
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