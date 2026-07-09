/**
 * Unit tests for command-client.ts -- CommandClient (CommandIF operations).
 *
 * Uses the same MockWebSocket pattern as engine.test.ts to simulate the
 * gateway. CommandClient is constructed over the engine's transport.
 *
 * Run with: npx vitest run
 */

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { RoISEngine, RoISError, type EngineOptions } from "../src/engine";
import { CommandClient } from "../src/command-client";
import { TransportError } from "../src/transport";
import { JSONRPC_VERSION } from "../src/jsonrpc";
import type { Parameter } from "@openrois/interfaces";

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

async function createConnectedCommandClient(): Promise<{
  engine: RoISEngine;
  command: CommandClient;
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
  const command = new CommandClient(engine.getTransport);
  return { engine, command, mock: currentMock };
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

describe("CommandClient", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  // -----------------------------------------------------------------------
  // search()
  // -----------------------------------------------------------------------

  describe("search()", () => {
    it("sends rois.command.search and returns component_ref_list", async () => {
      const { command, mock } = await createConnectedCommandClient();

      const resultPromise = command.search();
      respondWithResult(mock, {
        return_code: "OK",
        component_ref_list: ["PersonDetection_0", "Navigation_0"],
      });

      const refs = await resultPromise;
      expect(refs).toEqual(["PersonDetection_0", "Navigation_0"]);

      const sent = mock.sent[1] as Record<string, unknown>;
      expect(sent.method).toBe("rois.command.search");
      expect(sent.params).toEqual({ condition: "" });
    });

    it("passes a custom condition", async () => {
      const { command, mock } = await createConnectedCommandClient();

      command.search("component=Navigation");
      const sent = mock.sent[1] as Record<string, unknown>;
      expect(sent.params).toEqual({ condition: "component=Navigation" });

      respondWithResult(mock, { return_code: "OK", component_ref_list: [] });
    });

    it("returns empty array when component_ref_list is undefined", async () => {
      const { command, mock } = await createConnectedCommandClient();

      const resultPromise = command.search();
      respondWithResult(mock, { return_code: "OK" });

      const refs = await resultPromise;
      expect(refs).toEqual([]);
    });

    it("throws RoISError on non-OK return code", async () => {
      const { command, mock } = await createConnectedCommandClient();

      const resultPromise = command.search("bad-filter");
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

  // -----------------------------------------------------------------------
  // bind()
  // -----------------------------------------------------------------------

  describe("bind()", () => {
    it("sends rois.command.bind with the component_ref", async () => {
      const { command, mock } = await createConnectedCommandClient();

      const resultPromise = command.bind("PersonDetection_0");
      respondWithResult(mock, { return_code: "OK" });

      const returnCode = await resultPromise;
      expect(returnCode).toBe("OK");

      const sent = mock.sent[1] as Record<string, unknown>;
      expect(sent.method).toBe("rois.command.bind");
      expect(sent.params).toEqual({ component_ref: "PersonDetection_0" });
    });

    it("throws RoISError when binding a nonexistent component", async () => {
      const { command, mock } = await createConnectedCommandClient();

      const resultPromise = command.bind("UnknownComponent_0");
      respondWithResult(mock, { return_code: "UNSUPPORTED" });

      await expect(resultPromise).rejects.toThrow(RoISError);
      try {
        await resultPromise;
      } catch (err) {
        expect((err as RoISError).returnCode).toBe("UNSUPPORTED");
        expect((err as RoISError).method).toBe("rois.command.bind");
      }
    });
  });

  // -----------------------------------------------------------------------
  // release()
  // -----------------------------------------------------------------------

  describe("release()", () => {
    it("sends rois.command.release and returns the ReturnCode", async () => {
      const { command, mock } = await createConnectedCommandClient();

      const resultPromise = command.release("PersonDetection_0");
      respondWithResult(mock, { return_code: "OK" });

      const returnCode = await resultPromise;
      expect(returnCode).toBe("OK");

      const sent = mock.sent[1] as Record<string, unknown>;
      expect(sent.method).toBe("rois.command.release");
      expect(sent.params).toEqual({ component_ref: "PersonDetection_0" });
    });

    it("throws RoISError for an unknown component", async () => {
      const { command, mock } = await createConnectedCommandClient();

      const resultPromise = command.release("Unknown_0");
      respondWithResult(mock, { return_code: "UNSUPPORTED" });

      await expect(resultPromise).rejects.toThrow(RoISError);
    });
  });

  // -----------------------------------------------------------------------
  // getParameter()
  // -----------------------------------------------------------------------

  describe("getParameter()", () => {
    it("sends rois.command.get_parameter and returns results", async () => {
      const { command, mock } = await createConnectedCommandClient();

      const resultPromise = command.getParameter("Navigation_0");
      respondWithResult(mock, {
        return_code: "OK",
        results: [
          { name: "time_limit", data_type_ref: "int", value: "30" },
          { name: "routing_policy", data_type_ref: "string", value: "time" },
        ],
      });

      const results = await resultPromise;
      expect(results).toHaveLength(2);
      expect(results[0].name).toBe("time_limit");
      expect(results[0].value).toBe("30");

      const sent = mock.sent[1] as Record<string, unknown>;
      expect(sent.method).toBe("rois.command.get_parameter");
      expect(sent.params).toEqual({ component_ref: "Navigation_0" });
    });

    it("passes names filter when provided", async () => {
      const { command, mock } = await createConnectedCommandClient();

      command.getParameter("Navigation_0", ["time_limit", "routing_policy"]);
      const sent = mock.sent[1] as Record<string, unknown>;
      expect(sent.params).toEqual({
        component_ref: "Navigation_0",
        names: ["time_limit", "routing_policy"],
      });

      respondWithResult(mock, {
        return_code: "OK",
        results: [{ name: "time_limit", data_type_ref: "int", value: "30" }],
      });
    });

    it("returns empty array when results is undefined", async () => {
      const { command, mock } = await createConnectedCommandClient();

      const resultPromise = command.getParameter("Navigation_0");
      respondWithResult(mock, { return_code: "OK" });

      const results = await resultPromise;
      expect(results).toEqual([]);
    });

    it("throws RoISError on non-OK return code", async () => {
      const { command, mock } = await createConnectedCommandClient();

      const resultPromise = command.getParameter("Unknown_0");
      respondWithResult(mock, { return_code: "UNSUPPORTED", results: [] });

      await expect(resultPromise).rejects.toThrow(RoISError);
    });
  });

  // -----------------------------------------------------------------------
  // setParameter()
  // -----------------------------------------------------------------------

  describe("setParameter()", () => {
    it("sends rois.command.set_parameter with validated parameters", async () => {
      const { command, mock } = await createConnectedCommandClient();

      const params: Parameter[] = [
        { name: "target_positions", data_type_ref: "string[]", value: '["3.0,1.5,0.0"]' },
        { name: "time_limit", data_type_ref: "int", value: "30" },
      ];

      const resultPromise = command.setParameter("Navigation_0", params);
      respondWithResult(mock, { return_code: "OK", command_id: "" });

      const response = await resultPromise;
      expect(response.return_code).toBe("OK");

      const sent = mock.sent[1] as Record<string, unknown>;
      expect(sent.method).toBe("rois.command.set_parameter");
      expect(sent.params).toEqual({
        component_ref: "Navigation_0",
        parameters: params,
      });
    });

    it("throws when parameters do not validate against the Parameter schema", async () => {
      const { command } = await createConnectedCommandClient();

      // Missing data_type_ref and value.
      const badParams = [{ name: "bad" }] as unknown as Parameter[];

      await expect(command.setParameter("Navigation_0", badParams)).rejects.toThrow();
    });

    it("throws RoISError on non-OK return code", async () => {
      const { command, mock } = await createConnectedCommandClient();

      const resultPromise = command.setParameter("Unknown_0", [
        { name: "x", data_type_ref: "string", value: "1" },
      ]);
      respondWithResult(mock, { return_code: "UNSUPPORTED", command_id: "" });

      await expect(resultPromise).rejects.toThrow(RoISError);
      try {
        await resultPromise;
      } catch (err) {
        expect((err as RoISError).returnCode).toBe("UNSUPPORTED");
        expect((err as RoISError).method).toBe("rois.command.set_parameter");
      }
    });
  });

  // -----------------------------------------------------------------------
  // bindAny()
  // -----------------------------------------------------------------------

  describe("bindAny()", () => {
    it("sends rois.command.bind_any with the condition and returns component_ref", async () => {
      const { command, mock } = await createConnectedCommandClient();

      const resultPromise = command.bindAny("component=Navigation");
      respondWithResult(mock, {
        return_code: "OK",
        component_ref: "Navigation_0",
      });

      const ref = await resultPromise;
      expect(ref).toBe("Navigation_0");

      const sent = mock.sent[1] as Record<string, unknown>;
      expect(sent.method).toBe("rois.command.bind_any");
      expect(sent.params).toEqual({ condition: "component=Navigation" });
    });

    it("sends an empty condition by default", async () => {
      const { command, mock } = await createConnectedCommandClient();

      command.bindAny();
      const sent = mock.sent[1] as Record<string, unknown>;
      expect(sent.params).toEqual({ condition: "" });

      respondWithResult(mock, { return_code: "OK", component_ref: "PersonDetection_0" });
    });

    it("throws RoISError on non-OK return code", async () => {
      const { command, mock } = await createConnectedCommandClient();

      const resultPromise = command.bindAny("component=Nonexistent");
      respondWithResult(mock, { return_code: "OUT_OF_RESOURCES", component_ref: "" });

      await expect(resultPromise).rejects.toThrow(RoISError);
      try {
        await resultPromise;
      } catch (err) {
        expect((err as RoISError).returnCode).toBe("OUT_OF_RESOURCES");
        expect((err as RoISError).method).toBe("rois.command.bind_any");
      }
    });
  });

  // -----------------------------------------------------------------------
  // execute()
  // -----------------------------------------------------------------------

  describe("execute()", () => {
    it("sends rois.command.execute and returns InvokeResponse with command_id", async () => {
      const { command, mock } = await createConnectedCommandClient();

      const resultPromise = command.execute("Navigation_0", {
        target_positions: ["3.0,1.5,0.0"],
        time_limit: 30,
      });

      respondWithResult(mock, {
        return_code: "OK",
        command_id: "cmd-nav-001",
        results: [],
      });

      const response = await resultPromise;
      expect(response.return_code).toBe("OK");
      expect(response.command_id).toBe("cmd-nav-001");

      const sent = mock.sent[1] as Record<string, unknown>;
      expect(sent.method).toBe("rois.command.execute");
      expect(sent.params).toEqual({
        component_ref: "Navigation_0",
        target_positions: ["3.0,1.5,0.0"],
        time_limit: 30,
      });
    });

    it("throws RoISError on non-OK return code", async () => {
      const { command, mock } = await createConnectedCommandClient();

      const resultPromise = command.execute("Navigation_0", {});
      respondWithResult(mock, { return_code: "ERROR", command_id: "" });

      await expect(resultPromise).rejects.toThrow(RoISError);
      try {
        await resultPromise;
      } catch (err) {
        expect((err as RoISError).returnCode).toBe("ERROR");
        expect((err as RoISError).method).toBe("rois.command.execute");
      }
    });
  });

  // -----------------------------------------------------------------------
  // getCommandResult()
  // -----------------------------------------------------------------------

  describe("getCommandResult()", () => {
    it("sends rois.command.get_command_result and returns results", async () => {
      const { command, mock } = await createConnectedCommandClient();

      const resultPromise = command.getCommandResult("cmd-nav-001");
      respondWithResult(mock, {
        return_code: "OK",
        results: [
          { name: "status", data_type_ref: "CompletedStatus", value: "OK" },
        ],
      });

      const results = await resultPromise;
      expect(results).toHaveLength(1);
      expect(results[0].name).toBe("status");
      expect(results[0].value).toBe("OK");

      const sent = mock.sent[1] as Record<string, unknown>;
      expect(sent.method).toBe("rois.command.get_command_result");
      expect(sent.params).toEqual({ command_id: "cmd-nav-001" });
    });

    it("returns empty array when results is undefined", async () => {
      const { command, mock } = await createConnectedCommandClient();

      const resultPromise = command.getCommandResult("cmd-001");
      respondWithResult(mock, { return_code: "OK" });

      const results = await resultPromise;
      expect(results).toEqual([]);
    });

    it("throws RoISError on non-OK return code", async () => {
      const { command, mock } = await createConnectedCommandClient();

      const resultPromise = command.getCommandResult("cmd-001");
      respondWithResult(mock, { return_code: "ERROR", results: [] });

      await expect(resultPromise).rejects.toThrow(RoISError);
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

      const command = new CommandClient(engine.getTransport);
      expect(command).toBeInstanceOf(CommandClient);

      await engine.disconnect();
    });

    it("throws TransportError when the transport is not connected", async () => {
      const { engine, command } = await createConnectedCommandClient();
      await engine.disconnect();

      await expect(command.search()).rejects.toThrow(TransportError);
      await expect(command.bind("x")).rejects.toThrow(TransportError);
      await expect(command.bindAny()).rejects.toThrow(TransportError);
      await expect(command.release("x")).rejects.toThrow(TransportError);
      await expect(command.getParameter("x")).rejects.toThrow(TransportError);

      await expect(
        command.setParameter("x", [{ name: "n", data_type_ref: "string", value: "v" }]),
      ).rejects.toThrow(TransportError);
      
      await expect(command.execute("x", {})).rejects.toThrow(TransportError);
      await expect(command.getCommandResult("x")).rejects.toThrow(TransportError);
    });
  });

  // -----------------------------------------------------------------------
  // Full workflow: search -> bind -> setParameter -> getParameter -> release
  // -----------------------------------------------------------------------

  describe("full workflow", () => {
    it("completes a search -> bind -> setParameter -> getParameter -> release cycle", async () => {
      const { command, mock } = await createConnectedCommandClient();

      // 1. Search
      const searchPromise = command.search();
      respondWithResult(mock, {
        return_code: "OK",
        component_ref_list: ["Navigation_0"],
      });
      const refs = await searchPromise;
      expect(refs).toContain("Navigation_0");

      // 2. Bind
      const bindPromise = command.bind("Navigation_0");
      respondWithResult(mock, { return_code: "OK" });
      expect(await bindPromise).toBe("OK");

      // 3. Set parameters
      const setPromise = command.setParameter("Navigation_0", [
        { name: "target_positions", data_type_ref: "string[]", value: '["3.0,1.5,0.0"]' },
        { name: "time_limit", data_type_ref: "int", value: "60" },
      ]);
      respondWithResult(mock, { return_code: "OK", command_id: "" });
      expect((await setPromise).return_code).toBe("OK");

      // 4. Get parameters back
      const getPromise = command.getParameter("Navigation_0", ["time_limit"]);
      respondWithResult(mock, {
        return_code: "OK",
        results: [{ name: "time_limit", data_type_ref: "int", value: "60" }],
      });
      const results = await getPromise;
      expect(results[0].value).toBe("60");

      // 5. Release
      const releasePromise = command.release("Navigation_0");
      respondWithResult(mock, { return_code: "OK" });
      expect(await releasePromise).toBe("OK");
    });
  });
});