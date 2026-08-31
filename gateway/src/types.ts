/** RoIS ReturnCode values. */
export enum ReturnCode {
  OK = 'OK',
  ERROR = 'ERROR',
  UNSUPPORTED = 'UNSUPPORTED',
  BAD_PARAMETER = 'BAD_PARAMETER',
  OUT_OF_RESOURCES = 'OUT_OF_RESOURCES',
  TIMEOUT = 'TIMEOUT',
}

/** RoIS Parameter (input to commands). */
export interface Parameter {
  name: string;
  dataTypeRef: string;
  value: string;
}

/** RoIS Result (output from queries and events). */
export interface Result {
  name: string;
  dataTypeRef: string;
  value: string;
}

/** RoIS CommandRequest (Command Interface). */
export interface CommandRequest {
  componentRef: string;
  commandType: string;
  commandId: string;
  parameters: Parameter[];
}

/** RoIS InvokeResponse (response to Command Interface). */
export interface InvokeResponse {
  returnCode: ReturnCode;
  commandId: string;
}

/** RoIS DiscoverRequest (Command Interface, search). */
export interface DiscoverRequest {
  condition: string;
}

/** RoIS DiscoverResponse. */
export interface DiscoverResponse {
  returnCode: ReturnCode;
  componentRefList: string[];
}

/** RoIS QueryRequest (Query Interface). */
export interface QueryRequest {
  componentRef: string;
  queryType: string;
  condition: string;
}

/** RoIS QueryResponse. */
export interface QueryResponse {
  returnCode: ReturnCode;
  results: Result[];
}

/** RoIS SubscribeRequest (Event Interface). */
export interface SubscribeRequest {
  componentRef: string;
  eventType: string;
  condition: string;
}

/** RoIS SubscribeResponse. */
export interface SubscribeResponse {
  returnCode: ReturnCode;
  subscribeId: string;
}

/** RoIS EventEnvelope (pushed from sub-engine to engine). */
export interface EventEnvelope {
  eventId: string;
  subscribeId: string;
  componentRef: string;
  eventType: string;
  expire: string;
  results: Result[];
}

/** EventSink: callback the engine calls when an event fires. */
export type EventSink = (envelope: EventEnvelope) => Promise<void>;

/**
 * Component declaration sent by the adapter during registration.
 * The engine caches this and uses it for search() and bind/release.
 */
export interface RegisteredComponent {
  ref: string;
  function: string | null;
  queries: string[];
  commands: string[];
  events: string[];
  parameters: Array<Record<string, unknown>>;
}

/** JSON-RPC 2.0 request. */
export interface JsonRpcRequest {
  jsonrpc: '2.0';
  id?: string | number | null;
  method: string;
  params?: Record<string, unknown>;
}

/** JSON-RPC 2.0 response (from sub-engine). */
export interface JsonRpcResponse {
  jsonrpc: '2.0';
  id: string | number | null;
  result: Record<string, unknown>;
}

/** JSON-RPC 2.0 notification (from sub-engine, no id). */
export interface JsonRpcNotification {
  jsonrpc: '2.0';
  method: string;
  params: Record<string, unknown>;
}
