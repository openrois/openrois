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
 * ComponentContract: the contract between the engine and the components
 * it manages.
 *
 * The engine calls this contract. The SubEngine proxy implements it
 * remotely (forwarding over WebSocket to a child engine). The
 * ComponentRegistry implements it locally (dispatching to component
 * handlers via decorators).
 *
 * This is the single abstraction that decouples the engine from any
 * specific middleware (ROS 2, gRPC, avatars, AI services).
 */
export interface ComponentContract {
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
