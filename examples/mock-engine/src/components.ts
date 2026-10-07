/**
 * The components the mock engine simulates.
 *
 * Three basic RoIS components, with profiles built from the specification's
 * XML component profiles (PersonDetection.xml, Navigation.xml,
 * SystemInformation.xml and RoISCommon.xml). Each profile lists every message
 * its instance supports, including the RoIS_Common commands and the
 * component_status query that the XML profiles take from RoISCommon.
 */

import { HRIComponentProfileSchema } from "@openrois/interfaces";
import type { HRIComponentProfile, Parameter } from "@openrois/interfaces";

/** The engine id. Every ref is `mock/<name>`. */
export const ENGINE_ID = "mock";

/** The URN of the RoIS_Common profile the basic components include. */
export const ROIS_COMMON_URN = "urn:x-rois:def:Component:OMG::RoISCommon";

/** A component of the mock engine: its ref, its profile and its starting parameters. */
export interface MockComponent {
  /** Fully qualified ref, `mock/<name>`. */
  readonly ref: string;
  /** The profile get_profile returns for this component. */
  readonly profile: HRIComponentProfile;
  /** Parameter values before any set_parameter, from the profile defaults. */
  readonly parameters: Parameter[];
}

/** A parameter profile: a name, a type code, and an optional default. */
function parameterProfile(name: string, code: string, description: string, defaultValue = "") {
  return { name, data_type_ref: { code }, default_value: defaultValue, description };
}

/** The messages of RoIS_Common (RoISCommon.xml): four commands and component_status. */
const ROIS_COMMON = {
  command_profiles: ["start", "stop", "suspend", "resume"].map((name) => ({ name })),
  query_profiles: [
    {
      name: "component_status",
      results: [parameterProfile("status", "Component_Status", "status of the component")],
    },
  ],
};

/** Build a component, filling the profile defaults through the catalog schema. */
function component(name: string, profile: Record<string, unknown>): MockComponent {
  const parsed = HRIComponentProfileSchema.parse({ name, ...profile });
  const parameters = (parsed.parameter_profiles ?? []).map((p) => ({
    name: p.name,
    data_type_ref: p.data_type_ref.code,
    value: p.default_value,
  }));
  return { ref: `${ENGINE_ID}/${name}`, profile: parsed, parameters };
}

/** The components every mock engine starts with. */
export function mockComponents(): MockComponent[] {
  return [
    component("person_detection", {
      identifier: { authority: "OMG", code: "PersonDetection" },
      function: "sensing",
      sub_component_profiles: [ROIS_COMMON_URN],
      ...ROIS_COMMON,
      event_profiles: [
        {
          name: "person_detected",
          results: [
            parameterProfile("number", "int", "number of detected persons"),
            parameterProfile("timestamp", "DateTime", "time when measured"),
          ],
        },
      ],
    }),
    component("navigation", {
      identifier: { authority: "OMG", code: "Navigation" },
      function: "actuation",
      sub_component_profiles: [ROIS_COMMON_URN],
      ...ROIS_COMMON,
      event_profiles: [
        {
          name: "reached_target",
          results: [
            parameterProfile("target", "string", "reached target destination"),
            parameterProfile("is_final_target", "bool", "if it is the final destination point"),
          ],
        },
      ],
      parameter_profiles: [
        // Navigation.xml gives target_positions no default. The mock's own default
        // lets a client start navigation before setting any parameter.
        parameterProfile("target_positions", "string[]", "navigation target positions", '["home"]'),
        parameterProfile("time_limit", "int", "intended time limit to complete navigation", "0"),
        parameterProfile(
          "routing_policy",
          "string",
          "routing policy: 'time' priority or 'distance' priority",
          "time",
        ),
      ],
    }),
    component("system_information", {
      identifier: { authority: "OMG", code: "SystemInformation" },
      query_profiles: [
        {
          name: "robot_position",
          results: [
            parameterProfile("position_data", "String[]", "position of the robot as [x, y, th]"),
            parameterProfile("robot_ref", "RoISIdentifier[]", "list of robot IDs"),
            parameterProfile("timestamp", "DateTime", "timestamp of measurement"),
          ],
        },
        {
          name: "engine_status",
          results: [
            parameterProfile("operable_time", "DateTime", "operable time of the HRI Engine"),
            parameterProfile("status", "Component_Status", "status of this engine"),
          ],
        },
      ],
    }),
  ];
}
