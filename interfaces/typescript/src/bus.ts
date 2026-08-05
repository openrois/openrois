/**
 * Transport-neutral bus adapter contract for OpenRoIS.
 *
 * This module defines the BusAdapter interface — the only boundary the RoIS
 * engine and gateway depend on. Every concrete bus (in-process, ROS 2, gRPC,
 * WebSocket, etc.) implements this four-method contract:
 *
 *   discover  → CommandIF.search
 *   invoke    → CommandIF.bind/set_parameter/execute/start/stop/suspend/resume
 *   query     → QueryIF.query / RoIS_Common.component_status
 *   subscribe → EventIF.subscribe (async push via EventSink)
 *
 * The contract is intentionally transport-agnostic. No ROS, DDS, gRPC,
 * WebSocket, or socket symbols appear here.
 *
 * The request/response models and EventEnvelope are generated from JSON Schema
 * in `./generated/bus-models.ts`. The BusAdapter interface, EventSink type,
 * and error classes are hand-written here because JSON Schema cannot
 * represent behavioral interfaces.
 *
 * Source: roadmap.md M0 Task 0.2; mirrors interfaces/python/.../bus.py
 */

import type { ReturnCode, RoISIdentifier, CommandType } from "./hri";

// Import generated bus data models (so they're in scope for the BusAdapter interface)
import type {
  DiscoverRequest,
  DiscoverResponse,
  CommandRequest,
  InvokeResponse,
  QueryRequest,
  QueryResponse,
  SubscribeRequest,
  SubscribeResponse,
  EventEnvelope,
} from "./generated/bus-models";

// Re-export generated bus data models
export {
  DiscoverRequestSchema,
  DiscoverResponseSchema,
  CommandRequestSchema,
  InvokeResponseSchema,
  QueryRequestSchema,
  QueryResponseSchema,
  SubscribeRequestSchema,
  SubscribeResponseSchema,
  EventEnvelopeSchema,
} from "./generated/bus-models";

export type {
  DiscoverRequest,
  DiscoverResponse,
  CommandRequest,
  InvokeResponse,
  QueryRequest,
  QueryResponse,
  SubscribeRequest,
  SubscribeResponse,
  EventEnvelope,
} from "./generated/bus-models";

// ---------------------------------------------------------------------------
// Type aliases
// ---------------------------------------------------------------------------

/** Async callback that receives event envelopes from a BusAdapter. */
export type EventSink = (envelope: EventEnvelope) => Promise<void>;

// Re-export CommandType from hri (now an enum, not a type alias)
export type { CommandType } from "./hri";

/** Query operation name, e.g. 'component_status', 'robot_position'. */
export type QueryType = string;

/** Event type name, e.g. 'person_detected', 'reached_target'. */
export type EventType = string;

/** Identifier returned by subscribe() and carried in event envelopes. */
export type SubscribeId = string;

/** Identifier returned by invoke() for long-running commands. */
export type CommandId = string;

// ---------------------------------------------------------------------------
// Exceptions
// ---------------------------------------------------------------------------

/** Base error raised by BusAdapter implementations. */
export class BusAdapterError extends Error {
  readonly returnCode: ReturnCode;

  constructor(message: string, returnCode: ReturnCode = "ERROR") {
    super(message);
    this.name = "BusAdapterError";
    this.returnCode = returnCode;
  }
}

/** Raised when a component_ref cannot be resolved by the adapter. */
export class ComponentNotFoundError extends BusAdapterError {
  readonly componentRef: RoISIdentifier;

  constructor(componentRef: RoISIdentifier) {
    super(`Component not found: ${componentRef}`, "UNSUPPORTED");
    this.name = "ComponentNotFoundError";
    this.componentRef = componentRef;
  }
}

// ---------------------------------------------------------------------------
// BusAdapter interface
// ---------------------------------------------------------------------------

/**
 * Transport-neutral contract between the RoIS engine and a concrete bus.
 *
 * Implementations include:
 *   - UniversalBusAdapter  (M1, WS+JSON-RPC for non-ROS hosts)
 *   - ROS2BusAdapter        (M3)
 *   - RosBridgeBusAdapter   (future)
 *
 * The contract is intentionally limited to five async methods. Adapters must
 * not leak transport-specific types through these signatures.
 */
export interface BusAdapter {
  /** Discover components matching the request condition. Maps to CommandIF.search(). */
  discover(request: DiscoverRequest): Promise<DiscoverResponse>;

  /** Invoke a command on a bound component. Maps to CommandIF operations. */
  invoke(request: CommandRequest): Promise<InvokeResponse>;

  /** Execute a synchronous query on a component. Maps to QueryIF.query(). */
  query(request: QueryRequest): Promise<QueryResponse>;

  /** Subscribe to async events from a component. Maps to EventIF.subscribe(). */
  subscribe(request: SubscribeRequest, sink: EventSink): Promise<SubscribeResponse>;

  /** Cancel an event subscription. Maps to EventIF.unsubscribe(). Duplicate requests are silently ignored. */
  unsubscribe(subscribeId: SubscribeId): Promise<ReturnCode>;
}