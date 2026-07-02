/**
 * Unit tests for transport.ts -- WebSocket transport layer.
 *
 * Uses a MockWebSocket class to simulate the gateway without a real server.
 * The mock tracks sent messages, lets tests trigger incoming messages, and
 * simulates open/close/error events.
 *
 * Run with: npx vitest run
 */

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import {
  WebSocketTransport,
  TransportState,
  TransportError,
  ConnectionError,
  RequestTimeoutError,
  RpcError,
  WS_READY_STATE,
  type WebSocketLike,
} from "../src/transport";
import { JsonRpcErrorCode, JSONRPC_VERSION } from "../src/jsonrpc";

// ---------------------------------------------------------------------------
// MockWebSocket -- simulates the gateway side for testing
// ---------------------------------------------------------------------------

/**
 * A fake WebSocket that the transport can use in place of a real connection.
 *
 * Tests control the mock to simulate server behavior:
 *   mock.simulateOpen()    - triggers the onopen handler (connection established)
 *   mock.simulateMessage() - triggers onmessage with a JSON payload
 *   mock.simulateClose()   - triggers onclose
 *   mock.simulateError()   - triggers onerror
 *
 * The mock also records every message sent by the transport via send(),
 * accessible through mock.sent (array of parsed JSON objects).
 */
class MockWebSocket implements WebSocketLike {
  readyState: number = WS_READY_STATE.CONNECTING;

  onopen: ((event: { type: string }) => void) | null = null;
  onclose: ((event: { code: number; reason: string; type: string }) => void) | null = null;
  onmessage: ((event: { data: unknown; type: string }) => void) | null = null;
  onerror: ((event: { error?: unknown; message?: string; type: string }) => void) | null = null;

  /** Messages sent by the transport, parsed back to objects for easy assertion. */
  sent: unknown[] = [];

  /** Raw string messages sent by the transport. */
  sentRaw: string[] = [];

  send(data: string): void {
    this.sentRaw.push(data);
    try {
      this.sent.push(JSON.parse(data));
    } catch {
      this.sent.push(data);
    }
  }

  close(_code?: number, _reason?: string): void {
    this.readyState = WS_READY_STATE.CLOSED;
  }

  // --- Test helpers: simulate server-side events ---

  /** Simulate a successful connection. */
  simulateOpen(): void {
    this.readyState = WS_READY_STATE.OPEN;
    this.onopen?.({ type: "open" });
  }

  /** Simulate an incoming message from the gateway. */
  simulateMessage(data: unknown): void {
    const raw = typeof data === "string" ? data : JSON.stringify(data);
    this.onmessage?.({ data: raw, type: "message" });
  }

  /** Simulate the connection closing. */
  simulateClose(code: number = 1000, reason: string = ""): void {
    this.readyState = WS_READY_STATE.CLOSED;
    this.onclose?.({ code, reason, type: "close" });
  }

  /** Simulate a WebSocket error. */
  simulateError(message: string = "connection refused"): void {
    this.onerror?.({ message, type: "error" });
  }
}

// ---------------------------------------------------------------------------
// Test helpers
// ---------------------------------------------------------------------------

/** Create a transport wired to a mock WebSocket. Returns both. */
function createTestTransport(options?: {
  requestTimeout?: number;
  connectTimeout?: number;
}) {
  let mockWs: MockWebSocket;

  const transport = new WebSocketTransport({
    requestTimeout: options?.requestTimeout,
    connectTimeout: options?.connectTimeout,
    webSocketFactory: (_url: string) => {
      mockWs = new MockWebSocket();
      return mockWs;
    },
  });

  // Helper that connects and opens in one step (most tests need this).
  async function connectAndOpen(): Promise<MockWebSocket> {
    const connectPromise = transport.connect("ws://test-gateway:8765");
    // The factory runs synchronously inside connect(), so mockWs is set.
    mockWs!.simulateOpen();
    await connectPromise;
    return mockWs!;
  }

  return { transport, getMock: () => mockWs!, connectAndOpen };
}

/**
 * Build a JSON-RPC success response for a given request id and result.
 */
function successResponse(id: string, result: unknown) {
  return { jsonrpc: JSONRPC_VERSION, id, result };
}

/**
 * Build a JSON-RPC error response for a given request id.
 */
function errorResponse(id: string, code: number, message: string, data?: unknown) {
  return {
    jsonrpc: JSONRPC_VERSION,
    id,
    error: { code, message, ...(data !== undefined ? { data } : {}) },
  };
}

/**
 * Build a JSON-RPC notification.
 */
function notification(method: string, params?: Record<string, unknown>) {
  return {
    jsonrpc: JSONRPC_VERSION,
    method,
    ...(params !== undefined ? { params } : {}),
  };
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("WebSocketTransport", () => {
  // Use fake timers for timeout tests.
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  // -----------------------------------------------------------------------
  // connect()
  // -----------------------------------------------------------------------

  describe("connect()", () => {
    it("transitions to CONNECTED when the WebSocket opens", async () => {
      const { transport, connectAndOpen } = createTestTransport();
      expect(transport.state).toBe(TransportState.DISCONNECTED);

      await connectAndOpen();
      expect(transport.state).toBe(TransportState.CONNECTED);
    });

    it("emits an 'open' event on successful connection", async () => {
      const { transport, connectAndOpen } = createTestTransport();
      const openHandler = vi.fn();
      transport.on("open", openHandler);

      await connectAndOpen();
      expect(openHandler).toHaveBeenCalledOnce();
    });

    it("rejects if the WebSocket fires an error during connection", async () => {
      const { transport, getMock } = createTestTransport();

      const connectPromise = transport.connect("ws://test-gateway:8765");
      getMock().simulateError("connection refused");

      await expect(connectPromise).rejects.toThrow(ConnectionError);
      expect(transport.state).toBe(TransportState.DISCONNECTED);
    });

    it("rejects if the WebSocket closes during connection", async () => {
      const { transport, getMock } = createTestTransport();

      const connectPromise = transport.connect("ws://test-gateway:8765");
      getMock().simulateClose(1006, "abnormal closure");

      await expect(connectPromise).rejects.toThrow(ConnectionError);
      expect(transport.state).toBe(TransportState.DISCONNECTED);
    });

    it("rejects if the connection times out", async () => {
      const { transport } = createTestTransport({ connectTimeout: 500 });

      const connectPromise = transport.connect("ws://test-gateway:8765");
      // Advance time past the connect timeout without opening the socket.
      vi.advanceTimersByTime(600);

      await expect(connectPromise).rejects.toThrow(ConnectionError);
      await expect(connectPromise).rejects.toThrow("timed out");
      expect(transport.state).toBe(TransportState.DISCONNECTED);
    });

    it("rejects if called while already connected", async () => {
      const { transport, connectAndOpen } = createTestTransport();

      await connectAndOpen();

      await expect(
        transport.connect("ws://other-gateway:8765")
      ).rejects.toThrow(ConnectionError);
    });

    it("rejects if the WebSocket factory throws", async () => {
      const transport = new WebSocketTransport({
        webSocketFactory: () => { throw new Error("no ws library"); },
      });

      await expect(
        transport.connect("ws://test-gateway:8765")
      ).rejects.toThrow(ConnectionError);
      expect(transport.state).toBe(TransportState.DISCONNECTED);
    });
  });

  // -----------------------------------------------------------------------
  // send() -- request/response correlation
  // -----------------------------------------------------------------------

  describe("send()", () => {
    it("sends a JSON-RPC request and resolves with the result", async () => {
      const { transport, connectAndOpen } = createTestTransport();
      const mock = await connectAndOpen();

      // Send a request.
      const resultPromise = transport.send("rois.command.search", { condition: "" });

      // Inspect what the transport sent over the wire.
      expect(mock.sent).toHaveLength(1);
      const sent = mock.sent[0] as Record<string, unknown>;
      expect(sent.jsonrpc).toBe("2.0");
      expect(sent.method).toBe("rois.command.search");
      expect(sent.id).toBe("req-1");
      expect(sent.params).toEqual({ condition: "" });

      // Simulate the gateway responding.
      mock.simulateMessage(successResponse("req-1", {
        return_code: "OK",
        component_ref_list: ["PersonDetection_0", "Navigation_0"],
      }));

      const result = await resultPromise;
      expect(result).toEqual({
        return_code: "OK",
        component_ref_list: ["PersonDetection_0", "Navigation_0"],
      });
    });

    it("auto-increments request ids", async () => {
      const { transport, connectAndOpen } = createTestTransport();
      const mock = await connectAndOpen();

      // Fire two requests (don't await, just send).
      transport.send("rois.command.search", { condition: "" });
      transport.send("rois.query.query", {
        component_ref: "PersonDetection_0",
        query_type: "component_status",
      });

      expect((mock.sent[0] as Record<string, unknown>).id).toBe("req-1");
      expect((mock.sent[1] as Record<string, unknown>).id).toBe("req-2");

      // Resolve both to avoid hanging promises.
      mock.simulateMessage(successResponse("req-1", { return_code: "OK" }));
      mock.simulateMessage(successResponse("req-2", { return_code: "OK" }));
    });

    it("omits params when not provided", async () => {
      const { transport, connectAndOpen } = createTestTransport();
      const mock = await connectAndOpen();

      transport.send("rois.system.connect");
      const sent = mock.sent[0] as Record<string, unknown>;
      expect(sent).not.toHaveProperty("params");

      // Resolve to avoid hanging.
      mock.simulateMessage(successResponse("req-1", null));
    });

    it("rejects with RpcError on a JSON-RPC error response", async () => {
      const { transport, connectAndOpen } = createTestTransport();
      const mock = await connectAndOpen();

      const resultPromise = transport.send("rois.command.fly", {});

      mock.simulateMessage(errorResponse(
        "req-1",
        JsonRpcErrorCode.MethodNotFound,
        "Method not found: rois.command.fly",
      ));

      await expect(resultPromise).rejects.toThrow(RpcError);
      await expect(resultPromise).rejects.toThrow("Method not found");
    });

    it("includes RoIS ReturnCode in RpcError data for domain errors", async () => {
      const { transport, connectAndOpen } = createTestTransport();
      const mock = await connectAndOpen();

      const resultPromise = transport.send("rois.command.bind", {
        component_ref: "UnknownComponent_0",
      });

      mock.simulateMessage(errorResponse(
        "req-1",
        JsonRpcErrorCode.InvalidParams,
        "Component not found",
        { return_code: "UNSUPPORTED" },
      ));

      try {
        await resultPromise;
        expect.unreachable("should have thrown");
      } catch (err) {
        expect(err).toBeInstanceOf(RpcError);
        const rpcErr = err as RpcError;
        expect(rpcErr.code).toBe(JsonRpcErrorCode.InvalidParams);
        expect(rpcErr.data).toEqual({ return_code: "UNSUPPORTED" });
      }
    });

    it("rejects with RequestTimeoutError when no response arrives in time", async () => {
      const { transport, connectAndOpen } = createTestTransport({
        requestTimeout: 1000,
      });
      await connectAndOpen();

      const resultPromise = transport.send("rois.query.query", {
        component_ref: "Navigation_0",
        query_type: "component_status",
      });

      // Advance past the request timeout.
      vi.advanceTimersByTime(1100);

      await expect(resultPromise).rejects.toThrow(RequestTimeoutError);
      await expect(resultPromise).rejects.toThrow("timed out");
    });

    it("rejects with TransportError when not connected", async () => {
      const { transport } = createTestTransport();

      await expect(
        transport.send("rois.command.search", { condition: "" })
      ).rejects.toThrow(TransportError);
    });
  });

  // -----------------------------------------------------------------------
  // Request/response correlation with multiple in-flight requests
  // -----------------------------------------------------------------------

  describe("correlation", () => {
    it("resolves the correct promise when responses arrive out of order", async () => {
      const { transport, connectAndOpen } = createTestTransport();
      const mock = await connectAndOpen();

      // Send two requests.
      const first = transport.send("rois.command.search", { condition: "" });
      const second = transport.send("rois.query.query", {
        component_ref: "Navigation_0",
        query_type: "component_status",
      });

      // Respond to the second request first.
      mock.simulateMessage(successResponse("req-2", {
        return_code: "OK",
        results: [{ name: "status", data_type_ref: "ComponentStatus", value: "READY" }],
      }));

      // Then respond to the first.
      mock.simulateMessage(successResponse("req-1", {
        return_code: "OK",
        component_ref_list: ["Navigation_0"],
      }));

      // Each promise should get its own result.
      const firstResult = await first as Record<string, unknown>;
      const secondResult = await second as Record<string, unknown>;

      expect(firstResult).toHaveProperty("component_ref_list");
      expect(secondResult).toHaveProperty("results");
    });

    it("handles many concurrent in-flight requests", async () => {
      const { transport, connectAndOpen } = createTestTransport();
      const mock = await connectAndOpen();

      // Fire 10 requests.
      const promises = Array.from({ length: 10 }, (_, i) =>
        transport.send("rois.command.search", { condition: `filter-${i}` })
      );

      // Respond to all in reverse order.
      for (let i = 9; i >= 0; i--) {
        mock.simulateMessage(successResponse(`req-${i + 1}`, { index: i }));
      }

      const results = await Promise.all(promises);
      results.forEach((result, i) => {
        expect(result).toEqual({ index: i });
      });
    });
  });

  // -----------------------------------------------------------------------
  // Notifications
  // -----------------------------------------------------------------------

  describe("notifications", () => {
    it("emits a generic 'notification' event for any notification", async () => {
      const { transport, connectAndOpen } = createTestTransport();
      const mock = await connectAndOpen();
      const handler = vi.fn();
      transport.on("notification", handler);

      mock.simulateMessage(notification("rois.event.notify", {
        event_id: "evt-001",
        event_type: "person_detected",
        subscribe_id: "sub-1",
      }));

      expect(handler).toHaveBeenCalledOnce();
      expect(handler.mock.calls[0][0]).toMatchObject({
        method: "rois.event.notify",
      });
    });

    it("emits a method-specific event for targeted listeners", async () => {
      const { transport, connectAndOpen } = createTestTransport();
      const mock = await connectAndOpen();
      const eventHandler = vi.fn();
      const completedHandler = vi.fn();
      transport.on("rois.event.notify", eventHandler);
      transport.on("rois.command.completed", completedHandler);

      // Send a person_detected notification.
      mock.simulateMessage(notification("rois.event.notify", {
        event_id: "evt-001",
        event_type: "person_detected",
      }));

      // Send a command completed notification.
      mock.simulateMessage(notification("rois.command.completed", {
        command_id: "cmd-001",
        status: "OK",
      }));

      expect(eventHandler).toHaveBeenCalledOnce();
      expect(completedHandler).toHaveBeenCalledOnce();
    });

    it("emits a notify_error notification", async () => {
      const { transport, connectAndOpen } = createTestTransport();
      const mock = await connectAndOpen();
      const handler = vi.fn();
      transport.on("rois.system.notify_error", handler);

      mock.simulateMessage(notification("rois.system.notify_error", {
        error_id: "err-001",
        error_type: "COMPONENT_NOT_RESPONDING",
      }));

      expect(handler).toHaveBeenCalledOnce();
    });
  });

  // -----------------------------------------------------------------------
  // close()
  // -----------------------------------------------------------------------

  describe("close()", () => {
    it("transitions to DISCONNECTED", async () => {
      const { transport, connectAndOpen } = createTestTransport();
      await connectAndOpen();
      expect(transport.state).toBe(TransportState.CONNECTED);

      transport.close();
      expect(transport.state).toBe(TransportState.DISCONNECTED);
    });

    it("emits a 'close' event", async () => {
      const { transport, connectAndOpen } = createTestTransport();
      await connectAndOpen();
      const closeHandler = vi.fn();
      transport.on("close", closeHandler);

      transport.close(1000, "done");
      expect(closeHandler).toHaveBeenCalledWith(1000, "done");
    });

    it("rejects all pending requests with ConnectionError", async () => {
      const { transport, connectAndOpen } = createTestTransport();
      const mock = await connectAndOpen();

      const pendingPromise = transport.send("rois.command.search", { condition: "" });

      transport.close();

      await expect(pendingPromise).rejects.toThrow(ConnectionError);
      await expect(pendingPromise).rejects.toThrow("closed by client");
    });

    it("is a no-op when already disconnected", () => {
      const { transport } = createTestTransport();
      expect(transport.state).toBe(TransportState.DISCONNECTED);

      // Should not throw.
      transport.close();
      expect(transport.state).toBe(TransportState.DISCONNECTED);
    });
  });

  // -----------------------------------------------------------------------
  // Error handling
  // -----------------------------------------------------------------------

  describe("error handling", () => {
    it("rejects all pending requests on unexpected disconnect", async () => {
      const { transport, connectAndOpen } = createTestTransport();
      const mock = await connectAndOpen();

      const pending1 = transport.send("rois.command.search", { condition: "" });
      const pending2 = transport.send("rois.query.query", {
        component_ref: "Navigation_0",
        query_type: "component_status",
      });

      // Simulate unexpected server disconnect.
      mock.simulateClose(1006, "abnormal closure");

      await expect(pending1).rejects.toThrow(ConnectionError);
      await expect(pending2).rejects.toThrow(ConnectionError);
      expect(transport.state).toBe(TransportState.DISCONNECTED);
    });

    it("emits 'error' on malformed JSON from gateway", async () => {
      const { transport, connectAndOpen } = createTestTransport();
      const mock = await connectAndOpen();
      const errorHandler = vi.fn();
      transport.on("error", errorHandler);

      mock.simulateMessage("this is not valid JSON{{{");

      expect(errorHandler).toHaveBeenCalledOnce();
      expect(errorHandler.mock.calls[0][0]).toBeInstanceOf(TransportError);
      expect(errorHandler.mock.calls[0][0].message).toContain("malformed JSON");
    });

    it("emits 'error' on unrecognized message shape", async () => {
      const { transport, connectAndOpen } = createTestTransport();
      const mock = await connectAndOpen();
      const errorHandler = vi.fn();
      transport.on("error", errorHandler);

      // A message with no recognizable JSON-RPC fields.
      mock.simulateMessage({ foo: "bar" });

      expect(errorHandler).toHaveBeenCalledOnce();
      expect(errorHandler.mock.calls[0][0].message).toContain("unrecognized");
    });

    it("emits 'error' for a response with an unknown request id", async () => {
      const { transport, connectAndOpen } = createTestTransport();
      const mock = await connectAndOpen();
      const errorHandler = vi.fn();
      transport.on("error", errorHandler);

      // Response for a request that was never sent.
      mock.simulateMessage(successResponse("req-999", { return_code: "OK" }));

      expect(errorHandler).toHaveBeenCalledOnce();
      expect(errorHandler.mock.calls[0][0].message).toContain("unknown request id");
    });

    it("can connect again after a disconnect", async () => {
      const { transport, connectAndOpen } = createTestTransport();

      // First connection.
      await connectAndOpen();
      transport.close();
      expect(transport.state).toBe(TransportState.DISCONNECTED);

      // Second connection.
      await connectAndOpen();
      expect(transport.state).toBe(TransportState.CONNECTED);
    });
  });
});