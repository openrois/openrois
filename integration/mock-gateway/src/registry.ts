/**
 * Component registry for the mock RoIS gateway.
 *
 * Manages the set of mock components (PersonDetection, Navigation,
 * SystemInformation, Reaction) and their state: bound/free status and stored
 * parameters. The registry is a server-side concept. It is not sent over the
 * wire. The gateway's JSON-RPC dispatch calls into this registry to answer
 * search, bind, release, set_parameter, get_parameter, and get_profile
 * requests.
 *
 * The URN constants below identify component *types* per the RoIS spec's
 * RoISIdentifierType (authority + code). They are defined locally because the
 * @openrois/interfaces package does not yet export URN string constants. When
 * they are added there, this file should import them instead.
 *
 * Architecture: docs/architecture.md section 5 (Gateway) and section 7 (Hosts)
 * Protocol surface: project-outline.md section 6.2
 */

import type { Parameter, Result, ReturnCode } from "@openrois/interfaces";

// ---------------------------------------------------------------------------
// Component type URNs
// ---------------------------------------------------------------------------

/**
 * URN identifying the PersonDetection component type.
 *
 * Follows the project convention: urn:x-rois:def:component:<authority>::<code>
 * The authority is OMG because the component category is defined by the RoIS
 * spec taxonomy. The code is the component class name.
 */
export const PERSON_DETECTION_URN = "urn:x-rois:def:component:OMG::PersonDetection";

/** URN identifying the Navigation component type. */
export const NAVIGATION_URN = "urn:x-rois:def:component:OMG::Navigation";

/** URN identifying the SystemInformation component type. */
export const SYSTEM_INFORMATION_URN = "urn:x-rois:def:component:OMG::SystemInformation";

/**
 * URN identifying the Reaction component type.
 *
 * Reaction (RoIS spec component #12) executes a reaction specified by
 * reaction ID. On robots this maps to LED patterns or gestures. On avatars
 * it maps to animations or facial expressions. The mock gateway registers a
 * single instance so clients can bind and exercise the command lifecycle.
 */
export const REACTION_URN = "urn:x-rois:def:component:OMG::Reaction";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

/**
 * Component status values, matching the ComponentStatus enum from
 * @openrois/interfaces. Duplicated here as a const array to avoid importing
 * from a component-specific module just for the type.
 */
export const COMPONENT_STATUSES = [
  "UNINITIALIZED",
  "READY",
  "BUSY",
  "WARNING",
  "ERROR",
] as const;
export type ComponentStatus = (typeof COMPONENT_STATUSES)[number];

/**
 * A registered mock component and its current state.
 */
export interface ComponentEntry {
  /** Instance reference assigned by the gateway, e.g. "PersonDetection_0". */
  readonly ref: string;
  /** Component type URN, e.g. PERSON_DETECTION_URN. */
  readonly typeUrn: string;
  /** Current lifecycle status. */
  status: ComponentStatus;
  /** Whether a client has reserved this component via bind(). */
  bound: boolean;
  /** Parameters stored via set_parameter, retrievable via get_parameter. */
  parameters: Parameter[];
}

// ---------------------------------------------------------------------------
// Component registry
// ---------------------------------------------------------------------------

/**
 * In-memory registry of mock components.
 *
 * One instance is shared across all WebSocket connections (global bind state).
 * This means if client A binds PersonDetection_0, client B gets ERROR when
 * trying to bind the same ref. This matches the RoIS bind semantics where a
 * component is exclusively reserved.
 */
export class ComponentRegistry {
  private readonly components = new Map<string, ComponentEntry>();

  constructor() {
    this.seedDefaults();
  }

  /**
   * Seed the default mock components with realistic starting parameters.
   *
   * Each starts in READY status, unbound. The ref uses a zero-indexed suffix
   * to leave room for multiple instances later. Default parameters give
   * get_parameter something useful to return out of the box.
   */
  private seedDefaults(): void {
    this.register("PersonDetection_0", PERSON_DETECTION_URN, [
      { name: "confidence_threshold", data_type_ref: "float", value: "0.5" },
      { name: "model_name", data_type_ref: "string", value: "yolov8n" },
    ]);
    this.register("Navigation_0", NAVIGATION_URN, [
      { name: "target_positions", data_type_ref: "string[]", value: "[]" },
      { name: "time_limit", data_type_ref: "int", value: "30" },
      { name: "routing_policy", data_type_ref: "string", value: "time" },
    ]);
    this.register("SystemInformation_0", SYSTEM_INFORMATION_URN, [
      { name: "robot_position", data_type_ref: "string", value: "0.0,0.0,0.0" },
      { name: "battery_level", data_type_ref: "int", value: "85" },
    ]);
    this.register("Reaction_0", REACTION_URN, [
      { name: "reaction_id", data_type_ref: "string", value: "smile" },
      { name: "intensity", data_type_ref: "float", value: "1.0" },
      { name: "duration", data_type_ref: "int", value: "3" },
    ]);
  }

  /**
   * Register a component instance.
   *
   * Called during construction for the default components. Exposed as a method
   * so Week 3+ can add more components dynamically if needed. The optional
   * initialParameters list seeds the parameter store so get_parameter returns
   * useful values before any set_parameter call.
   */
  register(ref: string, typeUrn: string, initialParameters: Parameter[] = []): void {
    this.components.set(ref, {
      ref,
      typeUrn,
      status: "READY",
      bound: false,
      parameters: [...initialParameters],
    });
  }

  /**
   * Return all registered component refs.
   *
   * The condition parameter is accepted for wire-contract compliance but
   * ignored. Week 2 does not implement condition filtering. All components
   * are returned regardless.
   */
  search(_condition?: string): string[] {
    return [...this.components.keys()];
  }

  /**
   * Reserve a component for exclusive use.
   *
   * Returns OK if the component exists and is not already bound. Returns
   * UNSUPPORTED if the component does not exist. Returns ERROR if the
   * component is already bound by another client.
   */
  bind(ref: string): ReturnCode {
    const entry = this.components.get(ref);
    if (!entry) {
      return "UNSUPPORTED";
    }
    if (entry.bound) {
      return "ERROR";
    }
    entry.bound = true;
    return "OK";
  }

  /**
   * Free a previously bound component.
   *
   * Returns OK if the component exists and was bound. Returns UNSUPPORTED if
   * the component does not exist. Returns ERROR if the component was not
   * bound.
   */
  release(ref: string): ReturnCode {
    const entry = this.components.get(ref);
    if (!entry) {
      return "UNSUPPORTED";
    }
    if (!entry.bound) {
      return "ERROR";
    }
    entry.bound = false;
    return "OK";
  }

  /**
   * Store parameters on a component.
   *
   * Returns OK if the component exists. Returns UNSUPPORTED if it does not.
   * The parameters replace any previously stored values for matching names.
   */
  setParameter(ref: string, params: Parameter[]): ReturnCode {
    const entry = this.components.get(ref);
    if (!entry) {
      return "UNSUPPORTED";
    }
    // Merge: replace existing params with the same name, append new ones.
    for (const param of params) {
      const existing = entry.parameters.findIndex((p) => p.name === param.name);
      if (existing >= 0) {
        entry.parameters[existing] = param;
      } else {
        entry.parameters.push(param);
      }
    }
    return "OK";
  }

  /**
   * Retrieve parameters stored on a component.
   *
   * If names is provided and non-empty, only parameters matching those names
   * are returned. If names is empty or omitted, all parameters for the
   * component are returned. Returns UNSUPPORTED and an empty list if the
   * component does not exist.
   */
  getParameter(
    ref: string,
    names?: string[],
  ): { returnCode: ReturnCode; parameters: Parameter[] } {
    const entry = this.components.get(ref);
    if (!entry) {
      return { returnCode: "UNSUPPORTED", parameters: [] };
    }
    if (names && names.length > 0) {
      const filtered = entry.parameters.filter((p) => names.includes(p.name));
      return { returnCode: "OK", parameters: filtered };
    }
    return { returnCode: "OK", parameters: [...entry.parameters] };
  }

  /**
   * Auto-select and bind an available component.
   *
   * The condition parameter is accepted for wire-contract compliance but
   * ignored. Returns OK and the first unbound component ref. If all components
   * are bound or none are registered, returns OUT_OF_RESOURCES with an empty
   * ref.
   */
  bindAny(_condition?: string): { returnCode: ReturnCode; componentRef: string } {
    for (const [ref, entry] of this.components) {
      if (!entry.bound) {
        entry.bound = true;
        return { returnCode: "OK", componentRef: ref };
      }
    }
    return { returnCode: "OUT_OF_RESOURCES", componentRef: "" };
  }

  /**
   * Acknowledge a command execution request.
   *
   * Returns OK and a generated command_id if the component exists. Returns
   * UNSUPPORTED and an empty command_id if it does not. The mock does not
   * actually execute anything. Week 3 adds async completion notifications via
   * rois.command.completed.
   */
  execute(ref: string): { returnCode: ReturnCode; commandId: string } {
    const entry = this.components.get(ref);
    if (!entry) {
      return { returnCode: "UNSUPPORTED", commandId: "" };
    }
    const commandId = `cmd-${Date.now()}-${Math.floor(Math.random() * 10000)}`;
    return { returnCode: "OK", commandId };
  }

  /**
   * Return the result of a previously initiated command.
   *
   * The mock does not track command execution, so it returns OK with an empty
   * results array for any command_id. Week 3 will add real tracking when async
   * completion is implemented.
   */
  getCommandResult(_commandId: string): { returnCode: ReturnCode; results: Result[] } {
    return { returnCode: "OK", results: [] };
  }

  /**
   * Return canned error details for a known error_id.
   *
   * The mock recognizes a small set of error IDs (err-001, err-002) and
   * returns descriptive Result arrays. Unknown IDs return OK with an empty
   * results array, meaning the error was found but has no extra detail.
   */
  getErrorDetail(errorId: string): { returnCode: ReturnCode; results: Result[] } {
    const details = CANNED_ERROR_DETAILS[errorId] ?? [];
    return { returnCode: "OK", results: details };
  }

  /**
   * Return a canned HRI Engine Profile as a JSON string.
   *
   * The shape matches HRIEngineProfileType from @openrois/interfaces/profiles:
   * an identifier (authority + code), optional sub-profiles, and the list of
   * component_ids hosted by this engine. The string is opaque to the SDK,
   * which treats it as a string per the RoIS protocol (section 6.2).
   */
  getProfile(): string {
    const profile = {
      identifier: {
        authority: "OMG",
        code: "MockGateway",
        codebook_ref: "",
        version: "2.0",
      },
      sub_profiles: [
        {
          identifier: {
            authority: "OMG",
            code: "PerceptionSubEngine",
            codebook_ref: "",
            version: "2.0",
          },
          component_ids: ["PersonDetection_0"],
        },
      ],
      component_ids: [...this.components.keys()],
      parameter_profiles: [],
    };
    return JSON.stringify(profile);
  }
}

// ---------------------------------------------------------------------------
// Canned error details
// ---------------------------------------------------------------------------

/**
 * Canned error details keyed by error_id.
 *
 * The mock gateway recognizes a small set of known error IDs and returns
 * descriptive Result arrays. Unknown error IDs return an empty result list
 * with return_code OK (the error was found but has no extra detail).
 */
const CANNED_ERROR_DETAILS: Record<string, Result[]> = {
  "err-001": [
    {
      name: "component_ref",
      data_type_ref: "string",
      value: "robot-a1/Navigation",
    },
    {
      name: "description",
      data_type_ref: "string",
      value: "Navigation action timed out after 30s",
    },
  ],
  "err-002": [
    {
      name: "component_ref",
      data_type_ref: "string",
      value: "PersonDetection_0",
    },
    {
      name: "description",
      data_type_ref: "string",
      value: "Component internal error: model failed to load",
    },
  ],
};