/**
 * Self-tests for the mock gateway WebSocket server (Week 1 skeleton).
 *
 * Each test starts a gateway on an ephemeral port, connects a real ws client,
 * sends a JSON-RPC message, and asserts on the reply. This exercises the full
 * parse -> validate -> dispatch -> respond path over an actual socket.
 */

import { afterAll, beforeAll, describe, expect, it } from "vitest";
import { WebSocket } from "ws";
import { createMockGateway } from "../src/server";
import type { MockGateway } from "../src/server";

let gateway: MockGateway;

beforeAll(async () => {
  gateway = await createMockGateway({ port: 0 });
});

afterAll(async () => {
  await gateway.close();
});

/** Open a client connection to the running gateway. */
function connect(): Promise<WebSocket> {
  return new Promise((resolve, reject) => {
    const socket = new WebSocket(`ws://127.0.0.1:${gateway.port}`);
    socket.once("open", () => resolve(socket));
    socket.once("error", reject);
  });
}

/** Send a raw payload and resolve with the first parsed reply. */
function roundtrip(socket: WebSocket, payload: string): Promise<any> {
  return new Promise((resolve, reject) => {
    socket.once("message", (data) => {
      try {
        resolve(JSON.parse(data.toString()));
      } catch (err) {
        reject(err);
      }
    });
    socket.send(payload);
  });
}

describe("mock gateway", () => {
  it("answers rois.system.connect with return_code OK", async () => {
    const socket = await connect();
    const reply = await roundtrip(
      socket,
      JSON.stringify({ jsonrpc: "2.0", id: "req-1", method: "rois.system.connect" }),
    );
    expect(reply.id).toBe("req-1");
    expect(reply.result.return_code).toBe("OK");
    socket.close();
  });

  it("answers rois.system.disconnect with return_code OK", async () => {
    const socket = await connect();
    const reply = await roundtrip(
      socket,
      JSON.stringify({ jsonrpc: "2.0", id: 2, method: "rois.system.disconnect" }),
    );
    expect(reply.id).toBe(2);
    expect(reply.result.return_code).toBe("OK");
    socket.close();
  });

  it("returns MethodNotFound for an unknown method", async () => {
    const socket = await connect();
    const reply = await roundtrip(
      socket,
      JSON.stringify({ jsonrpc: "2.0", id: "req-3", method: "rois.command.fly" }),
    );
    expect(reply.id).toBe("req-3");
    expect(reply.error.code).toBe(-32601);
    socket.close();
  });

  it("returns ParseError for malformed JSON", async () => {
    const socket = await connect();
    const reply = await roundtrip(socket, "{ not valid json");
    expect(reply.id).toBeNull();
    expect(reply.error.code).toBe(-32700);
    socket.close();
  });

  it("returns InvalidRequest for a JSON payload that is not a valid request", async () => {
    const socket = await connect();
    const reply = await roundtrip(
      socket,
      JSON.stringify({ jsonrpc: "2.0", id: "req-5" }),
    );
    expect(reply.id).toBe("req-5");
    expect(reply.error.code).toBe(-32600);
    socket.close();
  });

  // -----------------------------------------------------------------------
  // rois.system.get_profile
  // -----------------------------------------------------------------------

  describe("rois.system.get_profile", () => {
    it("returns a canned HRI_Engine_Profile with return_code OK", async () => {
      const socket = await connect();
      const reply = await roundtrip(
        socket,
        JSON.stringify({
          jsonrpc: "2.0",
          id: "profile-1",
          method: "rois.system.get_profile",
          params: { condition: "" },
        }),
      );

      expect(reply.id).toBe("profile-1");
      expect(reply.result.return_code).toBe("OK");

      const profile = reply.result.profile;
      expect(profile.identifier.code).toBe("MockGateway");
      expect(profile.identifier.authority).toBe("OMG");
      expect(profile.component_ids).toEqual([
        "PersonDetection_0",
        "Navigation_0",
        "SystemInformation_0",
      ]);
      expect(profile.sub_profiles).toHaveLength(1);
      expect(profile.sub_profiles[0].identifier.code).toBe("PerceptionSubEngine");
      socket.close();
    });

    it("accepts a condition param without error", async () => {
      const socket = await connect();
      const reply = await roundtrip(
        socket,
        JSON.stringify({
          jsonrpc: "2.0",
          id: "profile-2",
          method: "rois.system.get_profile",
          params: { condition: "component=Navigation" },
        }),
      );

      expect(reply.result.return_code).toBe("OK");
      expect(reply.result.profile.identifier.code).toBe("MockGateway");
      socket.close();
    });
  });

  // -----------------------------------------------------------------------
  // rois.system.get_error_detail
  // -----------------------------------------------------------------------

  describe("rois.system.get_error_detail", () => {
    it("returns canned details for a known error_id", async () => {
      const socket = await connect();
      const reply = await roundtrip(
        socket,
        JSON.stringify({
          jsonrpc: "2.0",
          id: "err-1",
          method: "rois.system.get_error_detail",
          params: { error_id: "err-001" },
        }),
      );

      expect(reply.id).toBe("err-1");
      expect(reply.result.return_code).toBe("OK");
      expect(reply.result.results).toHaveLength(2);
      expect(reply.result.results[0].name).toBe("component_ref");
      expect(reply.result.results[0].value).toBe("robot-a1/Navigation");
      expect(reply.result.results[1].name).toBe("description");
      socket.close();
    });

    it("returns empty results for an unknown error_id", async () => {
      const socket = await connect();
      const reply = await roundtrip(
        socket,
        JSON.stringify({
          jsonrpc: "2.0",
          id: "err-2",
          method: "rois.system.get_error_detail",
          params: { error_id: "err-unknown" },
        }),
      );

      expect(reply.result.return_code).toBe("OK");
      expect(reply.result.results).toEqual([]);
      socket.close();
    });
  });

  // -----------------------------------------------------------------------
  // rois.command.search
  // -----------------------------------------------------------------------

  describe("rois.command.search", () => {
    it("returns all registered component_refs with return_code OK", async () => {
      const socket = await connect();
      const reply = await roundtrip(
        socket,
        JSON.stringify({
          jsonrpc: "2.0",
          id: "search-1",
          method: "rois.command.search",
          params: { condition: "" },
        }),
      );

      expect(reply.id).toBe("search-1");
      expect(reply.result.return_code).toBe("OK");
      expect(reply.result.component_ref_list).toEqual([
        "PersonDetection_0",
        "Navigation_0",
        "SystemInformation_0",
      ]);
      socket.close();
    });
  });

  // -----------------------------------------------------------------------
  // rois.command.bind
  // -----------------------------------------------------------------------

  describe("rois.command.bind", () => {
    it("returns OK for a registered component", async () => {
      const socket = await connect();
      const reply = await roundtrip(
        socket,
        JSON.stringify({
          jsonrpc: "2.0",
          id: "bind-1",
          method: "rois.command.bind",
          params: { component_ref: "Navigation_0" },
        }),
      );

      expect(reply.result.return_code).toBe("OK");
      socket.close();
    });

    it("returns UNSUPPORTED for an unknown component", async () => {
      const socket = await connect();
      const reply = await roundtrip(
        socket,
        JSON.stringify({
          jsonrpc: "2.0",
          id: "bind-2",
          method: "rois.command.bind",
          params: { component_ref: "Unknown_0" },
        }),
      );

      expect(reply.result.return_code).toBe("UNSUPPORTED");
      socket.close();
    });
  });

  // -----------------------------------------------------------------------
  // rois.command.release
  // -----------------------------------------------------------------------

  describe("rois.command.release", () => {
    it("returns OK for a registered component", async () => {
      const socket = await connect();
      const reply = await roundtrip(
        socket,
        JSON.stringify({
          jsonrpc: "2.0",
          id: "rel-1",
          method: "rois.command.release",
          params: { component_ref: "PersonDetection_0" },
        }),
      );

      expect(reply.result.return_code).toBe("OK");
      socket.close();
    });

    it("returns UNSUPPORTED for an unknown component", async () => {
      const socket = await connect();
      const reply = await roundtrip(
        socket,
        JSON.stringify({
          jsonrpc: "2.0",
          id: "rel-2",
          method: "rois.command.release",
          params: { component_ref: "Unknown_0" },
        }),
      );

      expect(reply.result.return_code).toBe("UNSUPPORTED");
      socket.close();
    });
  });

  // -----------------------------------------------------------------------
  // rois.command.get_parameter
  // -----------------------------------------------------------------------

  describe("rois.command.get_parameter", () => {
    it("returns all parameters when names is omitted", async () => {
      const socket = await connect();
      const reply = await roundtrip(
        socket,
        JSON.stringify({
          jsonrpc: "2.0",
          id: "getparam-1",
          method: "rois.command.get_parameter",
          params: { component_ref: "Navigation_0" },
        }),
      );

      expect(reply.result.return_code).toBe("OK");
      expect(reply.result.results).toHaveLength(3);
      const names = reply.result.results.map((r: any) => r.name);
      expect(names).toContain("target_positions");
      expect(names).toContain("time_limit");
      expect(names).toContain("routing_policy");
      socket.close();
    });

    it("returns only requested parameters when names is provided", async () => {
      const socket = await connect();
      const reply = await roundtrip(
        socket,
        JSON.stringify({
          jsonrpc: "2.0",
          id: "getparam-2",
          method: "rois.command.get_parameter",
          params: { component_ref: "Navigation_0", names: ["time_limit"] },
        }),
      );

      expect(reply.result.return_code).toBe("OK");
      expect(reply.result.results).toHaveLength(1);
      expect(reply.result.results[0].name).toBe("time_limit");
      expect(reply.result.results[0].value).toBe("30");
      socket.close();
    });

    it("returns UNSUPPORTED for an unknown component", async () => {
      const socket = await connect();
      const reply = await roundtrip(
        socket,
        JSON.stringify({
          jsonrpc: "2.0",
          id: "getparam-3",
          method: "rois.command.get_parameter",
          params: { component_ref: "Unknown_0" },
        }),
      );

      expect(reply.result.return_code).toBe("UNSUPPORTED");
      socket.close();
    });
  });

  // -----------------------------------------------------------------------
  // rois.command.set_parameter
  // -----------------------------------------------------------------------

  describe("rois.command.set_parameter", () => {
    it("stores parameters and returns OK with command_id", async () => {
      const socket = await connect();
      const reply = await roundtrip(
        socket,
        JSON.stringify({
          jsonrpc: "2.0",
          id: "setparam-1",
          method: "rois.command.set_parameter",
          params: {
            component_ref: "Navigation_0",
            parameters: [
              { name: "time_limit", data_type_ref: "int", value: "60" },
              { name: "routing_policy", data_type_ref: "string", value: "distance" },
            ],
          },
        }),
      );

      expect(reply.result.return_code).toBe("OK");
      expect(reply.result.command_id).toBe("");
      socket.close();
    });

    it("persists values that get_parameter can read back", async () => {
      const socket = await connect();

      // Set a parameter.
      await roundtrip(
        socket,
        JSON.stringify({
          jsonrpc: "2.0",
          id: "set-1",
          method: "rois.command.set_parameter",
          params: {
            component_ref: "Navigation_0",
            parameters: [
              { name: "time_limit", data_type_ref: "int", value: "120" },
            ],
          },
        }),
      );

      // Read it back.
      const reply = await roundtrip(
        socket,
        JSON.stringify({
          jsonrpc: "2.0",
          id: "get-1",
          method: "rois.command.get_parameter",
          params: {
            component_ref: "Navigation_0",
            names: ["time_limit"],
          },
        }),
      );

      expect(reply.result.return_code).toBe("OK");
      expect(reply.result.results).toHaveLength(1);
      expect(reply.result.results[0].value).toBe("120");
      socket.close();
    });

    it("returns UNSUPPORTED for an unknown component", async () => {
      const socket = await connect();
      const reply = await roundtrip(
        socket,
        JSON.stringify({
          jsonrpc: "2.0",
          id: "setparam-2",
          method: "rois.command.set_parameter",
          params: {
            component_ref: "Unknown_0",
            parameters: [
              { name: "x", data_type_ref: "string", value: "1" },
            ],
          },
        }),
      );

      expect(reply.result.return_code).toBe("UNSUPPORTED");
      socket.close();
    });

    it("returns BAD_PARAMETER when parameters is not an array", async () => {
      const socket = await connect();
      const reply = await roundtrip(
        socket,
        JSON.stringify({
          jsonrpc: "2.0",
          id: "setparam-3",
          method: "rois.command.set_parameter",
          params: {
            component_ref: "Navigation_0",
            parameters: "not-an-array",
          },
        }),
      );

      expect(reply.result.return_code).toBe("BAD_PARAMETER");
      socket.close();
    });
  });

  // -----------------------------------------------------------------------
  // rois.command.bind_any
  // -----------------------------------------------------------------------

  describe("rois.command.bind_any", () => {
    it("returns OK with a component_ref", async () => {
      const socket = await connect();
      const reply = await roundtrip(
        socket,
        JSON.stringify({
          jsonrpc: "2.0",
          id: "bindany-1",
          method: "rois.command.bind_any",
          params: { condition: "" },
        }),
      );

      expect(reply.result.return_code).toBe("OK");
      expect(reply.result.component_ref).toBeTruthy();
      socket.close();
    });
  });

  // -----------------------------------------------------------------------
  // rois.command.execute
  // -----------------------------------------------------------------------

  describe("rois.command.execute", () => {
    it("returns OK with a command_id for a registered component", async () => {
      const socket = await connect();
      const reply = await roundtrip(
        socket,
        JSON.stringify({
          jsonrpc: "2.0",
          id: "exec-1",
          method: "rois.command.execute",
          params: {
            component_ref: "Navigation_0",
            target_positions: ["3.0,1.5,0.0"],
          },
        }),
      );

      expect(reply.result.return_code).toBe("OK");
      expect(reply.result.command_id).toBeTruthy();
      socket.close();
    });

    it("returns UNSUPPORTED for an unknown component", async () => {
      const socket = await connect();
      const reply = await roundtrip(
        socket,
        JSON.stringify({
          jsonrpc: "2.0",
          id: "exec-2",
          method: "rois.command.execute",
          params: { component_ref: "Unknown_0" },
        }),
      );

      expect(reply.result.return_code).toBe("UNSUPPORTED");
      socket.close();
    });
  });

  // -----------------------------------------------------------------------
  // rois.command.get_command_result
  // -----------------------------------------------------------------------

  describe("rois.command.get_command_result", () => {
    it("returns OK with results array", async () => {
      const socket = await connect();
      const reply = await roundtrip(
        socket,
        JSON.stringify({
          jsonrpc: "2.0",
          id: "result-1",
          method: "rois.command.get_command_result",
          params: { command_id: "cmd-001" },
        }),
      );

      expect(reply.result.return_code).toBe("OK");
      expect(Array.isArray(reply.result.results)).toBe(true);
      socket.close();
    });
  });
});
