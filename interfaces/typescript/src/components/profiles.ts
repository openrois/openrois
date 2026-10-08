// GENERATED FROM interfaces/schema — DO NOT EDIT
// Source: profiles.json
// Generator: scripts/generate.ts
//
// The full profile of each basic component type: its XML profile with the
// RoIS_Common messages it includes, and its RoSO function. A component declares
// the profile of its type and implements a part of it, and the engine serves
// the part the component implements.

import type { HRIComponentProfile } from "../profiles";

/** The OMG RoISCommon profile. */
export const ROIS_COMMON_PROFILE: HRIComponentProfile = {
  identifier: {
    authority: "OMG",
    code: "RoISCommon",
    codebook_ref: "",
    version: "",
  },
  name: "rois_common",
  function: null,
  sub_component_profiles: [],
  command_profiles: [
    {
      name: "start",
      results: [],
      arguments: [],
      timeout: null,
    },
    {
      name: "stop",
      results: [],
      arguments: [],
      timeout: null,
    },
    {
      name: "suspend",
      results: [],
      arguments: [],
      timeout: null,
    },
    {
      name: "resume",
      results: [],
      arguments: [],
      timeout: null,
    },
  ],
  query_profiles: [
    {
      name: "component_status",
      results: [
        {
          name: "status",
          data_type_ref: {
            authority: "",
            code: "Component_Status",
            codebook_ref: "",
            version: "",
          },
          default_value: "",
          description: "",
        },
      ],
    },
  ],
  event_profiles: [],
  parameter_profiles: [],
};

/** The OMG Navigation profile. */
export const NAVIGATION_PROFILE: HRIComponentProfile = {
  identifier: {
    authority: "OMG",
    code: "Navigation",
    codebook_ref: "",
    version: "",
  },
  name: "navigation",
  function: "actuation",
  sub_component_profiles: [
    "urn:x-rois:def:Component:OMG::RoISCommon",
  ],
  command_profiles: [
    {
      name: "start",
      results: [],
      arguments: [],
      timeout: null,
    },
    {
      name: "stop",
      results: [],
      arguments: [],
      timeout: null,
    },
    {
      name: "suspend",
      results: [],
      arguments: [],
      timeout: null,
    },
    {
      name: "resume",
      results: [],
      arguments: [],
      timeout: null,
    },
  ],
  query_profiles: [
    {
      name: "component_status",
      results: [
        {
          name: "status",
          data_type_ref: {
            authority: "",
            code: "Component_Status",
            codebook_ref: "",
            version: "",
          },
          default_value: "",
          description: "",
        },
      ],
    },
  ],
  event_profiles: [
    {
      name: "reached_target",
      results: [
        {
          name: "target",
          data_type_ref: {
            authority: "",
            code: "string",
            codebook_ref: "",
            version: "",
          },
          default_value: "",
          description: "reached target destination",
        },
        {
          name: "is_final_target",
          data_type_ref: {
            authority: "",
            code: "bool",
            codebook_ref: "",
            version: "",
          },
          default_value: "",
          description: "if it is final destination point",
        },
      ],
    },
  ],
  parameter_profiles: [
    {
      name: "target_positions",
      data_type_ref: {
        authority: "",
        code: "string[]",
        codebook_ref: "",
        version: "",
      },
      default_value: "",
      description: "navigation target positions",
    },
    {
      name: "time_limit",
      data_type_ref: {
        authority: "",
        code: "int",
        codebook_ref: "",
        version: "",
      },
      default_value: "0",
      description: "intended time limit to complete navigation",
    },
    {
      name: "routing_policy",
      data_type_ref: {
        authority: "",
        code: "string",
        codebook_ref: "",
        version: "",
      },
      default_value: "time",
      description: "routing policy: 'time' priority or 'distance' priority",
    },
  ],
};

/** The OMG PersonDetection profile. */
export const PERSON_DETECTION_PROFILE: HRIComponentProfile = {
  identifier: {
    authority: "OMG",
    code: "PersonDetection",
    codebook_ref: "",
    version: "",
  },
  name: "person_detecter",
  function: "sensing",
  sub_component_profiles: [
    "urn:x-rois:def:Component:OMG::RoISCommon",
  ],
  command_profiles: [
    {
      name: "start",
      results: [],
      arguments: [],
      timeout: null,
    },
    {
      name: "stop",
      results: [],
      arguments: [],
      timeout: null,
    },
    {
      name: "suspend",
      results: [],
      arguments: [],
      timeout: null,
    },
    {
      name: "resume",
      results: [],
      arguments: [],
      timeout: null,
    },
  ],
  query_profiles: [
    {
      name: "component_status",
      results: [
        {
          name: "status",
          data_type_ref: {
            authority: "",
            code: "Component_Status",
            codebook_ref: "",
            version: "",
          },
          default_value: "",
          description: "",
        },
      ],
    },
  ],
  event_profiles: [
    {
      name: "person_detected",
      results: [
        {
          name: "number",
          data_type_ref: {
            authority: "",
            code: "int",
            codebook_ref: "",
            version: "",
          },
          default_value: "",
          description: "number of detected persons",
        },
        {
          name: "timestamp",
          data_type_ref: {
            authority: "",
            code: "DateTime",
            codebook_ref: "",
            version: "",
          },
          default_value: "",
          description: "time when measuered",
        },
      ],
    },
  ],
  parameter_profiles: [],
};

/** The OMG Reaction profile. */
export const REACTION_PROFILE: HRIComponentProfile = {
  identifier: {
    authority: "OMG",
    code: "Reaction",
    codebook_ref: "",
    version: "",
  },
  name: "reaction",
  function: "actuation",
  sub_component_profiles: [
    "urn:x-rois:def:Component:OMG::RoISCommon",
  ],
  command_profiles: [
    {
      name: "start",
      results: [],
      arguments: [],
      timeout: null,
    },
    {
      name: "stop",
      results: [],
      arguments: [],
      timeout: null,
    },
    {
      name: "suspend",
      results: [],
      arguments: [],
      timeout: null,
    },
    {
      name: "resume",
      results: [],
      arguments: [],
      timeout: null,
    },
  ],
  query_profiles: [
    {
      name: "component_status",
      results: [
        {
          name: "status",
          data_type_ref: {
            authority: "",
            code: "Component_Status",
            codebook_ref: "",
            version: "",
          },
          default_value: "",
          description: "",
        },
      ],
    },
    {
      name: "available_reactions",
      results: [
        {
          name: "available_reactions",
          data_type_ref: {
            authority: "",
            code: "RoISIdentifier[]",
            codebook_ref: "",
            version: "",
          },
          default_value: "",
          description: "list of available reaction IDs, this robot can perform",
        },
      ],
    },
  ],
  event_profiles: [],
  parameter_profiles: [
    {
      name: "reaction_ref",
      data_type_ref: {
        authority: "",
        code: "RoISIdentifier",
        codebook_ref: "",
        version: "",
      },
      default_value: "",
      description: "Reaction type as ID",
    },
  ],
};

/** The OMG SpeechSynthesis profile. */
export const SPEECH_SYNTHESIS_PROFILE: HRIComponentProfile = {
  identifier: {
    authority: "OMG",
    code: "SpeechSynthesis",
    codebook_ref: "",
    version: "",
  },
  name: "speech_synthesizer",
  function: "actuation",
  sub_component_profiles: [
    "urn:x-rois:def:Component:OMG::RoISCommon",
  ],
  command_profiles: [
    {
      name: "start",
      results: [],
      arguments: [],
      timeout: null,
    },
    {
      name: "stop",
      results: [],
      arguments: [],
      timeout: null,
    },
    {
      name: "suspend",
      results: [],
      arguments: [],
      timeout: null,
    },
    {
      name: "resume",
      results: [],
      arguments: [],
      timeout: null,
    },
  ],
  query_profiles: [
    {
      name: "component_status",
      results: [
        {
          name: "status",
          data_type_ref: {
            authority: "",
            code: "Component_Status",
            codebook_ref: "",
            version: "",
          },
          default_value: "",
          description: "",
        },
      ],
    },
    {
      name: "synthesizable_languages",
      results: [
        {
          name: "languages",
          data_type_ref: {
            authority: "",
            code: "string[]",
            codebook_ref: "",
            version: "",
          },
          default_value: "",
          description: "list of available languages",
        },
      ],
    },
    {
      name: "available_voices",
      results: [
        {
          name: "characters",
          data_type_ref: {
            authority: "",
            code: "string[]",
            codebook_ref: "",
            version: "",
          },
          default_value: "",
          description: "list of available voice characters",
        },
      ],
    },
  ],
  event_profiles: [],
  parameter_profiles: [
    {
      name: "speech_text",
      data_type_ref: {
        authority: "",
        code: "string",
        codebook_ref: "",
        version: "",
      },
      default_value: "",
      description: "speech text in plain text",
    },
    {
      name: "ssml_text",
      data_type_ref: {
        authority: "",
        code: "string",
        codebook_ref: "",
        version: "",
      },
      default_value: "",
      description: "speech text in SSML text",
    },
    {
      name: "volume",
      data_type_ref: {
        authority: "",
        code: "int",
        codebook_ref: "",
        version: "",
      },
      default_value: "50",
      description: "Volume",
    },
    {
      name: "language",
      data_type_ref: {
        authority: "",
        code: "string",
        codebook_ref: "",
        version: "",
      },
      default_value: "en",
      description: "Language of the speech",
    },
    {
      name: "character",
      data_type_ref: {
        authority: "",
        code: "string",
        codebook_ref: "",
        version: "",
      },
      default_value: "default",
      description: "character of the voice",
    },
  ],
};

/** The OMG SystemInformation profile. */
export const SYSTEM_INFORMATION_PROFILE: HRIComponentProfile = {
  identifier: {
    authority: "OMG",
    code: "SystemInformation",
    codebook_ref: "",
    version: "",
  },
  name: "system_info",
  function: null,
  sub_component_profiles: [],
  command_profiles: [],
  query_profiles: [
    {
      name: "robot_position",
      results: [
        {
          name: "position_data",
          data_type_ref: {
            authority: "",
            code: "String[]",
            codebook_ref: "",
            version: "",
          },
          default_value: "",
          description: "position of robot or its parts in comma seperated double values [x, y, th]",
        },
        {
          name: "robot_ref",
          data_type_ref: {
            authority: "",
            code: "RoISIdentifier[]",
            codebook_ref: "",
            version: "",
          },
          default_value: "",
          description: "List of robot IDs",
        },
        {
          name: "timestamp",
          data_type_ref: {
            authority: "",
            code: "DateTime",
            codebook_ref: "",
            version: "",
          },
          default_value: "",
          description: "timestamp of measurement",
        },
      ],
    },
    {
      name: "engine_status",
      results: [
        {
          name: "operable_time",
          data_type_ref: {
            authority: "",
            code: "DateTime",
            codebook_ref: "",
            version: "",
          },
          default_value: "",
          description: "Operable time of the HRI Engine that includes this basic component",
        },
        {
          name: "status",
          data_type_ref: {
            authority: "",
            code: "Component_Status",
            codebook_ref: "",
            version: "",
          },
          default_value: "",
          description: "Status information of this engine",
        },
      ],
    },
  ],
  event_profiles: [],
  parameter_profiles: [],
};
