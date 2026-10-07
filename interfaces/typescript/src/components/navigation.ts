// GENERATED FROM interfaces/schema — DO NOT EDIT
// Source: NavigationGetParameterResult.schema.json, NavigationReachedTargetEvent.schema.json, NavigationSetParameter.schema.json, NavigationSetParameterResult.schema.json, NavigationStatusResult.schema.json
// Generator: scripts/generate.ts

import { z } from "zod";
import { ComponentStatusSchema } from "../common";

// ─── Shared type definitions ($defs) ─────────────────────────────

/**
 * Routing policy for Navigation.
 * 
 * The XML profile defines routing_policy as a string with values 'time'
 * or 'distance'. We constrain it to an enum for compile-time safety.
 */

export const RoutingPolicySchema = z.enum(["time", "distance"]);
export type RoutingPolicy = z.infer<typeof RoutingPolicySchema>;


/**
 * Result payload for Navigation::Query::get_parameter.
 * 
 * Maps to the get_parameter operation in Navigation.xml.
 * 
 * Attributes:
 *     target_positions: Current navigation target positions.
 *     time_limit: Current time limit setting.
 *     routing_policy: Current routing policy setting.
 */

export const NavigationGetParameterResultSchema = z.object({
  target_positions: z.array(z.string()), // Current navigation target positions
  time_limit: z.number().int(), // Current time limit setting
  routing_policy: RoutingPolicySchema, // Current routing policy setting
}).strict();
export type NavigationGetParameterResult = z.infer<typeof NavigationGetParameterResultSchema>;

/**
 * Event payload for Navigation::Event::reached_target.
 * 
 * Maps to the reached_target event in Navigation.xml.
 * 
 * Attributes:
 *     target: The reached target destination.
 *     is_final_target: Whether this is the final destination point.
 */

export const NavigationReachedTargetEventSchema = z.object({
  target: z.string(), // Reached target destination
  is_final_target: z.boolean(), // Whether this is the final destination point
}).strict();
export type NavigationReachedTargetEvent = z.infer<typeof NavigationReachedTargetEventSchema>;

/**
 * Command payload for Navigation::Command::set_parameter.
 * 
 * Maps to the set_parameter operation in Navigation.xml.
 * 
 * Attributes:
 *     target_positions: Navigation target positions as structured data.
 *         In the XML profile, data_type_ref is 'string[]'.
 *     time_limit: Intended time limit to complete navigation (default: 0).
 *     routing_policy: Routing policy: 'time' priority or 'distance' priority
 *         (default: 'time').
 */

export const NavigationSetParameterSchema = z.object({
  target_positions: z.array(z.string()), // Navigation target positions
  time_limit: z.number().int().default(0), // Intended time limit to complete navigation
  routing_policy: RoutingPolicySchema.default("time"), // Routing policy: 'time' or 'distance' priority
}).strict();
export type NavigationSetParameter = z.infer<typeof NavigationSetParameterSchema>;

/**
 * Result of Navigation set_parameter command.
 * 
 * Attributes:
 *     command_id: The assigned command identifier for this navigation command.
 */

export const NavigationSetParameterResultSchema = z.object({
  command_id: z.string(),
}).strict();
export type NavigationSetParameterResult = z.infer<typeof NavigationSetParameterResultSchema>;

/**
 * Result model for Navigation component_status query.
 * 
 * Attributes:
 *     status: Current status of the Navigation component.
 */

export const NavigationStatusResultSchema = z.object({
  status: ComponentStatusSchema,
}).strict();
export type NavigationStatusResult = z.infer<typeof NavigationStatusResultSchema>;
