// GENERATED FROM interfaces/schema — DO NOT EDIT
// Source: ComponentStatus.schema.json, StreamStatus.schema.json
// Generator: scripts/generate.ts

import { z } from "zod";

// ─── Numeric type aliases (from RoIS_Common.idl) ────────────────

/** Numeric representation of StreamStatus for wire compatibility. */
export type StreamStatusT = number;

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
