/**
 * Transport tests on real sockets, in Node.js: the global WebSocket that the
 * transport uses by default, and the `ws` package through webSocketFactory. A fake
 * socket cannot show either, because the bugs they guard against are in how the real
 * implementations open and close.
 *
 * Run with: npx vitest run
 */

import { createServer, type Server, type Socket } from "node:net";
import type { AddressInfo } from "node:net";
import { describe, it, expect, afterEach, vi } from "vitest";
import WebSocket, { WebSocketServer } from "ws";
import { RoISClient } from "../src/rois-client";
import {
  ConnectionError,
  TransportError,
  TransportState,
  WebSocketTransport,
  type TransportOptions,
  type WebSocketLike,
} from "../src/transport";

/** Each way the transport can get a socket. */
const factories: [string, TransportOptions["webSocketFactory"]][] = [
  ["the global WebSocket", undefined],
  ["the ws package", (url) => new WebSocket(url) as unknown as WebSocketLike],
];

const cleanups: (() => Promise<void> | void)[] = [];

afterEach(async () => {
  for (const cleanup of cleanups.splice(0)) {
    await cleanup();
  }
});

/** A TCP connection as the server sees it. */
interface Connection {
  socket: Socket;
  ended: boolean;
}

/** A TCP server that accepts connections and never answers the WebSocket handshake. */
async function silentServer(): Promise<{ url: string; connections: Connection[] }> {
  const connections: Connection[] = [];
  const server: Server = createServer((socket) => {
    const connection = { socket, ended: false };
    connections.push(connection);
    socket.on("error", () => {});
    socket.on("close", () => {
      connection.ended = true;
    });
    // Reading is what lets the server see the client leave.
    socket.resume();
  });
  await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
  cleanups.push(() => {
    connections.forEach(({ socket }) => socket.destroy());
    server.close();
  });
  const { port } = server.address() as AddressInfo;
  return { url: `ws://127.0.0.1:${port}`, connections };
}

/** A WebSocket server that answers every request with return_code OK. */
async function answeringServer(): Promise<{ url: string; server: WebSocketServer }> {
  const server = new WebSocketServer({ host: "127.0.0.1", port: 0 });
  await new Promise((resolve) => server.once("listening", resolve));
  server.on("connection", (socket) => {
    socket.on("message", (data) => {
      const { id } = JSON.parse(String(data));
      socket.send(JSON.stringify({ jsonrpc: "2.0", id, result: { return_code: "OK" } }));
    });
  });
  cleanups.push(() => {
    server.clients.forEach((socket) => socket.terminate());
    server.close();
  });
  const { port } = server.address() as AddressInfo;
  return { url: `ws://127.0.0.1:${port}`, server };
}

describe.each(factories)("with %s", (_name, webSocketFactory) => {
  it("runs a session and closes it", async () => {
    const { url } = await answeringServer();
    const client = await RoISClient.connect(url, { transport: { webSocketFactory } });

    await expect(client.search()).resolves.toEqual([]);
    const closed = vi.fn();
    client.on("close", closed);
    await client.disconnect();

    expect(closed).toHaveBeenCalledWith(1000, "client closed");
  });

  it("reports a server close with its code and reason", async () => {
    const { url, server } = await answeringServer();
    const client = await RoISClient.connect(url, { transport: { webSocketFactory } });
    const closed = new Promise<[number, string]>((resolve) => {
      client.on("close", (code, reason) => resolve([code, reason]));
    });

    server.clients.forEach((socket) => socket.close(1001, "going away"));

    await expect(closed).resolves.toEqual([1001, "going away"]);
  });

  it("drops the connection when the connect timeout fires", async () => {
    const { url, connections } = await silentServer();
    const transport = new WebSocketTransport({ connectTimeout: 100, webSocketFactory });

    await expect(transport.connect(url)).rejects.toThrow(ConnectionError);

    // Only the first connection counts: the global WebSocket's connection pool can open
    // a spare one afterwards, which never starts a handshake.
    await vi.waitFor(() => {
      expect(connections[0]?.ended).toBe(true);
    });
  });

  it("keeps the next connection when close() ended the attempt before it", async () => {
    const silent = await silentServer();
    const { url } = await answeringServer();
    const transport = new WebSocketTransport({ connectTimeout: 100, webSocketFactory });
    const closed = vi.fn();
    transport.on("close", closed);

    const abandoned = transport.connect(silent.url);
    transport.close();
    await expect(abandoned).rejects.toThrow(ConnectionError);
    await vi.waitFor(() => {
      expect(silent.connections[0]?.ended).toBe(true);
    });

    await transport.connect(url);
    await new Promise((resolve) => setTimeout(resolve, 200));

    expect(transport.state).toBe(TransportState.CONNECTED);
    await expect(transport.send("rois.system.ping")).resolves.toEqual({ return_code: "OK" });
    expect(closed).not.toHaveBeenCalled();
    transport.close();
  });

  it.each([
    ["a code the WebSocket API refuses", 1001, "leaving"],
    ["a reason over the limit", 1000, "r".repeat(124)],
  ])("keeps the session on %s, and a plain close ends it", async (_name, code, reason) => {
    const { url, server } = await answeringServer();
    const transport = new WebSocketTransport({ webSocketFactory });
    await transport.connect(url);
    const closed = vi.fn();
    transport.on("close", closed);

    expect(() => transport.close(code, reason)).toThrow(TransportError);

    expect(closed).not.toHaveBeenCalled();
    await expect(transport.send("rois.system.ping")).resolves.toEqual({ return_code: "OK" });
    transport.close();
    await vi.waitFor(() => {
      expect(server.clients.size).toBe(0);
    });
    expect(closed).toHaveBeenCalledOnce();
  });
});
