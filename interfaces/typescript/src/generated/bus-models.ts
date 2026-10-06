// GENERATED FROM interfaces/schema — DO NOT EDIT
// Source: CommandRequest.schema.json, DiscoverRequest.schema.json, DiscoverResponse.schema.json, EventEnvelope.schema.json, InvokeResponse.schema.json, QueryRequest.schema.json, QueryResponse.schema.json, SubscribeRequest.schema.json, SubscribeResponse.schema.json
// Generator: scripts/generate.ts

import { z } from "zod";

// ─── Shared type definitions ($defs) ─────────────────────────────

/**
 * A named argument for command execution.
 * 
 * Maps to RoIS_HRI::Argument in the IDL.
 * 
 * Attributes:
 *     name: The argument name.
 *     data_type_ref: Reference to the data type.
 *     value: The argument value as a string.
 */

export const ArgumentSchema = z.object({
  name: z.string(),
  data_type_ref: z.string(),
  value: z.string(),
}).strict();
export type Argument = z.infer<typeof ArgumentSchema>;

export const ArgumentListSchema = z.array(ArgumentSchema);
export type ArgumentList = z.infer<typeof ArgumentListSchema>;

/**
 * Command operation type for RoIS commands.
 * 
 * Not an IDL enum — the IDL uses plain `string` for command_type. OpenRoIS
 * defines this enum for compile-time safety. The wire values match the
 * RoIS_Common::Command method names plus `set_parameter` and `execute`.
 */

export const CommandTypeSchema = z.enum(["start", "stop", "suspend", "resume", "set_parameter", "execute"]);
export type CommandType = z.infer<typeof CommandTypeSchema>;

/**
 * A single command within a CommandUnitSequence.
 * 
 * Maps to CommandMessageType in XML-Profiles.xsd (CommandBaseType subtype).
 * 
 * Attributes:
 *     component_ref: The component to send the command to.
 *     command_type: The command operation (e.g., 'start', 'stop',
 *         'set_parameter', 'execute').
 *     command_id: Unique identifier for this command instance.
 *     arguments: Optional list of arguments for the command.
 *     delay_time: Optional delay in milliseconds before executing this command.
 */

export const CommandUnitSchema = z.object({
  component_ref: z.string(),
  command_type: CommandTypeSchema, // Command operation: start, stop, suspend, resume, set_parameter, execute
  command_id: z.string(), // Unique command instance identifier
  arguments: ArgumentListSchema.optional(),
  delay_time: z.number().int().nullable().default(null), // Delay in ms before execution
}).strict();
export type CommandUnit = z.infer<typeof CommandUnitSchema>;

/**
 * A group of commands to be executed concurrently.
 * 
 * Maps to ConcurrentCommandsType in XML-Profiles.xsd.
 * 
 * Attributes:
 *     command_list: The commands to execute in parallel.
 *     delay_time: Optional delay in milliseconds before executing this group.
 */

export const ConcurrentCommandsSchema = z.object({
  command_list: z.array(CommandUnitSchema),
  delay_time: z.number().int().nullable().default(null), // Delay in ms before execution
}).strict();
export type ConcurrentCommands = z.infer<typeof ConcurrentCommandsSchema>;

export const CommandUnitSequenceItemSchema = z.union([CommandUnitSchema, ConcurrentCommandsSchema]);
export type CommandUnitSequenceItem = z.infer<typeof CommandUnitSequenceItemSchema>;

/**
 * An ordered sequence of command units (sequential and/or concurrent).
 * 
 * Maps to CommandUnitSequenceType in XML-Profiles.xsd. The IDL typedefs this
 * as `string`, but the XSD defines a rich structure with sequential and
 * concurrent branches. We model the structured form; the string representation
 * is the wire serialization format.
 * 
 * Attributes:
 *     command_unit_list: Ordered list of command units and/or concurrent groups.
 */

export const CommandUnitSequenceSchema = z.object({
  command_unit_list: z.array(CommandUnitSequenceItemSchema), // Ordered sequence of command units (sequential) and concurrent groups
}).strict();
export type CommandUnitSequence = z.infer<typeof CommandUnitSequenceSchema>;

/**
 * A named parameter for command operations (set_parameter, execute).
 * 
 * Maps to RoIS_HRI::Parameter in the IDL.
 * 
 * Attributes:
 *     name: The parameter name (e.g., 'target_position', 'time_limit').
 *     data_type_ref: Reference to the data type.
 *     value: The parameter value as a string.
 */

export const ParameterSchema = z.object({
  name: z.string(),
  data_type_ref: z.string(),
  value: z.string(),
}).strict();
export type Parameter = z.infer<typeof ParameterSchema>;

export const ParameterListSchema = z.array(ParameterSchema);
export type ParameterList = z.infer<typeof ParameterListSchema>;

/**
 * Return code for all RoIS operations.
 * 
 * Maps to RoIS_HRI::ReturnCode_t in the IDL.
 */

export const ReturnCodeSchema = z.enum(["OK", "ERROR", "BAD_PARAMETER", "UNSUPPORTED", "OUT_OF_RESOURCES", "TIMEOUT"]);
export type ReturnCode = z.infer<typeof ReturnCodeSchema>;

export const RoISIdentifierListSchema = z.array(z.string());
export type RoISIdentifierList = z.infer<typeof RoISIdentifierListSchema>;

/**
 * Status of a completed command execution.
 * 
 * Maps to RoIS_Service::Completed_Status in the IDL.
 * 
 * OK: Command completed successfully.
 * ERROR: Command completed with an error.
 * ABORT: Command was aborted.
 * OUT_OF_RESOURCES: Command failed due to resource exhaustion.
 * TIMEOUT: Command timed out before completion.
 */

export const CompletedStatusSchema = z.enum(["OK", "ERROR", "ABORT", "OUT_OF_RESOURCES", "TIMEOUT"]);
export type CompletedStatus = z.infer<typeof CompletedStatusSchema>;

/**
 * Status of a RoIS component.
 * 
 * Maps to RoIS_Common::Component_Status in the IDL.
 * 
 * UNINITIALIZED: Component has not been initialized.
 * READY: Component is ready to operate.
 * BUSY: Component is currently processing.
 * WARNING: Component is operational but has a warning condition.
 * ERROR: Component has encountered an error.
 */

export const ComponentStatusSchema = z.enum(["UNINITIALIZED", "READY", "BUSY", "WARNING", "ERROR"]);
export type ComponentStatus = z.infer<typeof ComponentStatusSchema>;

/**
 * Classification of error notifications.
 * 
 * Maps to RoIS_Service::ErrorType in the IDL.
 * 
 * ENGINE_INTERNAL_ERROR: Error originating from the HRI Engine itself.
 * COMPONENT_INTERNAL_ERROR: Error originating from a component.
 * COMPONENT_NOT_RESPONDING: A component failed to respond within timeout.
 * USER_DEFINED_ERROR: Application-specific error.
 */

export const ErrorTypeSchema = z.enum(["ENGINE_INTERNAL_ERROR", "COMPONENT_INTERNAL_ERROR", "COMPONENT_NOT_RESPONDING", "USER_DEFINED_ERROR"]);
export type ErrorType = z.infer<typeof ErrorTypeSchema>;

/**
 * A named result value returned by query or event operations.
 * 
 * Maps to RoIS_HRI::Result in the IDL.
 * 
 * Attributes:
 *     name: The result parameter name (e.g., 'number', 'timestamp').
 *     data_type_ref: Reference to the data type (e.g., 'int', 'DateTime').
 *     value: The result value as a string. Component-specific typed models
 *         provide structured access.
 */

export const ResultSchema = z.object({
  name: z.string(),
  data_type_ref: z.string(),
  value: z.string(),
}).strict();
export type Result = z.infer<typeof ResultSchema>;

export const ResultListSchema = z.array(ResultSchema);
export type ResultList = z.infer<typeof ResultListSchema>;

/**
 * Status of a streaming connection.
 * 
 * Maps to RoIS_Common::Stream_Status in the IDL.
 * 
 * NOT_CONNECTED: No peer connection established.
 * NOT_RUNNING: Connection exists but stream is not active.
 * RUNNING: Stream is actively delivering data.
 * SUSPENDED: Stream has been suspended (track disabled).
 * RESUMED: Stream has been resumed after suspension.
 */

export const StreamStatusSchema = z.enum(["STREAMING_NOT_CONNECTED", "STREAMING_NOT_RUNNING", "STREAMING_RUNNING", "STREAMING_SUSPENDED", "STREAMING_RESUMED"]);
export type StreamStatus = z.infer<typeof StreamStatusSchema>;


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
  arguments: ArgumentListSchema.optional(),
  parameters: ParameterListSchema.optional(), // Named parameter values for set_parameter-style commands
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
  component_ref_list: RoISIdentifierListSchema.optional(),
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
  payload: ResultListSchema.optional(), // Event payload as generic results; typed by component profile
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
  results: ResultListSchema.optional(), // Immediate results, if any; typed by component profile
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
  results: ResultListSchema.optional(), // Query results; typed by component profile
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
