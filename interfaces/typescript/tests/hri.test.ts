import { describe, it, expect } from "vitest";
import {
  ResultSchema,
  ParameterSchema,
  ArgumentSchema,
  CommandUnitSchema,
  ConcurrentCommandsSchema,
  CommandUnitSequenceSchema,
  ReturnCodeSchema,
  type Result,
  type Parameter,
  type Argument,
  type CommandUnit,
  type ReturnCode,
  type RoISIdentifier,
  type ConditionT,
  type DateTime,
  type Integer,
} from "../src/hri";

describe("ResultSchema", () => {
  it("parses a valid result", () => {
    const result = ResultSchema.parse({
      name: "number",
      data_type_ref: "int",
      value: "3",
    });
    expect(result).toEqual({
      name: "number",
      data_type_ref: "int",
      value: "3",
    });
  });

  it("rejects missing required fields", () => {
    expect(() => ResultSchema.parse({ name: "x" })).toThrow();
  });
});

describe("ParameterSchema", () => {
  it("parses a valid parameter", () => {
    const param = ParameterSchema.parse({
      name: "target_position",
      data_type_ref: "string",
      value: "1.0,2.0,0.0",
    });
    expect(param.name).toBe("target_position");
  });
});

describe("ArgumentSchema", () => {
  it("parses a valid argument", () => {
    const arg = ArgumentSchema.parse({
      name: "timeout",
      data_type_ref: "int",
      value: "5000",
    });
    expect(arg.value).toBe("5000");
  });
});

describe("CommandUnitSchema", () => {
  it("parses a command with defaults", () => {
    const cmd = CommandUnitSchema.parse({
      component_ref: "robot/nav",
      command_type: "set_parameter",
      command_id: "cmd-1",
    });
    expect(cmd.component_ref).toBe("robot/nav");
    expect(cmd.arguments).toBeUndefined();
    expect(cmd.delay_time).toBeNull();
  });

  it("parses a command the component defines, with arguments and delay", () => {
    const cmd = CommandUnitSchema.parse({
      component_ref: "robot/nav",
      command_type: "go_to",
      command_id: "cmd-2",
      arguments: [{ name: "x", data_type_ref: "int", value: "1" }],
      delay_time: 100,
    });
    expect(cmd.arguments).toHaveLength(1);
    expect(cmd.delay_time).toBe(100);
  });
});

describe("CommandUnitSequenceSchema", () => {
  it("parses a sequence with sequential commands", () => {
    const seq = CommandUnitSequenceSchema.parse({
      command_unit_list: [
        {
          component_ref: "robot/nav",
          command_type: "start",
          command_id: "cmd-1",
        },
      ],
    });
    expect(seq.command_unit_list).toHaveLength(1);
  });

  it("parses a sequence with concurrent commands", () => {
    const seq = CommandUnitSequenceSchema.parse({
      command_unit_list: [
        {
          command_list: [
            {
              component_ref: "robot/nav",
              command_type: "start",
              command_id: "cmd-1",
            },
          ],
        },
      ],
    });
    expect(seq.command_unit_list).toHaveLength(1);
  });
});

describe("ReturnCodeSchema", () => {
  it("accepts valid return codes", () => {
    expect(ReturnCodeSchema.parse("OK")).toBe("OK");
    expect(ReturnCodeSchema.parse("ERROR")).toBe("ERROR");
    expect(ReturnCodeSchema.parse("UNSUPPORTED")).toBe("UNSUPPORTED");
  });

  it("rejects invalid return codes", () => {
    expect(() => ReturnCodeSchema.parse("INVALID")).toThrow();
  });
});

describe("Type aliases", () => {
  it("RoISIdentifier is string", () => {
    const id: RoISIdentifier = "robot/nav";
    expect(typeof id).toBe("string");
  });

  it("ConditionT is string", () => {
    const c: ConditionT = "component_type='Navigation'";
    expect(typeof c).toBe("string");
  });

  it("DateTime is string", () => {
    const dt: DateTime = "2025-01-15T10:30:00Z";
    expect(typeof dt).toBe("string");
  });

  it("Integer is number", () => {
    const i: Integer = 42;
    expect(typeof i).toBe("number");
  });
});