// GENERATED FROM interfaces/schema — DO NOT EDIT
// Source: CommandMessageProfile.schema.json, EventMessageProfile.schema.json, HRIComponentProfile.schema.json, HRIEngineProfileType.schema.json, MessageProfile.schema.json, ParameterProfile.schema.json, QueryMessageProfile.schema.json, RoISIdentifierType.schema.json
// Generator: scripts/generate.ts

import { z } from "zod";

// ─── Shared type definitions ($defs) ─────────────────────────────

/**
 * A structured RoIS identifier with optional metadata.
 * 
 * Maps to RoISIdentifierType in XML-Profiles.xsd.
 * 
 * Attributes:
 *     authority: Optional naming authority (e.g., 'OMG').
 *     code: The identifier code (e.g., 'PersonDetection').
 *     codebook_ref: Optional reference to a codebook or ontology.
 *     version: Optional version string.
 */

export const RoISIdentifierTypeSchema = z.object({
  authority: z.string().default(""),
  code: z.string(),
  codebook_ref: z.string().default(""),
  version: z.string().default(""),
}).strict();
export type RoISIdentifierType = z.infer<typeof RoISIdentifierTypeSchema>;

/**
 * Describes a parameter's data type and metadata.
 * 
 * Maps to ParameterProfileType in XML-Profiles.xsd.
 * 
 * Used in both message profiles (Arguments/Results) and component-level
 * parameter declarations.
 * 
 * Attributes:
 *     name: The parameter name.
 *     data_type_ref: Reference to the data type (e.g., 'int', 'DateTime',
 *         'RoISIdentifier[]').
 *     default_value: Optional default value as a string.
 *     description: Optional human-readable description.
 */

export const ParameterProfileSchema = z.object({
  name: z.string(),
  data_type_ref: RoISIdentifierTypeSchema,
  default_value: z.string().default(""),
  description: z.string().default(""),
}).strict();
export type ParameterProfile = z.infer<typeof ParameterProfileSchema>;

/**
 * A command message profile with arguments and optional timeout.
 * 
 * Maps to CommandMessageProfileType in XML-Profiles.xsd.
 * 
 * Attributes:
 *     arguments: The input arguments for this command.
 *     timeout: Optional timeout in milliseconds.
 */

export const CommandMessageProfileSchema = z.object({
  name: z.string(),
  results: z.array(ParameterProfileSchema).optional(),
  arguments: z.array(ParameterProfileSchema).optional(),
  timeout: z.number().int().nullable().default(null),
}).strict();
export type CommandMessageProfile = z.infer<typeof CommandMessageProfileSchema>;

/**
 * An event message profile.
 * 
 * Maps to EventMessageProfileType in XML-Profiles.xsd.
 * 
 * Events have results (the event payload) but no arguments.
 */

export const EventMessageProfileSchema = z.object({
  name: z.string(),
  results: z.array(ParameterProfileSchema).optional(),
}).strict();
export type EventMessageProfile = z.infer<typeof EventMessageProfileSchema>;

/**
 * A query message profile.
 * 
 * Maps to QueryMessageProfileType in XML-Profiles.xsd.
 * 
 * Queries have results but no arguments (the query_type and condition
 * are passed separately, not as message arguments).
 */

export const QueryMessageProfileSchema = z.object({
  name: z.string(),
  results: z.array(ParameterProfileSchema).optional(),
}).strict();
export type QueryMessageProfile = z.infer<typeof QueryMessageProfileSchema>;

/**
 * Describes a RoIS component's capabilities, messages, and parameters.
 * 
 * Maps to HRIComponentProfileType in XML-Profiles.xsd.
 * 
 * Attributes:
 *     identifier: The component's structured identifier (URN).
 *     name: A short human-readable name (e.g., 'person_detecter').
 *     sub_component_profiles: URNs of sub-component profiles (e.g., RoISCommon).
 *     command_profiles: Command message profiles this component supports.
 *     query_profiles: Query message profiles this component supports.
 *     event_profiles: Event message profiles this component supports.
 *     parameter_profiles: Parameter declarations for this component.
 */

export const HRIComponentProfileSchema = z.object({
  identifier: RoISIdentifierTypeSchema,
  name: z.string(),
  sub_component_profiles: z.array(z.string()).optional(),
  command_profiles: z.array(CommandMessageProfileSchema).optional(),
  query_profiles: z.array(QueryMessageProfileSchema).optional(),
  event_profiles: z.array(EventMessageProfileSchema).optional(),
  parameter_profiles: z.array(ParameterProfileSchema).optional(),
}).strict();
export type HRIComponentProfile = z.infer<typeof HRIComponentProfileSchema>;

/**
 * Describes an HRI Engine's composition of sub-engines and components.
 * 
 * Maps to HRIEngineProfileType in XML-Profiles.xsd.
 * 
 * Attributes:
 *     identifier: The engine's structured identifier.
 *     sub_profiles: Nested sub-engine profiles.
 *     component_ids: IDs of components hosted by this engine.
 *     component_profiles: Full capability profiles for each component.
 *         Populated from adapter registration data. Optional (default
 *         empty) for backward compatibility with engines that only
 *         return component_ids.
 *     parameter_profiles: Engine-level parameter declarations.
 */

export interface HRIEngineProfileType {
  identifier: RoISIdentifierType;
  sub_profiles?: HRIEngineProfileType[];
  component_ids?: string[];
  component_profiles?: HRIComponentProfile[];
  parameter_profiles?: ParameterProfile[];
}
export const HRIEngineProfileTypeSchema: z.ZodType<any> = z.lazy(() => z.object({
    identifier: RoISIdentifierTypeSchema,
    sub_profiles: z.array(HRIEngineProfileTypeSchema).optional(),
    component_ids: z.array(z.string()).optional(),
    component_profiles: z.array(HRIComponentProfileSchema).optional(),
    parameter_profiles: z.array(ParameterProfileSchema).optional(),
  }).strict());


/**
 * Base message profile describing a command, query, or event message.
 * 
 * Maps to MessageProfileType in XML-Profiles.xsd.
 * 
 * Attributes:
 *     name: The message name (e.g., 'person_detected', 'set_parameter').
 *     results: The result parameters of this message.
 */

export const MessageProfileSchema = z.object({
  name: z.string(),
  results: z.array(ParameterProfileSchema).optional(),
}).strict();
export type MessageProfile = z.infer<typeof MessageProfileSchema>;
