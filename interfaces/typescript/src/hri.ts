// GENERATED FROM interfaces/schema — DO NOT EDIT
// Source: Argument.schema.json, CommandUnit.schema.json, CommandUnitSequence.schema.json, ConcurrentCommands.schema.json, Parameter.schema.json, Result.schema.json, ReturnCode.schema.json
// Generator: scripts/generate.ts

import { z } from "zod";

// ─── Semantic type aliases (from RoIS_HRI.idl) ──────────────────

/** Unique identifier for a component, sub-engine, or other RoIS entity. */
export type RoISIdentifier = string;
/** Ordered list of RoIS identifiers. */
export type RoISIdentifierList = RoISIdentifier[];
/** ISO 19143 filter expression used by search(), query(), subscribe(). */
export type ConditionT = string;
/** XML profile document describing an HRI Engine's capabilities. */
export type HRIEngineProfile = string;
/** ISO 8601 datetime string. */
export type DateTime = string;
/**
 * IDL `typedef long Integer` — 32-bit signed integer.
 *
 * Note: The zod schema validates that the value is an integer but does not
 * enforce the 32-bit range (±2^31). Values outside this range will pass
 * TypeScript validation but may overflow in C# consumers (where `int` is
 * 32-bit). This is a known limitation to be addressed in a future release.
 */
export type Integer = number;
/** Positional or measurement data from the RoLo Architecture module. */
export type RoLoData = string;
/** Ordered list of Result values. */
export type ResultList = Result[];
/** Ordered list of Parameter values. */
export type ParameterList = Parameter[];

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
 * Not an IDL enum: the IDL uses plain `string` for command_type. OpenRoIS
 * defines this enum for compile-time safety. The wire values match the
 * RoIS_Common::Command method names plus `set_parameter` and `execute`, and
 * the stream control commands of the Audio and Video Streaming profiles.
 */

export const CommandTypeSchema = z.enum(["start", "stop", "suspend", "resume", "set_parameter", "execute", "connect_stream", "disconnect_stream", "suspend_stream", "resume_stream"]);
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

/**
 * Return code for all RoIS operations.
 * 
 * Maps to RoIS_HRI::ReturnCode_t in the IDL.
 */

export const ReturnCodeSchema = z.enum(["OK", "ERROR", "BAD_PARAMETER", "UNSUPPORTED", "OUT_OF_RESOURCES", "TIMEOUT"]);
export type ReturnCode = z.infer<typeof ReturnCodeSchema>;
