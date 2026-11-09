import type { Argument, HRIComponentProfile } from "@openrois/interfaces";
import type { CommandUnitSequenceItemInput } from "@openrois/sdk";
import { toWire } from "./values";

/** One command of a sequence, as the form holds it. */
export interface Step {
  key: string;
  ref: string;
  command: string;
  /** The text typed for each argument, by name. */
  args: Record<string, string>;
  /** Milliseconds to wait before the command starts, or empty. */
  delay: string;
}

/** A group of branches that run at the same time. Each branch runs its steps in order. */
export interface Group {
  key: string;
  branches: Step[][];
}

/** One item of a sequence: a command, or a group of concurrent branches. */
export type Item = { kind: "step"; step: Step } | { kind: "group"; group: Group };

let counter = 0;

/** A key that identifies a form row while it is reordered. */
export function newKey(): string {
  counter += 1;
  return `k${counter}`;
}

/** A new step on a component, with its first command selected. */
export function newStep(ref: string, profile: HRIComponentProfile | undefined): Step {
  const command = profile?.command_profiles?.[0]?.name ?? "";
  return { key: newKey(), ref, command, args: {}, delay: "" };
}

/** Every step of a sequence, in the order the engine assigns command ids. */
export function flatSteps(items: Item[]): Step[] {
  return items.flatMap((item) =>
    item.kind === "step" ? [item.step] : item.group.branches.flatMap((branch) => branch),
  );
}

/** A problem that keeps a sequence from running, attached to the step it concerns. */
export interface Problem {
  key: string;
  message: string;
}

/**
 * The problems of a sequence against the profiles and the binds of this session.
 *
 * The engine refuses a sequence whose command a profile does not declare, whose
 * argument does not fit its type, or whose component this session has not bound, so
 * the form says so before sending it.
 */
export function problems(
  items: Item[],
  profiles: Record<string, HRIComponentProfile>,
  bound: ReadonlySet<string>,
): Problem[] {
  const found: Problem[] = [];
  if (items.length === 0) {
    found.push({ key: "", message: "Add a command or a group to the sequence." });
  }
  for (const item of items) {
    if (item.kind === "group" && item.group.branches.every((b) => b.length === 0)) {
      found.push({ key: item.group.key, message: "This group has no commands." });
    }
  }
  for (const step of flatSteps(items)) {
    const profile = profiles[step.ref];
    if (!profile) {
      found.push({ key: step.key, message: `${step.ref} is not in the engine profile.` });
      continue;
    }
    const message = (profile.command_profiles ?? []).find((c) => c.name === step.command);
    if (!message) {
      found.push({ key: step.key, message: `${step.ref} declares no command "${step.command}".` });
      continue;
    }
    if (!bound.has(step.ref)) {
      found.push({ key: step.key, message: `Bind ${step.ref} before you run a command on it.` });
    }
    for (const arg of message.arguments ?? []) {
      const text = step.args[arg.name] ?? "";
      if (text.trim() === "") continue;
      try {
        toWire(arg.data_type_ref.code, text);
      } catch (error) {
        found.push({ key: step.key, message: `${arg.name}: ${(error as Error).message}` });
      }
    }
    if (step.delay.trim() !== "" && !/^\d+$/.test(step.delay.trim())) {
      found.push({ key: step.key, message: "The delay is a whole number of milliseconds." });
    }
  }
  return found;
}

/** The command of one step, as execute() takes it. */
function unit(step: Step, profiles: Record<string, HRIComponentProfile>) {
  const message = (profiles[step.ref]?.command_profiles ?? []).find((c) => c.name === step.command);
  const args: Argument[] = (message?.arguments ?? [])
    .filter((arg) => (step.args[arg.name] ?? "").trim() !== "")
    .map((arg) => ({
      name: arg.name,
      data_type_ref: arg.data_type_ref.code,
      value: toWire(arg.data_type_ref.code, step.args[arg.name]),
    }));
  const delay = step.delay.trim();
  return {
    component_ref: step.ref,
    command_type: step.command,
    ...(args.length > 0 ? { arguments: args } : {}),
    ...(delay !== "" ? { delay_time: Number(delay) } : {}),
  };
}

/** The command_unit_list of rois.command.execute for a sequence that has no problems. */
export function commandUnitList(
  items: Item[],
  profiles: Record<string, HRIComponentProfile>,
): CommandUnitSequenceItemInput[] {
  return items.map((item) =>
    item.kind === "step"
      ? unit(item.step, profiles)
      : {
          branch_list: item.group.branches
            .filter((branch) => branch.length > 0)
            .map((branch) => ({ command_list: branch.map((step) => unit(step, profiles)) })),
        },
  );
}

/** A sequence as it ran: every step with the command id the engine gave it. */
export type PlanItem =
  | { kind: "step"; step: Step; id: string }
  | { kind: "group"; key: string; branches: { step: Step; id: string }[][] };

/**
 * Pair the ids that execute() returned with the steps that produced them.
 *
 * The SDK lists the ids item by item, and inside a concurrent group branch by branch,
 * command by command, which is the order of flatSteps.
 */
export function runPlan(items: Item[], ids: string[]): PlanItem[] {
  let next = 0;
  const take = () => ids[next++] ?? "";
  return items.map((item) =>
    item.kind === "step"
      ? { kind: "step", step: item.step, id: take() }
      : {
          kind: "group",
          key: item.group.key,
          branches: item.group.branches
            .filter((branch) => branch.length > 0)
            .map((branch) => branch.map((step) => ({ step, id: take() }))),
        },
  );
}

const SEVERITY = ["OK", "ABORT", "TIMEOUT", "OUT_OF_RESOURCES", "ERROR"];

/**
 * The status a group shows: pending while any command runs, then the worst way one
 * of its commands ended.
 */
export function worstStatus(statuses: string[]): string {
  if (statuses.some((s) => s === "RUNNING" || s === "")) return "RUNNING";
  return statuses.reduce((worst, s) => (SEVERITY.indexOf(s) > SEVERITY.indexOf(worst) ? s : worst), "OK");
}

/**
 * A first sequence on the components a profile has: a command, then a concurrent group
 * of two branches. With the mock adapter, the second branch ends with ERROR on purpose,
 * through the end_with command of its test fixture.
 */
export function exampleSequence(profiles: Record<string, HRIComponentProfile>): Item[] {
  const ofType = (type: string) => Object.keys(profiles).find((ref) => profiles[ref].identifier.code === type);
  const navigation = ofType("Navigation");
  const people = ofType("PersonDetection");
  const fault = ofType("TestFault");
  const first = navigation ?? people ?? Object.keys(profiles).find((ref) => (profiles[ref].command_profiles ?? []).length > 0);
  if (!first) return [];
  const make = (ref: string, command: string, args: Record<string, string> = {}): Step => ({
    key: newKey(),
    ref,
    command,
    args,
    delay: "",
  });
  const second = people ?? first;
  const failing = fault ? make(fault, "end_with", { status: "ERROR" }) : make(second, "stop");
  return [
    { kind: "step", step: make(first, "start") },
    { kind: "group", group: { key: newKey(), branches: [[make(second, "start")], [failing]] } },
  ];
}
