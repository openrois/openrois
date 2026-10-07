// GENERATED FROM interfaces/schema — DO NOT EDIT
// Source: CompletedParams.schema.json, CompletedStatus.schema.json, ErrorType.schema.json, NotifyErrorParams.schema.json, NotifyEventParams.schema.json, ProfileChangedParams.schema.json
// Generator: scripts/generate.ts

import { z } from "zod";
import { ResultSchema } from "./hri";

// ─── Shared type definitions ($defs) ─────────────────────────────

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
 * Params of the rois.command.completed notification.
 * 
 * Maps to ServiceApplicationBase::completed(in command_id, in status). The results
 * come from CommandIF::get_command_result(command_id).
 * 
 * Attributes:
 *     command_id: The command that ended, as the application named it.
 *     status: How the command ended.
 */

export const CompletedParamsSchema = z.object({
  command_id: z.string(), // The command that ended
  status: CompletedStatusSchema,
}).strict();
export type CompletedParams = z.infer<typeof CompletedParamsSchema>;

/**
 * Params of the rois.system.notify_error notification.
 * 
 * Maps to ServiceApplicationBase::notify_error(in error_id, in error_type). The
 * details come from SystemIF::get_error_detail(error_id).
 * 
 * Attributes:
 *     error_id: Identifier of this error, for get_error_detail.
 *     error_type: Classification of the error.
 */

export const NotifyErrorParamsSchema = z.object({
  error_id: z.string(), // Identifier of this error, for get_error_detail
  error_type: ErrorTypeSchema,
}).strict();
export type NotifyErrorParams = z.infer<typeof NotifyErrorParamsSchema>;

/**
 * Params of the rois.event.notify_event notification.
 * 
 * Maps to ServiceApplicationBase::notify_event(in event_id, in event_type,
 * in subscribe_id, in expire). The payload also comes from
 * EventIF::get_event_detail(event_id) until the event expires.
 * 
 * Attributes:
 *     event_id: Identifier of this event, for get_event_detail.
 *     event_type: The type of event (e.g., 'person_detected').
 *     subscribe_id: The subscription this event matches.
 *     expire: ISO 8601 datetime after which get_event_detail no longer has the
 *         event, or empty if it does not expire.
 *     results: The event payload. An OpenRoIS extension that saves one
 *         get_event_detail round trip per event.
 */

export const NotifyEventParamsSchema = z.object({
  event_id: z.string(), // Identifier of this event, for get_event_detail
  event_type: z.string(),
  subscribe_id: z.string(),
  expire: z.string().default(""),
  results: z.array(ResultSchema).optional(), // The event payload (OpenRoIS extension)
}).strict();
export type NotifyEventParams = z.infer<typeof NotifyEventParamsSchema>;

/**
 * Params of the rois.system.profile_changed notification.
 * 
 * Not part of RoIS: an OpenRoIS extension. The engine sends it when its profile
 * changes, for example when a child engine connects or disconnects, so a client
 * calls get_profile again instead of polling it. It carries no params.
 */

export const ProfileChangedParamsSchema = z.object({}).strict();
export type ProfileChangedParams = z.infer<typeof ProfileChangedParamsSchema>;
