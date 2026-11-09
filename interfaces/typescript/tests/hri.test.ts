import { describe, it, expect } from "vitest";
import {
  ResultSchema,
  ParameterSchema,
  ArgumentSchema,
  CommandUnitSchema,
  ConcurrentCommandsSchema,
  BranchSchema,
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
import { CommandMessageProfileSchema } from "../src/profiles";
import {
  NavigationGetParameterResultSchema,
  NavigationSetParameterSchema,
} from "../src/components/navigation";
import { PersonDetectedEventSchema } from "../src/components/person-detection";

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
          branch_list: [
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

describe("Integer bounds", () => {
  const INTEGER_MIN = -2147483648;
  const INTEGER_MAX = 2147483647;

  const fields: [string, (value: number) => { success: boolean }][] = [
    [
      "CommandUnit.delay_time",
      (value) =>
        CommandUnitSchema.safeParse({
          component_ref: "a/b",
          command_type: "start",
          delay_time: value,
        }),
    ],
    [
      "ConcurrentCommands.delay_time",
      (value) => ConcurrentCommandsSchema.safeParse({ branch_list: [], delay_time: value }),
    ],
    [
      "NavigationSetParameter.time_limit",
      (value) =>
        NavigationSetParameterSchema.safeParse({ target_positions: ["a"], time_limit: value }),
    ],
    [
      "NavigationGetParameterResult.time_limit",
      (value) =>
        NavigationGetParameterResultSchema.safeParse({
          target_positions: ["a"],
          time_limit: value,
          routing_policy: "time",
        }),
    ],
    [
      "PersonDetectedEvent.number",
      (value) =>
        PersonDetectedEventSchema.safeParse({ timestamp: "2025-01-15T10:30:00Z", number: value }),
    ],
    [
      "CommandMessageProfile.timeout",
      (value) => CommandMessageProfileSchema.safeParse({ name: "start", timeout: value }),
    ],
  ];

  it.each(fields)("%s takes the whole range", (_, parse) => {
    expect(parse(INTEGER_MIN).success).toBe(true);
    expect(parse(INTEGER_MAX).success).toBe(true);
  });

  it.each(fields)("%s refuses a value outside the range", (_, parse) => {
    expect(parse(INTEGER_MIN - 1).success).toBe(false);
    expect(parse(INTEGER_MAX + 1).success).toBe(false);
  });
});

describe("minItems", () => {
  const unit = { component_ref: "a/b", command_type: "start" };

  it("BranchSchema refuses an empty command_list", () => {
    expect(BranchSchema.safeParse({ command_list: [] }).success).toBe(false);
    expect(BranchSchema.safeParse({ command_list: [unit] }).success).toBe(true);
  });

  it("ConcurrentCommandsSchema refuses an empty branch, and takes an empty branch_list", () => {
    expect(
      ConcurrentCommandsSchema.safeParse({ branch_list: [{ command_list: [] }] }).success,
    ).toBe(false);
    expect(ConcurrentCommandsSchema.safeParse({ branch_list: [] }).success).toBe(true);
  });
});
