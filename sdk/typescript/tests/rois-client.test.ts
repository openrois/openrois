/**
 * Unit tests for rois-client.ts, the RoISClient of the SDK.
 *
 * A MockWebSocket plays the engine: tests read the requests the client sends
 * and answer them with catalog results, errors and notifications.
 *
 * Run with: npx vitest run
 */

import { describe, it, expect, vi } from "vitest";
import { ZodError } from "zod";
import type { Parameter } from "@openrois/interfaces";
import {
  RoISClient,
  RoISError,
  componentRef,
  type ClientOptions,
} from "../src/rois-client";
import { RpcError, TransportError, type WebSocketLike } from "../src/transport";
import { JSONRPC_VERSION, JsonRpcErrorCode } from "../src/jsonrpc";

// ---------------------------------------------------------------------------
// MockWebSocket
// ---------------------------------------------------------------------------

/** A request as the engine receives it. */
interface SentRequest {
  jsonrpc: string;
  id: string;
  method: string;
  params?: Record<string, unknown>;
}

/** A command unit of an execute request, as sent. */
interface SentUnit {
  component_ref: string;
  command_id: string;
  delay_time?: number;
  command_list?: SentUnit[];
}

class MockWebSocket implements WebSocketLike {
  readyState: number = 0; // CONNECTING

  onopen: ((event: { type: string }) => void) | null = null;
  onclose: ((event: { code: number; reason: string; type: string }) => void) | null = null;
  onmessage: ((event: { data: unknown; type: string }) => void) | null = null;
  onerror: ((event: { error?: unknown; message?: string; type: string }) => void) | null = null;

  sent: SentRequest[] = [];

  send(data: string): void {
    this.sent.push(JSON.parse(data));
  }

  close(_code?: number, _reason?: string): void {
    this.readyState = 3; // CLOSED
  }

  simulateOpen(): void {
    this.readyState = 1; // OPEN
    this.onopen?.({ type: "open" });
  }

  simulateMessage(data: unknown): void {
    this.onmessage?.({ data: JSON.stringify(data), type: "message" });
  }

  simulateClose(code: number = 1000, reason: string = ""): void {
    this.readyState = 3;
    this.onclose?.({ code, reason, type: "close" });
  }

  simulateError(message: string = "connection refused"): void {
    this.onerror?.({ message, type: "error" });
  }

  /** The most recent request the client sent. */
  get last(): SentRequest {
    return this.sent[this.sent.length - 1];
  }
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** The MockWebSocket the most recent connect() created. */
let currentMock: MockWebSocket;

const testOptions: ClientOptions = {
  transport: {
    webSocketFactory: (_url: string) => {
      currentMock = new MockWebSocket();
      return currentMock;
    },
  },
};

/** Let pending promise callbacks run until the client has sent `count` requests. */
async function untilSent(mock: MockWebSocket, count: number): Promise<void> {
  for (let i = 0; i < 50 && mock.sent.length < count; i++) {
    await Promise.resolve();
  }
}

/** Answer the most recent request with a result. */
function respond(mock: MockWebSocket, result: unknown): void {
  mock.simulateMessage({ jsonrpc: JSONRPC_VERSION, id: mock.last.id, result });
}

/** Answer the most recent request with a JSON-RPC error. */
function respondWithError(mock: MockWebSocket, code: number, message: string): void {
  mock.simulateMessage({ jsonrpc: JSONRPC_VERSION, id: mock.last.id, error: { code, message } });
}

/** Push a notification from the engine. */
function notify(mock: MockWebSocket, method: string, params?: unknown): void {
  mock.simulateMessage({
    jsonrpc: JSONRPC_VERSION,
    method,
    ...(params !== undefined ? { params } : {}),
  });
}

/** Open a client whose connect handshake succeeded. */
async function connected(): Promise<{ client: RoISClient; mock: MockWebSocket }> {
  const connecting = RoISClient.connect("ws://engine:8765", testOptions);
  const mock = currentMock;
  mock.simulateOpen();
  await untilSent(mock, 1);
  respond(mock, { return_code: "OK" });
  return { client: await connecting, mock };
}

/** Disconnect a client, answering its rois.system.disconnect. */
async function disconnect(client: RoISClient, mock: MockWebSocket): Promise<void> {
  const before = mock.sent.length;
  const disconnecting = client.disconnect();
  await untilSent(mock, before + 1);
  respond(mock, { return_code: "OK" });
  await disconnecting;
}

/** Call a client method, answer it with `result` and return what the method returned. */
async function answered<T>(mock: MockWebSocket, call: Promise<T>, result: unknown): Promise<T> {
  respond(mock, result);
  return call;
}

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;

const headProfile = {
  identifier: { authority: "OpenRoIS", code: "Head" },
  name: "head",
  function: "actuation",
};

// ---------------------------------------------------------------------------
// Connection lifecycle
// ---------------------------------------------------------------------------

describe("RoISClient.connect()", () => {
  it("returns a connected client after rois.system.connect", async () => {
    const { client, mock } = await connected();
    expect(client).toBeInstanceOf(RoISClient);
    expect(mock.sent[0].method).toBe("rois.system.connect");
    expect(mock.sent[0].params).toEqual({});
  });

  it("rejects when the WebSocket cannot open", async () => {
    const connecting = RoISClient.connect("ws://engine:8765", testOptions);
    currentMock.simulateError("connection refused");
    await expect(connecting).rejects.toThrow("connection refused");
  });

  it("rejects with RoISError and closes the socket when connect is not OK", async () => {
    const connecting = RoISClient.connect("ws://engine:8765", testOptions);
    const mock = currentMock;
    mock.simulateOpen();
    await untilSent(mock, 1);
    respond(mock, { return_code: "OUT_OF_RESOURCES" });

    await expect(connecting).rejects.toThrow(RoISError);
    expect(mock.readyState).toBe(3);
  });
});

describe("disconnect()", () => {
  it("sends rois.system.disconnect, then closes the connection", async () => {
    const { client, mock } = await connected();
    await disconnect(client, mock);

    expect(mock.sent[1].method).toBe("rois.system.disconnect");
    expect(mock.readyState).toBe(3);
    await expect(client.search()).rejects.toThrow(TransportError);
  });

  it("is safe to call more than once", async () => {
    const { client, mock } = await connected();
    await disconnect(client, mock);
    await client.disconnect();
    expect(mock.sent).toHaveLength(2);
  });

  it("closes the connection even when the engine answers with an error", async () => {
    const { client, mock } = await connected();
    const disconnecting = client.disconnect();
    await untilSent(mock, 2);
    respond(mock, { return_code: "ERROR" });

    await expect(disconnecting).rejects.toThrow(RoISError);
    expect(mock.readyState).toBe(3);
    await expect(client.search()).rejects.toThrow("not connected");
  });
});

describe("a disconnected client", () => {
  it("rejects every call with TransportError", async () => {
    const { client, mock } = await connected();
    await disconnect(client, mock);

    await expect(client.getProfile()).rejects.toThrow(TransportError);
    await expect(client.query("component_status")).rejects.toThrow(TransportError);
    await expect(client.subscribe("person_detected")).rejects.toThrow(TransportError);
    await expect(client.execute([])).rejects.toThrow(TransportError);
  });
});

// ---------------------------------------------------------------------------
// SystemIF
// ---------------------------------------------------------------------------

describe("getProfile()", () => {
  it("returns the engine profile and the component profiles", async () => {
    const { client, mock } = await connected();
    const profile = await answered(mock, client.getProfile(), {
      return_code: "OK",
      profile: {
        identifier: { code: "main" },
        component_ids: ["reachy_real/head", "reachy_sim/head"],
      },
      component_profiles: { "reachy_real/head": headProfile, "reachy_sim/head": headProfile },
    });

    expect(mock.last.method).toBe("rois.system.get_profile");
    expect(mock.last.params).toEqual({ condition: "" });
    expect(profile.profile.component_ids).toEqual(["reachy_real/head", "reachy_sim/head"]);
    expect(profile.component_profiles["reachy_sim/head"].function).toBe("actuation");
  });

  it("passes the condition", async () => {
    const { client, mock } = await connected();
    const condition = componentRef("reachy_real/head");
    await answered(mock, client.getProfile(condition), {
      return_code: "OK",
      profile: { identifier: { code: "main" }, component_ids: ["reachy_real/head"] },
    });
    expect(mock.last.params).toEqual({ condition: "component_ref = 'reachy_real/head'" });
  });

  it("returns no component profiles when the engine sends none", async () => {
    const { client, mock } = await connected();
    const profile = await answered(mock, client.getProfile(), {
      return_code: "OK",
      profile: { identifier: { code: "main" } },
    });
    expect(profile.component_profiles).toEqual({});
  });

  it("rejects an OK result without a profile", async () => {
    const { client, mock } = await connected();
    const call = client.getProfile();
    respond(mock, { return_code: "OK" });
    await expect(call).rejects.toThrow("without a profile");
  });
});

describe("getErrorDetail()", () => {
  it("sends the error_id and returns the results", async () => {
    const { client, mock } = await connected();
    const results = await answered(mock, client.getErrorDetail("err-1"), {
      return_code: "OK",
      results: [{ name: "message", data_type_ref: "string", value: "motor overheated" }],
    });
    expect(mock.last.method).toBe("rois.system.get_error_detail");
    expect(mock.last.params).toEqual({ error_id: "err-1", condition: "" });
    expect(results).toHaveLength(1);
  });
});

// ---------------------------------------------------------------------------
// CommandIF
// ---------------------------------------------------------------------------

describe("search()", () => {
  it("sends the condition and returns the refs", async () => {
    const { client, mock } = await connected();
    const refs = await answered(mock, client.search("component_ref LIKE 'reachy_real/%'"), {
      return_code: "OK",
      component_ref_list: ["reachy_real/head"],
    });
    expect(mock.last.method).toBe("rois.command.search");
    expect(mock.last.params).toEqual({ condition: "component_ref LIKE 'reachy_real/%'" });
    expect(refs).toEqual(["reachy_real/head"]);
  });

  it("returns an empty list when the engine lists no refs", async () => {
    const { client, mock } = await connected();
    expect(await answered(mock, client.search(), { return_code: "OK" })).toEqual([]);
  });
});

describe("bind(), bindAny() and release()", () => {
  it("bind sends the component_ref", async () => {
    const { client, mock } = await connected();
    await answered(mock, client.bind("reachy_real/head"), { return_code: "OK" });
    expect(mock.last.method).toBe("rois.command.bind");
    expect(mock.last.params).toEqual({ component_ref: "reachy_real/head" });
  });

  it("bindAny returns the component the engine reserved", async () => {
    const { client, mock } = await connected();
    const ref = await answered(mock, client.bindAny("component_type = 'urn:x'"), {
      return_code: "OK",
      component_ref: "reachy_sim/head",
    });
    expect(mock.last.method).toBe("rois.command.bind_any");
    expect(ref).toBe("reachy_sim/head");
  });

  it("release sends the component_ref", async () => {
    const { client, mock } = await connected();
    await answered(mock, client.release("reachy_real/head"), { return_code: "OK" });
    expect(mock.last.method).toBe("rois.command.release");
    expect(mock.last.params).toEqual({ component_ref: "reachy_real/head" });
  });
});

describe("getParameter() and setParameter()", () => {
  const timeLimit = { name: "time_limit", data_type_ref: "int", value: "30" };

  it("getParameter returns the parameters", async () => {
    const { client, mock } = await connected();
    const parameters = await answered(mock, client.getParameter("robot/nav"), {
      return_code: "OK",
      parameters: [timeLimit],
    });
    expect(mock.last.method).toBe("rois.command.get_parameter");
    expect(mock.last.params).toEqual({ component_ref: "robot/nav" });
    expect(parameters).toEqual([timeLimit]);
  });

  it("setParameter returns the command_id", async () => {
    const { client, mock } = await connected();
    const commandId = await answered(mock, client.setParameter("robot/nav", [timeLimit]), {
      return_code: "OK",
      command_id: "param-1",
    });
    expect(mock.last.method).toBe("rois.command.set_parameter");
    expect(mock.last.params).toEqual({ component_ref: "robot/nav", parameters: [timeLimit] });
    expect(commandId).toBe("param-1");
  });

  it("setParameter rejects invalid parameters before sending", async () => {
    const { client, mock } = await connected();
    const invalid = [{ name: "time_limit" }] as unknown as Parameter[];
    await expect(client.setParameter("robot/nav", invalid)).rejects.toThrow(ZodError);
    expect(mock.sent).toHaveLength(1);
  });
});

describe("execute()", () => {
  it("names unnamed commands with UUIDs and returns every id in order", async () => {
    const { client, mock } = await connected();
    const ids = await answered(
      mock,
      client.execute([
        { component_ref: "reachy_real/head", command_type: "start" },
        {
          command_list: [
            { component_ref: "reachy_real/antennas", command_type: "start", command_id: "mine" },
            { component_ref: "reachy_sim/head", command_type: "start" },
          ],
          delay_time: 500,
        },
      ]),
      { return_code: "OK" },
    );

    expect(ids).toHaveLength(3);
    expect(ids[0]).toMatch(UUID);
    expect(ids[1]).toBe("mine");
    expect(ids[2]).toMatch(UUID);

    const sent = mock.last.params?.command_unit_list as SentUnit[];
    expect(mock.last.method).toBe("rois.command.execute");
    expect(sent[0]).toMatchObject({ component_ref: "reachy_real/head", command_id: ids[0] });
    expect(sent[1].delay_time).toBe(500);
    expect(sent[1].command_list?.map((unit) => unit.command_id)).toEqual(["mine", ids[2]]);
  });

  it("gives every unnamed command its own id", async () => {
    const { client, mock } = await connected();
    const unit = { component_ref: "reachy_real/head", command_type: "start" };
    const ids = await answered(mock, client.execute([unit, unit]), { return_code: "OK" });
    expect(ids[0]).not.toBe(ids[1]);
  });

  it("raises the return code when the engine refuses the commands", async () => {
    const { client, mock } = await connected();
    const call = client.execute([
      { component_ref: "reachy_real/head", command_type: "start", command_id: "dup" },
    ]);
    respond(mock, { return_code: "BAD_PARAMETER" });
    await expect(call).rejects.toThrow("rois.command.execute failed with BAD_PARAMETER");
  });
});

describe("getCommandResult()", () => {
  it("sends the command_id and returns the results", async () => {
    const { client, mock } = await connected();
    const results = await answered(mock, client.getCommandResult("nod-1"), {
      return_code: "OK",
      results: [{ name: "reached", data_type_ref: "bool", value: "true" }],
    });
    expect(mock.last.method).toBe("rois.command.get_command_result");
    expect(mock.last.params).toEqual({ command_id: "nod-1", condition: "" });
    expect(results).toHaveLength(1);
  });
});

// ---------------------------------------------------------------------------
// QueryIF and EventIF
// ---------------------------------------------------------------------------

describe("query()", () => {
  it("selects the component with the condition and returns the results", async () => {
    const { client, mock } = await connected();
    const results = await answered(
      mock,
      client.query("component_status", componentRef("reachy_real/head")),
      {
        return_code: "OK",
        results: [{ name: "status", data_type_ref: "ComponentStatus", value: "READY" }],
      },
    );
    expect(mock.last.method).toBe("rois.query.query");
    expect(mock.last.params).toEqual({
      query_type: "component_status",
      condition: "component_ref = 'reachy_real/head'",
    });
    expect(results[0].value).toBe("READY");
  });

  it("raises UNSUPPORTED when no component answers the query", async () => {
    const { client, mock } = await connected();
    const call = client.query("robot_position");
    respond(mock, { return_code: "UNSUPPORTED" });
    await expect(call).rejects.toThrow(RoISError);
  });
});

describe("subscribe(), unsubscribe() and getEventDetail()", () => {
  it("subscribe returns the subscribe_id", async () => {
    const { client, mock } = await connected();
    const id = await answered(mock, client.subscribe("person_detected", componentRef("r/cam")), {
      return_code: "OK",
      subscribe_id: "sub-1",
    });
    expect(mock.last.method).toBe("rois.event.subscribe");
    expect(mock.last.params).toEqual({
      event_type: "person_detected",
      condition: "component_ref = 'r/cam'",
    });
    expect(id).toBe("sub-1");
  });

  it("unsubscribe sends the subscribe_id", async () => {
    const { client, mock } = await connected();
    await answered(mock, client.unsubscribe("sub-1"), { return_code: "OK" });
    expect(mock.last.method).toBe("rois.event.unsubscribe");
    expect(mock.last.params).toEqual({ subscribe_id: "sub-1" });
  });

  it("getEventDetail returns the payload", async () => {
    const { client, mock } = await connected();
    const results = await answered(mock, client.getEventDetail("evt-1"), {
      return_code: "OK",
      results: [{ name: "number", data_type_ref: "int", value: "2" }],
    });
    expect(mock.last.method).toBe("rois.event.get_event_detail");
    expect(mock.last.params).toEqual({ event_id: "evt-1", condition: "" });
    expect(results[0].value).toBe("2");
  });
});

// ---------------------------------------------------------------------------
// Results and errors
// ---------------------------------------------------------------------------

describe("result checking", () => {
  it("raises RoISError with the return code and the method", async () => {
    const { client, mock } = await connected();
    const call = client.bind("reachy_real/head");
    respond(mock, { return_code: "OUT_OF_RESOURCES" });

    try {
      await call;
      expect.unreachable("bind should have failed");
    } catch (error) {
      expect(error).toBeInstanceOf(RoISError);
      expect((error as RoISError).returnCode).toBe("OUT_OF_RESOURCES");
      expect((error as RoISError).method).toBe("rois.command.bind");
    }
  });

  it("rejects a result that does not match the catalog", async () => {
    const { client, mock } = await connected();
    const call = client.search();
    respond(mock, { return_code: "OK", component_ref_list: "reachy_real/head" });
    await expect(call).rejects.toThrow(ZodError);
  });

  it("raises RpcError for a JSON-RPC error", async () => {
    const { client, mock } = await connected();
    const call = client.search();
    respondWithError(mock, JsonRpcErrorCode.INTERNAL_ERROR, "engine failure");
    await expect(call).rejects.toThrow(RpcError);
  });

  it("rejects pending calls when the connection drops", async () => {
    const { client, mock } = await connected();
    const search = client.search();
    const query = client.query("component_status");
    mock.simulateClose(1006, "abnormal closure");
    await expect(search).rejects.toThrow();
    await expect(query).rejects.toThrow();
  });
});

// ---------------------------------------------------------------------------
// Notifications
// ---------------------------------------------------------------------------

describe("notifications", () => {
  const event = {
    event_id: "evt-1",
    event_type: "person_detected",
    subscribe_id: "sub-1",
    results: [{ name: "number", data_type_ref: "int", value: "2" }],
  };

  it("emits notify_event with its validated params", async () => {
    const { client, mock } = await connected();
    const listener = vi.fn();
    client.on("rois.event.notify_event", listener);

    notify(mock, "rois.event.notify_event", event);

    expect(listener).toHaveBeenCalledOnce();
    expect(listener).toHaveBeenCalledWith({ ...event, expire: "" });
  });

  it("emits each event under its event type as well", async () => {
    const { client, mock } = await connected();
    const listener = vi.fn();
    client.on("person_detected", listener);

    notify(mock, "rois.event.notify_event", event);

    expect(listener).toHaveBeenCalledOnce();
    expect(listener.mock.calls[0][0].results[0].value).toBe("2");
  });

  it("does not let an event type shadow the client's own events", async () => {
    const { client, mock } = await connected();
    const closeListener = vi.fn();
    client.on("close", closeListener);

    notify(mock, "rois.event.notify_event", { ...event, event_type: "close" });

    expect(closeListener).not.toHaveBeenCalled();
  });

  it("emits completed, notify_error and profile_changed with their params", async () => {
    const { client, mock } = await connected();
    const completed = vi.fn();
    const error = vi.fn();
    const profileChanged = vi.fn();
    client.on("rois.command.completed", completed);
    client.on("rois.system.notify_error", error);
    client.on("rois.system.profile_changed", profileChanged);

    notify(mock, "rois.command.completed", { command_id: "nod-1", status: "OK" });
    notify(mock, "rois.system.notify_error", {
      error_id: "err-1",
      error_type: "COMPONENT_NOT_RESPONDING",
    });
    notify(mock, "rois.system.profile_changed");

    expect(completed).toHaveBeenCalledWith({ command_id: "nod-1", status: "OK" });
    expect(error).toHaveBeenCalledWith({
      error_id: "err-1",
      error_type: "COMPONENT_NOT_RESPONDING",
    });
    expect(profileChanged).toHaveBeenCalledWith({});
  });

  it("reports a notification with invalid params as an error", async () => {
    const { client, mock } = await connected();
    const completed = vi.fn();
    const errors = vi.fn();
    client.on("rois.command.completed", completed);
    client.on("error", errors);

    notify(mock, "rois.command.completed", { command_id: "nod-1", status: "FINISHED" });

    expect(completed).not.toHaveBeenCalled();
    expect(errors).toHaveBeenCalledOnce();
    expect(errors.mock.calls[0][0]).toBeInstanceOf(TransportError);
  });

  it("emits every notification's envelope as 'notification'", async () => {
    const { client, mock } = await connected();
    const all = vi.fn();
    const named = vi.fn();
    client.on("notification", all);
    client.on("rois.event.notify", named);

    notify(mock, "rois.event.notify", { event_id: "evt-1" });
    notify(mock, "rois.command.completed", { command_id: "nod-1", status: "OK" });

    expect(all).toHaveBeenCalledTimes(2);
    expect(all.mock.calls[0][0]).toMatchObject({ method: "rois.event.notify" });
    expect(named).not.toHaveBeenCalled();
  });

  it("passes each listener the arguments its event declares", async () => {
    const { client, mock } = await connected();
    const statuses: string[] = [];
    const resultCounts: number[] = [];
    const closeCodes: number[] = [];
    client.on("rois.command.completed", (params) => statuses.push(params.status));
    client.on("person_detected", (params) => resultCounts.push(params.results?.length ?? 0));
    client.on("close", (code) => closeCodes.push(code));

    notify(mock, "rois.command.completed", { command_id: "nod-1", status: "ABORT" });
    notify(mock, "rois.event.notify_event", event);
    mock.simulateClose(1000, "done");

    expect(statuses).toEqual(["ABORT"]);
    expect(resultCounts).toEqual([1]);
    expect(closeCodes).toEqual([1000]);
  });

  it("stops calling a listener removed with off()", async () => {
    const { client, mock } = await connected();
    const listener = vi.fn();
    client.on("rois.command.completed", listener);
    client.off("rois.command.completed", listener);

    notify(mock, "rois.command.completed", { command_id: "nod-1", status: "OK" });

    expect(listener).not.toHaveBeenCalled();
  });

  it("emits 'close' when the connection drops", async () => {
    const { client, mock } = await connected();
    const listener = vi.fn();
    client.on("close", listener);

    mock.simulateClose(1006, "abnormal closure");

    expect(listener).toHaveBeenCalledWith(1006, "abnormal closure");
    await expect(client.search()).rejects.toThrow("not connected");
  });
});

// ---------------------------------------------------------------------------
// A whole session
// ---------------------------------------------------------------------------

describe("a session", () => {
  it("finds, reserves, commands and releases a component", async () => {
    const { client, mock } = await connected();

    const refs = await answered(mock, client.search(), {
      return_code: "OK",
      component_ref_list: ["reachy_real/head"],
    });
    await answered(mock, client.bind(refs[0]), { return_code: "OK" });

    const completed = vi.fn();
    client.on("rois.command.completed", completed);
    const [commandId] = await answered(
      mock,
      client.execute([{ component_ref: refs[0], command_type: "start" }]),
      { return_code: "OK" },
    );
    notify(mock, "rois.command.completed", { command_id: commandId, status: "OK" });
    expect(completed).toHaveBeenCalledWith({ command_id: commandId, status: "OK" });

    const results = await answered(mock, client.getCommandResult(commandId), {
      return_code: "OK",
      results: [],
    });
    expect(results).toEqual([]);

    await answered(mock, client.release(refs[0]), { return_code: "OK" });
    await disconnect(client, mock);
    expect(mock.sent.map((request) => request.method)).toEqual([
      "rois.system.connect",
      "rois.command.search",
      "rois.command.bind",
      "rois.command.execute",
      "rois.command.get_command_result",
      "rois.command.release",
      "rois.system.disconnect",
    ]);
  });
});
