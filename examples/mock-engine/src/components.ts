/**
 * The components the mock engine simulates.
 *
 * Three basic RoIS components, each with the profile constant of its type from
 * the interfaces package: the specification's XML component profile with the
 * RoIS_Common messages it includes. Each instance implements its whole profile,
 * so it serves the constant under its own name.
 */

import {
  NAVIGATION_PROFILE,
  PERSON_DETECTION_PROFILE,
  SYSTEM_INFORMATION_PROFILE,
} from "@openrois/interfaces/components";
import type { HRIComponentProfile, Parameter } from "@openrois/interfaces";

/** The engine id. Every ref is `mock/<name>`. */
export const ENGINE_ID = "mock";

/** A component of the mock engine: its ref, its profile and its starting parameters. */
export interface MockComponent {
  /** Fully qualified ref, `mock/<name>`. */
  readonly ref: string;
  /** The profile get_profile returns for this component. */
  readonly profile: HRIComponentProfile;
  /** Parameter values before any set_parameter, from the profile defaults. */
  readonly parameters: Parameter[];
}

/** An instance of a component type, named `name`, with the defaults of its profile. */
function component(name: string, type: HRIComponentProfile): MockComponent {
  const profile = { ...type, name };
  const parameters = (profile.parameter_profiles ?? []).map((p) => ({
    name: p.name,
    data_type_ref: p.data_type_ref.code,
    value: p.default_value ?? "",
  }));
  return { ref: `${ENGINE_ID}/${name}`, profile, parameters };
}

/**
 * Navigation with a default for target_positions. Navigation.xml gives it none,
 * and the default lets a client start navigation before setting any parameter.
 */
const NAVIGATION_WITH_HOME: HRIComponentProfile = {
  ...NAVIGATION_PROFILE,
  parameter_profiles: (NAVIGATION_PROFILE.parameter_profiles ?? []).map((p) =>
    p.name === "target_positions" ? { ...p, default_value: '["home"]' } : p,
  ),
};

/** The components every mock engine starts with. */
export function mockComponents(): MockComponent[] {
  return [
    component("person_detection", PERSON_DETECTION_PROFILE),
    component("navigation", NAVIGATION_WITH_HOME),
    component("system_information", SYSTEM_INFORMATION_PROFILE),
  ];
}
