import { describe, it, expect } from "vitest";
import {
  ResultSchema,
  ParameterSchema,
  ArgumentSchema,
  CommandUnitSchema,
  ReturnCodeSchema,
  ComponentStatusSchema,
  StreamStatusSchema,
  CompletedStatusSchema,
  ErrorTypeSchema,
  NotifyEventParamsSchema,
  SearchParamsSchema,
  SearchResultSchema,
} from "../src";
import {
  PersonDetectedEventSchema,
  NavigationSetParameterSchema,
} from "../src/components";
import {
  SystemInformationRobotPositionResultSchema,
  SystemInformationEngineStatusResultSchema,
} from "../src/components";

describe("Schema roundtrip — all schemas parse valid payloads", () => {
  it("ResultSchema roundtrip", () => {
    const data = { name: "number", data_type_ref: "int", value: "3" };
    const parsed = ResultSchema.parse(data);
    expect(parsed).toEqual(data);
  });

  it("ParameterSchema roundtrip", () => {
    const data = { name: "target", data_type_ref: "string", value: "1,2,3" };
    const parsed = ParameterSchema.parse(data);
    expect(parsed).toEqual(data);
  });

  it("ArgumentSchema roundtrip", () => {
    const data = { name: "timeout", data_type_ref: "int", value: "5000" };
    const parsed = ArgumentSchema.parse(data);
    expect(parsed).toEqual(data);
  });

  it("CommandUnitSchema roundtrip with defaults", () => {
    const data = {
      component_ref: "robot/nav",
      command_type: "start",
      command_id: "cmd-1",
    };
    const parsed = CommandUnitSchema.parse(data);
    expect(parsed.component_ref).toBe("robot/nav");
    expect(parsed.delay_time).toBeNull();
  });

  it("ReturnCodeSchema accepts all enum values", () => {
    const codes = ["OK", "ERROR", "BAD_PARAMETER", "UNSUPPORTED", "OUT_OF_RESOURCES", "TIMEOUT"];
    for (const code of codes) {
      expect(ReturnCodeSchema.parse(code)).toBe(code);
    }
  });

  it("ComponentStatusSchema accepts all enum values", () => {
    const statuses = ["UNINITIALIZED", "READY", "BUSY", "WARNING", "ERROR"];
    for (const s of statuses) {
      expect(ComponentStatusSchema.parse(s)).toBe(s);
    }
  });

  it("StreamStatusSchema accepts all enum values", () => {
    const statuses = [
      "STREAMING_NOT_CONNECTED",
      "STREAMING_NOT_RUNNING",
      "STREAMING_RUNNING",
      "STREAMING_SUSPENDED",
      "STREAMING_RESUMED",
    ];
    for (const s of statuses) {
      expect(StreamStatusSchema.parse(s)).toBe(s);
    }
  });

  it("CompletedStatusSchema accepts all enum values", () => {
    const statuses = ["OK", "ERROR", "ABORT", "OUT_OF_RESOURCES", "TIMEOUT"];
    for (const s of statuses) {
      expect(CompletedStatusSchema.parse(s)).toBe(s);
    }
  });

  it("ErrorTypeSchema accepts all enum values", () => {
    const types = [
      "ENGINE_INTERNAL_ERROR",
      "COMPONENT_INTERNAL_ERROR",
      "COMPONENT_NOT_RESPONDING",
      "USER_DEFINED_ERROR",
    ];
    for (const t of types) {
      expect(ErrorTypeSchema.parse(t)).toBe(t);
    }
  });

  it("PersonDetectedEventSchema roundtrip", () => {
    const data = { timestamp: "2025-01-15T10:30:00Z", number: 3 };
    const parsed = PersonDetectedEventSchema.parse(data);
    expect(parsed).toEqual(data);
  });

  it("NavigationSetParameterSchema roundtrip with defaults", () => {
    const data = { target_positions: ["1.0,2.0,0.0"] };
    const parsed = NavigationSetParameterSchema.parse(data);
    expect(parsed.target_positions).toEqual(["1.0,2.0,0.0"]);
    expect(parsed.time_limit).toBe(0);
    expect(parsed.routing_policy).toBe("time");
  });

  it("SystemInformationRobotPositionResultSchema roundtrip", () => {
    const data = {
      timestamp: "2025-01-15T10:30:00Z",
      robot_ref: ["robot-a1", "robot-a2"],
      position_data: ["1.0,2.0,0.0", "3.0,4.0,1.5"],
    };
    const parsed = SystemInformationRobotPositionResultSchema.parse(data);
    expect(parsed).toEqual(data);
  });

  it("SystemInformationEngineStatusResultSchema roundtrip", () => {
    const data = {
      status: "READY",
      operable_time: ["2025-01-15T08:00:00Z", "2025-01-15T12:00:00Z"],
    };
    const parsed = SystemInformationEngineStatusResultSchema.parse(data);
    expect(parsed).toEqual(data);
  });

  it("SearchParamsSchema roundtrip with default condition", () => {
    const parsed = SearchParamsSchema.parse({});
    expect(parsed.condition).toBe("");
  });

  it("SearchResultSchema roundtrip", () => {
    const data = { return_code: "OK", component_ref_list: ["robot/nav"] };
    const parsed = SearchResultSchema.parse(data);
    expect(parsed).toEqual(data);
  });

  it("NotifyEventParamsSchema roundtrip with defaults", () => {
    const data = {
      event_id: "robot/evt-1",
      event_type: "person_detected",
      subscribe_id: "robot/sub-1",
    };
    const parsed = NotifyEventParamsSchema.parse(data);
    expect(parsed.event_id).toBe("robot/evt-1");
    expect(parsed.expire).toBe("");
    // results is optional (no default in JSON Schema), undefined when omitted
    expect(parsed.results).toBeUndefined();
  });
});