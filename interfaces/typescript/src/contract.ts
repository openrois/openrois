/**
 * Transport-neutral component contract for OpenRoIS.
 *
 * This module defines the ComponentContract interface, the only boundary between
 * an engine and the components it reaches. Local components and remote child
 * engines implement the same five-method contract:
 *
 *   discover    → CommandIF.search
 *   invoke      → CommandIF.bind/set_parameter/execute/start/stop/suspend/resume
 *   query       → QueryIF.query / RoIS_Common.component_status
 *   subscribe   → EventIF.subscribe (async push via EventSink)
 *   unsubscribe → EventIF.unsubscribe
 *
 * The contract is intentionally transport-agnostic. No ROS, DDS, gRPC,
 * WebSocket, or socket symbols appear here.
 *
 * The request/response models and EventEnvelope are generated from JSON Schema
 * in `./generated/contract-models.ts`. The ComponentContract interface, EventSink
 * type, and error classes are hand-written here because JSON Schema cannot
 * represent behavioral interfaces.
 *
 * Mirrors interfaces/python/src/openrois/interfaces/contract.py.
 */

import type { ReturnCode, RoISIdentifier, CommandType } from "./hri";

// Import the generated contract data models, so they are in scope for the interface below.
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
} from "./generated/contract-models";

// Re-export the generated contract data models.
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
} from "./generated/contract-models";

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
} from "./generated/contract-models";

// ---------------------------------------------------------------------------
// Type aliases
// ---------------------------------------------------------------------------

/** Async callback that receives event envelopes from a ComponentContract. */
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

/** Base error raised by ComponentContract implementations. */
export class ComponentContractError extends Error {
  readonly returnCode: ReturnCode;

  constructor(message: string, returnCode: ReturnCode = "ERROR") {
    super(message);
    this.name = "ComponentContractError";
    this.returnCode = returnCode;
  }
}

/** Raised when a component_ref cannot be resolved by the adapter. */
export class ComponentNotFoundError extends ComponentContractError {
  readonly componentRef: RoISIdentifier;

  constructor(componentRef: RoISIdentifier) {
    super(`Component not found: ${componentRef}`, "UNSUPPORTED");
    this.name = "ComponentNotFoundError";
    this.componentRef = componentRef;
  }
}

// ---------------------------------------------------------------------------
// ComponentContract interface
// ---------------------------------------------------------------------------

/**
 * Transport-neutral contract between an engine and the components it reaches.
 *
 * The Python engine implements it with ComponentRegistry (local components) and
 * ChildEngineProxy (a remote child engine over WebSocket JSON-RPC).
 *
 * The contract is intentionally limited to five async methods. Implementations
 * must not leak transport-specific types through these signatures.
 */
export interface ComponentContract {
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