/**
 * Tests for MockEngineCore, the RoIS behaviour of the mock engine.
 *
 * Each test drives the core directly with in-memory sessions that record the
 * notifications they receive. The timing is shortened so commands and events
 * arrive within milliseconds.
 */

import { afterEach, describe, expect, it } from "vitest";
import { componentRef, componentType } from "@openrois/interfaces";
import type { HRIEngineProfileType as EngineProfile, RoISNotification } from "@openrois/interfaces";
import { MockEngineCore, type Session } from "../src/engine";

const TIMING = { commandMs: 5, navigationMs: 40, detectionIntervalMs: 10, eventLifetimeMs: 1000 };

const PERSON = "mock/person_detection";
const NAV = "mock/navigation";
const SYSTEM = "mock/system_information";

let core: MockEngineCore;

afterEach(() => {
  core.close();
});

interface Received {
  method: RoISNotification;
  params: Record<string, unknown>;
}

/** A session that records its notifications. */
function client(id: string): Session & { received: Received[] } {
  const received: Received[] = [];
  return {
    id,
    received,
    notify: (method, params) => received.push({ method, params: params as Record<string, unknown> }),
  };
}

/** The params of every notification of one kind a client received. */
function paramsOf(session: { received: Received[] }, method: RoISNotification): Record<string, unknown>[] {
  return session.received.filter((n) => n.method === method).map((n) => n.params);
}

/** Wait until `check` holds, polling every few milliseconds. */
async function until(check: () => boolean, timeoutMs = 1000): Promise<void> {
  const start = Date.now();
  while (!check()) {
    if (Date.now() - start > timeoutMs) {
      throw new Error("timed out waiting for the engine");
    }
    await new Promise((resolve) => setTimeout(resolve, 2));
  }
}

function start(): MockEngineCore {
  core = new MockEngineCore(TIMING);
  return core;
}

// ---------------------------------------------------------------------------
// Profiles and selection
// ---------------------------------------------------------------------------

describe("get_profile", () => {
  it("lists every component by fully qualified ref, with its profile", () => {
    const result = start().handle(client("a"), "rois.system.get_profile", { condition: "" });
    expect(result.return_code).toBe("OK");
    expect((result.profile as EngineProfile).component_ids).toEqual([PERSON, NAV, SYSTEM]);
    expect(Object.keys(result.component_profiles ?? {})).toEqual([PERSON, NAV, SYSTEM]);
  });

  it("includes the RoIS_Common messages in each basic component profile", () => {
    const result = start().handle(client("a"), "rois.system.get_profile", { condition: "" });
    const navigation = result.component_profiles?.[NAV];
    expect(navigation?.function).toBe("actuation");
    expect(navigation?.command_profiles?.map((c) => c.name)).toEqual(["start", "stop", "suspend", "resume"]);
    expect(navigation?.query_profiles?.map((q) => q.name)).toEqual(["component_status"]);
    expect(navigation?.parameter_profiles?.map((p) => p.name)).toEqual([
      "target_positions",
      "time_limit",
      "routing_policy",
    ]);
  });

  it("lists the components a condition selects", () => {
    const result = start().handle(client("a"), "rois.system.get_profile", {
      condition: componentType({ authority: "OMG", code: "Navigation" }),
    });
    expect((result.profile as EngineProfile).component_ids).toEqual([NAV]);
  });
});

describe("search", () => {
  it("selects with LIKE and AND", () => {
    const result = start().handle(client("a"), "rois.command.search", {
      condition: "component_ref LIKE 'mock/%' AND component_type LIKE '%::PersonDetection'",
    });
    expect(result.component_ref_list).toEqual([PERSON]);
  });

  it("answers a condition outside the subset with BAD_PARAMETER", () => {
    const result = start().handle(client("a"), "rois.command.search", {
      condition: "component_ref = 'a' OR component_ref = 'b'",
    });
    expect(result.return_code).toBe("BAD_PARAMETER");
  });
});

describe("query", () => {
  it("answers the one component the condition selects", () => {
    const result = start().handle(client("a"), "rois.query.query", {
      query_type: "component_status",
      condition: componentRef(NAV),
    });
    expect(result.return_code).toBe("OK");
    expect(result.results).toEqual([{ name: "status", data_type_ref: "Component_Status", value: "READY" }]);
  });

  it("needs no condition when one component declares the query", () => {
    const result = start().handle(client("a"), "rois.query.query", {
      query_type: "robot_position",
      condition: "",
    });
    expect(result.return_code).toBe("OK");
    expect(result.results?.map((r) => r.name)).toEqual(["position_data", "robot_ref", "timestamp"]);
  });

  it("answers BAD_PARAMETER when several components declare the query", () => {
    const result = start().handle(client("a"), "rois.query.query", {
      query_type: "component_status",
      condition: "",
    });
    expect(result.return_code).toBe("BAD_PARAMETER");
  });

  it("answers UNSUPPORTED when no component declares the query", () => {
    const result = start().handle(client("a"), "rois.query.query", {
      query_type: "battery_level",
      condition: "",
    });
    expect(result.return_code).toBe("UNSUPPORTED");
  });
});

// ---------------------------------------------------------------------------
// Bindings and parameters
// ---------------------------------------------------------------------------

describe("bindings", () => {
  it("reserves an actuation component for the client that bound it", () => {
    const engine = start();
    const a = client("a");
    const b = client("b");
    expect(engine.handle(a, "rois.command.bind", { component_ref: NAV }).return_code).toBe("OK");
    expect(engine.handle(b, "rois.command.bind", { component_ref: NAV }).return_code).toBe("OUT_OF_RESOURCES");
    engine.handle(a, "rois.command.release", { component_ref: NAV });
    expect(engine.handle(b, "rois.command.bind", { component_ref: NAV }).return_code).toBe("OK");
  });

  it("lets every client bind a sensing component", () => {
    const engine = start();
    expect(engine.handle(client("a"), "rois.command.bind", { component_ref: PERSON }).return_code).toBe("OK");
    expect(engine.handle(client("b"), "rois.command.bind", { component_ref: PERSON }).return_code).toBe("OK");
  });

  it("answers UNSUPPORTED for a ref it does not host", () => {
    const result = start().handle(client("a"), "rois.command.bind", { component_ref: "mock/arm" });
    expect(result.return_code).toBe("UNSUPPORTED");
  });

  it("bind_any reserves a free component the condition selects", () => {
    const engine = start();
    const navigation = componentType({ authority: "OMG", code: "Navigation" });
    const first = engine.handle(client("a"), "rois.command.bind_any", { condition: navigation });
    expect(first).toEqual({ return_code: "OK", component_ref: NAV });
    const second = engine.handle(client("b"), "rois.command.bind_any", { condition: navigation });
    expect(second.return_code).toBe("OUT_OF_RESOURCES");
  });

  it("releases the binds of a closed session", () => {
    const engine = start();
    const a = client("a");
    engine.handle(a, "rois.command.bind", { component_ref: NAV });
    engine.closeSession(a);
    expect(engine.handle(client("b"), "rois.command.bind", { component_ref: NAV }).return_code).toBe("OK");
  });
});

describe("parameters", () => {
  const target = { name: "target_positions", data_type_ref: "string[]", value: '["kitchen"]' };

  it("set_parameter stores the values and completes its command", async () => {
    const engine = start();
    const a = client("a");
    engine.handle(a, "rois.command.bind", { component_ref: NAV });
    const result = engine.handle(a, "rois.command.set_parameter", {
      component_ref: NAV,
      parameters: [target],
    });
    expect(result.return_code).toBe("OK");
    await until(() => paramsOf(a, "rois.command.completed").length === 1);
    expect(paramsOf(a, "rois.command.completed")[0]).toEqual({ command_id: result.command_id, status: "OK" });
    const read = engine.handle(a, "rois.command.get_parameter", { component_ref: NAV });
    expect(read.parameters).toContainEqual(target);
  });

  it("set_parameter needs the bind of an actuation component", () => {
    const result = start().handle(client("a"), "rois.command.set_parameter", {
      component_ref: NAV,
      parameters: [target],
    });
    expect(result.return_code).toBe("OUT_OF_RESOURCES");
  });

  it("set_parameter answers BAD_PARAMETER for a parameter the profile lacks", () => {
    const engine = start();
    const a = client("a");
    engine.handle(a, "rois.command.bind", { component_ref: NAV });
    const result = engine.handle(a, "rois.command.set_parameter", {
      component_ref: NAV,
      parameters: [{ name: "speed", data_type_ref: "float", value: "1.0" }],
    });
    expect(result.return_code).toBe("BAD_PARAMETER");
  });
});

// ---------------------------------------------------------------------------
// Commands
// ---------------------------------------------------------------------------

describe("execute", () => {
  const unit = (component_ref: string, command_type: string, command_id: string) => ({
    component_ref,
    command_type,
    command_id,
    arguments: [],
    delay_time: null,
  });

  it("runs items in order and the commands of a group together", async () => {
    const engine = start();
    const a = client("a");
    const result = engine.handle(a, "rois.command.execute", {
      command_unit_list: [
        unit(PERSON, "start", "c1"),
        { command_list: [unit(PERSON, "suspend", "c2"), unit(PERSON, "resume", "c3")], delay_time: 5 },
      ],
    });
    expect(result.return_code).toBe("OK");
    await until(() => paramsOf(a, "rois.command.completed").length === 3);
    const ids = paramsOf(a, "rois.command.completed").map((p) => p.command_id);
    expect(ids[0]).toBe("c1");
    expect(ids.slice(1).sort()).toEqual(["c2", "c3"]);
  });

  it("answers BAD_PARAMETER for a command_id already in the table", async () => {
    const engine = start();
    const a = client("a");
    engine.handle(a, "rois.command.execute", { command_unit_list: [unit(PERSON, "start", "same")] });
    const again = engine.handle(a, "rois.command.execute", { command_unit_list: [unit(PERSON, "stop", "same")] });
    expect(again.return_code).toBe("BAD_PARAMETER");
    const twice = engine.handle(a, "rois.command.execute", {
      command_unit_list: [unit(PERSON, "start", "x"), unit(PERSON, "stop", "x")],
    });
    expect(twice.return_code).toBe("BAD_PARAMETER");
  });

  it("answers UNSUPPORTED for a command the component does not declare", () => {
    const result = start().handle(client("a"), "rois.command.execute", {
      command_unit_list: [unit(SYSTEM, "start", "c1")],
    });
    expect(result.return_code).toBe("UNSUPPORTED");
  });

  it("needs the bind of an actuation component", () => {
    const result = start().handle(client("a"), "rois.command.execute", {
      command_unit_list: [unit(NAV, "start", "n1")],
    });
    expect(result.return_code).toBe("OUT_OF_RESOURCES");
  });

  it("answers BAD_PARAMETER for an empty command_unit_list", () => {
    const result = start().handle(client("a"), "rois.command.execute", { command_unit_list: [] });
    expect(result.return_code).toBe("BAD_PARAMETER");
  });

  it("drives to the target and reports reached_target", async () => {
    const engine = start();
    const a = client("a");
    engine.handle(a, "rois.command.bind", { component_ref: NAV });
    engine.handle(a, "rois.event.subscribe", { event_type: "reached_target", condition: "" });
    engine.handle(a, "rois.command.execute", { command_unit_list: [unit(NAV, "start", "n1")] });

    const status = engine.handle(a, "rois.query.query", { query_type: "component_status", condition: componentRef(NAV) });
    expect(status.results?.[0].value).toBe("BUSY");

    await until(() => paramsOf(a, "rois.command.completed").length === 1);
    expect(paramsOf(a, "rois.command.completed")[0]).toEqual({ command_id: "n1", status: "OK" });
    const results = engine.handle(a, "rois.command.get_command_result", { command_id: "n1", condition: "" });
    expect(results.results).toEqual([{ name: "target", data_type_ref: "string", value: "home" }]);

    const event = paramsOf(a, "rois.event.notify_event")[0];
    expect(event.event_type).toBe("reached_target");
    expect(event.results).toEqual([
      { name: "target", data_type_ref: "string", value: "home" },
      { name: "is_final_target", data_type_ref: "bool", value: "true" },
    ]);
  });

  it("aborts a drive when the component is stopped", async () => {
    const engine = start();
    const a = client("a");
    engine.handle(a, "rois.command.bind", { component_ref: NAV });
    engine.handle(a, "rois.command.execute", { command_unit_list: [unit(NAV, "start", "n1")] });
    engine.handle(a, "rois.command.execute", { command_unit_list: [unit(NAV, "stop", "n2")] });

    await until(() => paramsOf(a, "rois.command.completed").length === 2);
    expect(paramsOf(a, "rois.command.completed")).toEqual([
      { command_id: "n1", status: "ABORT" },
      { command_id: "n2", status: "OK" },
    ]);
  });

  it("stores the arguments of a set_parameter command", async () => {
    const engine = start();
    const a = client("a");
    engine.handle(a, "rois.command.bind", { component_ref: NAV });
    engine.handle(a, "rois.command.execute", {
      command_unit_list: [
        {
          component_ref: NAV,
          command_type: "set_parameter",
          command_id: "p1",
          arguments: [{ name: "time_limit", data_type_ref: "int", value: "45" }],
          delay_time: null,
        },
      ],
    });
    await until(() => paramsOf(a, "rois.command.completed").length === 1);
    const read = engine.handle(a, "rois.command.get_parameter", { component_ref: NAV });
    expect(read.parameters).toContainEqual({ name: "time_limit", data_type_ref: "int", value: "45" });
  });
});

describe("get_command_result", () => {
  it("answers BAD_PARAMETER for an unknown command or a non-empty filter", () => {
    const engine = start();
    const a = client("a");
    expect(engine.handle(a, "rois.command.get_command_result", { command_id: "nope", condition: "" }).return_code).toBe(
      "BAD_PARAMETER",
    );
    engine.handle(a, "rois.command.execute", { command_unit_list: [{ ...unitOf(PERSON), command_id: "c1" }] });
    expect(
      engine.handle(a, "rois.command.get_command_result", { command_id: "c1", condition: "component_ref = 'x'" })
        .return_code,
    ).toBe("BAD_PARAMETER");
  });
});

function unitOf(ref: string) {
  return { component_ref: ref, command_type: "start", command_id: "", arguments: [], delay_time: null };
}

// ---------------------------------------------------------------------------
// Events
// ---------------------------------------------------------------------------

describe("events", () => {
  it("sends person_detected events until unsubscribe", async () => {
    const engine = start();
    const a = client("a");
    const subscribed = engine.handle(a, "rois.event.subscribe", { event_type: "person_detected", condition: "" });
    expect(subscribed.return_code).toBe("OK");

    await until(() => paramsOf(a, "rois.event.notify_event").length >= 2);
    const event = paramsOf(a, "rois.event.notify_event")[0];
    expect(event.subscribe_id).toBe(subscribed.subscribe_id);
    expect(event.event_type).toBe("person_detected");

    const detail = engine.handle(a, "rois.event.get_event_detail", {
      event_id: String(event.event_id),
      condition: "",
    });
    expect(detail.results).toEqual(event.results);

    engine.handle(a, "rois.event.unsubscribe", { subscribe_id: String(subscribed.subscribe_id) });
    const count = paramsOf(a, "rois.event.notify_event").length;
    await new Promise((resolve) => setTimeout(resolve, 40));
    expect(paramsOf(a, "rois.event.notify_event")).toHaveLength(count);
  });

  it("answers UNSUPPORTED for an event no component declares", () => {
    const result = start().handle(client("a"), "rois.event.subscribe", { event_type: "door_opened", condition: "" });
    expect(result.return_code).toBe("UNSUPPORTED");
  });

  it("answers BAD_PARAMETER for an unknown event_id", () => {
    const result = start().handle(client("a"), "rois.event.get_event_detail", { event_id: "evt-0", condition: "" });
    expect(result.return_code).toBe("BAD_PARAMETER");
  });
});
