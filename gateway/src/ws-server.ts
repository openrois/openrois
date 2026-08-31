import { WebSocketServer, WebSocket } from 'ws';
import { randomUUID } from 'crypto';
import { Engine } from './engine.js';
import { SubEngine } from './sub-engine.js';
import type { EventEnvelope, EventSink } from './types.js';

/**
 * WsServer: one WebSocket server with role-based routing.
 *
 * Sub-engines and clients connect to the same port. The server distinguishes
 * them by the messages they send:
 * - rois.adapter.register (has id + method) -> adapter connection, creates
 *   a SubEngine and registers it with the Engine.
 * - rois.system.* / rois.command.* / rois.query.* / rois.event.* -> client
 *   connection, dispatched to the Engine.
 * - JSON-RPC response (has id, no method) -> from adapter, resolving a
 *   pending request in the SubEngine.
 * - JSON-RPC notification (has method, no id) -> from adapter, event push.
 *
 * Event relay: when an adapter sends rois.event.notify, the WsServer
 * pushes the notification to all subscribed client WebSockets.
 */
export class WsServer {
  private wss: WebSocketServer | null = null;
  private subEngines = new Map<WebSocket, SubEngine>();
  // subscribe_id -> set of client WebSockets to push events to
  private clientSubscriptions = new Map<string, Set<WebSocket>>();
  // All client WebSockets (for profile-change broadcasts)
  private clientSockets = new Set<WebSocket>();

  constructor(private engine: Engine) {}

  /**
   * Start the WebSocket server.
   *
   * @param host Host to bind (default: 0.0.0.0, all interfaces).
   * @param port Port to listen on (default: 31166).
   */
  start(host: string = '0.0.0.0', port: number = 8765): void {
    this.wss = new WebSocketServer({ host, port });

    this.wss.on('error', (err: NodeJS.ErrnoException) => {
      console.error('[engine] server error:', err.message);
      if (err.code === 'EADDRINUSE') {
        console.error(`[engine] port ${port} already in use`);
      }
    });

    this.wss.on('connection', (ws: WebSocket) => {
      console.log('[engine] new connection');
      this.handleConnection(ws);
    });

    console.log(`[engine] listening on ws://${host}:${port}`);
  }

  /** Stop the WebSocket server. */
  stop(): void {
    for (const subEngine of this.subEngines.values()) {
      if (subEngine.engineId) {
        this.engine.unregisterSubEngine(subEngine.engineId);
      }
    }
    this.subEngines.clear();

    if (this.wss) {
      this.wss.close();
      this.wss = null;
    }
    this.clientSubscriptions.clear();
    this.clientSockets.clear();
  }

  // ─── Profile-change notifications ────────────────────────────

  /**
   * Broadcast a rois.system.profile_changed notification to all
   * connected clients. Clients should re-call get_profile to
   * refresh their component list.
   */
  private notifyProfileChanged(): void {
    const notification = JSON.stringify({
      jsonrpc: '2.0',
      method: 'rois.system.profile_changed',
      params: {},
    });
    for (const ws of this.clientSockets) {
      if (ws.readyState === ws.OPEN) {
        ws.send(notification);
      }
    }
  }

  // ─── Connection handling ─────────────────────────────────────

  private handleConnection(ws: WebSocket): void {
    let role: 'unknown' | 'adapter' | 'client' = 'unknown';
    let subEngine: SubEngine | null = null;

    ws.on('message', (data: Buffer) => {
      try {
        const msg = JSON.parse(data.toString()) as Record<string, unknown>;
        const hasId = typeof msg.id !== 'undefined';
        const hasMethod = typeof msg.method === 'string';

        // ── Adapter registration ──────────────────────────────
        if (hasId && hasMethod && msg.method === 'rois.adapter.register') {
          role = 'adapter';
          subEngine = new SubEngine(ws);
          subEngine.handleRegister(msg);
          this.subEngines.set(ws, subEngine);
          this.engine.registerSubEngine(
            subEngine.engineId,
            subEngine.components,
            subEngine,
            subEngine.platform,
          );
          this.notifyProfileChanged();
          return;
        }

        // ── Adapter responses and notifications ───────────────
        if (role === 'adapter' && subEngine) {
          // The SubEngine's own ws listeners handle responses
          // (has id, no method) and notifications (has method, no id).
          // We intercept event notifications here to relay to clients.
          if (!hasId && hasMethod && msg.method === 'rois.event.notify') {
            this.relayEventToClients(msg.params as Record<string, unknown>);
          }
          return;
        }

        // ── Client messages ────────────────────────────────────
        if (role === 'unknown') {
          role = 'client';
          this.clientSockets.add(ws);
        }

        if (role === 'client' && hasId && hasMethod) {
          // Client JSON-RPC request. Dispatch to the engine.
          const requestId = msg.id as string | number | null;
          const method = msg.method as string;
          const params = (msg.params as Record<string, unknown>) ?? {};

          // Create an event sink that pushes events to this client.
          const sink: EventSink = async (envelope: EventEnvelope) => {
            const notification = {
              jsonrpc: '2.0',
              method: 'rois.event.notify',
              params: {
                event_id: envelope.eventId,
                subscribe_id: envelope.subscribeId,
                component_ref: envelope.componentRef,
                event_type: envelope.eventType,
                expire: envelope.expire,
                results: envelope.results,
              },
            };
            // Track the subscription so adapter-originated events
            // can be relayed to this client.
            const subs = this.clientSubscriptions.get(envelope.subscribeId);
            if (subs) {
              subs.add(ws);
            } else {
              this.clientSubscriptions.set(envelope.subscribeId, new Set([ws]));
            }
            ws.send(JSON.stringify(notification));
          };

          // Generate a unique client ID for this connection.
          // In the future, this will be replaced by the JWT sub claim
          // when authentication is implemented (Phase 9).
          const clientId = (ws as WebSocket & { __clientId?: string }).__clientId ??= randomUUID();

          this.engine
            .dispatch(method, params, sink, clientId)
            .then((result) => {
              ws.send(
                JSON.stringify({
                  jsonrpc: '2.0',
                  id: requestId,
                  result,
                }),
              );
            })
            .catch((err) => {
              console.error('[engine] dispatch error:', err);
              ws.send(
                JSON.stringify({
                  jsonrpc: '2.0',
                  id: requestId,
                  error: {
                    code: -32603,
                    message: 'Internal error',
                  },
                }),
              );
            });
          return;
        }

        // Client unsubscribe notification (has method, no id).
        if (role === 'client' && !hasId && hasMethod) {
          if (msg.method === 'rois.event.unsubscribe') {
            const subscribeId = String(
              (msg.params as Record<string, unknown>)?.subscribe_id ?? '',
            );
            this.clientSubscriptions.delete(subscribeId);
          }
          return;
        }
      } catch (err) {
        console.error('[engine] parse error:', err);
      }
    });

    ws.on('close', () => {
      if (role === 'adapter' && subEngine) {
        console.log(`[engine] adapter "${subEngine.engineId}" disconnected`);
        if (subEngine.engineId) {
          this.engine.unregisterSubEngine(subEngine.engineId);
        }
        this.subEngines.delete(ws);
        this.notifyProfileChanged();
      }
      if (role === 'client') {
        const clientId = (ws as WebSocket & { __clientId?: string }).__clientId;
        if (clientId) {
          this.engine.releaseAll(clientId);
        }
        this.clientSockets.delete(ws);
        // Clean up this client's subscriptions.
        for (const [subId, subs] of this.clientSubscriptions) {
          subs.delete(ws);
          if (subs.size === 0) {
            this.clientSubscriptions.delete(subId);
          }
        }
      }
    });

    ws.on('error', (err) => {
      console.error('[engine] ws error:', err);
    });
  }

  // ─── Event relay ─────────────────────────────────────────────

  /**
   * Relay an event notification from an adapter to all subscribed clients.
   *
   * This handles events that originate from the adapter (via
   * SubEngine's notification handler) and need to be pushed to
   * client WebSocket connections.
   */
  private relayEventToClients(params: Record<string, unknown>): void {
    const subscribeId = String(params.subscribe_id ?? '');
    const subs = this.clientSubscriptions.get(subscribeId);
    if (subs) {
      const notification = JSON.stringify({
        jsonrpc: '2.0',
        method: 'rois.event.notify',
        params,
      });
      for (const ws of subs) {
        if (ws.readyState === WebSocket.OPEN) {
          ws.send(notification);
        }
      }
    }
  }
}
