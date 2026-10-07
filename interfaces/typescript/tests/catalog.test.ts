import { describe, it, expect } from "vitest";
import {
  ExecuteParamsSchema,
  GetParameterResultSchema,
  GetProfileResultSchema,
  JsonRpcErrorCode,
  RoISCommandTypes,
  RoISMethods,
  RoISMethodSchemas,
  RoISNotifications,
  RoISNotificationSchemas,
  SearchResultSchema,
  UnmodelledMethodPrefixes,
  type RoISMethodMap,
  type RoISNotificationMap,
} from "../src/catalog";
import { CommandUnitSchema } from "../src/hri";

describe("method table", () => {
  it("lists the sixteen catalog methods", () => {
    expect(Object.keys(RoISMethods)).toHaveLength(16);
  });

  it("has a params and result schema for every method", () => {
    expect(Object.keys(RoISMethodSchemas).sort()).toEqual(Object.values(RoISMethods).sort());
  });

  it("uses the wire names", () => {
    expect(RoISMethods.GetProfile).toBe("rois.system.get_profile");
    expect(RoISMethods.Execute).toBe("rois.command.execute");
    expect(RoISMethods.Query).toBe("rois.query.query");
    expect(RoISMethods.Subscribe).toBe("rois.event.subscribe");
  });

  it("does not model streaming", () => {
    expect(UnmodelledMethodPrefixes).toEqual(["rois.stream."]);
    for (const method of Object.values(RoISMethods)) {
      expect(method.startsWith("rois.stream.")).toBe(false);
    }
  });

  it("uses the JSON-RPC 2.0 error codes", () => {
    expect(JsonRpcErrorCode.PARSE_ERROR).toBe(-32700);
    expect(JsonRpcErrorCode.INVALID_REQUEST).toBe(-32600);
    expect(JsonRpcErrorCode.METHOD_NOT_FOUND).toBe(-32601);
    expect(JsonRpcErrorCode.INVALID_PARAMS).toBe(-32602);
    expect(JsonRpcErrorCode.INTERNAL_ERROR).toBe(-32603);
  });

  it("accepts a failure result that carries only the return code", () => {
    for (const { result } of Object.values(RoISMethodSchemas)) {
      expect(result.safeParse({ return_code: "ERROR" }).success).toBe(true);
    }
  });
});

describe("execute", () => {
  it("accepts sequential and concurrent command units", () => {
    const params = ExecuteParamsSchema.parse({
      command_unit_list: [
        { component_ref: "reachy_real/head", command_type: "start", command_id: "nod-1" },
        {
          command_list: [
            { component_ref: "reachy_real/head", command_type: "stop", command_id: "nod-2" },
            { component_ref: "reachy_sim/head", command_type: "stop", command_id: "nod-3" },
          ],
          delay_time: 500,
        },
      ],
    });
    expect(params.command_unit_list).toHaveLength(2);
  });

  it("rejects a top-level component_ref", () => {
    const parsed = ExecuteParamsSchema.safeParse({
      component_ref: "reachy_real/head",
      command_unit_list: [
        { component_ref: "reachy_real/head", command_type: "start", command_id: "nod-1" },
      ],
    });
    expect(parsed.success).toBe(false);
  });

  it("requires a command_id on every unit", () => {
    const parsed = ExecuteParamsSchema.safeParse({
      command_unit_list: [{ component_ref: "reachy_real/head", command_type: "start" }],
    });
    expect(parsed.success).toBe(false);
  });
});

describe("results", () => {
  it("validates a search result", () => {
    const result = SearchResultSchema.parse({
      return_code: "OK",
      component_ref_list: ["reachy_real/head"],
    });
    expect(result.component_ref_list).toEqual(["reachy_real/head"]);
  });

  it("reads get_parameter values from parameters", () => {
    const result = GetParameterResultSchema.parse({
      return_code: "OK",
      parameters: [{ name: "time_limit", data_type_ref: "int", value: "30" }],
    });
    expect(result.parameters).toEqual([{ name: "time_limit", data_type_ref: "int", value: "30" }]);
  });

  it("defaults the profile to null on failure", () => {
    expect(GetProfileResultSchema.parse({ return_code: "ERROR" }).profile).toBeNull();
  });

  it("carries the component profiles keyed by ref", () => {
    const head = {
      identifier: { authority: "OpenRoIS", code: "Head" },
      name: "head",
      function: "actuation",
    };
    const result = GetProfileResultSchema.parse({
      return_code: "OK",
      profile: {
        identifier: { code: "main" },
        component_ids: ["reachy_real/head", "reachy_sim/head"],
      },
      component_profiles: { "reachy_real/head": head, "reachy_sim/head": head },
    });
    expect(Object.keys(result.component_profiles ?? {}).sort()).toEqual(
      result.profile.component_ids.sort(),
    );
    expect(result.component_profiles?.["reachy_real/head"]?.function).toBe("actuation");
  });

  it("keeps component profiles out of the engine profile", () => {
    const parsed = GetProfileResultSchema.safeParse({
      return_code: "OK",
      profile: { identifier: { code: "main" }, component_profiles: [] },
    });
    expect(parsed.success).toBe(false);
  });

  it("types the method map", () => {
    const result: RoISMethodMap["rois.command.execute"]["result"] = { return_code: "OK" };
    expect(result.return_code).toBe("OK");
  });
});

describe("notifications", () => {
  it("lists the three RoIS callbacks and profile_changed", () => {
    expect(RoISNotifications).toEqual({
      NotifyError: "rois.system.notify_error",
      Completed: "rois.command.completed",
      NotifyEvent: "rois.event.notify_event",
      ProfileChanged: "rois.system.profile_changed",
    });
  });

  it("has a params schema for every notification", () => {
    expect(Object.keys(RoISNotificationSchemas).sort()).toEqual(
      Object.values(RoISNotifications).sort(),
    );
  });

  it("validates notify_event with its payload", () => {
    const params = RoISNotificationSchemas["rois.event.notify_event"].params.parse({
      event_id: "evt-1",
      event_type: "person_detected",
      subscribe_id: "sub-1",
      results: [{ name: "number", data_type_ref: "int", value: "2" }],
    });
    expect(params.expire).toBe("");
    expect(params.results).toHaveLength(1);
  });

  it("validates profile_changed with no params", () => {
    const schema = RoISNotificationSchemas["rois.system.profile_changed"].params;
    expect(schema.safeParse({}).success).toBe(true);
    expect(schema.safeParse({ engine_id: "main" }).success).toBe(false);
  });

  it("types the notification map", () => {
    const params: RoISNotificationMap["rois.command.completed"]["params"] = {
      command_id: "nod-1",
      status: "OK",
    };
    expect(params.status).toBe("OK");
  });
});

describe("command types", () => {
  it("lists the standard command names", () => {
    expect(Object.values(RoISCommandTypes)).toEqual([
      "start",
      "stop",
      "suspend",
      "resume",
      "set_parameter",
    ]);
  });

  it("accepts command names a component defines", () => {
    const unit = CommandUnitSchema.parse({
      component_ref: "reachy_real/head",
      command_type: "nod",
      command_id: "nod-1",
    });
    expect(unit.command_type).toBe("nod");
  });
});
