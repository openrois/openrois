import type { WebSocket } from 'ws';
import type { ComponentContract } from './component-contract.js';
import {
  ReturnCode,
  type Result,
  type RegisteredComponent,
  type DiscoverRequest,
  type DiscoverResponse,
  type CommandRequest,
  type InvokeResponse,
  type QueryRequest,
  type QueryResponse,
  type SubscribeRequest,
  type SubscribeResponse,
  type EventSink,
  type EventEnvelope,
  type JsonRpcRequest,
  type JsonRpcResponse,
  type JsonRpcNotification,
} from './types.js';

/**
 * SubEngine: the main engine's proxy for a remote sub-engine (adapter
 * process).
 *
 * Implements the Component Contract by forwarding JSON-RPC requests over
 * the WebSocket and awaiting matching responses. Event notifications from
 * the adapter are routed to the EventSink associated with the subscribe_id.
 *
 * Multiple SubEngine instances can exist simultaneously, one per
 * connected adapter.
 */
export class SubEngine implements ComponentContract {
  private ws: WebSocket | null;
  private pendingRequests = new Map<string, (response: JsonRpcResponse) => void>();
  private eventSinks = new Map<string, EventSink>();
  private nextId = 0;

  /** The engine_id from registration. */
  engineId = '';

  /** Platform identifier from registration (e.g. "kachaka", "teleco-pao"). */
  platform = '';

  /** Components registered by this sub-engine. */
  components: RegisteredComponent[] = [];

  /** Whether the WebSocket is open. */
  get isConnected(): boolean {
    return this.ws !== null && this.ws.readyState === this.ws.OPEN;
  }

  constructor(ws: WebSocket | null) {
    this.ws = ws;
    if (ws) {
      this.attachWebSocket(ws);
    }
  }

  /** Attach a WebSocket and start listening for messages. */
  attachWebSocket(ws: WebSocket): void {
    this.ws = ws;
    ws.on('message', (data: Buffer) => {
      try {
        const msg = JSON.parse(data.toString()) as Record<string, unknown>;
        // Registration: has both id and method "rois.adapter.register".
        if (
          typeof msg.id !== 'undefined' &&
          typeof msg.method === 'string' &&
          msg.method === 'rois.adapter.register'
        ) {
          this.handleRegister(msg);
          return;
        }
        // Response: has id, no method.
        if (typeof msg.id !== 'undefined' && typeof msg.method === 'undefined') {
          const resolve = this.pendingRequests.get(String(msg.id));
          if (resolve) {
            this.pendingRequests.delete(String(msg.id));
            resolve(msg as unknown as JsonRpcResponse);
          }
          return;
        }
        // Notification: has method, no id.
        if (typeof msg.method === 'string' && typeof msg.id === 'undefined') {
          this.handleNotification(msg as unknown as JsonRpcNotification);
        }
      } catch (err) {
        console.error('[sub-engine] parse error:', err);
      }
    });

    ws.on('close', () => {
      console.log(`[sub-engine] "${this.engineId}" disconnected`);
      this.ws = null;
      // Reject all pending requests.
      for (const resolve of this.pendingRequests.values()) {
        resolve({
          jsonrpc: '2.0',
          id: '',
          result: { return_code: ReturnCode.ERROR },
        });
      }
      this.pendingRequests.clear();
      this.eventSinks.clear();
    });

    ws.on('error', (err) => {
      console.error(`[sub-engine] "${this.engineId}" ws error:`, err);
    });
  }

  /** Process rois.adapter.register and cache engine_id + components. */
  handleRegister(msg: Record<string, unknown>): void {
    const params = msg.params as Record<string, unknown> | undefined;
    this.engineId = String(params?.engine_id ?? '');
    this.platform = String(params?.platform ?? '');
    const rawComponents = (params?.components as Array<Record<string, unknown>>) ?? [];
    this.components = rawComponents.map((c) => ({
      ref: String(c.ref ?? ''),
      function: (c.function as string | null) ?? null,
      queries: (c.queries as string[]) ?? [],
      commands: (c.commands as string[]) ?? [],
      events: (c.events as string[]) ?? [],
      parameters: (c.parameters as Array<Record<string, unknown>>) ?? [],
    }));
    console.log(
      `[sub-engine] registered "${this.engineId}" (platform: ${this.platform || 'unknown'}) with ${this.components.length} components`,
    );
    // Respond with OK.
    this.ws?.send(JSON.stringify({
      jsonrpc: '2.0',
      id: msg.id,
      result: { return_code: ReturnCode.OK },
    }));
  }

  // ─── SubEngine implementation ────────────────────────────────

  async discover(request: DiscoverRequest): Promise<DiscoverResponse> {
    const result = await this.sendRequest('rois.command.search', {
      condition: request.condition,
    });
    return {
      returnCode: (result.return_code as ReturnCode) ?? ReturnCode.ERROR,
      componentRefList: (result.component_ref_list as string[]) ?? [],
    };
  }

  async invoke(request: CommandRequest): Promise<InvokeResponse> {
    const result = await this.sendRequest('rois.command.execute', {
      component_ref: request.componentRef,
      command_type: request.commandType,
      parameters: request.parameters,
    });
    return {
      returnCode: (result.return_code as ReturnCode) ?? ReturnCode.ERROR,
      commandId: (result.command_id as string) ?? '',
    };
  }

  async query(request: QueryRequest): Promise<QueryResponse> {
    const result = await this.sendRequest('rois.query.query', {
      component_ref: request.componentRef,
      query_type: request.queryType,
      condition: request.condition,
    });
    return {
      returnCode: (result.return_code as ReturnCode) ?? ReturnCode.ERROR,
      results: (result.results as Result[]) ?? [],
    };
  }

  async subscribe(
    request: SubscribeRequest,
    sink: EventSink,
  ): Promise<SubscribeResponse> {
    const result = await this.sendRequest('rois.event.subscribe', {
      component_ref: request.componentRef,
      event_type: request.eventType,
      condition: request.condition,
    });
    const subscribeId = (result.subscribe_id as string) ?? '';
    if (subscribeId) {
      this.eventSinks.set(subscribeId, sink);
    }
    return {
      returnCode: (result.return_code as ReturnCode) ?? ReturnCode.ERROR,
      subscribeId,
    };
  }

  async unsubscribe(subscribeId: string): Promise<ReturnCode> {
    const result = await this.sendRequest('rois.event.unsubscribe', {
      subscribe_id: subscribeId,
    });
    this.eventSinks.delete(subscribeId);
    return (result.return_code as ReturnCode) ?? ReturnCode.ERROR;
  }

  // ─── Internal ─────────────────────────────────────────────────

  private async sendRequest(
    method: string,
    params: Record<string, unknown>,
  ): Promise<Record<string, unknown>> {
    if (!this.isConnected) {
      return { return_code: ReturnCode.ERROR };
    }

    const id = `req-${++this.nextId}`;
    const message: JsonRpcRequest = {
      jsonrpc: '2.0',
      id,
      method,
      params,
    };

    return new Promise((resolve) => {
      const timeout = setTimeout(() => {
        this.pendingRequests.delete(id);
        resolve({ return_code: ReturnCode.ERROR });
      }, 10_000);

      this.pendingRequests.set(id, (response: JsonRpcResponse) => {
        clearTimeout(timeout);
        resolve(response.result);
      });

      this.ws!.send(JSON.stringify(message), (err) => {
        if (err) {
          clearTimeout(timeout);
          this.pendingRequests.delete(id);
          resolve({ return_code: ReturnCode.ERROR });
        }
      });
    });
  }

  private handleNotification(notification: JsonRpcNotification): void {
    if (notification.method === 'rois.event.notify') {
      const subscribeId = String(notification.params.subscribe_id ?? '');
      const sink = this.eventSinks.get(subscribeId);
      if (sink) {
        const envelope: EventEnvelope = {
          eventId: String(notification.params.event_id ?? ''),
          subscribeId,
          componentRef: String(notification.params.component_ref ?? ''),
          eventType: String(notification.params.event_type ?? ''),
          expire: String(notification.params.expire ?? ''),
          results: (notification.params.results as EventEnvelope['results']) ?? [],
        };
        void sink(envelope).catch((err) => {
          console.error('[sub-engine] event sink error:', err);
        });
      }
    }
  }
}
