/**
 * Tests for the mock engine component registry and its integration with the
 * WebSocket server dispatch.
 *
 * Two describe blocks:
 *   - "ComponentRegistry" — unit tests against the registry class directly
 *     (no socket, no JSON-RPC).
 *   - "mock engine: registry methods" — integration tests over a real
 *     WebSocket connection, exercising the full parse -> dispatch -> respond
 *     path for the Week 2 methods.
 */

import { afterAll, beforeAll, describe, expect, it } from "vitest";
import { WebSocket } from "ws";
import { createMockEngine } from "../src/server";
import type { MockEngine } from "../src/server";
import { ComponentRegistry } from "../src/registry";

// ---------------------------------------------------------------------------
// Helpers for integration tests
// ---------------------------------------------------------------------------

let engine: MockEngine;

beforeAll(async () => {
  engine = await createMockEngine({ port: 0 });
});

afterAll(async () => {
  await engine.close();
});

function connect(): Promise<WebSocket> {
  return new Promise((resolve, reject) => {
    const socket = new WebSocket(`ws://127.0.0.1:${engine.port}`);
    socket.once("open", () => resolve(socket));
    socket.once("error", reject);
  });
}

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

/** Build a minimal JSON-RPC request string. */
function req(id: string | number, method: string, params?: Record<string, unknown>): string {
  return JSON.stringify({ jsonrpc: "2.0", id, method, ...(params ? { params } : {}) });
}

// ---------------------------------------------------------------------------
// Unit tests: ComponentRegistry
// ---------------------------------------------------------------------------

describe("ComponentRegistry", () => {
  // Use a fresh registry for each test so bind state does not leak between
  // tests. The default constructor seeds three components.
  function freshRegistry(): ComponentRegistry {
    return new ComponentRegistry();
  }

  it("search returns all three default component refs", () => {
    const reg = freshRegistry();
    const refs = reg.search("");
    expect(refs).toHaveLength(3);
    expect(refs).toContain("PersonDetection_0");
    expect(refs).toContain("Navigation_0");
    expect(refs).toContain("SystemInformation_0");
  });

  it("search ignores the condition and returns all components", () => {
    const reg = freshRegistry();
    const refs = reg.search("component_type='PersonDetection'");
    expect(refs).toHaveLength(3);
  });

  it("bind returns OK for a free component", () => {
    const reg = freshRegistry();
    expect(reg.bind("PersonDetection_0")).toBe("OK");
  });

  it("bind returns ERROR for an already-bound component", () => {
    const reg = freshRegistry();
    expect(reg.bind("Navigation_0")).toBe("OK");
    expect(reg.bind("Navigation_0")).toBe("ERROR");
  });

  it("bind returns ERROR for an unknown component", () => {
    const reg = freshRegistry();
    expect(reg.bind("Unknown_0")).toBe("ERROR");
  });

  it("release returns OK for a bound component", () => {
    const reg = freshRegistry();
    reg.bind("PersonDetection_0");
    expect(reg.release("PersonDetection_0")).toBe("OK");
  });

  it("release returns ERROR for a component that was not bound", () => {
    const reg = freshRegistry();
    expect(reg.release("Navigation_0")).toBe("ERROR");
  });

  it("release returns ERROR for an unknown component", () => {
    const reg = freshRegistry();
    expect(reg.release("Unknown_0")).toBe("ERROR");
  });

  it("setParameter and getParameter roundtrip", () => {
    const reg = freshRegistry();
    const params = [
      { name: "target_positions", data_type_ref: "string[]", value: '["3.0,1.5,0.0"]' },
      { name: "time_limit", data_type_ref: "int", value: "30" },
    ];
    expect(reg.setParameter("Navigation_0", params)).toBe("OK");
    const result = reg.getParameter("Navigation_0");
    expect(result.returnCode).toBe("OK");
    expect(result.parameters).toHaveLength(2);
    expect(result.parameters[0].name).toBe("target_positions");
    expect(result.parameters[1].value).toBe("30");
  });

  it("setParameter merges params with the same name", () => {
    const reg = freshRegistry();
    reg.setParameter("Navigation_0", [
      { name: "time_limit", data_type_ref: "int", value: "30" },
    ]);
    reg.setParameter("Navigation_0", [
      { name: "time_limit", data_type_ref: "int", value: "60" },
    ]);
    const result = reg.getParameter("Navigation_0");
    expect(result.parameters).toHaveLength(1);
    expect(result.parameters[0].value).toBe("60");
  });

  it("setParameter returns ERROR for an unknown component", () => {
    const reg = freshRegistry();
    expect(
      reg.setParameter("Unknown_0", [
        { name: "x", data_type_ref: "string", value: "1" },
      ]),
    ).toBe("ERROR");
  });

  it("getParameter returns ERROR for an unknown component", () => {
    const reg = freshRegistry();
    const result = reg.getParameter("Unknown_0");
    expect(result.returnCode).toBe("ERROR");
    expect(result.parameters).toEqual([]);
  });

  it("getProfile returns a profile with component_ids and component_profiles", () => {
    const reg = freshRegistry();
    const profile = reg.getProfile();
    expect(profile.identifier.authority).toBe("OMG");
    expect(profile.identifier.code).toBe("MockEngine");
    expect(profile.component_ids).toHaveLength(3);
    expect(profile.component_ids).toContain("PersonDetection_0");
    expect(profile.component_profiles).toHaveLength(3);
    const navProfile = profile.component_profiles!.find(
      (p) => p.name === "Navigation_0",
    );
    expect(navProfile).toBeDefined();
    expect(navProfile!.command_profiles.map((p) => p.name)).toEqual(
      expect.arrayContaining(["start", "stop", "suspend", "resume", "set_parameter", "execute"]),
    );
    expect(navProfile!.query_profiles.map((p) => p.name)).toEqual(
      expect.arrayContaining(["component_status", "get_parameter"]),
    );
    expect(navProfile!.event_profiles.map((p) => p.name)).toEqual(
      expect.arrayContaining(["reached_target"]),
    );
  });
});

// ---------------------------------------------------------------------------
// Integration tests: server dispatch of registry methods
// ---------------------------------------------------------------------------

describe("mock engine: registry methods", () => {
  it("rois.command.search returns all three component refs", async () => {
    const socket = await connect();
    const reply = await roundtrip(socket, req("s1", "rois.command.search", { condition: "" }));
    expect(reply.id).toBe("s1");
    expect(reply.result.return_code).toBe("OK");
    expect(reply.result.component_ref_list).toHaveLength(3);
    expect(reply.result.component_ref_list).toContain("PersonDetection_0");
    socket.close();
  });

  it("rois.command.bind and release lifecycle", async () => {
    const socket = await connect();
    const bindReply = await roundtrip(socket, req("b1", "rois.command.bind", { component_ref: "Navigation_0" }));
    expect(bindReply.result.return_code).toBe("OK");
    const releaseReply = await roundtrip(socket, req("r1", "rois.command.release", { component_ref: "Navigation_0" }));
    expect(releaseReply.result.return_code).toBe("OK");
    socket.close();
  });

  it("rois.command.bind on unknown component returns ERROR", async () => {
    const socket = await connect();
    const reply = await roundtrip(socket, req("b2", "rois.command.bind", { component_ref: "Unknown_0" }));
    expect(reply.result.return_code).toBe("ERROR");
    socket.close();
  });

  it("rois.command.set_parameter and get_parameter roundtrip", async () => {
    const socket = await connect();
    const setReply = await roundtrip(socket, req("sp1", "rois.command.set_parameter", {
      component_ref: "Navigation_0",
      parameters: [
        { name: "time_limit", data_type_ref: "int", value: "30" },
      ],
    }));
    expect(setReply.result.return_code).toBe("OK");
    const getReply = await roundtrip(socket, req("gp1", "rois.command.get_parameter", {
      component_ref: "Navigation_0",
    }));
    expect(getReply.result.return_code).toBe("OK");
    expect(getReply.result.parameters).toHaveLength(1);
    expect(getReply.result.parameters[0].name).toBe("time_limit");
    expect(getReply.result.parameters[0].value).toBe("30");
    socket.close();
  });

  it("rois.system.get_profile returns a profile with component_profiles", async () => {
    const socket = await connect();
    const reply = await roundtrip(socket, req("p1", "rois.system.get_profile", { condition: "" }));
    expect(reply.result.return_code).toBe("OK");
    const profile = reply.result.profile;
    expect(profile.identifier.code).toBe("MockEngine");
    expect(profile.component_ids).toHaveLength(3);
    expect(profile.component_profiles).toHaveLength(3);
    socket.close();
  });
});