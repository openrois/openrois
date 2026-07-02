/**
 * Component registry for the mock RoIS gateway.
 *
 * Manages the set of mock components (PersonDetection, Navigation,
 * SystemInformation) and their state: bound/free status and stored parameters.
 * The registry is a server-side concept. It is not sent over the wire. The
 * gateway's JSON-RPC dispatch calls into this registry to answer search, bind,
 * release, set_parameter, get_parameter, and get_profile requests.
 *
 * The URN constants below identify component *types* per the RoIS spec's
 * RoISIdentifierType (authority + code). They are defined locally because the
 * @openrois/interfaces package does not yet export URN string constants. When
 * they are added there, this file should import them instead.
 *
 * Architecture: docs/architecture.md section 5 (Gateway) and section 7 (Hosts)
 * Protocol surface: project-outline.md section 6.2
 */

import type { Parameter, ReturnCode } from "@openrois/interfaces";

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
    this.register("PersonDetection_0", PERSON_DETECTION_URN);
    this.register("Navigation_0", NAVIGATION_URN);
    this.register("SystemInformation_0", SYSTEM_INFORMATION_URN);
  }

  /**
   * Register a component instance.
   *
   * Called during construction for the default components. Exposed as a method
   * so Week 3+ can add more components dynamically if needed.
   */
  register(ref: string, typeUrn: string): void {
    this.components.set(ref, {
      ref,
      typeUrn,
      status: "READY",
      bound: false,
      parameters: [],
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
      return "ERROR";
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
      return "ERROR";
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
   * Returns OK if the component exists. Returns ERROR if it does not. The
   * parameters replace any previously stored values for matching names.
   */
  setParameter(ref: string, params: Parameter[]): ReturnCode {
    const entry = this.components.get(ref);
    if (!entry) {
      return "ERROR";
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
      return { returnCode: "ERROR", parameters: [] };
    }
    return { returnCode: "OK", parameters: [...entry.parameters] };
  }

  /**
   * Return a canned HRI Engine Profile as a JSON string.
   *
   * The shape matches HRIEngineProfileType from @openrois/interfaces/profiles:
   * an identifier (authority + code) and the list of component_ids hosted by
   * this engine. The string is opaque to the SDK, which treats it as a string.
   */
  getProfile(): string {
    const profile = {
      identifier: {
        authority: "OMG",
        code: "MockEngine",
        codebook_ref: "",
        version: "",
      },
      component_ids: [...this.components.keys()],
    };
    return JSON.stringify(profile);
  }
}