/**
 * Unit tests for event-client.ts -- EventClient (EventIF operations).
 *
 * Uses the same MockWebSocket pattern as engine.test.ts to simulate the
 * gateway. EventClient is constructed over the engine's transport and
 * listens for rois.event.notify notifications.
 *
 * Run with: npx vitest run
 */

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { RoISEngine, RoISError, type EngineOptions } from "../src/engine";
import { EventClient } from "../src/event-client";
import { TransportError } from "../src/transport";
import { JSONRPC_VERSION } from "../src/jsonrpc";

// ---------------------------------------------------------------------------
// MockWebSocket (same pattern as engine.test.ts)
// ---------------------------------------------------------------------------

class MockWebSocket {
  readyState: number = 0;

  onopen: ((event: { type: string }) => void) | null = null;
  onclose: ((event: { code: number; reason: string; type: string }) => void) | null = null;
  onmessage: ((event: { data: unknown; type: string }) => void) | null = null;
  onerror: ((event: { error?: unknown; message?: string; type: string }) => void) | null = null;

  sent: unknown[] = [];

  send(data: string): void {
    try {
      this.sent.push(JSON.parse(data));
    } catch {
      this.sent.push(data);
    }
  }

  close(_code?: number, _reason?: string): void {
    this.readyState = 3;
  }

  simulateOpen(): void {
    this.readyState = 1;
    this.onopen?.({ type: "open" });
  }

  simulateMessage(data: unknown): void {
    const raw = typeof data === "string" ? data : JSON.stringify(data);
    this.onmessage?.({ data: raw, type: "message" });
  }
}

// ---------------------------------------------------------------------------
// Test helpers
// ---------------------------------------------------------------------------

let currentMock: MockWebSocket;

const testOptions: EngineOptions = {
  transport: {
    webSocketFactory: (_url: string) => {
      currentMock = new MockWebSocket();
      return currentMock as any;
    },
  },
};

async function createConnectedEventClient(): Promise<{
  engine: RoISEngine;
  events: EventClient;
  mock: MockWebSocket;
}> {
  const connectPromise = RoISEngine.connect("ws://test-gateway:8765", testOptions);
  currentMock.simulateOpen();
  // Drain microtasks so the rois.system.connect send fires before we respond.
  for (let i = 0; i < 5; i++) {
    await Promise.resolve();
  }
  respondWithResult(currentMock, { return_code: "OK" });
  const engine = await connectPromise;
  const events = new EventClient(engine.getTransport);
  return { engine, events, mock: currentMock };
}

function respondWithResult(mock: MockWebSocket, result: unknown): void {
  const lastSent = mock.sent[mock.sent.length - 1] as Record<string, unknown>;
  mock.simulateMessage({
    jsonrpc: JSONRPC_VERSION,
    id: lastSent.id,
    result,
  });
}

/**
 * Simulate a gateway notification (no id) pushed to the client.
 */
function sendNotification(
  mock: MockWebSocket,
  method: string,
  params?: Record<string, unknown>,
): void {
  mock.simulateMessage({
    jsonrpc: JSONRPC_VERSION,
    method,
    ...(params !== undefined ? { params } : {}),
  });
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("EventClient", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  // -----------------------------------------------------------------------
  // subscribe()
  // -----------------------------------------------------------------------

  describe("subscribe()", () => {
    it("sends rois.event.subscribe and returns the subscribe_id", async () => {
      const { events, mock } = await createConnectedEventClient();

      const resultPromise = events.subscribe("PersonDetection_0", "person_detected");
      respondWithResult(mock, {
        return_code: "OK",
        subscribe_id: "sub-001",
      });

      const subscribeId = await resultPromise;
      expect(subscribeId).toBe("sub-001");

      const sent = mock.sent[1] as Record<string, unknown>;
      expect(sent.method).toBe("rois.event.subscribe");
      expect(sent.params).toEqual({
        component_ref: "PersonDetection_0",
        event_type: "person_detected",
        condition: "",
      });
    });

    it("passes a custom condition", async () => {
      const { events, mock } = await createConnectedEventClient();

      events.subscribe("PersonDetection_0", "person_detected", "confidence>0.8");
      const sent = mock.sent[1] as Record<string, unknown>;
      expect((sent.params as Record<string, unknown>).condition).toBe("confidence>0.8");

      respondWithResult(mock, { return_code: "OK", subscribe_id: "sub-002" });
    });

    it("throws RoISError on non-OK return code", async () => {
      const { events, mock } = await createConnectedEventClient();

      const resultPromise = events.subscribe("PersonDetection_0", "unknown_event");
      respondWithResult(mock, { return_code: "UNSUPPORTED", subscribe_id: "" });

      await expect(resultPromise).rejects.toThrow(RoISError);
      try {
        await resultPromise;
      } catch (err) {
        expect((err as RoISError).returnCode).toBe("UNSUPPORTED");
        expect((err as RoISError).method).toBe("rois.event.subscribe");
      }
    });
  });

  // -----------------------------------------------------------------------
  // unsubscribe()
  // -----------------------------------------------------------------------

  describe("unsubscribe()", () => {
    it("sends rois.event.unsubscribe and returns the ReturnCode", async () => {
      const { events, mock } = await createConnectedEventClient();

      const resultPromise = events.unsubscribe("sub-001");
      respondWithResult(mock, { return_code: "OK" });

      const returnCode = await resultPromise;
      expect(returnCode).toBe("OK");

      const sent = mock.sent[1] as Record<string, unknown>;
      expect(sent.method).toBe("rois.event.unsubscribe");
      expect(sent.params).toEqual({ subscribe_id: "sub-001" });
    });

    it("throws RoISError on non-OK return code", async () => {
      const { events, mock } = await createConnectedEventClient();

      const resultPromise = events.unsubscribe("sub-001");
      respondWithResult(mock, { return_code: "ERROR" });

      await expect(resultPromise).rejects.toThrow(RoISError);
    });
  });

  // -----------------------------------------------------------------------
  // getEventDetail()
  // -----------------------------------------------------------------------

  describe("getEventDetail()", () => {
    it("sends rois.event.get_event_detail with the event_id", async () => {
      const { events, mock } = await createConnectedEventClient();

      const resultPromise = events.getEventDetail("evt-001");
      respondWithResult(mock, {
        return_code: "OK",
        results: [
          { name: "number", data_type_ref: "int", value: "3" },
          { name: "timestamp", data_type_ref: "DateTime", value: "2026-07-08T12:00:00Z" },
        ],
      });

      const results = await resultPromise;
      expect(results).toHaveLength(2);
      expect(results[0].name).toBe("number");
      expect(results[0].value).toBe("3");

      const sent = mock.sent[1] as Record<string, unknown>;
      expect(sent.method).toBe("rois.event.get_event_detail");
      expect(sent.params).toEqual({ event_id: "evt-001" });
    });

    it("returns empty array when results is undefined", async () => {
      const { events, mock } = await createConnectedEventClient();

      const resultPromise = events.getEventDetail("evt-unknown");
      respondWithResult(mock, { return_code: "OK" });

      const results = await resultPromise;
      expect(results).toEqual([]);
    });

    it("throws RoISError on non-OK return code", async () => {
      const { events, mock } = await createConnectedEventClient();

      const resultPromise = events.getEventDetail("evt-001");
      respondWithResult(mock, { return_code: "ERROR", results: [] });

      await expect(resultPromise).rejects.toThrow(RoISError);
    });
  });

  // -----------------------------------------------------------------------
  // Notification dispatch
  // -----------------------------------------------------------------------

  describe("notification dispatch", () => {
    it("emits 'notify' for any rois.event.notify push", async () => {
      const { events, mock } = await createConnectedEventClient();
      const handler = vi.fn();
      events.on("notify", handler);

      sendNotification(mock, "rois.event.notify", {
        event_id: "evt-001",
        event_type: "person_detected",
        subscribe_id: "sub-001",
        expire: "",
      });

      expect(handler).toHaveBeenCalledOnce();
      const payload = handler.mock.calls[0][0];
      expect(payload.event_id).toBe("evt-001");
      expect(payload.event_type).toBe("person_detected");
      expect(payload.subscribe_id).toBe("sub-001");
    });

    it("emits the specific event_type for convenience", async () => {
      const { events, mock } = await createConnectedEventClient();
      const handler = vi.fn();
      events.on("person_detected", handler);

      sendNotification(mock, "rois.event.notify", {
        event_id: "evt-002",
        event_type: "person_detected",
        subscribe_id: "sub-001",
        expire: "",
      });

      expect(handler).toHaveBeenCalledOnce();
      const payload = handler.mock.calls[0][0];
      expect(payload.event_id).toBe("evt-002");
    });

    it("emits different event_types to different handlers", async () => {
      const { events, mock } = await createConnectedEventClient();
      const personHandler = vi.fn();
      const faceHandler = vi.fn();
      events.on("person_detected", personHandler);
      events.on("face_localized", faceHandler);

      sendNotification(mock, "rois.event.notify", {
        event_id: "evt-001",
        event_type: "person_detected",
        subscribe_id: "sub-001",
        expire: "",
      });
      sendNotification(mock, "rois.event.notify", {
        event_id: "evt-002",
        event_type: "face_localized",
        subscribe_id: "sub-002",
        expire: "",
      });

      expect(personHandler).toHaveBeenCalledOnce();
      expect(faceHandler).toHaveBeenCalledOnce();
    });

    it("ignores notifications with no params", async () => {
      const { events, mock } = await createConnectedEventClient();
      const handler = vi.fn();
      events.on("notify", handler);

      sendNotification(mock, "rois.event.notify");

      expect(handler).not.toHaveBeenCalled();
    });

    it("ignores notifications with invalid payload (schema validation)", async () => {
      const { events, mock } = await createConnectedEventClient();
      const handler = vi.fn();
      events.on("notify", handler);

      // Missing required event_id field.
      sendNotification(mock, "rois.event.notify", {
        event_type: "person_detected",
        subscribe_id: "sub-001",
      });

      expect(handler).not.toHaveBeenCalled();
    });
  });

  // -----------------------------------------------------------------------
  // Integration with RoISEngine
  // -----------------------------------------------------------------------

  describe("integration with RoISEngine", () => {
    it("can be constructed from engine.getTransport after connect", async () => {
      const connectPromise = RoISEngine.connect("ws://test:8765", testOptions);
      currentMock.simulateOpen();
      for (let i = 0; i < 5; i++) {
        await Promise.resolve();
      }
      respondWithResult(currentMock, { return_code: "OK" });
      const engine = await connectPromise;

      const events = new EventClient(engine.getTransport);
      expect(events).toBeInstanceOf(EventClient);

      await engine.disconnect();
    });

    it("throws TransportError when the transport is not connected", async () => {
      const { engine, events } = await createConnectedEventClient();
      await engine.disconnect();

      await expect(events.subscribe("x", "y")).rejects.toThrow(TransportError);
      await expect(events.unsubscribe("x")).rejects.toThrow(TransportError);
      await expect(events.getEventDetail("x")).rejects.toThrow(TransportError);
    });
  });

  // -----------------------------------------------------------------------
  // Full workflow: subscribe -> notify -> getEventDetail -> unsubscribe
  // -----------------------------------------------------------------------

  describe("full workflow", () => {
    it("completes a subscribe -> notify -> getEventDetail -> unsubscribe cycle", async () => {
      const { events, mock } = await createConnectedEventClient();

      // 1. Subscribe.
      const subPromise = events.subscribe("PersonDetection_0", "person_detected");
      respondWithResult(mock, { return_code: "OK", subscribe_id: "sub-001" });
      const subId = await subPromise;
      expect(subId).toBe("sub-001");

      // 2. Receive notification.
      const notifyHandler = vi.fn();
      events.on("person_detected", notifyHandler);

      sendNotification(mock, "rois.event.notify", {
        event_id: "evt-001",
        event_type: "person_detected",
        subscribe_id: "sub-001",
        expire: "",
      });

      expect(notifyHandler).toHaveBeenCalledOnce();
      const payload = notifyHandler.mock.calls[0][0];
      expect(payload.event_id).toBe("evt-001");

      // 3. Get event detail.
      const detailPromise = events.getEventDetail("evt-001");
      respondWithResult(mock, {
        return_code: "OK",
        results: [
          { name: "number", data_type_ref: "int", value: "3" },
        ],
      });
      const details = await detailPromise;
      expect(details).toHaveLength(1);
      expect(details[0].value).toBe("3");

      // 4. Unsubscribe.
      const unsubPromise = events.unsubscribe(subId);
      respondWithResult(mock, { return_code: "OK" });
      expect(await unsubPromise).toBe("OK");
    });
  });
});