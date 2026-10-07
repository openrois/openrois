// GENERATED FROM interfaces/schema — DO NOT EDIT
// Source: BindAnyParams.schema.json, BindAnyResult.schema.json, BindParams.schema.json, BindResult.schema.json, ConnectParams.schema.json, ConnectResult.schema.json, DisconnectParams.schema.json, DisconnectResult.schema.json, ExecuteParams.schema.json, ExecuteResult.schema.json, GetCommandResultParams.schema.json, GetCommandResultResult.schema.json, GetErrorDetailParams.schema.json, GetErrorDetailResult.schema.json, GetEventDetailParams.schema.json, GetEventDetailResult.schema.json, GetParameterParams.schema.json, GetParameterResult.schema.json, GetProfileParams.schema.json, GetProfileResult.schema.json, QueryParams.schema.json, QueryResult.schema.json, ReleaseParams.schema.json, ReleaseResult.schema.json, SearchParams.schema.json, SearchResult.schema.json, SetParameterParams.schema.json, SetParameterResult.schema.json, SubscribeParams.schema.json, SubscribeResult.schema.json, UnsubscribeParams.schema.json, UnsubscribeResult.schema.json
// Generator: scripts/generate.ts

import { z } from "zod";
import { CommandUnitSequenceItemSchema, ParameterSchema, ResultSchema, ReturnCodeSchema } from "./hri";
import { HRIEngineProfileTypeSchema } from "./profiles";

/**
 * Params of rois.command.bind_any.
 * 
 * Maps to CommandIF::bind_any(in condition, out component_ref).
 * 
 * Attributes:
 *     condition: Selection condition on component_ref and component_type for the
 *         components the engine may choose from. The engine binds a free one.
 */

export const BindAnyParamsSchema = z.object({
  condition: z.string().default(""), // Selection condition (CQL2-Text) on the components to choose from
}).strict();
export type BindAnyParams = z.infer<typeof BindAnyParamsSchema>;

/**
 * Result of rois.command.bind_any.
 * 
 * Maps to CommandIF::bind_any(in condition, out component_ref).
 * 
 * Attributes:
 *     return_code: Outcome of the operation.
 *     component_ref: The component the engine reserved. Empty when return_code is
 *         not OK.
 */

export const BindAnyResultSchema = z.object({
  return_code: ReturnCodeSchema,
  component_ref: z.string().default(""), // The component reserved
}).strict();
export type BindAnyResult = z.infer<typeof BindAnyResultSchema>;

/**
 * Params of rois.command.bind.
 * 
 * Maps to CommandIF::bind(in component_ref).
 * 
 * Attributes:
 *     component_ref: The component to reserve for this client.
 */

export const BindParamsSchema = z.object({
  component_ref: z.string(), // The component to reserve
}).strict();
export type BindParams = z.infer<typeof BindParamsSchema>;

/**
 * Result of rois.command.bind.
 * 
 * Maps to CommandIF::bind(in component_ref).
 * 
 * Attributes:
 *     return_code: Outcome of the operation. OUT_OF_RESOURCES when another client
 *         holds the component.
 */

export const BindResultSchema = z.object({
  return_code: ReturnCodeSchema,
}).strict();
export type BindResult = z.infer<typeof BindResultSchema>;

/**
 * Params of rois.system.connect.
 * 
 * Maps to SystemIF::connect(), which takes no arguments. A request may omit params.
 */

export const ConnectParamsSchema = z.object({

}).strict();
export type ConnectParams = z.infer<typeof ConnectParamsSchema>;

/**
 * Result of rois.system.connect.
 * 
 * Maps to SystemIF::connect().
 * 
 * Attributes:
 *     return_code: Outcome of the operation.
 */

export const ConnectResultSchema = z.object({
  return_code: ReturnCodeSchema,
}).strict();
export type ConnectResult = z.infer<typeof ConnectResultSchema>;

/**
 * Params of rois.system.disconnect.
 * 
 * Maps to SystemIF::disconnect(), which takes no arguments. A request may omit params.
 */

export const DisconnectParamsSchema = z.object({

}).strict();
export type DisconnectParams = z.infer<typeof DisconnectParamsSchema>;

/**
 * Result of rois.system.disconnect.
 * 
 * Maps to SystemIF::disconnect().
 * 
 * Attributes:
 *     return_code: Outcome of the operation.
 */

export const DisconnectResultSchema = z.object({
  return_code: ReturnCodeSchema,
}).strict();
export type DisconnectResult = z.infer<typeof DisconnectResultSchema>;

/**
 * Params of rois.command.execute.
 * 
 * Maps to CommandIF::execute(in command_unit_list). The application names every
 * command with its own command_id, and completed notifications report each one.
 * The engine rejects a command_id it already tracks with BAD_PARAMETER.
 * 
 * Attributes:
 *     command_unit_list: Commands to run in order. A ConcurrentCommands item runs
 *         its commands at the same time.
 */

export const ExecuteParamsSchema = z.object({
  command_unit_list: z.array(CommandUnitSequenceItemSchema), // Commands to run in order
}).strict();
export type ExecuteParams = z.infer<typeof ExecuteParamsSchema>;

/**
 * Result of rois.command.execute.
 * 
 * Maps to CommandIF::execute(in command_unit_list), which has no out parameters.
 * 
 * Attributes:
 *     return_code: Whether the engine accepted the commands. Completed
 *         notifications report how each command ended.
 */

export const ExecuteResultSchema = z.object({
  return_code: ReturnCodeSchema,
}).strict();
export type ExecuteResult = z.infer<typeof ExecuteResultSchema>;

/**
 * Params of rois.command.get_command_result.
 * 
 * Maps to CommandIF::get_command_result(in command_id, in condition, out results).
 * 
 * Attributes:
 *     command_id: The command whose results to read.
 *     condition: Filter on the results. No property is defined for it yet, so it
 *         must be empty.
 */

export const GetCommandResultParamsSchema = z.object({
  command_id: z.string(), // The command whose results to read
  condition: z.string().default(""), // Filter on the results (CQL2-Text). Must be empty for now
}).strict();
export type GetCommandResultParams = z.infer<typeof GetCommandResultParamsSchema>;

/**
 * Result of rois.command.get_command_result.
 * 
 * Maps to CommandIF::get_command_result(in command_id, in condition, out results).
 * 
 * Attributes:
 *     return_code: Outcome of the operation.
 *     results: Results of the command.
 */

export const GetCommandResultResultSchema = z.object({
  return_code: ReturnCodeSchema,
  results: z.array(ResultSchema).optional(), // Results of the command
}).strict();
export type GetCommandResultResult = z.infer<typeof GetCommandResultResultSchema>;

/**
 * Params of rois.system.get_error_detail.
 * 
 * Maps to SystemIF::get_error_detail(in error_id, in condition, out results).
 * 
 * Attributes:
 *     error_id: The error_id from a notify_error notification.
 *     condition: Filter on the results. No property is defined for it yet, so it
 *         must be empty.
 */

export const GetErrorDetailParamsSchema = z.object({
  error_id: z.string(), // The error_id from a notify_error notification
  condition: z.string().default(""), // Filter on the results (CQL2-Text). Must be empty for now
}).strict();
export type GetErrorDetailParams = z.infer<typeof GetErrorDetailParamsSchema>;

/**
 * Result of rois.system.get_error_detail.
 * 
 * Maps to SystemIF::get_error_detail(in error_id, in condition, out results).
 * 
 * Attributes:
 *     return_code: Outcome of the operation.
 *     results: Details of the error.
 */

export const GetErrorDetailResultSchema = z.object({
  return_code: ReturnCodeSchema,
  results: z.array(ResultSchema).optional(), // Details of the error
}).strict();
export type GetErrorDetailResult = z.infer<typeof GetErrorDetailResultSchema>;

/**
 * Params of rois.event.get_event_detail.
 * 
 * Maps to EventIF::get_event_detail(in event_id, in condition, out results).
 * 
 * Attributes:
 *     event_id: The event_id from a notify_event notification.
 *     condition: Filter on the results. No property is defined for it yet, so it
 *         must be empty.
 */

export const GetEventDetailParamsSchema = z.object({
  event_id: z.string(), // The event_id from a notify_event notification
  condition: z.string().default(""), // Filter on the results (CQL2-Text). Must be empty for now
}).strict();
export type GetEventDetailParams = z.infer<typeof GetEventDetailParamsSchema>;

/**
 * Result of rois.event.get_event_detail.
 * 
 * Maps to EventIF::get_event_detail(in event_id, in condition, out results).
 * 
 * Attributes:
 *     return_code: Outcome of the operation.
 *     results: The event payload.
 */

export const GetEventDetailResultSchema = z.object({
  return_code: ReturnCodeSchema,
  results: z.array(ResultSchema).optional(), // The event payload
}).strict();
export type GetEventDetailResult = z.infer<typeof GetEventDetailResultSchema>;

/**
 * Params of rois.command.get_parameter.
 * 
 * Maps to CommandIF::get_parameter(in component_ref, out parameters).
 * 
 * Attributes:
 *     component_ref: The component whose parameters to read.
 */

export const GetParameterParamsSchema = z.object({
  component_ref: z.string(), // The component whose parameters to read
}).strict();
export type GetParameterParams = z.infer<typeof GetParameterParamsSchema>;

/**
 * Result of rois.command.get_parameter.
 * 
 * Maps to CommandIF::get_parameter(in component_ref, out parameters).
 * 
 * Attributes:
 *     return_code: Outcome of the operation.
 *     parameters: The current value of every parameter of the component.
 */

export const GetParameterResultSchema = z.object({
  return_code: ReturnCodeSchema,
  parameters: z.array(ParameterSchema).optional(), // The current value of every parameter of the component
}).strict();
export type GetParameterResult = z.infer<typeof GetParameterResultSchema>;

/**
 * Params of rois.system.get_profile.
 * 
 * Maps to SystemIF::get_profile(in condition, out profile).
 * 
 * Attributes:
 *     condition: Selection condition on component_ref and component_type. The
 *         profile lists only the matching components. Empty means every component.
 */

export const GetProfileParamsSchema = z.object({
  condition: z.string().default(""), // Selection condition (CQL2-Text) on the components the profile lists
}).strict();
export type GetProfileParams = z.infer<typeof GetProfileParamsSchema>;

/**
 * Result of rois.system.get_profile.
 * 
 * Maps to SystemIF::get_profile(in condition, out profile). The IDL carries the
 * profile as an XML document in a string. OpenRoIS sends the structured form of
 * the same XSD type.
 * 
 * Attributes:
 *     return_code: Outcome of the operation.
 *     profile: The engine profile. Null when return_code is not OK.
 */

export const GetProfileResultSchema = z.object({
  return_code: ReturnCodeSchema,
  profile: HRIEngineProfileTypeSchema.nullable().default(null), // The engine profile
}).strict();
export type GetProfileResult = z.infer<typeof GetProfileResultSchema>;

/**
 * Params of rois.query.query.
 * 
 * Maps to QueryIF::query(in query_type, in condition, out results). An engine sends
 * the query to the one component that declares query_type and matches the condition.
 * When none does it returns UNSUPPORTED. When several do it returns BAD_PARAMETER,
 * and a component_ref comparison picks one.
 * 
 * Attributes:
 *     query_type: Name of the query, from a component profile.
 *     condition: Selection condition on component_ref and component_type.
 */

export const QueryParamsSchema = z.object({
  query_type: z.string(), // Name of the query, from a component profile
  condition: z.string().default(""), // Selection condition (CQL2-Text) that picks the component
}).strict();
export type QueryParams = z.infer<typeof QueryParamsSchema>;

/**
 * Result of rois.query.query.
 * 
 * Maps to QueryIF::query(in query_type, in condition, out results).
 * 
 * Attributes:
 *     return_code: Outcome of the operation.
 *     results: Results of the query.
 */

export const QueryResultSchema = z.object({
  return_code: ReturnCodeSchema,
  results: z.array(ResultSchema).optional(), // Results of the query
}).strict();
export type QueryResult = z.infer<typeof QueryResultSchema>;

/**
 * Params of rois.command.release.
 * 
 * Maps to CommandIF::release(in component_ref).
 * 
 * Attributes:
 *     component_ref: The component to release.
 */

export const ReleaseParamsSchema = z.object({
  component_ref: z.string(), // The component to release
}).strict();
export type ReleaseParams = z.infer<typeof ReleaseParamsSchema>;

/**
 * Result of rois.command.release.
 * 
 * Maps to CommandIF::release(in component_ref).
 * 
 * Attributes:
 *     return_code: Outcome of the operation.
 */

export const ReleaseResultSchema = z.object({
  return_code: ReturnCodeSchema,
}).strict();
export type ReleaseResult = z.infer<typeof ReleaseResultSchema>;

/**
 * Params of rois.command.search.
 * 
 * Maps to CommandIF::search(in condition, out component_ref_list).
 * 
 * Attributes:
 *     condition: Selection condition on component_ref and component_type. Empty
 *         matches every component.
 */

export const SearchParamsSchema = z.object({
  condition: z.string().default(""), // Selection condition (CQL2-Text) on the components
}).strict();
export type SearchParams = z.infer<typeof SearchParamsSchema>;

/**
 * Result of rois.command.search.
 * 
 * Maps to CommandIF::search(in condition, out component_ref_list).
 * 
 * Attributes:
 *     return_code: Outcome of the operation.
 *     component_ref_list: Refs of the matching components.
 */

export const SearchResultSchema = z.object({
  return_code: ReturnCodeSchema,
  component_ref_list: z.array(z.string()).optional(), // Refs of the matching components
}).strict();
export type SearchResult = z.infer<typeof SearchResultSchema>;

/**
 * Params of rois.command.set_parameter.
 * 
 * Maps to CommandIF::set_parameter(in component_ref, in parameters, out command_id).
 * 
 * Attributes:
 *     component_ref: The component to configure.
 *     parameters: The parameters to set.
 */

export const SetParameterParamsSchema = z.object({
  component_ref: z.string(), // The component to configure
  parameters: z.array(ParameterSchema), // The parameters to set
}).strict();
export type SetParameterParams = z.infer<typeof SetParameterParamsSchema>;

/**
 * Result of rois.command.set_parameter.
 * 
 * Maps to CommandIF::set_parameter(in component_ref, in parameters, out command_id).
 * The engine assigns the command_id. A completed notification reports the outcome.
 * 
 * Attributes:
 *     return_code: Outcome of the request.
 *     command_id: Identifier of the parameter change, assigned by the engine.
 */

export const SetParameterResultSchema = z.object({
  return_code: ReturnCodeSchema,
  command_id: z.string().default(""), // Identifier of the parameter change, assigned by the engine
}).strict();
export type SetParameterResult = z.infer<typeof SetParameterResultSchema>;

/**
 * Params of rois.event.subscribe.
 * 
 * Maps to EventIF::subscribe(in event_type, in condition, out subscribe_id). An
 * engine subscribes to the one component that declares event_type and matches the
 * condition. When none does it returns UNSUPPORTED. When several do it returns
 * BAD_PARAMETER, and a component_ref comparison picks one.
 * 
 * Attributes:
 *     event_type: Name of the event, from a component profile.
 *     condition: Selection condition on component_ref and component_type.
 */

export const SubscribeParamsSchema = z.object({
  event_type: z.string(), // Name of the event, from a component profile
  condition: z.string().default(""), // Selection condition (CQL2-Text) that picks the component
}).strict();
export type SubscribeParams = z.infer<typeof SubscribeParamsSchema>;

/**
 * Result of rois.event.subscribe.
 * 
 * Maps to EventIF::subscribe(in event_type, in condition, out subscribe_id).
 * 
 * Attributes:
 *     return_code: Outcome of the operation.
 *     subscribe_id: Identifier of the subscription. Empty when return_code is not OK.
 */

export const SubscribeResultSchema = z.object({
  return_code: ReturnCodeSchema,
  subscribe_id: z.string().default(""), // Identifier of the subscription
}).strict();
export type SubscribeResult = z.infer<typeof SubscribeResultSchema>;

/**
 * Params of rois.event.unsubscribe.
 * 
 * Maps to EventIF::unsubscribe(in subscribe_id). Unsubscribing twice is not an error.
 * 
 * Attributes:
 *     subscribe_id: The subscription to cancel.
 */

export const UnsubscribeParamsSchema = z.object({
  subscribe_id: z.string(), // The subscription to cancel
}).strict();
export type UnsubscribeParams = z.infer<typeof UnsubscribeParamsSchema>;

/**
 * Result of rois.event.unsubscribe.
 * 
 * Maps to EventIF::unsubscribe(in subscribe_id).
 * 
 * Attributes:
 *     return_code: Outcome of the operation.
 */

export const UnsubscribeResultSchema = z.object({
  return_code: ReturnCodeSchema,
}).strict();
export type UnsubscribeResult = z.infer<typeof UnsubscribeResultSchema>;

// ─── Method catalog (from catalog.json) ──────────────────────────

/** JSON-RPC method names of the RoIS method catalog, keyed by operation. */
export const RoISMethods = {
  Connect: "rois.system.connect",
  Disconnect: "rois.system.disconnect",
  GetProfile: "rois.system.get_profile",
  GetErrorDetail: "rois.system.get_error_detail",
  Search: "rois.command.search",
  Bind: "rois.command.bind",
  BindAny: "rois.command.bind_any",
  Release: "rois.command.release",
  GetParameter: "rois.command.get_parameter",
  SetParameter: "rois.command.set_parameter",
  Execute: "rois.command.execute",
  GetCommandResult: "rois.command.get_command_result",
  Query: "rois.query.query",
  Subscribe: "rois.event.subscribe",
  Unsubscribe: "rois.event.unsubscribe",
  GetEventDetail: "rois.event.get_event_detail",
} as const;
/** A JSON-RPC method name from the RoIS method catalog. */
export type RoISMethod = (typeof RoISMethods)[keyof typeof RoISMethods];

/** The params and result type of every catalog method. */
export interface RoISMethodMap {
  "rois.system.connect": { params: ConnectParams; result: ConnectResult };
  "rois.system.disconnect": { params: DisconnectParams; result: DisconnectResult };
  "rois.system.get_profile": { params: GetProfileParams; result: GetProfileResult };
  "rois.system.get_error_detail": { params: GetErrorDetailParams; result: GetErrorDetailResult };
  "rois.command.search": { params: SearchParams; result: SearchResult };
  "rois.command.bind": { params: BindParams; result: BindResult };
  "rois.command.bind_any": { params: BindAnyParams; result: BindAnyResult };
  "rois.command.release": { params: ReleaseParams; result: ReleaseResult };
  "rois.command.get_parameter": { params: GetParameterParams; result: GetParameterResult };
  "rois.command.set_parameter": { params: SetParameterParams; result: SetParameterResult };
  "rois.command.execute": { params: ExecuteParams; result: ExecuteResult };
  "rois.command.get_command_result": { params: GetCommandResultParams; result: GetCommandResultResult };
  "rois.query.query": { params: QueryParams; result: QueryResult };
  "rois.event.subscribe": { params: SubscribeParams; result: SubscribeResult };
  "rois.event.unsubscribe": { params: UnsubscribeParams; result: UnsubscribeResult };
  "rois.event.get_event_detail": { params: GetEventDetailParams; result: GetEventDetailResult };
}

/** The params and result schema of every catalog method, for validating messages. */
export const RoISMethodSchemas = {
  "rois.system.connect": { params: ConnectParamsSchema, result: ConnectResultSchema },
  "rois.system.disconnect": { params: DisconnectParamsSchema, result: DisconnectResultSchema },
  "rois.system.get_profile": { params: GetProfileParamsSchema, result: GetProfileResultSchema },
  "rois.system.get_error_detail": { params: GetErrorDetailParamsSchema, result: GetErrorDetailResultSchema },
  "rois.command.search": { params: SearchParamsSchema, result: SearchResultSchema },
  "rois.command.bind": { params: BindParamsSchema, result: BindResultSchema },
  "rois.command.bind_any": { params: BindAnyParamsSchema, result: BindAnyResultSchema },
  "rois.command.release": { params: ReleaseParamsSchema, result: ReleaseResultSchema },
  "rois.command.get_parameter": { params: GetParameterParamsSchema, result: GetParameterResultSchema },
  "rois.command.set_parameter": { params: SetParameterParamsSchema, result: SetParameterResultSchema },
  "rois.command.execute": { params: ExecuteParamsSchema, result: ExecuteResultSchema },
  "rois.command.get_command_result": { params: GetCommandResultParamsSchema, result: GetCommandResultResultSchema },
  "rois.query.query": { params: QueryParamsSchema, result: QueryResultSchema },
  "rois.event.subscribe": { params: SubscribeParamsSchema, result: SubscribeResultSchema },
  "rois.event.unsubscribe": { params: UnsubscribeParamsSchema, result: UnsubscribeResultSchema },
  "rois.event.get_event_detail": { params: GetEventDetailParamsSchema, result: GetEventDetailResultSchema },
} as const;

/** JSON-RPC 2.0 error codes an engine returns for protocol faults. */
export const JsonRpcErrorCode = {
  PARSE_ERROR: -32700,
  INVALID_REQUEST: -32600,
  METHOD_NOT_FOUND: -32601,
  INVALID_PARAMS: -32602,
  INTERNAL_ERROR: -32603,
} as const;

/** Method name prefixes the catalog does not model. Engines answer them with METHOD_NOT_FOUND. */
export const UnmodelledMethodPrefixes = ["rois.stream."] as const;
