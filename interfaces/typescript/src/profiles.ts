// GENERATED FROM interfaces/schema — DO NOT EDIT
// Source: CommandMessageProfile.schema.json, ComponentFunction.schema.json, EventMessageProfile.schema.json, HRIComponentProfile.schema.json, HRIEngineProfileType.schema.json, MessageProfile.schema.json, ParameterProfile.schema.json, QueryMessageProfile.schema.json, RoISIdentifierType.schema.json
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
 * The RoSO function class of a component.
 * 
 * Not part of XML-Profiles.xsd. The values are the Robotic Service Function
 * Ontology classes that the spec's ontology file assigns to the basic components:
 * Navigation, Reaction and SpeechSynthesis are Actuation, the detection,
 * localization and recognition components are Sensing, and AudioStreaming is the
 * generic Function class. An engine requires a bind before commands on an
 * actuation component.
 * 
 * ACTUATION: The component acts on the world (moves, speaks, shows).
 * SENSING: The component observes the world.
 * FUNCTION: The component is neither, for example a stream.
 */

export const ComponentFunctionSchema = z.enum(["actuation", "sensing", "function"]);
export type ComponentFunction = z.infer<typeof ComponentFunctionSchema>;

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
 * Describes an HRI Engine's composition of sub-engines and components.
 * 
 * Maps to HRIEngineProfileType in XML-Profiles.xsd, field for field. The profile
 * names its components by ref only, as the XSD does. The get_profile result carries
 * their HRIComponentProfiles next to it.
 * 
 * Attributes:
 *     identifier: The engine's structured identifier.
 *     sub_profiles: One profile per child engine (XSD SubProfile).
 *     component_ids: Fully qualified refs of every component reachable through this
 *         engine, including the components of its child engines (XSD HRIComponent).
 *     parameter_profiles: Engine-level parameter declarations.
 */

export interface HRIEngineProfileType {
  identifier: RoISIdentifierType;
  sub_profiles?: HRIEngineProfileType[];
  component_ids?: string[];
  parameter_profiles?: ParameterProfile[];
}
export const HRIEngineProfileTypeSchema: z.ZodType<any> = z.lazy(() => z.object({
    identifier: RoISIdentifierTypeSchema,
    sub_profiles: z.array(HRIEngineProfileTypeSchema).optional(),
    component_ids: z.array(z.string()).optional(),
    parameter_profiles: z.array(ParameterProfileSchema).optional(),
  }).strict());


/**
 * Describes a RoIS component's capabilities, messages, and parameters.
 * 
 * Maps to HRIComponentProfileType in XML-Profiles.xsd. One profile describes one
 * component instance: its messages are the ones that instance supports.
 * 
 * Attributes:
 *     identifier: The component type, for example authority 'OMG' and code
 *         'PersonDetection' for urn:x-rois:def:component:OMG::PersonDetection.
 *     name: A short human-readable name (e.g., 'person_detecter').
 *     function: The RoSO function class. An OpenRoIS extension: the XSD has no
 *         such element.
 *     sub_component_profiles: URNs of sub-component profiles (e.g., RoISCommon).
 *     command_profiles: Command message profiles this component supports.
 *     query_profiles: Query message profiles this component supports.
 *     event_profiles: Event message profiles this component supports.
 *     parameter_profiles: Parameter declarations for this component.
 */

export const HRIComponentProfileSchema = z.object({
  identifier: RoISIdentifierTypeSchema,
  name: z.string(),
  function: ComponentFunctionSchema.nullable().default(null), // RoSO function class (OpenRoIS extension)
  sub_component_profiles: z.array(z.string()).optional(),
  command_profiles: z.array(CommandMessageProfileSchema).optional(),
  query_profiles: z.array(QueryMessageProfileSchema).optional(),
  event_profiles: z.array(EventMessageProfileSchema).optional(),
  parameter_profiles: z.array(ParameterProfileSchema).optional(),
}).strict();
export type HRIComponentProfile = z.infer<typeof HRIComponentProfileSchema>;

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
