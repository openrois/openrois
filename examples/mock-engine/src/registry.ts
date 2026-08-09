/**
 * Component registry for the mock RoIS engine.
 *
 * Manages the set of mock components (PersonDetection, Navigation,
 * SystemInformation) and their state: bound/free status and stored parameters.
 * The registry is a server-side concept. It is not sent over the wire. The
 * engine's JSON-RPC dispatch calls into this registry to answer search, bind,
 * release, set_parameter, get_parameter, and get_profile requests.
 *
 * The URN constants below identify component *types* per the RoIS spec's
 * RoISIdentifierType (authority + code). They are defined locally because the
 * @openrois/interfaces package does not yet export URN string constants. When
 * they are added there, this file should import them instead.
 *
 * Architecture: docs/architecture.md section 5 (Engine) and section 7 (Hosts)
 * Protocol surface: project-outline.md section 6.2
 */

import type { Parameter, ReturnCode } from "@openrois/interfaces";
import type {
  HRIComponentProfile,
  HRIEngineProfileType,
} from "@openrois/interfaces/profiles";

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
   * Seed the three default mock components.
   *
   * Each starts in READY status, unbound, with no stored parameters. The ref
   * uses a zero-indexed suffix to leave room for multiple instances later.
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
  }

  /**
   * Register a component instance with optional default parameters.
   *
   * Called during construction for the default components. Exposed as a method
   * so Week 3+ can add more components dynamically if needed.
   */
  register(ref: string, typeUrn: string, parameters: Parameter[] = []): void {
    this.components.set(ref, {
      ref,
      typeUrn,
      status: "READY",
      bound: false,
      parameters: [...parameters],
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
   * Returns OK if the component exists and is not already bound. Returns ERROR
   * if the component does not exist or is already bound by another client.
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
   * Returns OK if the component exists and was bound. Returns ERROR if the
   * component does not exist or was not bound.
   */
  release(ref: string): ReturnCode {
    const entry = this.components.get(ref);
    if (!entry) {
      return "UNSUPPORTED";
    }
    // Silently ignore release of an unbound component (per the RoIS
    // spec, duplicate unsubscribe/release requests are silently
    // ignored).
    if (entry.bound) {
      entry.bound = false;
    }
    return "OK";
  }

  /**
   * Store parameters on a component.
   *
   * Returns OK if the component exists. Returns ERROR if it does not. The
   * parameters replace any previously stored values for matching names.
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
   * Returns OK and the parameter list if the component exists. Returns ERROR
   * and an empty list if it does not.
   */
  getParameter(ref: string): { returnCode: ReturnCode; parameters: Parameter[] } {
    const entry = this.components.get(ref);
    if (!entry) {
      return { returnCode: "UNSUPPORTED", parameters: [] };
    }
    return { returnCode: "OK", parameters: [...entry.parameters] };
  }

  /**
   * Execute a command on a component.
   *
   * The mock does not actually execute anything. It acknowledges the
   * command with a generated command_id. Returns UNSUPPORTED if the
   * component does not exist.
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
   * Auto-select a component for bind_any.
   *
   * Returns the first registered component ref, or OUT_OF_RESOURCES if
   * no components are registered.
   */
  bindAny(): { returnCode: ReturnCode; componentRef: string } {
    const first = this.components.keys().next();
    if (first.done) {
      return { returnCode: "OUT_OF_RESOURCES", componentRef: "" };
    }
    return { returnCode: "OK", componentRef: first.value };
  }

  /**
   * Check whether a component ref is registered.
   */
  has(ref: string): boolean {
    return this.components.has(ref);
  }

  /**
   * Return the HRI Engine Profile with embedded component profiles.
   *
   * The shape matches HRIEngineProfileType from @openrois/interfaces/profiles.
   * Includes component_ids (the registered refs) and component_profiles
   * (full capability descriptions built from the component type URNs).
   *
   * Returns a structured object, not a JSON string. The server wraps it in
   * the JSON-RPC response.
   */
  getProfile(): HRIEngineProfileType {
    return {
      identifier: {
        authority: "OMG",
        code: "MockEngine",
        codebook_ref: "",
        version: "",
      },
      component_ids: [...this.components.keys()],
      component_profiles: [...this.components.values()].map((entry) =>
        this.buildComponentProfile(entry),
      ),
    };
  }

  /**
   * Build an HRIComponentProfile from a registered component entry.
   *
   * Maps the component type URN to canned command, query, and event
   * message profiles matching the RoIS spec component definitions.
   */
  private buildComponentProfile(entry: ComponentEntry): HRIComponentProfile {
    const code = entry.typeUrn.split("::").pop() ?? entry.ref;
    return {
      identifier: {
        authority: "OMG",
        code,
        codebook_ref: "",
        version: "",
      },
      name: entry.ref,
      command_profiles: COMPONENT_COMMAND_PROFILES[code] ?? [],
      query_profiles: COMPONENT_QUERY_PROFILES[code] ?? [],
      event_profiles: COMPONENT_EVENT_PROFILES[code] ?? [],
    };
  }
}

// ---------------------------------------------------------------------------
// Canned message profiles per component type
// ---------------------------------------------------------------------------

import type {
  CommandMessageProfile,
  QueryMessageProfile,
  EventMessageProfile,
} from "@openrois/interfaces/profiles";

/** Command profiles for each component type, keyed by code. */
const COMPONENT_COMMAND_PROFILES: Record<string, CommandMessageProfile[]> = {
  SystemInformation: [],
  Navigation: [
    { name: "start", results: [], arguments: [], timeout: null },
    { name: "stop", results: [], arguments: [], timeout: null },
    { name: "suspend", results: [], arguments: [], timeout: null },
    { name: "resume", results: [], arguments: [], timeout: null },
    { name: "set_parameter", results: [], arguments: [], timeout: null },
    { name: "execute", results: [], arguments: [], timeout: null },
  ],
  PersonDetection: [
    { name: "start", results: [], arguments: [], timeout: null },
    { name: "stop", results: [], arguments: [], timeout: null },
    { name: "suspend", results: [], arguments: [], timeout: null },
    { name: "resume", results: [], arguments: [], timeout: null },
  ],
};

/** Query profiles for each component type, keyed by code. */
const COMPONENT_QUERY_PROFILES: Record<string, QueryMessageProfile[]> = {
  SystemInformation: [
    { name: "robot_position", results: [] },
    { name: "engine_status", results: [] },
  ],
  Navigation: [
    { name: "component_status", results: [] },
    { name: "get_parameter", results: [] },
  ],
  PersonDetection: [
    { name: "component_status", results: [] },
  ],
};

/** Event profiles for each component type, keyed by code. */
const COMPONENT_EVENT_PROFILES: Record<string, EventMessageProfile[]> = {
  SystemInformation: [],
  Navigation: [
    { name: "reached_target", results: [] },
  ],
  PersonDetection: [
    { name: "person_detected", results: [] },
  ],
};