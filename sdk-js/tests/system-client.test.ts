/**
 * Unit tests for system-client.ts -- SystemClient (SystemIF query operations).
 *
 * Uses the same MockWebSocket pattern as engine.test.ts to simulate the
 * gateway. SystemClient is constructed over the engine's transport, so we
 * create a connected RoISEngine first and then wrap its transport.
 *
 * Run with: npx vitest run
 */

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { RoISEngine, RoISError, type EngineOptions } from "../src/engine";
import { SystemClient } from "../src/system-client";
import { TransportError } from "../src/transport";
import { JSONRPC_VERSION } from "../src/jsonrpc";
import type { HRIEngineProfileType } from "@openrois/interfaces";

// ---------------------------------------------------------------------------
// MockWebSocket (same pattern as engine.test.ts)
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
const testOptions: EngineOptions = {
  transport: {
    webSocketFactory: (_url: string) => {
      currentMock = new MockWebSocket();
      return currentMock as any;
    },
  },
};

/**
 * Create a connected RoISEngine and a SystemClient over its transport.
 * Returns the engine, the system client, and the mock for simulating responses.
 */
async function createConnectedSystemClient(): Promise<{
  engine: RoISEngine;
  system: SystemClient;
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
  const system = new SystemClient(engine.getTransport);
  return { engine, system, mock: currentMock };
}

/**
 * Simulate a gateway response to the most recent request.
 */
function respondWithResult(mock: MockWebSocket, result: unknown): void {
  const lastSent = mock.sent[mock.sent.length - 1] as Record<string, unknown>;
  mock.simulateMessage({
    jsonrpc: JSONRPC_VERSION,
    id: lastSent.id,
    result,
  });
}

// ---------------------------------------------------------------------------
// Canned profile used in tests
// ---------------------------------------------------------------------------

const CANNED_PROFILE: HRIEngineProfileType = {
  identifier: {
    authority: "OMG",
    code: "MockGateway",
    codebook_ref: "",
    version: "2.0",
  },
  sub_profiles: [
    {
      identifier: {
        authority: "OMG",
        code: "PerceptionSubEngine",
        codebook_ref: "",
        version: "2.0",
      },
      component_ids: ["PersonDetection_0"],
    },
  ],
  component_ids: ["PersonDetection_0", "Navigation_0", "SystemInformation_0"],
  parameter_profiles: [],
};

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("SystemClient", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  // -----------------------------------------------------------------------
  // getProfile()
  // -----------------------------------------------------------------------

  describe("getProfile()", () => {
    it("sends rois.system.get_profile and returns the validated profile", async () => {
      const { system, mock } = await createConnectedSystemClient();

      const resultPromise = system.getProfile();
      respondWithResult(mock, {
        return_code: "OK",
        profile: CANNED_PROFILE,
      });

      const profile = await resultPromise;
      expect(profile.identifier.code).toBe("MockGateway");
      expect(profile.component_ids).toEqual([
        "PersonDetection_0",
        "Navigation_0",
        "SystemInformation_0",
      ]);
      expect(profile.sub_profiles).toHaveLength(1);
      expect(profile.sub_profiles![0].identifier.code).toBe("PerceptionSubEngine");

      const sent = mock.sent[1] as Record<string, unknown>;
      expect(sent.method).toBe("rois.system.get_profile");
      expect(sent.params).toEqual({ condition: "" });
    });

    it("passes a custom condition", async () => {
      const { system, mock } = await createConnectedSystemClient();

      system.getProfile("component=Navigation");
      const sent = mock.sent[1] as Record<string, unknown>;
      expect(sent.params).toEqual({ condition: "component=Navigation" });

      respondWithResult(mock, { return_code: "OK", profile: CANNED_PROFILE });
    });

    it("throws RoISError on non-OK return code", async () => {
      const { system, mock } = await createConnectedSystemClient();

      const resultPromise = system.getProfile();
      respondWithResult(mock, { return_code: "UNSUPPORTED", profile: null });

      await expect(resultPromise).rejects.toThrow(RoISError);
      try {
        await resultPromise;
      } catch (err) {
        expect((err as RoISError).returnCode).toBe("UNSUPPORTED");
        expect((err as RoISError).method).toBe("rois.system.get_profile");
      }
    });

    it("throws when the profile does not validate against the schema", async () => {
      const { system, mock } = await createConnectedSystemClient();

      const resultPromise = system.getProfile();
      // Missing required 'identifier' field.
      respondWithResult(mock, {
        return_code: "OK",
        profile: { component_ids: ["x"] },
      });

      await expect(resultPromise).rejects.toThrow();
    });
  });

  // -----------------------------------------------------------------------
  // getErrorDetail()
  // -----------------------------------------------------------------------

  describe("getErrorDetail()", () => {
    it("sends rois.system.get_error_detail with the error_id and returns results", async () => {
      const { system, mock } = await createConnectedSystemClient();

      const resultPromise = system.getErrorDetail("err-001");
      respondWithResult(mock, {
        return_code: "OK",
        results: [
          { name: "component_ref", data_type_ref: "string", value: "robot-a1/Navigation" },
          { name: "description", data_type_ref: "string", value: "Navigation action timed out after 30s" },
        ],
      });

      const results = await resultPromise;
      expect(results).toHaveLength(2);
      expect(results[0].name).toBe("component_ref");
      expect(results[0].value).toBe("robot-a1/Navigation");
      expect(results[1].name).toBe("description");

      const sent = mock.sent[1] as Record<string, unknown>;
      expect(sent.method).toBe("rois.system.get_error_detail");
      expect(sent.params).toEqual({ error_id: "err-001" });
    });

    it("returns empty array when results is undefined", async () => {
      const { system, mock } = await createConnectedSystemClient();

      const resultPromise = system.getErrorDetail("err-unknown");
      respondWithResult(mock, { return_code: "OK" });

      const results = await resultPromise;
      expect(results).toEqual([]);
    });

    it("throws RoISError on non-OK return code", async () => {
      const { system, mock } = await createConnectedSystemClient();

      const resultPromise = system.getErrorDetail("err-001");
      respondWithResult(mock, { return_code: "ERROR", results: [] });

      await expect(resultPromise).rejects.toThrow(RoISError);
      try {
        await resultPromise;
      } catch (err) {
        expect((err as RoISError).returnCode).toBe("ERROR");
        expect((err as RoISError).method).toBe("rois.system.get_error_detail");
      }
    });

    it("throws when results do not validate against the Result schema", async () => {
      const { system, mock } = await createConnectedSystemClient();

      const resultPromise = system.getErrorDetail("err-001");
      // Missing required 'value' field on a Result.
      respondWithResult(mock, {
        return_code: "OK",
        results: [{ name: "bad", data_type_ref: "string" }],
      });

      await expect(resultPromise).rejects.toThrow();
    });
  });

  // -----------------------------------------------------------------------
  // Integration with RoISEngine
  // -----------------------------------------------------------------------

  describe("integration with RoISEngine", () => {
    it("can be constructed from engine.transport after connect", async () => {
      const connectPromise = RoISEngine.connect("ws://test:8765", testOptions);
      currentMock.simulateOpen();
      for (let i = 0; i < 5; i++) {
        await Promise.resolve();
      }
      respondWithResult(currentMock, { return_code: "OK" });
      const engine = await connectPromise;

      const system = new SystemClient(engine.getTransport);
      expect(system).toBeInstanceOf(SystemClient);

      await engine.disconnect();
    });

    it("throws TransportError when the transport is not connected", async () => {
      const { engine, system } = await createConnectedSystemClient();
      await engine.disconnect();

      await expect(system.getProfile()).rejects.toThrow(TransportError);
      await expect(system.getErrorDetail("err-001")).rejects.toThrow(TransportError);
    });
  });
});