/**
 * JSON-RPC 2.0 envelopes for the OpenRoIS SDK.
 *
 * Defines the four message types exchanged with an engine over WebSocket:
 *
 *   JsonRpcRequest      - A call that expects a reply (has `id`)
 *   JsonRpcResponse     - A successful reply to a request
 *   JsonRpcError        - A failed reply to a request
 *   JsonRpcNotification - A push with no reply expected (no `id`)
 *
 * This module knows nothing about RoIS. The method names, the params and result
 * of each method, the notifications and the JSON-RPC error codes come from the
 * method catalog in @openrois/interfaces (RoISMethods, RoISMethodSchemas,
 * RoISNotifications, JsonRpcErrorCode). Section 17 of docs/rois-reference.md
 * describes the binding.
 *
 * A RoIS failure is a normal JsonRpcResponse whose result has a return_code
 * other than OK. A JsonRpcError only reports a protocol fault: unparseable
 * JSON, an invalid request, an unknown method, params that fail validation, or
 * an internal error.
 *
 * Source: JSON-RPC 2.0 Specification (https://www.jsonrpc.org/specification)
 */

import { z } from "zod";

export { JsonRpcErrorCode } from "@openrois/interfaces";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

/** The only valid JSON-RPC version string per the spec. */
export const JSONRPC_VERSION = "2.0" as const;

// ---------------------------------------------------------------------------
// Shared primitives
// ---------------------------------------------------------------------------

/**
 * Valid JSON-RPC request/response ID.
 *
 * The spec allows string, number, or null. Null is reserved for parse-error
 * responses where the original id could not be determined.
 */
export const JsonRpcIdSchema = z.union([z.string(), z.number(), z.null()]);
export type JsonRpcId = z.infer<typeof JsonRpcIdSchema>;

/**
 * Method name, for example "rois.command.search".
 *
 * Names beginning with "rois." are reserved for OpenRoIS operations.
 * Names beginning with "rpc." are reserved by the JSON-RPC spec itself.
 */
export const JsonRpcMethodSchema = z.string().min(3);
export type JsonRpcMethod = z.infer<typeof JsonRpcMethodSchema>;

/**
 * Params field: named params (an object) or positional params (an array).
 *
 * OpenRoIS always sends named params, shaped by the catalog's params model for
 * the method. Arrays are accepted for spec compliance but are not sent.
 */
export const JsonRpcParamsSchema = z.union([
  z.record(z.string(), z.unknown()),
  z.array(z.unknown()),
]);
export type JsonRpcParams = z.infer<typeof JsonRpcParamsSchema>;

// ---------------------------------------------------------------------------
// Error object (used inside JsonRpcError)
// ---------------------------------------------------------------------------

/**
 * The error object carried inside a JsonRpcError message.
 *
 * Maps to the Error Object defined in section 5.1 of the JSON-RPC 2.0 spec.
 * The standard codes are in JsonRpcErrorCode. Codes from -32000 to -32099 are
 * left to the engine.
 */
export const JsonRpcErrorObjectSchema = z.object({
  /** Numeric error code. */
  code: z.number().int(),
  /** Short human-readable summary of the error. */
  message: z.string(),
  /** Optional additional data, defined by the engine. */
  data: z.unknown().optional(),
}).strict();
export type JsonRpcErrorObject = z.infer<typeof JsonRpcErrorObjectSchema>;

// ---------------------------------------------------------------------------
// The four message envelopes
// ---------------------------------------------------------------------------

/**
 * A JSON-RPC 2.0 Request. Always carries an `id`, which the reply echoes.
 *
 * Example:
 *   {
 *     "jsonrpc": "2.0",
 *     "id": "req-2",
 *     "method": "rois.query.query",
 *     "params": {
 *       "query_type": "component_status",
 *       "condition": "component_ref = 'reachy_real/head'"
 *     }
 *   }
 */
export const JsonRpcRequestSchema = z.object({
  jsonrpc: z.literal(JSONRPC_VERSION),
  /** Unique identifier chosen by the caller and echoed back in the response. */
  id: JsonRpcIdSchema,
  /** Namespaced method name, for example "rois.command.search". */
  method: JsonRpcMethodSchema,
  /** Named parameter object for the method. Omitted when the method takes none. */
  params: JsonRpcParamsSchema.optional(),
}).strict();
export type JsonRpcRequest = z.infer<typeof JsonRpcRequestSchema>;

/**
 * A JSON-RPC 2.0 Success Response. The `result` is the catalog's result model
 * for the method, validated by the caller.
 *
 * Example:
 *   {
 *     "jsonrpc": "2.0",
 *     "id": "req-1",
 *     "result": {
 *       "return_code": "OK",
 *       "component_ref_list": ["reachy_real/head", "reachy_sim/head"]
 *     }
 *   }
 */
export const JsonRpcResponseSchema = z.object({
  jsonrpc: z.literal(JSONRPC_VERSION),
  /** Matches the `id` of the originating request. */
  id: JsonRpcIdSchema,
  /** Return value of the method. Its shape is method-specific. */
  result: z.unknown(),
}).strict();
export type JsonRpcResponse = z.infer<typeof JsonRpcResponseSchema>;

/**
 * A JSON-RPC 2.0 Error Response, for protocol faults only. The `id` matches the
 * originating request, or is null if the request could not be parsed at all.
 *
 * Example:
 *   {
 *     "jsonrpc": "2.0",
 *     "id": "req-5",
 *     "error": { "code": -32601, "message": "Method not found: rois.stream.connect_stream" }
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
 * A JSON-RPC 2.0 Notification: a push from the engine with no `id`, so the
 * client never replies. The `params` are the catalog's params model for the
 * notification.
 *
 * Example:
 *   {
 *     "jsonrpc": "2.0",
 *     "method": "rois.command.completed",
 *     "params": { "command_id": "3f2a9c1e-5b7d-4e2a-9f10-6c8d2b4a7e01", "status": "OK" }
 *   }
 */
export const JsonRpcNotificationSchema = z.object({
  jsonrpc: z.literal(JSONRPC_VERSION),
  /** Namespaced notification name, for example "rois.event.notify_event". */
  method: JsonRpcMethodSchema,
  /** Notification params. Their shape depends on the method. */
  params: JsonRpcParamsSchema.optional(),
}).strict();
export type JsonRpcNotification = z.infer<typeof JsonRpcNotificationSchema>;

// ---------------------------------------------------------------------------
// Union of every message
// ---------------------------------------------------------------------------

/**
 * Any JSON-RPC 2.0 message. The transport classifies an incoming message by
 * its fields: `id` and `result` is a response, `id` and `error` is an error,
 * and `method` without `id` is a notification.
 */
export type JsonRpcMessage =
  | JsonRpcRequest
  | JsonRpcResponse
  | JsonRpcError
  | JsonRpcNotification;
