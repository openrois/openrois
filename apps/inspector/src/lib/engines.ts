import type { HRIComponentProfile, HRIEngineProfileType } from "@openrois/interfaces";
import type { EngineProfile } from "@openrois/sdk";

/** One engine of the hierarchy, with the components it hosts itself. */
export interface EngineNode {
  id: string;
  /** The refs of the components this engine hosts, not those of its child engines. */
  components: string[];
  children: EngineNode[];
}

/** The engine id that a profile identifies, for example "gateway" or "mock". */
function engineId(profile: HRIEngineProfileType): string {
  return profile.identifier?.code || profile.name || "engine";
}

/**
 * The engine hierarchy of a get_profile answer.
 *
 * An engine lists every component below it in `component_ids`, its own and those of
 * its child engines. Each node keeps only its own, so every component appears once,
 * under the engine that hosts it.
 */
export function engineTree(answer: EngineProfile): EngineNode {
  const build = (profile: HRIEngineProfileType): EngineNode => {
    const children: EngineNode[] = (profile.sub_profiles ?? []).map(build);
    const below = new Set(children.flatMap(allComponents));
    const components = (profile.component_ids ?? []).filter((ref: string) => !below.has(ref));
    return { id: engineId(profile), components, children };
  };
  return build(answer.profile);
}

/** Every component ref at or below an engine. */
export function allComponents(node: EngineNode): string[] {
  return [...node.components, ...node.children.flatMap(allComponents)];
}

/** The display name of a component type, such as "Navigation". */
export function typeName(profile: HRIComponentProfile): string {
  return profile.identifier.code;
}

/** Whether a component answers component_status, which RoIS_Common brings. */
export function hasStatus(profile: HRIComponentProfile): boolean {
  return (profile.query_profiles ?? []).some((q) => q.name === "component_status");
}
