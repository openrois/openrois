/**
 * Unit tests for query-rois-client.ts -- QueryClient (QueryIF operations).
 *
 * Uses the same MockWebSocket pattern as rois-client.test.ts to simulate the
 * gateway. QueryClient is constructed over the client's transport.
 *
 * Run with: npx vitest run
 */

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { RoISClient, RoISError, type EngineOptions } from "../src/rois-client";
import { QueryClient } from "../src/query-client";
import { TransportError } from "../src/transport";
import { JSONRPC_VERSION } from "../src/jsonrpc";

// ---------------------------------------------------------------------------
// MockWebSocket (same pattern as rois-client.test.ts)
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

async function createConnectedQueryClient(): Promise<{
  client: RoISClient;
  query: QueryClient;
  mock: MockWebSocket;
}> {
  const connectPromise = RoISClient.connect("ws://test-gateway:8765", testOptions);
  currentMock.simulateOpen();
  // Drain microtasks so the rois.system.connect send fires before we respond.
  for (let i = 0; i < 5; i++) {
    await Promise.resolve();
  }
  respondWithResult(currentMock, { return_code: "OK" });
  const client = await connectPromise;
  const query = new QueryClient(client.getTransport);
  return { client, query, mock: currentMock };
}

function respondWithResult(mock: MockWebSocket, result: unknown): void {
  const lastSent = mock.sent[mock.sent.length - 1] as Record<string, unknown>;
  mock.simulateMessage({
    jsonrpc: JSONRPC_VERSION,
    id: lastSent.id,
    result,
  });
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("QueryClient", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  // -----------------------------------------------------------------------
  // query()
  // -----------------------------------------------------------------------

  describe("query()", () => {
    it("sends rois.query.query and returns validated results", async () => {
      const { query, mock } = await createConnectedQueryClient();

      const resultPromise = query.query("SystemInformation_0", "robot_position");
      respondWithResult(mock, {
        return_code: "OK",
        results: [
          { name: "position", data_type_ref: "string", value: "1.5,2.0,0.0" },
          { name: "orientation", data_type_ref: "string", value: "0.0,0.0,0.0,1.0" },
        ],
      });

      const results = await resultPromise;
      expect(results).toHaveLength(2);
      expect(results[0].name).toBe("position");
      expect(results[0].value).toBe("1.5,2.0,0.0");

      const sent = mock.sent[1] as Record<string, unknown>;
      expect(sent.method).toBe("rois.query.query");
      expect(sent.params).toEqual({
        component_ref: "SystemInformation_0",
        query_type: "robot_position",
        condition: "",
      });
    });

    it("passes a custom condition", async () => {
      const { query, mock } = await createConnectedQueryClient();

      query.query("SystemInformation_0", "robot_position", "robot_ref=robot_1");
      const sent = mock.sent[1] as Record<string, unknown>;
      expect((sent.params as Record<string, unknown>).condition).toBe("robot_ref=robot_1");

      respondWithResult(mock, { return_code: "OK", results: [] });
    });

    it("returns empty array when results is undefined", async () => {
      const { query, mock } = await createConnectedQueryClient();

      const resultPromise = query.query("SystemInformation_0", "robot_position");
      respondWithResult(mock, { return_code: "OK" });

      const results = await resultPromise;
      expect(results).toEqual([]);
    });

    it("throws RoISError on non-OK return code", async () => {
      const { query, mock } = await createConnectedQueryClient();

      const resultPromise = query.query("Unknown_0", "unknown_query");
      respondWithResult(mock, { return_code: "UNSUPPORTED", results: [] });

      await expect(resultPromise).rejects.toThrow(RoISError);
      try {
        await resultPromise;
      } catch (err) {
        expect((err as RoISError).returnCode).toBe("UNSUPPORTED");
        expect((err as RoISError).method).toBe("rois.query.query");
      }
    });
  });

  // -----------------------------------------------------------------------
  // Integration with RoISClient
  // -----------------------------------------------------------------------

  describe("integration with RoISClient", () => {
    it("can be constructed from client.getTransport after connect", async () => {
      const connectPromise = RoISClient.connect("ws://test:8765", testOptions);
      currentMock.simulateOpen();
      for (let i = 0; i < 5; i++) {
        await Promise.resolve();
      }
      respondWithResult(currentMock, { return_code: "OK" });
      const client = await connectPromise;

      const query = new QueryClient(client.getTransport);
      expect(query).toBeInstanceOf(QueryClient);

      await client.disconnect();
    });

    it("throws TransportError when the transport is not connected", async () => {
      const { client, query } = await createConnectedQueryClient();
      await client.disconnect();

      await expect(query.query("x", "y")).rejects.toThrow(TransportError);
    });
  });
});