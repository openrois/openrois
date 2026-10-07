/**
 * Tests for the mock engine's WebSocket server.
 *
 * The protocol checks send raw JSON over a ws client. The session tests drive
 * the engine with the TypeScript SDK, so they also check that the SDK and the
 * mock engine agree on the wire contract.
 */

import { afterAll, beforeAll, describe, expect, it } from "vitest";
import { WebSocket } from "ws";
import { RoISClient, RoISError, componentRef } from "@openrois/sdk";
import type { CompletedParams, NotifyEventParams } from "@openrois/interfaces";
import { createMockEngine } from "../src/server";
import type { MockEngine } from "../src/server";

let engine: MockEngine;

beforeAll(async () => {
  engine = await createMockEngine({
    port: 0,
    timing: { commandMs: 5, navigationMs: 30, detectionIntervalMs: 10, eventLifetimeMs: 1000 },
  });
});

afterAll(async () => {
  await engine.close();
});

const url = () => `ws://127.0.0.1:${engine.port}`;

/** Open a raw client connection to the running engine. */
function open(): Promise<WebSocket> {
  return new Promise((resolve, reject) => {
    const socket = new WebSocket(url());
    socket.once("open", () => resolve(socket));
    socket.once("error", reject);
  });
}

/** Send a raw payload and resolve with the next parsed reply. */
function roundtrip(socket: WebSocket, payload: string): Promise<Record<string, any>> {
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

/** Resolve with the params of the next notification of a kind. */
function next<T>(client: RoISClient, event: string, accept: (params: T) => boolean = () => true): Promise<T> {
  return new Promise((resolve) => {
    const listener = (params: T) => {
      if (accept(params)) {
        client.off(event, listener as never);
        resolve(params);
      }
    };
    client.on(event, listener as never);
  });
}

// ---------------------------------------------------------------------------
// JSON-RPC protocol
// ---------------------------------------------------------------------------

describe("JSON-RPC protocol", () => {
  it("answers connect without params", async () => {
    const socket = await open();
    const reply = await roundtrip(socket, JSON.stringify({ jsonrpc: "2.0", id: "r1", method: "rois.system.connect" }));
    expect(reply).toEqual({ jsonrpc: "2.0", id: "r1", result: { return_code: "OK" } });
    socket.close();
  });

  it("answers JSON that does not parse with PARSE_ERROR and a null id", async () => {
    const socket = await open();
    const reply = await roundtrip(socket, "{not json");
    expect(reply.id).toBeNull();
    expect(reply.error.code).toBe(-32700);
    socket.close();
  });

  it("answers an object that is not a request with INVALID_REQUEST", async () => {
    const socket = await open();
    const reply = await roundtrip(socket, JSON.stringify({ jsonrpc: "1.0", id: 7, method: "rois.system.connect" }));
    expect(reply.id).toBe(7);
    expect(reply.error.code).toBe(-32600);
    socket.close();
  });

  it("answers methods outside the catalog with METHOD_NOT_FOUND", async () => {
    const socket = await open();
    for (const method of ["rois.command.fly", "rois.stream.connect_stream", "rois.event.notify"]) {
      const reply = await roundtrip(socket, JSON.stringify({ jsonrpc: "2.0", id: method, method, params: {} }));
      expect(reply.error.code).toBe(-32601);
    }
    socket.close();
  });

  it("answers params that fail the catalog model with INVALID_PARAMS", async () => {
    const socket = await open();
    const reply = await roundtrip(
      socket,
      JSON.stringify({ jsonrpc: "2.0", id: "r2", method: "rois.query.query", params: { condition: "" } }),
    );
    expect(reply.error.code).toBe(-32602);
    expect(reply.error.data[0].path).toBe("query_type");
    socket.close();
  });

  it("does not answer a notification from the client", async () => {
    const socket = await open();
    socket.send(JSON.stringify({ jsonrpc: "2.0", method: "rois.system.connect" }));
    const reply = await roundtrip(socket, JSON.stringify({ jsonrpc: "2.0", id: "after", method: "rois.system.connect" }));
    expect(reply.id).toBe("after");
    socket.close();
  });
});

// ---------------------------------------------------------------------------
// Sessions through the SDK
// ---------------------------------------------------------------------------

describe("a session through the SDK", () => {
  it("reads the profile of every component", async () => {
    const client = await RoISClient.connect(url());
    const { profile, component_profiles } = await client.getProfile();
    expect(profile.component_ids).toEqual([
      "mock/person_detection",
      "mock/navigation",
      "mock/system_information",
    ]);
    expect(component_profiles["mock/navigation"].identifier.code).toBe("Navigation");
    await client.disconnect();
  });

  it("binds, sets parameters, drives, and reports the target", async () => {
    const client = await RoISClient.connect(url());
    const nav = "mock/navigation";
    await client.bind(nav);

    await client.subscribe("reached_target", componentRef(nav));
    const reached = next<NotifyEventParams>(client, "reached_target");

    const parameterId = await client.setParameter(nav, [
      { name: "target_positions", data_type_ref: "string[]", value: '["kitchen"]' },
    ]);
    await next<CompletedParams>(client, "rois.command.completed", (p) => p.command_id === parameterId);

    const [commandId] = await client.execute([{ component_ref: nav, command_type: "start" }]);
    const completed = await next<CompletedParams>(client, "rois.command.completed", (p) => p.command_id === commandId);
    expect(completed.status).toBe("OK");
    expect((await reached).results?.[0].value).toBe("kitchen");
    expect(await client.getCommandResult(commandId)).toEqual([
      { name: "target", data_type_ref: "string", value: "kitchen" },
    ]);

    await client.release(nav);
    await client.disconnect();
  });

  it("keeps an actuation component for the client that bound it", async () => {
    const first = await RoISClient.connect(url());
    const second = await RoISClient.connect(url());
    await first.bind("mock/navigation");

    await expect(second.bind("mock/navigation")).rejects.toThrow(RoISError);
    await first.disconnect();
    await second.bind("mock/navigation");

    await second.release("mock/navigation");
    await second.disconnect();
  });

  it("selects the component of a query with a condition", async () => {
    const client = await RoISClient.connect(url());
    const results = await client.query("component_status", componentRef("mock/person_detection"));
    expect(results[0]).toEqual({ name: "status", data_type_ref: "Component_Status", value: "READY" });
    await expect(client.query("component_status")).rejects.toThrow("BAD_PARAMETER");
    await client.disconnect();
  });

  it("delivers person_detected events to their subscription", async () => {
    const client = await RoISClient.connect(url());
    const subscribeId = await client.subscribe("person_detected");
    const event = await next<NotifyEventParams>(client, "person_detected");
    expect(event.subscribe_id).toBe(subscribeId);
    expect(await client.getEventDetail(event.event_id)).toEqual(event.results);
    await client.unsubscribe(subscribeId);
    await client.disconnect();
  });
});
