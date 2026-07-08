/**
 * EventClient: RoIS Event interface client for the OpenRoIS TypeScript SDK.
 *
 * Implements the EventIF operations defined in the RoIS Framework 2.0
 * specification (RoIS_HRI::EventApplicationBase):
 *
 *   subscribe(componentRef, eventType, condition) -> rois.event.subscribe
 *   unsubscribe(subscribeId)                       -> rois.event.unsubscribe
 *   getEventDetail(eventId)                        -> rois.event.get_event_detail
 *
 * After subscribing, the gateway pushes `rois.event.notify` notifications to
 * the SDK whenever the event fires. EventClient listens on the transport for
 * these notifications and dispatches them to user callbacks via EventEmitter.
 *
 * Wire contract (docs/white-paper.md §8.2):
 *   rois.event.subscribe        {component_ref, event_type, condition} -> {return_code, subscribe_id}
 *   rois.event.unsubscribe      {subscribe_id}                        -> {return_code}
 *   rois.event.get_event_detail {event_id}                             -> {return_code, results: Result[]}
 *   rois.event.notify           {event_id, event_type, subscribe_id, expire}  (notification, no id)
 *
 * Architecture: docs/architecture.md section 4 (Client SDK layer)
 */

// 1. Node.js built-ins
import { EventEmitter } from "node:events";

// 3. Internal packages (@openrois/*)
import {
  ReturnCodeSchema,
  ResultSchema,
  SubscribeResponseSchema,
  NotifyEventPayloadSchema,
} from "@openrois/interfaces";

import type {
  ReturnCode,
  Result,
  NotifyEventPayload,
} from "@openrois/interfaces";

// 4. Local modules
import { type WebSocketTransport } from "./transport";
import { RoISError } from "./engine";

// ---------------------------------------------------------------------------
// Response helpers (lightweight inline schemas)
// ---------------------------------------------------------------------------

/**
 * Response shape for rois.event.unsubscribe.
 *
 *   { return_code }
 */
interface ReturnCodeResponse {
  return_code: ReturnCode;
}

/**
 * Response shape for rois.event.get_event_detail.
 *
 *   { return_code, results: Result[] }
 */
interface GetEventDetailResponse {
  return_code: ReturnCode;
  results?: Result[];
}

// ---------------------------------------------------------------------------
// EventClient
// ---------------------------------------------------------------------------

/**
 * Client for the RoIS Event interface operations.
 *
 * Wraps a connected {@link WebSocketTransport} and provides typed, validated
 * methods for subscribe/unsubscribe/getEventDetail. It also listens on the
 * transport for `rois.event.notify` push notifications and dispatches them to
 * user callbacks via EventEmitter.
 *
 * The transport must already be connected before constructing or using an
 * EventClient.
 *
 * Usage:
 *   const engine = await RoISEngine.connect("wss://gateway.example.com");
 *   const events = new EventClient(engine.getTransport);
 *
 *   // Subscribe to person_detected events.
 *   const subId = await events.subscribe("PersonDetection_0", "person_detected");
 *
 *   // Listen for notifications.
 *   events.on("person_detected", (payload) => {
 *     console.log(`${payload.event_id}: person detected`);
 *   });
 *
 *   // Or listen for all events generically.
 *   events.on("notify", (payload) => {
 *     console.log(payload.event_type, payload.event_id);
 *   });
 *
 *   // Unsubscribe when done.
 *   await events.unsubscribe(subId);
 *
 * Events emitted:
 *   "notify"       - Any rois.event.notify notification (generic).
 *   <event_type>   - The specific event_type (e.g. "person_detected").
 *
 * Errors:
 *   - RoISError: the gateway returned a non-OK return_code.
 *   - RpcError: the gateway returned a JSON-RPC level error.
 *   - TransportError: the connection is not open.
 */
export class EventClient extends EventEmitter {
  /** The underlying transport (must be connected). */
  private readonly transport: WebSocketTransport;

  /** Whether the transport notification listener has been wired up. */
  private listening: boolean = false;

  /**
   * Create an EventClient over an existing transport.
   *
   * Automatically wires up a listener on the transport for
   * `rois.event.notify` notifications. The listener dispatches to
   * EventEmitter callbacks on this instance.
   *
   * @param transport - A connected WebSocketTransport instance.
   */
  constructor(transport: WebSocketTransport) {
    super();
    this.transport = transport;
    this.startListening();
  }

  // -----------------------------------------------------------------------
  // EventIF operations
  // -----------------------------------------------------------------------

  /**
   * Subscribe to events from a component.
   *
   * After subscribing, the gateway pushes `rois.event.notify` notifications
   * to the SDK whenever the event fires. Listen for them with:
   *   events.on("person_detected", (payload) => { ... })
   * or the generic:
   *   events.on("notify", (payload) => { ... })
   *
   * Maps to: rois.event.subscribe
   * Request:  { component_ref: string, event_type: string, condition: string }
   * Response: { return_code, subscribe_id: string }
   *
   * @param componentRef - The component_ref to subscribe to.
   * @param eventType    - Event type name, e.g. "person_detected".
   * @param condition    - Optional ISO 19143 filter expression. Defaults to "".
   * @returns The subscribe_id for this subscription (use to unsubscribe).
   *
   * @throws RoISError      if the gateway returns a non-OK return_code
   *                         (e.g. UNSUPPORTED for an unknown event type).
   * @throws TransportError if the connection is not open.
   */
  async subscribe(
    componentRef: string,
    eventType: string,
    condition: string = "",
  ): Promise<string> {
    const result = await this.transport.send("rois.event.subscribe", {
      component_ref: componentRef,
      event_type: eventType,
      condition,
    });

    const parsed = SubscribeResponseSchema.parse(result);
    this.checkReturnCode(parsed.return_code, "rois.event.subscribe");

    return parsed.subscribe_id;
  }

  /**
   * Cancel an event subscription.
   *
   * Per the RoIS spec, duplicate unsubscribe requests are silently ignored
   * (no error). The gateway returns OK even if the subscribe_id was already
   * unsubscribed or never existed.
   *
   * Maps to: rois.event.unsubscribe
   * Request:  { subscribe_id: string }
   * Response: { return_code }
   *
   * @param subscribeId - The subscribe_id returned by subscribe().
   * @returns The ReturnCode from the gateway (OK on success).
   *
   * @throws RoISError      if the gateway returns a non-OK return_code.
   * @throws TransportError if the connection is not open.
   */
  async unsubscribe(subscribeId: string): Promise<ReturnCode> {
    const result = await this.transport.send("rois.event.unsubscribe", {
      subscribe_id: subscribeId,
    });

    const parsed = result as ReturnCodeResponse;
    const returnCode = ReturnCodeSchema.parse(parsed.return_code);
    this.checkReturnCode(returnCode, "rois.event.unsubscribe");

    return returnCode;
  }

  /**
   * Get detailed information about a specific event.
   *
   * Call this after receiving a `rois.event.notify` notification to fetch
   * the full event payload (subject to the event's `expire` time limit).
   *
   * Maps to: rois.event.get_event_detail
   * Request:  { event_id: string }
   * Response: { return_code, results: Result[] }
   *
   * @param eventId - The event_id from a notify notification.
   * @returns The event detail results as an array of Result objects.
   *
   * @throws RoISError      if the gateway returns a non-OK return_code.
   * @throws TransportError if the connection is not open.
   */
  async getEventDetail(eventId: string): Promise<Result[]> {
    const result = await this.transport.send("rois.event.get_event_detail", {
      event_id: eventId,
    });

    const parsed = result as GetEventDetailResponse;
    const returnCode = ReturnCodeSchema.parse(parsed.return_code);
    this.checkReturnCode(returnCode, "rois.event.get_event_detail");

    return ResultSchema.array().parse(parsed.results ?? []);
  }

  // -----------------------------------------------------------------------
  // Notification dispatch
  // -----------------------------------------------------------------------

  /**
   * Wire up the transport listener for rois.event.notify notifications.
   *
   * Called once from the constructor. The listener validates the notification
   * payload with NotifyEventPayloadSchema and then emits two events:
   *   - "notify" (generic, for all event notifications)
   *   - <event_type> (specific, e.g. "person_detected")
   *
   * This is idempotent: calling it multiple times is safe.
   */
  private startListening(): void {
    if (this.listening) {
      return;
    }
    this.listening = true;

    this.transport.on("rois.event.notify", (notification: { params?: unknown }) => {
      const rawParams = notification.params;
      if (!rawParams) {
        return;
      }

      // Validate the notification payload with the canonical schema.
      // Use safeParse so invalid payloads are silently ignored rather than
      // throwing and crashing the notification dispatch.
      const parseResult = NotifyEventPayloadSchema.safeParse(rawParams);
      if (!parseResult.success) {
        return;
      }
      const payload = parseResult.data;

      // Emit the generic "notify" event for all notifications.
      this.emit("notify", payload);

      // Emit the specific event_type for convenience.
      // This lets callers do: events.on("person_detected", handler)
      if (payload.event_type) {
        this.emit(payload.event_type, payload);
      }
    });
  }

  // -----------------------------------------------------------------------
  // Private: helpers
  // -----------------------------------------------------------------------

  /**
   * Check a ReturnCode and throw a RoISError if it is not OK.
   *
   * Mirrors the pattern in RoISEngine.checkReturnCode().
   */
  private checkReturnCode(returnCode: ReturnCode, method: string): void {
    if (returnCode !== "OK") {
      throw new RoISError(returnCode, method);
    }
  }
}