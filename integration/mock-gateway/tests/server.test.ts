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
});
