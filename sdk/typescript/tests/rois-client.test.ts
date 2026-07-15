/**
 * RoISClient Unit tests for rois-client.ts -- RoISClient high-level SDK entry point.
 *
 * Uses the same MockWebSocket pattern as transport.test.ts to simulate
 * the gateway. The client creates its own transport internally, so we
 * inject the mock via the webSocketFactory option.
 *
 * Run with: npx vitest run
 */

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import {
  RoISClient,
  RoISError,
  type ClientOptions,
} from "../src/rois-client";
import { TransportError } from "../src/transport";
import { JSONRPC_VERSION, JsonRpcErrorCode } from "../src/jsonrpc";

// ---------------------------------------------------------------------------
// MockWebSocket (same pattern as transport.test.ts)
// ---------------------------------------------------------------------------

class MockWebSocket {
  readyState: number = 0; // CONNECTING

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
    this.readyState = 3; // CLOSED
  }

  simulateOpen(): void {
    this.readyState = 1; // OPEN
    this.onopen?.({ type: "open" });
  }

  simulateMessage(data: unknown): void {
    const raw = typeof data === "string" ? data : JSON.stringify(data);
    this.onmessage?.({ data: raw, type: "message" });
  }

  simulateClose(code: number = 1000, reason: string = ""): void {
    this.readyState = 3;
    this.onclose?.({ code, reason, type: "close" });
  }

  simulateError(message: string = "connection refused"): void {
    this.onerror?.({ message, type: "error" });
  }
}

// ---------------------------------------------------------------------------
// Test helpers
// ---------------------------------------------------------------------------

/** Tracks the most recently created MockWebSocket so tests can interact with it. */
let currentMock: MockWebSocket;

/** Engine options that inject our MockWebSocket. */
const testOptions: ClientOptions = {
  transport: {
    webSocketFactory: (_url: string) => {
      currentMock = new MockWebSocket();
      return currentMock as any;
    },
  },
};

/**
 * Create a connected RoISClient wired to a MockWebSocket.
 * Returns the client and the mock for simulating gateway responses.
 */
async function createConnectedClient(): Promise<{
  client: RoISClient;
  mock: MockWebSocket;
}> {
  const connectPromise = RoISClient.connect("ws://test-gateway:8765", testOptions);
  // The factory runs synchronously inside connect(), so currentMock is set.
  currentMock.simulateOpen();
  // The client's connect() awaits transport.connect(), which resolves on
  // simulateOpen(). After that, connect() sends rois.system.connect.
  // We need to drain microtasks so the send runs before we respond.
  // With fake timers, we need several awaits to let the promise chain
  // progress from transport.connect() resolution to the transport.send()
  // call inside client.connect().
  for (let i = 0; i < 5; i++) {
    await Promise.resolve();
  }
  // Simulate the gateway responding with { return_code: "OK" }.
  respondWithResult(currentMock, { return_code: "OK" });
  const client = await connectPromise;
  return { client, mock: currentMock };
}

/**
 * Simulate a gateway response to the most recent request.
 *
 * Reads the id from the last sent message and wraps the result
 * in a JSON-RPC success response.
 */
function respondWithResult(mock: MockWebSocket, result: unknown): void {
  const lastSent = mock.sent[mock.sent.length - 1] as Record<string, unknown>;
  mock.simulateMessage({
    jsonrpc: JSONRPC_VERSION,
    id: lastSent.id,
    result,
  });
}

/**
 * Simulate a gateway JSON-RPC error response to the most recent request.
 */
function respondWithError(
  mock: MockWebSocket,
  code: number,
  message: string,
  data?: unknown,
): void {
  const lastSent = mock.sent[mock.sent.length - 1] as Record<string, unknown>;
  mock.simulateMessage({
    jsonrpc: JSONRPC_VERSION,
    id: lastSent.id,
    error: { code, message, ...(data !== undefined ? { data } : {}) },
  });
}

/**
 * Simulate a gateway notification (no id).
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

describe("RoISClient", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  // -----------------------------------------------------------------------
  // connect() and disconnect()
  // -----------------------------------------------------------------------

  describe("connect()", () => {
    it("returns a connected client instance", async () => {
      const { client } = await createConnectedClient();
      expect(client).toBeInstanceOf(RoISClient);
    });

    it("rejects if the WebSocket connection fails", async () => {
      const connectPromise = RoISClient.connect("ws://bad-gateway:8765", testOptions);
      currentMock.simulateError("connection refused");

      await expect(connectPromise).rejects.toThrow();
    });

    it("sends rois.system.connect with empty params", async () => {
      const { mock } = await createConnectedClient();
      const connectMsg = mock.sent[0] as Record<string, unknown>;
      expect(connectMsg.method).toBe("rois.system.connect");
      // The token is NOT in the params. Auth is at the transport layer.
      expect(connectMsg.params).toBeUndefined();
    });

    it("rejects if the gateway returns a non-OK return code", async () => {
      const connectPromise = RoISClient.connect("ws://test-gateway:8765", testOptions);
      currentMock.simulateOpen();
      // Drain microtasks so the client sends rois.system.connect.
      for (let i = 0; i < 5; i++) {
        await Promise.resolve();
      }
      // Respond with UNSUPPORTED instead of OK.
      respondWithResult(currentMock, { return_code: "UNSUPPORTED" });

      await expect(connectPromise).rejects.toThrow(RoISError);
    });
  });

  describe("disconnect()", () => {
    it("disconnects without error", async () => {
      const { client } = await createConnectedClient();
      await client.disconnect();

      // Methods should throw after disconnect.
      await expect(client.search()).rejects.toThrow("not connected");
    });

    it("is safe to call multiple times", async () => {
      const { client } = await createConnectedClient();
      await client.disconnect();
      await client.disconnect(); // Should not throw.
    });
  });

  // -----------------------------------------------------------------------
  // Guards
  // -----------------------------------------------------------------------

  describe("ensureConnected guard", () => {
    it("throws TransportError when calling methods on a disconnected client", async () => {
      const { client } = await createConnectedClient();
      await client.disconnect();

      await expect(client.search()).rejects.toThrow(TransportError);
      await expect(client.query("x", "y")).rejects.toThrow(TransportError);
      await expect(client.subscribe("x", "y")).rejects.toThrow(TransportError);
      await expect(client.execute("x", {})).rejects.toThrow(TransportError);
    });
  });

  // -----------------------------------------------------------------------
  // SystemIF
  // -----------------------------------------------------------------------

  describe("getProfile()", () => {
    it("sends rois.system.get_profile and returns the result", async () => {
      const { client, mock } = await createConnectedClient();

      const resultPromise = client.getProfile();
      respondWithResult(mock, { profile: "<xml>...</xml>" });

      const result = await resultPromise;
      expect(result).toEqual({ profile: "<xml>...</xml>" });

      const sent = mock.sent[1] as Record<string, unknown>;
      expect(sent.method).toBe("rois.system.get_profile");
    });
  });

  describe("getErrorDetail()", () => {
    it("sends rois.system.get_error_detail with the error_id", async () => {
      const { client, mock } = await createConnectedClient();

      const resultPromise = client.getErrorDetail("err-001");
      respondWithResult(mock, { detail: "component timeout" });

      const result = await resultPromise;
      expect(result).toEqual({ detail: "component timeout" });

      const sent = mock.sent[1] as Record<string, unknown>;
      expect(sent.method).toBe("rois.system.get_error_detail");
      expect(sent.params).toEqual({ error_id: "err-001" });
    });
  });

  // -----------------------------------------------------------------------
  // CommandIF
  // -----------------------------------------------------------------------

  describe("search()", () => {
    it("returns component_ref_list from a DiscoverResponse", async () => {
      const { client, mock } = await createConnectedClient();

      const resultPromise = client.search();
      respondWithResult(mock, {
        return_code: "OK",
        component_ref_list: ["PersonDetection_0", "Navigation_0", "SystemInformation_0"],
      });

      const components = await resultPromise;
      expect(components).toEqual(["PersonDetection_0", "Navigation_0", "SystemInformation_0"]);
    });

    it("sends an empty condition by default", async () => {
      const { client, mock } = await createConnectedClient();

      client.search();
      const sent = mock.sent[1] as Record<string, unknown>;
      expect(sent.params).toEqual({ condition: "" });

      respondWithResult(mock, { return_code: "OK", component_ref_list: [] });
    });

    it("passes a custom condition", async () => {
      const { client, mock } = await createConnectedClient();

      client.search("urn:x-rois:def:component:OMG::PersonDetection");
      const sent = mock.sent[1] as Record<string, unknown>;
      expect((sent.params as Record<string, unknown>).condition).toBe(
        "urn:x-rois:def:component:OMG::PersonDetection"
      );

      respondWithResult(mock, { return_code: "OK", component_ref_list: ["PersonDetection_0"] });
    });

    it("returns empty array when component_ref_list is undefined", async () => {
      const { client, mock } = await createConnectedClient();

      const resultPromise = client.search();
      respondWithResult(mock, { return_code: "OK" });

      const components = await resultPromise;
      expect(components).toEqual([]);
    });

    it("throws RoISError on non-OK return code", async () => {
      const { client, mock } = await createConnectedClient();

      const resultPromise = client.search("bad-filter");
      respondWithResult(mock, { return_code: "BAD_PARAMETER" });

      await expect(resultPromise).rejects.toThrow(RoISError);
      try {
        await resultPromise;
      } catch (err) {
        expect((err as RoISError).returnCode).toBe("BAD_PARAMETER");
        expect((err as RoISError).method).toBe("rois.command.search");
      }
    });
  });

  describe("bind()", () => {
    it("sends rois.command.bind with the component_ref", async () => {
      const { client, mock } = await createConnectedClient();

      const resultPromise = client.bind("PersonDetection_0");
      respondWithResult(mock, { return_code: "OK" });

      const returnCode = await resultPromise;
      expect(returnCode).toBe("OK");

      const sent = mock.sent[1] as Record<string, unknown>;
      expect(sent.method).toBe("rois.command.bind");
      expect(sent.params).toEqual({ component_ref: "PersonDetection_0" });
    });

    it("throws RoISError when binding a nonexistent component", async () => {
      const { client, mock } = await createConnectedClient();

      const resultPromise = client.bind("UnknownComponent_0");
      respondWithResult(mock, { return_code: "UNSUPPORTED" });

      await expect(resultPromise).rejects.toThrow(RoISError);
    });
  });

  describe("release()", () => {
    it("sends rois.command.release and returns the ReturnCode", async () => {
      const { client, mock } = await createConnectedClient();

      const resultPromise = client.release("PersonDetection_0");
      respondWithResult(mock, { return_code: "OK" });

      const returnCode = await resultPromise;
      expect(returnCode).toBe("OK");

      const sent = mock.sent[1] as Record<string, unknown>;
      expect(sent.method).toBe("rois.command.release");
    });
  });

  describe("setParameter()", () => {
    it("sends rois.command.set_parameter and returns InvokeResponse", async () => {
      const { client, mock } = await createConnectedClient();

      const resultPromise = client.setParameter("Navigation_0", [
        { name: "target_positions", data_type_ref: "string[]", value: '["3.0,1.5,0.0"]' },
        { name: "time_limit", data_type_ref: "int", value: "30" },
        { name: "routing_policy", data_type_ref: "string", value: "time" },
      ]);

      respondWithResult(mock, {
        return_code: "OK",
        command_id: "cmd-nav-001",
      });

      const response = await resultPromise;
      expect(response.return_code).toBe("OK");
      expect(response.command_id).toBe("cmd-nav-001");
    });
  });

  describe("execute()", () => {
    it("sends rois.command.execute and returns InvokeResponse with command_id", async () => {
      const { client, mock } = await createConnectedClient();

      const resultPromise = client.execute("Navigation_0", {
        target_positions: ["3.0,1.5,0.0"],
        time_limit: 30,
      });

      respondWithResult(mock, {
        return_code: "OK",
        command_id: "cmd-nav-002",
        results: [],
      });

      const response = await resultPromise;
      expect(response.command_id).toBe("cmd-nav-002");

      const sent = mock.sent[1] as Record<string, unknown>;
      expect(sent.method).toBe("rois.command.execute");
    });

    it("throws RoISError on non-OK return code", async () => {
      const { client, mock } = await createConnectedClient();

      const resultPromise = client.execute("Navigation_0", {});
      respondWithResult(mock, { return_code: "ERROR", command_id: "" });

      await expect(resultPromise).rejects.toThrow(RoISError);
    });
  });

  describe("getCommandResult()", () => {
    it("sends rois.command.get_command_result and returns results", async () => {
      const { client, mock } = await createConnectedClient();

      const resultPromise = client.getCommandResult("cmd-nav-002");
      respondWithResult(mock, {
        return_code: "OK",
        results: [
          { name: "status", data_type_ref: "CompletedStatus", value: "OK" },
        ],
      });

      const results = await resultPromise;
      expect(results).toHaveLength(1);
      expect(results[0].name).toBe("status");

      const sent = mock.sent[1] as Record<string, unknown>;
      expect(sent.params).toEqual({ command_id: "cmd-nav-002" });
    });
  });

  // -----------------------------------------------------------------------
  // QueryIF
  // -----------------------------------------------------------------------

  describe("query()", () => {
    it("sends rois.query.query and returns validated results", async () => {
      const { client, mock } = await createConnectedClient();

      const resultPromise = client.query("PersonDetection_0", "component_status");
      respondWithResult(mock, {
        return_code: "OK",
        results: [
          { name: "status", data_type_ref: "ComponentStatus", value: "READY" },
        ],
      });

      const results = await resultPromise;
      expect(results).toHaveLength(1);
      expect(results[0].value).toBe("READY");

      const sent = mock.sent[1] as Record<string, unknown>;
      expect(sent.method).toBe("rois.query.query");
      expect(sent.params).toEqual({
        component_ref: "PersonDetection_0",
        query_type: "component_status",
        condition: "",
      });
    });

    it("passes a custom condition", async () => {
      const { client, mock } = await createConnectedClient();

      client.query("SystemInformation_0", "robot_position", "robot_ref=robot_1");
      const sent = mock.sent[1] as Record<string, unknown>;
      expect((sent.params as Record<string, unknown>).condition).toBe("robot_ref=robot_1");

      respondWithResult(mock, { return_code: "OK", results: [] });
    });

    it("returns empty array when results is undefined", async () => {
      const { client, mock } = await createConnectedClient();

      const resultPromise = client.query("PersonDetection_0", "component_status");
      respondWithResult(mock, { return_code: "OK" });

      const results = await resultPromise;
      expect(results).toEqual([]);
    });

    it("throws RoISError on non-OK return code", async () => {
      const { client, mock } = await createConnectedClient();

      const resultPromise = client.query("PersonDetection_0", "unknown_query");
      respondWithResult(mock, { return_code: "UNSUPPORTED" });

      await expect(resultPromise).rejects.toThrow(RoISError);
    });
  });

  // -----------------------------------------------------------------------
  // EventIF
  // -----------------------------------------------------------------------

  describe("subscribe()", () => {
    it("sends rois.event.subscribe and returns the subscribe_id", async () => {
      const { client, mock } = await createConnectedClient();

      const resultPromise = client.subscribe("PersonDetection_0", "person_detected");
      respondWithResult(mock, {
        return_code: "OK",
        subscribe_id: "sub-pd-001",
      });

      const subscribeId = await resultPromise;
      expect(subscribeId).toBe("sub-pd-001");

      const sent = mock.sent[1] as Record<string, unknown>;
      expect(sent.method).toBe("rois.event.subscribe");
      expect(sent.params).toEqual({
        component_ref: "PersonDetection_0",
        event_type: "person_detected",
        condition: "",
      });
    });

    it("throws RoISError on non-OK return code", async () => {
      const { client, mock } = await createConnectedClient();

      const resultPromise = client.subscribe("PersonDetection_0", "unknown_event");
      respondWithResult(mock, { return_code: "UNSUPPORTED", subscribe_id: "" });

      await expect(resultPromise).rejects.toThrow(RoISError);
    });
  });

  describe("unsubscribe()", () => {
    it("sends rois.event.unsubscribe and returns the ReturnCode", async () => {
      const { client, mock } = await createConnectedClient();

      const resultPromise = client.unsubscribe("sub-pd-001");
      respondWithResult(mock, { return_code: "OK" });

      const returnCode = await resultPromise;
      expect(returnCode).toBe("OK");

      const sent = mock.sent[1] as Record<string, unknown>;
      expect(sent.method).toBe("rois.event.unsubscribe");
      expect(sent.params).toEqual({ subscribe_id: "sub-pd-001" });
    });
  });

  describe("getEventDetail()", () => {
    it("sends rois.event.get_event_detail with the event_id", async () => {
      const { client, mock } = await createConnectedClient();

      const resultPromise = client.getEventDetail("evt-001");
      respondWithResult(mock, {
        event_id: "evt-001",
        event_type: "person_detected",
        payload: [
          { name: "timestamp", data_type_ref: "DateTime", value: "2026-06-30T10:00:00Z" },
          { name: "number", data_type_ref: "int", value: "3" },
        ],
      });

      const result = await resultPromise;
      expect(result).toHaveProperty("event_id", "evt-001");

      const sent = mock.sent[1] as Record<string, unknown>;
      expect(sent.method).toBe("rois.event.get_event_detail");
      expect(sent.params).toEqual({ event_id: "evt-001" });
    });
  });

  // -----------------------------------------------------------------------
  // Event forwarding
  // -----------------------------------------------------------------------

  describe("event forwarding", () => {
    it("emits 'notification' for any server push", async () => {
      const { client, mock } = await createConnectedClient();
      const handler = vi.fn();
      client.on("notification", handler);

      sendNotification(mock, "rois.event.notify", {
        event_id: "evt-001",
        event_type: "person_detected",
        subscribe_id: "sub-pd-001",
      });

      expect(handler).toHaveBeenCalledOnce();
    });

    it("emits 'rois.event.notify' for component events", async () => {
      const { client, mock } = await createConnectedClient();
      const handler = vi.fn();
      client.on("rois.event.notify", handler);

      sendNotification(mock, "rois.event.notify", {
        event_id: "evt-001",
        event_type: "person_detected",
      });

      expect(handler).toHaveBeenCalledOnce();
    });

    it("emits the specific event_type for convenience", async () => {
      const { client, mock } = await createConnectedClient();
      const handler = vi.fn();
      client.on("person_detected", handler);

      sendNotification(mock, "rois.event.notify", {
        event_id: "evt-001",
        event_type: "person_detected",
        subscribe_id: "sub-pd-001",
        payload: [
          { name: "number", data_type_ref: "int", value: "2" },
        ],
      });

      expect(handler).toHaveBeenCalledOnce();
    });

    it("emits 'rois.command.completed' for command completions", async () => {
      const { client, mock } = await createConnectedClient();
      const handler = vi.fn();
      client.on("rois.command.completed", handler);

      sendNotification(mock, "rois.command.completed", {
        command_id: "cmd-nav-002",
        status: "OK",
      });

      expect(handler).toHaveBeenCalledOnce();
      expect(handler.mock.calls[0][0]).toMatchObject({
        method: "rois.command.completed",
      });
    });

    it("emits 'rois.system.notify_error' for gateway errors", async () => {
      const { client, mock } = await createConnectedClient();
      const handler = vi.fn();
      client.on("rois.system.notify_error", handler);

      sendNotification(mock, "rois.system.notify_error", {
        error_id: "err-001",
        error_type: "COMPONENT_NOT_RESPONDING",
      });

      expect(handler).toHaveBeenCalledOnce();
    });

    it("emits 'close' and marks disconnected on unexpected close", async () => {
      const { client, mock } = await createConnectedClient();
      const closeHandler = vi.fn();
      client.on("close", closeHandler);

      mock.simulateClose(1006, "abnormal closure");

      expect(closeHandler).toHaveBeenCalledWith(1006, "abnormal closure");

      // Engine should be disconnected now.
      await expect(client.search()).rejects.toThrow("not connected");
    });
  });

  // -----------------------------------------------------------------------
  // Error handling
  // -----------------------------------------------------------------------

  describe("error handling", () => {
    it("throws RpcError when the gateway returns a JSON-RPC error", async () => {
      const { client, mock } = await createConnectedClient();

      const resultPromise = client.search();
      respondWithError(
        mock,
        JsonRpcErrorCode.InternalError,
        "Gateway internal error",
      );

      await expect(resultPromise).rejects.toThrow("Gateway internal error");
    });

    it("throws RoISError with the specific ReturnCode on domain errors", async () => {
      const { client, mock } = await createConnectedClient();

      const resultPromise = client.bind("UnknownComponent_0");
      respondWithResult(mock, { return_code: "UNSUPPORTED" });

      try {
        await resultPromise;
        expect.unreachable("should have thrown");
      } catch (err) {
        expect(err).toBeInstanceOf(RoISError);
        const roisErr = err as RoISError;
        expect(roisErr.returnCode).toBe("UNSUPPORTED");
        expect(roisErr.method).toBe("rois.command.bind");
      }
    });

    it("throws RoISError with TIMEOUT return code", async () => {
      const { client, mock } = await createConnectedClient();

      const resultPromise = client.execute("Navigation_0", {});
      respondWithResult(mock, {
        return_code: "TIMEOUT",
        command_id: "",
      });

      try {
        await resultPromise;
        expect.unreachable("should have thrown");
      } catch (err) {
        expect(err).toBeInstanceOf(RoISError);
        expect((err as RoISError).returnCode).toBe("TIMEOUT");
      }
    });

    it("rejects pending requests when the connection drops", async () => {
      const { client, mock } = await createConnectedClient();

      const searchPromise = client.search();
      const queryPromise = client.query("PersonDetection_0", "component_status");

      mock.simulateClose(1006, "unexpected disconnect");

      await expect(searchPromise).rejects.toThrow();
      await expect(queryPromise).rejects.toThrow();
    });
  });

  // -----------------------------------------------------------------------
  // Full workflow: search -> bind -> subscribe -> execute -> release
  // -----------------------------------------------------------------------

  describe("full workflow", () => {
    it("completes a search -> bind -> execute -> release cycle", async () => {
      const { client, mock } = await createConnectedClient();

      // 1. Search for components.
      const searchPromise = client.search();
      respondWithResult(mock, {
        return_code: "OK",
        component_ref_list: ["Navigation_0"],
      });
      const components = await searchPromise;
      expect(components).toContain("Navigation_0");

      // 2. Bind the component.
      const bindPromise = client.bind("Navigation_0");
      respondWithResult(mock, { return_code: "OK" });
      await bindPromise;

      // 3. Execute a navigation command.
      const execPromise = client.execute("Navigation_0", {
        target_positions: ["3.0,1.5,0.0"],
        time_limit: 30,
      });
      respondWithResult(mock, {
        return_code: "OK",
        command_id: "cmd-nav-001",
        results: [],
      });
      const execResponse = await execPromise;
      expect(execResponse.command_id).toBe("cmd-nav-001");

      // 4. Receive command completion notification.
      const completedHandler = vi.fn();
      client.on("rois.command.completed", completedHandler);

      sendNotification(mock, "rois.command.completed", {
        command_id: "cmd-nav-001",
        status: "OK",
      });
      expect(completedHandler).toHaveBeenCalledOnce();

      // 5. Release the component.
      const releasePromise = client.release("Navigation_0");
      respondWithResult(mock, { return_code: "OK" });
      const releaseCode = await releasePromise;
      expect(releaseCode).toBe("OK");

      // 6. Disconnect.
      await client.disconnect();
    });
  });
});