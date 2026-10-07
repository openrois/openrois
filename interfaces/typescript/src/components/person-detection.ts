// GENERATED FROM interfaces/schema — DO NOT EDIT
// Source: PersonDetectedEvent.schema.json, PersonDetectionStatusResult.schema.json
// Generator: scripts/generate.ts

import { z } from "zod";
import { ComponentStatusSchema } from "../common";

/**
 * Event payload for Person_Detection::Event::person_detected.
 * 
 * Maps to the person_detected event in PersonDetection.xml.
 * 
 * Attributes:
 *     timestamp: ISO 8601 datetime when the detection was measured.
 *     number: Number of detected persons in the current frame/observation.
 */

export const PersonDetectedEventSchema = z.object({
  timestamp: z.string(), // Time when measured
  number: z.number().int(), // Number of detected persons
}).strict();
export type PersonDetectedEvent = z.infer<typeof PersonDetectedEventSchema>;

/**
 * Result model for PersonDetection component_status query.
 * 
 * Attributes:
 *     status: Current status of the PersonDetection component.
 */

export const PersonDetectionStatusResultSchema = z.object({
  status: ComponentStatusSchema,
}).strict();
export type PersonDetectionStatusResult = z.infer<typeof PersonDetectionStatusResultSchema>;
