/**
 * JSON-RPC 2.0 message type definitions for the OpenRoIS SDK.
 *
 * Defines the four envelope types that the SDK sends and receives over
 * WebSocket connections to the gateway:
 *
 *   JsonRpcRequest      - Client calls a method and expects a reply (has `id`)
 *   JsonRpcResponse     - Gateway returns a successful result for a request
 *   JsonRpcError        - Gateway returns a failure for a request
 *   JsonRpcNotification - Server-to-client push with no reply expected (no `id`)
 *
 * Every RoIS interface operation maps to a JSON-RPC method in a namespaced
 * hierarchy (see RoISMethod below). The `params` of each request carry one of
 * the canonical schema types (DiscoverRequest, CommandRequest, QueryRequest,
 * SubscribeRequest), and the `result` of each response carries the matching
 * schema response type (DiscoverResponse, InvokeResponse, QueryResponse,
 * SubscribeResponse). Server-to-client notifications carry EventEnvelope,
 * CompletedEvent, or NotifyErrorEvent payloads.
 *
 * Source: JSON-RPC 2.0 Specification (https://www.jsonrpc.org/specification)
 * Architecture: docs/architecture.md section 4 (Client SDK layer)
 * Wire contract: interfaces/schema/ (canonical JSON Schema)
 */

import { z } from "zod";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

/** The only valid JSON-RPC version string per the spec. */
export const JSONRPC_VERSION = "2.0" as const;

// ---------------------------------------------------------------------------
// RoIS method namespace constants
// ---------------------------------------------------------------------------

/**
 * RoIS method namespaces used in JSON-RPC `method` fields.
 *
 * Each namespace corresponds to one of the five RoIS interfaces (architecture.md
 * section 12). The SDK sends requests using these method names. The gateway
 * sends notifications using the async push methods (completed, notify_error,
 * notify, notify_status).
 *
 * Request methods (SDK to gateway):
 *   rois.system.connect, rois.system.disconnect, rois.system.get_profile,
 *   rois.system.get_error_detail
 *   rois.command.search, rois.command.bind, rois.command.bind_any,
 *   rois.command.release, rois.command.get_parameter,
 *   rois.command.set_parameter, rois.command.execute,
 *   rois.command.get_command_result
 *   rois.query.query
 *   rois.event.subscribe, rois.event.unsubscribe, rois.event.get_event_detail
 *   rois.stream.connect_stream, rois.stream.disconnect_stream,
 *   rois.stream.suspend_stream, rois.stream.resume_stream,
 *   rois.stream.query_stream_status
 *
 * Notification methods (gateway to SDK, no id):
 *   rois.command.completed      -> params: CompletedEvent schema
 *   rois.system.notify_error    -> params: NotifyErrorEvent schema
 *   rois.event.notify           -> params: EventEnvelope schema
 *   rois.stream.notify_status   -> params: (stream status payload)
 */
export const RoISNamespace = {
  System:  "rois.system",
  Command: "rois.command",
  Query:   "rois.query",
  Event:   "rois.event",
  Stream:  "rois.stream",
} as const;

/**
 * Known RoIS JSON-RPC method names.
 *
 * Not exhaustive (gateway extensions may add more), but covers all methods
 * from the five normative interfaces. Typed as a string union for
 * autocomplete and compile-time safety. The SDK is free to use the string
 * literal directly when needed.
 */
export type RoISMethod =
  // SystemIF
  | "rois.system.connect"
  | "rois.system.disconnect"
  | "rois.system.get_profile"
  | "rois.system.get_error_detail"
  // SystemIF async push (notification, no id)
  | "rois.system.notify_error"
  // CommandIF
  | "rois.command.search"
  | "rois.command.bind"
  | "rois.command.bind_any"
  | "rois.command.release"
  | "rois.command.get_parameter"
  | "rois.command.set_parameter"
  | "rois.command.execute"
  | "rois.command.get_command_result"
  // CommandIF async push (notification, no id)
  | "rois.command.completed"
  // QueryIF
  | "rois.query.query"
  // EventIF
  | "rois.event.subscribe"
  | "rois.event.unsubscribe"
  | "rois.event.get_event_detail"
  // EventIF async push (notification, no id)
  | "rois.event.notify"
  // Streaming
  | "rois.stream.connect_stream"
  | "rois.stream.disconnect_stream"
  | "rois.stream.suspend_stream"
  | "rois.stream.resume_stream"
  | "rois.stream.query_stream_status"
  // Streaming async push (notification, no id)
  | "rois.stream.notify_status";

// ---------------------------------------------------------------------------
// Shared primitives
// ---------------------------------------------------------------------------

/**
 * Valid JSON-RPC request/response ID.
 *
 * The spec allows string, number, or null. Null is reserved for parse-error
 * responses where the original id could not be determined. We discourage null
 * as a call-site choice; use string or number.
 */
export const JsonRpcIdSchema = z.union([z.string(), z.number(), z.null()]);
export type JsonRpcId = z.infer<typeof JsonRpcIdSchema>;

/**
 * Method name, e.g. "rois.command.search" or "rois.event.notify".
 *
 * Names beginning with "rois." are reserved for OpenRoIS operations.
 * Names beginning with "rpc." are reserved by the JSON-RPC spec itself.
 */
export const JsonRpcMethodSchema = z.string().min(3);
export type JsonRpcMethod = z.infer<typeof JsonRpcMethodSchema>;

/**
 * Params field: structured value holding call arguments.
 *
 * The spec allows an object (named params) or an array (positional params).
 * OpenRoIS always uses named params (objects) for clarity. The object shape
 * matches the canonical JSON Schema for each method:
 *
 *   rois.command.search   -> DiscoverRequest   { condition }
 *   rois.command.execute  -> CommandRequest     { component_ref, command_type, command_id, ... }
 *   rois.query.query      -> QueryRequest      { component_ref, query_type, condition }
 *   rois.event.subscribe  -> SubscribeRequest  { component_ref, event_type, condition }
 *   rois.event.notify     -> EventEnvelope     { event_id, event_type, subscribe_id, payload, ... }
 *   rois.command.completed-> CompletedEvent    { command_id, status }
 *   rois.system.notify_error -> NotifyErrorEvent { error_id, error_type }
 *
 * Arrays are accepted here for spec compliance but are not emitted by the SDK.
 */
export const JsonRpcParamsSchema = z.union([
  z.record(z.string(), z.unknown()), // named params (preferred by OpenRoIS)
  z.array(z.unknown()),  // positional params (spec-compliant, not emitted by SDK)
]);
export type JsonRpcParams = z.infer<typeof JsonRpcParamsSchema>;

// ---------------------------------------------------------------------------
// Error object (used inside JsonRpcError)
// ---------------------------------------------------------------------------

/**
 * Standard JSON-RPC 2.0 error codes.
 *
 * Codes from -32768 to -32000 are reserved by the spec.
 * Codes from -32000 to -32099 are reserved for implementation-defined
 * server errors (the gateway may define codes in this range).
 *
 * Application-level errors from the RoIS layer (BAD_PARAMETER, UNSUPPORTED,
 * OUT_OF_RESOURCES, TIMEOUT) are carried in the `data` field of the error
 * object, not as JSON-RPC error codes. The JSON-RPC code reflects the
 * transport-level failure; the `data.return_code` field carries the
 * RoIS-level ReturnCode.
 */
export enum JsonRpcErrorCode {
  ParseError     = -32700, // Invalid JSON was received
  InvalidRequest = -32600, // The JSON is not a valid Request object
  MethodNotFound = -32601, // The method does not exist or is not available
  InvalidParams  = -32602, // Invalid method parameters
  InternalError  = -32603, // Internal JSON-RPC error in the gateway
  // -32000 to -32099: gateway-defined server errors (not enumerated here)
}

/**
 * The error object carried inside a JsonRpcError message.
 *
 * Maps to the Error Object defined in section 5.1 of the JSON-RPC 2.0 spec.
 */
export const JsonRpcErrorObjectSchema = z.object({
  /** Numeric error code. Standard codes are defined in JsonRpcErrorCode. */
  code: z.number().int(),
  /** Short human-readable summary of the error. */
  message: z.string(),
  /**
   * Optional additional error data.
   *
   * For RoIS operations, the gateway places the ReturnCode and any component
   * error details here. Shape is gateway-defined; the SDK treats it as opaque
   * unless it knows the originating method.
   *
   * Example: { return_code: "BAD_PARAMETER", detail: "unknown component_ref" }
   */
  data: z.unknown().optional(),
}).strict();
export type JsonRpcErrorObject = z.infer<typeof JsonRpcErrorObjectSchema>;

// ---------------------------------------------------------------------------
// The four message envelopes
// ---------------------------------------------------------------------------

/**
 * A JSON-RPC 2.0 Request.
 *
 * Sent by the SDK (client) to call a gateway method. Always carries an `id`
 * so the gateway can correlate its response. The gateway replies with either
 * a JsonRpcResponse (success) or a JsonRpcError (failure).
 *
 * The `params` object matches the canonical schema for the method being called.
 * For example, rois.command.search carries a DiscoverRequest (with `condition`),
 * and rois.query.query carries a QueryRequest (with `component_ref`,
 * `query_type`, and optional `condition`).
 *
 * Example (search for all components):
 *   {
 *     "jsonrpc": "2.0",
 *     "id": "req-001",
 *     "method": "rois.command.search",
 *     "params": { "condition": "" }
 *   }
 *
 * Example (query person detection status):
 *   {
 *     "jsonrpc": "2.0",
 *     "id": "req-002",
 *     "method": "rois.query.query",
 *     "params": {
 *       "component_ref": "PersonDetection_0",
 *       "query_type": "component_status"
 *     }
 *   }
 */
export const JsonRpcRequestSchema = z.object({
  jsonrpc: z.literal(JSONRPC_VERSION),
  /** Unique identifier chosen by the caller; echoed back in the response. */
  id: JsonRpcIdSchema,
  /** Namespaced method name, e.g. "rois.command.search". */
  method: JsonRpcMethodSchema,
  /** Named parameter object for the method. Omit if the method takes no args. */
  params: JsonRpcParamsSchema.optional(),
}).strict();
export type JsonRpcRequest = z.infer<typeof JsonRpcRequestSchema>;

/**
 * A JSON-RPC 2.0 Success Response.
 *
 * Sent by the gateway when a request completes without error. The `id` field
 * matches the `id` from the originating request. The `result` field carries
 * the return value, whose shape is defined by the canonical schema for the
 * corresponding method:
 *
 *   rois.command.search  -> DiscoverResponse  { return_code, component_ref_list }
 *   rois.command.execute -> InvokeResponse    { return_code, command_id, results }
 *   rois.query.query     -> QueryResponse     { return_code, results }
 *   rois.event.subscribe -> SubscribeResponse { return_code, subscribe_id }
 *
 * Example (search results):
 *   {
 *     "jsonrpc": "2.0",
 *     "id": "req-001",
 *     "result": {
 *       "return_code": "OK",
 *       "component_ref_list": ["PersonDetection_0", "Navigation_0"]
 *     }
 *   }
 */
export const JsonRpcResponseSchema = z.object({
  jsonrpc: z.literal(JSONRPC_VERSION),
  /** Matches the `id` of the originating request. */
  id: JsonRpcIdSchema,
  /** Return value of the method. Shape is method-specific; validated downstream. */
  result: z.unknown(),
}).strict();
export type JsonRpcResponse = z.infer<typeof JsonRpcResponseSchema>;

/**
 * A JSON-RPC 2.0 Error Response.
 *
 * Sent by the gateway when a request fails. The `id` matches the originating
 * request, or is null if the request could not be parsed at all.
 *
 * RoIS-level errors (e.g. BAD_PARAMETER from a bind() to an invalid
 * component_ref) are surfaced in the error object's `data` field alongside
 * the ReturnCode. The numeric `code` stays within the JSON-RPC reserved range
 * for transport-level failures.
 *
 * Example (method not found):
 *   {
 *     "jsonrpc": "2.0",
 *     "id": "req-005",
 *     "error": {
 *       "code": -32601,
 *       "message": "Method not found: rois.command.fly"
 *     }
 *   }
 *
 * Example (RoIS-level bad parameter):
 *   {
 *     "jsonrpc": "2.0",
 *     "id": "req-006",
 *     "error": {
 *       "code": -32602,
 *       "message": "Invalid component_ref",
 *       "data": { "return_code": "BAD_PARAMETER" }
 *     }
 *   }
 */
export const JsonRpcErrorSchema = z.object({
  jsonrpc: z.literal(JSONRPC_VERSION),
  /** Matches the originating request `id`, or null for parse-level failures. */
  id: JsonRpcIdSchema,
  /** Structured error payload. */
  error: JsonRpcErrorObjectSchema,
}).strict();
export type JsonRpcError = z.infer<typeof JsonRpcErrorSchema>;

/**
 * A JSON-RPC 2.0 Notification.
 *
 * Sent by the gateway as a server-to-client push event. Has NO `id` field,
 * so the client never sends a response back. Used for the four async push
 * channels defined by the architecture:
 *
 *   rois.command.completed    -> CompletedEvent    { command_id, status }
 *   rois.system.notify_error  -> NotifyErrorEvent  { error_id, error_type }
 *   rois.event.notify         -> EventEnvelope     { event_id, event_type, ... }
 *   rois.stream.notify_status -> (stream status)
 *
 * Example (person detected event):
 *   {
 *     "jsonrpc": "2.0",
 *     "method": "rois.event.notify",
 *     "params": {
 *       "event_id": "evt-001",
 *       "event_type": "person_detected",
 *       "subscribe_id": "sub-1",
 *       "component_ref": "PersonDetection_0",
 *       "payload": [
 *         { "name": "timestamp", "data_type_ref": "DateTime", "value": "2026-06-25T10:30:00Z" },
 *         { "name": "number", "data_type_ref": "int", "value": "2" }
 *       ]
 *     }
 *   }
 *
 * Example (command completed):
 *   {
 *     "jsonrpc": "2.0",
 *     "method": "rois.command.completed",
 *     "params": { "command_id": "cmd-001", "status": "OK" }
 *   }
 */
export const JsonRpcNotificationSchema = z.object({
  jsonrpc: z.literal(JSONRPC_VERSION),
  /** Namespaced push method name, e.g. "rois.event.notify". */
  method: JsonRpcMethodSchema,
  /** Event payload. Shape depends on the method; validated downstream. */
  params: JsonRpcParamsSchema.optional(),
  // NOTE: No `id` field. Its absence is what distinguishes a Notification
  // from a Request at the protocol level.
}).strict();
export type JsonRpcNotification = z.infer<typeof JsonRpcNotificationSchema>;

// ---------------------------------------------------------------------------
// Union discriminator (for the incoming message router)
// ---------------------------------------------------------------------------

/**
 * Any valid JSON-RPC 2.0 message that the SDK might receive from the gateway.
 *
 * The router in the transport layer should:
 *   1. Parse raw JSON into a plain object.
 *   2. Check for the presence of `id` and `error`/`result`/`method` to classify:
 *        - Has `id` + `result`  -> JsonRpcResponse
 *        - Has `id` + `error`   -> JsonRpcError
 *        - Has `method`, no `id` -> JsonRpcNotification
 *        - Has `method` + `id`  -> JsonRpcRequest (should not come from gateway)
 *   3. Validate with the matching schema before dispatching.
 *   4. For responses/errors, match to the pending request by `id`.
 *   5. For notifications, dispatch by method to the right event handler.
 *
 * TODO (Week 1): Implement the classify() helper that maps an unknown object
 * to one of these four types.
 */
export type JsonRpcMessage =
  | JsonRpcRequest
  | JsonRpcResponse
  | JsonRpcError
  | JsonRpcNotification;