import { describe, expect, it } from "vitest";
import type { EngineProfile } from "@openrois/sdk";
import answer from "./mock-profile.json";
import { commandUnitList, flatSteps, newKey, problems, type Item, type Step } from "../lib/sequence";
import { allComponents, engineTree } from "../lib/engines";

// A get_profile answer of the gateway with the mock adapter behind it.
const profile = answer as unknown as EngineProfile;
const profiles = profile.component_profiles;

const step = (ref: string, command: string, args: Record<string, string> = {}, delay = ""): Step => ({
  key: newKey(),
  ref,
  command,
  args,
  delay,
});

describe("engineTree", () => {
  it("puts every component under the engine that hosts it", () => {
    const tree = engineTree(profile);
    expect(tree.id).toBe("gateway");
    expect(tree.components).toEqual([]);
    expect(tree.children.map((c) => c.id)).toEqual(["mock"]);
    expect(allComponents(tree).sort()).toEqual(Object.keys(profiles).sort());
  });
});

describe("a sequence", () => {
  const bound = new Set(["mock/navigation", "mock/person_detection"]);

  it("serializes commands and a group of branches in order", () => {
    const items: Item[] = [
      { kind: "step", step: step("mock/navigation", "start", {}, "100") },
      {
        kind: "group",
        group: {
          key: newKey(),
          branches: [
            [step("mock/navigation", "stop")],
            [step("mock/person_detection", "start"), step("mock/person_detection", "stop")],
          ],
        },
      },
    ];
    expect(problems(items, profiles, bound)).toEqual([]);
    expect(commandUnitList(items, profiles)).toEqual([
      { component_ref: "mock/navigation", command_type: "start", delay_time: 100 },
      {
        branch_list: [
          { command_list: [{ component_ref: "mock/navigation", command_type: "stop" }] },
          {
            command_list: [
              { component_ref: "mock/person_detection", command_type: "start" },
              { component_ref: "mock/person_detection", command_type: "stop" },
            ],
          },
        ],
      },
    ]);
    // execute() returns the ids item by item and branch by branch, in this order.
    expect(flatSteps(items).map((s) => `${s.ref} ${s.command}`)).toEqual([
      "mock/navigation start",
      "mock/navigation stop",
      "mock/person_detection start",
      "mock/person_detection stop",
    ]);
  });

  it("writes arguments in their wire form", () => {
    const echo = (profiles["mock/fault"].command_profiles ?? []).find((c) => c.name === "echo");
    const arg = echo?.arguments?.[0];
    expect(arg).toBeDefined();
    const items: Item[] = [{ kind: "step", step: step("mock/fault", "echo", { [arg!.name]: "7" }) }];
    const [unit] = commandUnitList(items, profiles) as { arguments: { name: string; value: string }[] }[];
    expect(unit.arguments[0].name).toBe(arg!.name);
  });

  it("names what keeps it from running", () => {
    const unboundStep = step("mock/fault", "raise_error");
    const badDelay = step("mock/navigation", "start", {}, "soon");
    const items: Item[] = [
      { kind: "step", step: unboundStep },
      { kind: "step", step: badDelay },
      { kind: "group", group: { key: "empty", branches: [[]] } },
    ];
    const found = problems(items, profiles, bound);
    expect(found.find((p) => p.key === unboundStep.key)?.message).toMatch(/Bind mock\/fault/);
    expect(found.find((p) => p.key === badDelay.key)?.message).toMatch(/whole number/);
    expect(found.find((p) => p.key === "empty")?.message).toMatch(/no commands/);
    expect(problems([], profiles, bound)).toHaveLength(1);
  });
});

describe("a run", () => {
  it("pairs ids with steps in SDK order, and rolls a group up to its worst status", async () => {
    const { runPlan, worstStatus, exampleSequence } = await import("../lib/sequence");
    const items = exampleSequence(profiles);
    expect(items).toHaveLength(2);
    const plan = runPlan(items, ["c1", "c2", "c3"]);
    expect(plan[0]).toMatchObject({ kind: "step", id: "c1" });
    expect(plan[1].kind === "group" && plan[1].branches.map((b) => b.map((s) => s.id))).toEqual([["c2"], ["c3"]]);
    expect(worstStatus(["OK", "RUNNING"])).toBe("RUNNING");
    expect(worstStatus(["OK", "ERROR", "ABORT"])).toBe("ERROR");
    expect(worstStatus(["OK", "OK"])).toBe("OK");
  });
});
