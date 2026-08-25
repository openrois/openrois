import type {
  DiscoverRequest,
  DiscoverResponse,
  CommandRequest,
  InvokeResponse,
  QueryRequest,
  QueryResponse,
  SubscribeRequest,
  SubscribeResponse,
  EventSink,
  ReturnCode,
} from './types.js';

/**
 * SubEngine: the contract between the main HRI Engine and a sub HRI Engine.
 *
 * The main engine holds a collection of SubEngine instances and routes
 * RoIS calls to the correct one based on component ref. Implementations:
 * - RemoteSubEngine: WebSocket connection to an adapter process.
 * - LocalSubEngine (future): in-process component runtime.
 */
export interface SubEngine {
  /** Discover available HRI Components. */
  discover(request: DiscoverRequest): Promise<DiscoverResponse>;
  /** Execute a command on an HRI Component. */
  invoke(request: CommandRequest): Promise<InvokeResponse>;
  /** Query an HRI Component for information. */
  query(request: QueryRequest): Promise<QueryResponse>;
  /** Subscribe to events from an HRI Component. */
  subscribe(request: SubscribeRequest, sink: EventSink): Promise<SubscribeResponse>;
  /** Unsubscribe from events. */
  unsubscribe(subscribeId: string): Promise<ReturnCode>;
}
