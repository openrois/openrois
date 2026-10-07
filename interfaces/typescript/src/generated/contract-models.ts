// GENERATED FROM interfaces/schema — DO NOT EDIT
// Source: CommandRequest.schema.json, DiscoverRequest.schema.json, DiscoverResponse.schema.json, EventEnvelope.schema.json, InvokeResponse.schema.json, QueryRequest.schema.json, QueryResponse.schema.json, SubscribeRequest.schema.json, SubscribeResponse.schema.json
// Generator: scripts/generate.ts

import { z } from "zod";
import { ComponentStatusSchema, StreamStatusSchema } from "../common";
import { ArgumentSchema, CommandTypeSchema, CommandUnitSequenceSchema, ParameterSchema, ResultSchema, ReturnCodeSchema } from "../hri";
import { CompletedStatusSchema, ErrorTypeSchema } from "../service";

/**
 * Generic command request sent via ComponentContract.invoke().
 * 
 * Carries the same information as a CommandUnit plus the target component_ref.
 * Typed component models (e.g., NavigationSetParameter) serialize their fields
 * into arguments/parameters and are wrapped in this generic container.
 */

export const CommandRequestSchema = z.object({
  component_ref: z.string(), // Target component instance ref
  command_type: CommandTypeSchema, // Command operation: start, stop, suspend, resume, set_parameter, execute
  command_id: z.string(), // Unique command instance identifier
  arguments: z.array(ArgumentSchema).optional(),
  parameters: z.array(ParameterSchema).optional(), // Named parameter values for set_parameter-style commands
  command_unit_sequence: CommandUnitSequenceSchema.nullable().default(null), // Structured command sequence for execute()
}).strict();
export type CommandRequest = z.infer<typeof CommandRequestSchema>;

/**
 * Request to discover components matching a condition.
 * 
 * Maps to CommandIF.search(condition, component_ref_list).
 */

export const DiscoverRequestSchema = z.object({
  condition: z.string().default(""), // ISO 19143 filter expression; empty means all components
}).strict();
export type DiscoverRequest = z.infer<typeof DiscoverRequestSchema>;

/** Response from discover() carrying matching component references. */

export const DiscoverResponseSchema = z.object({
  return_code: ReturnCodeSchema.default("OK"),
  component_ref_list: z.array(z.string()).optional(),
}).strict();
export type DiscoverResponse = z.infer<typeof DiscoverResponseSchema>;

/**
 * Generic event envelope delivered to an EventSink.
 * 
 * The ComponentContract emits this for every async notification: component events,
 * command completion, errors, and stream status changes. The engine/gateway
 * inspects event_type and dispatches to the appropriate ServiceApplicationBase
 * callback.
 */

export const EventEnvelopeSchema = z.object({
  event_id: z.string(), // Unique identifier for this event occurrence
  event_type: z.string(), // Event type, e.g. person_detected, completed, notify_error
  subscribe_id: z.string().default(""), // Subscription identifier this event matches, if any
  component_ref: z.string().default(""), // Component ref that emitted the event, if any
  expire: z.string().default(""), // ISO 8601 datetime when this event expires
  payload: z.array(ResultSchema).optional(), // Event payload as generic results; typed by component profile
  error_type: ErrorTypeSchema.nullable().default(null), // Error classification when event_type is notify_error
  completed_status: CompletedStatusSchema.nullable().default(null), // Completion status when event_type is completed
  stream_status: StreamStatusSchema.nullable().default(null), // Stream status when event_type is notify_stream_status
  component_status: ComponentStatusSchema.nullable().default(null), // Component status when event_type is component_status
}).strict();
export type EventEnvelope = z.infer<typeof EventEnvelopeSchema>;

/** Response from ComponentContract.invoke(). */

export const InvokeResponseSchema = z.object({
  return_code: ReturnCodeSchema.default("OK"),
  command_id: z.string().default(""), // Identifier for the invoked command; empty for synchronous ops
  results: z.array(ResultSchema).optional(), // Immediate results, if any; typed by component profile
}).strict();
export type InvokeResponse = z.infer<typeof InvokeResponseSchema>;

/**
 * Generic query request sent via ComponentContract.query().
 * 
 * Maps to QueryIF.query(query_type, condition, results) and
 * RoIS_Common.component_status(status).
 */

export const QueryRequestSchema = z.object({
  component_ref: z.string(), // Target component instance ref
  query_type: z.string(), // Query operation name
  condition: z.string().default(""), // Optional filter expression for the query
}).strict();
export type QueryRequest = z.infer<typeof QueryRequestSchema>;

/** Response from ComponentContract.query(). */

export const QueryResponseSchema = z.object({
  return_code: ReturnCodeSchema.default("OK"),
  results: z.array(ResultSchema).optional(), // Query results; typed by component profile
}).strict();
export type QueryResponse = z.infer<typeof QueryResponseSchema>;

/**
 * Request to subscribe to events matching a condition.
 * 
 * Maps to EventIF.subscribe(event_type, condition, subscribe_id).
 */

export const SubscribeRequestSchema = z.object({
  component_ref: z.string(), // Target component instance ref
  event_type: z.string(), // Event type to subscribe to
  condition: z.string().default(""), // Optional filter expression for the subscription
}).strict();
export type SubscribeRequest = z.infer<typeof SubscribeRequestSchema>;

/** Response from ComponentContract.subscribe(). */

export const SubscribeResponseSchema = z.object({
  return_code: ReturnCodeSchema.default("OK"),
  subscribe_id: z.string().default(""), // Identifier for the active subscription
}).strict();
export type SubscribeResponse = z.infer<typeof SubscribeResponseSchema>;
