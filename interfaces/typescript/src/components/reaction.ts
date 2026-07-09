// GENERATED FROM interfaces/schema — DO NOT EDIT
// Source: ReactionGetParameterResult.schema.json, ReactionSetParameter.schema.json, ReactionSetParameterResult.schema.json, ReactionStatusResult.schema.json
// Generator: scripts/generate.ts

import { z } from "zod";

// ─── Shared type definitions ($defs) ─────────────────────────────

export const RoISIdentifierListSchema = z.array(z.string());
export type RoISIdentifierList = z.infer<typeof RoISIdentifierListSchema>;

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
 * Result payload for Reaction::Query::get_parameter.
 * 
 * Maps to the get_parameter operation in RoIS_Reaction.idl, which returns the
 * list of available reactions and the currently selected reaction reference.
 * 
 * Attributes:
 *     available_reactions: List of reaction identifiers this host can perform.
 *     reaction_ref: Currently selected reaction identifier.
 */

export const ReactionGetParameterResultSchema = z.object({
  available_reactions: RoISIdentifierListSchema, // List of available reaction identifiers this host can perform
  reaction_ref: z.string(), // Currently selected reaction identifier
}).strict();
export type ReactionGetParameterResult = z.infer<typeof ReactionGetParameterResultSchema>;

/**
 * Command payload for Reaction::Command::set_parameter.
 * 
 * Maps to the set_parameter operation in RoIS_Reaction.idl, which takes a
 * ``RoIS_IdentifierList`` of reaction references. The XML profile declares
 * ``reaction_ref`` as a single ``RoISIdentifier`` parameter, but the IDL
 * operation signature accepts a list, so the model uses a list to match the
 * operation contract.
 * 
 * Attributes:
 *     reaction_ref: List of reaction identifiers to trigger. Each identifier
 *         is an opaque string whose meaning is defined by the host backend
 *         (e.g., "wave", "nod", "smile" for an avatar, or "led_green" for a
 *         robot).
 */

export const ReactionSetParameterSchema = z.object({
  reaction_ref: RoISIdentifierListSchema, // Reaction identifiers to trigger
}).strict();
export type ReactionSetParameter = z.infer<typeof ReactionSetParameterSchema>;

/**
 * Result of Reaction set_parameter command.
 * 
 * Attributes:
 *     command_id: The assigned command identifier for this reaction command.
 */

export const ReactionSetParameterResultSchema = z.object({
  command_id: z.string(),
}).strict();
export type ReactionSetParameterResult = z.infer<typeof ReactionSetParameterResultSchema>;

/**
 * Result model for Reaction component_status query.
 * 
 * Attributes:
 *     status: Current status of the Reaction component.
 */

export const ReactionStatusResultSchema = z.object({
  status: ComponentStatusSchema,
}).strict();
export type ReactionStatusResult = z.infer<typeof ReactionStatusResultSchema>;
