// GENERATED FROM interfaces/schema — DO NOT EDIT
// Source: SystemInformationEngineStatusResult.schema.json, SystemInformationRobotPositionResult.schema.json
// Generator: scripts/generate.ts

import { z } from "zod";
import { ComponentStatusSchema } from "../common";

/**
 * Result payload for System_Information::Query::engine_status.
 * 
 * Maps to the engine_status query in SystemInformation.xml.
 * 
 * Attributes:
 *     status: Current component status of the engine.
 *     operable_time: List of ISO 8601 datetimes representing operable periods.
 */

export const SystemInformationEngineStatusResultSchema = z.object({
  status: ComponentStatusSchema, // Engine component status
  operable_time: z.array(z.string()), // Operable time periods
}).strict();
export type SystemInformationEngineStatusResult = z.infer<typeof SystemInformationEngineStatusResultSchema>;

/**
 * Result payload for System_Information::Query::robot_position.
 * 
 * Maps to the robot_position query in SystemInformation.xml.
 * 
 * Attributes:
 *     timestamp: ISO 8601 datetime when the position was measured.
 *     robot_ref: List of robot identifiers in the position data.
 *     position_data: Positional/measurement data (RoLo Data sequence as strings).
 */

export const SystemInformationRobotPositionResultSchema = z.object({
  timestamp: z.string(), // Time when measured
  robot_ref: z.array(z.string()), // List of robot IDs
  position_data: z.array(z.string()), // Position data (RoLo Data sequence)
}).strict();
export type SystemInformationRobotPositionResult = z.infer<typeof SystemInformationRobotPositionResultSchema>;
