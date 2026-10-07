/**
 * Unit tests for condition.ts, the builders of the CQL2-Text condition strings.
 *
 * The expected strings are the canonical text the Python parser
 * (openrois.interfaces.condition) writes back for the same condition.
 *
 * Run with: npx vitest run
 */

import { describe, it, expect } from "vitest";
import {
  COMPONENT_REF,
  COMPONENT_TYPE,
  allOf,
  componentRef,
  componentType,
  componentTypeUrn,
  eq,
  like,
  quote,
} from "../src/condition";

describe("quote()", () => {
  it("wraps a value in single quotes", () => {
    expect(quote("reachy_real/head")).toBe("'reachy_real/head'");
  });

  it("writes a single quote inside the value twice", () => {
    expect(quote("it's")).toBe("'it''s'");
    expect(quote("''")).toBe("''''''");
  });

  it("leaves LIKE wildcards and backslashes as they are", () => {
    expect(quote("%_\\")).toBe("'%_\\'");
  });
});

describe("comparisons", () => {
  it("eq builds an equality", () => {
    expect(eq(COMPONENT_REF, "reachy_real/head")).toBe("component_ref = 'reachy_real/head'");
  });

  it("like builds a LIKE comparison and keeps the pattern", () => {
    expect(like(COMPONENT_REF, "reachy_real/%")).toBe("component_ref LIKE 'reachy_real/%'");
  });

  it("quotes values that look like condition text", () => {
    expect(eq(COMPONENT_REF, "a' OR component_ref = 'b")).toBe(
      "component_ref = 'a'' OR component_ref = ''b'",
    );
  });
});

describe("allOf()", () => {
  it("joins conditions with AND", () => {
    expect(allOf(eq(COMPONENT_REF, "a"), like(COMPONENT_TYPE, "u%"))).toBe(
      "component_ref = 'a' AND component_type LIKE 'u%'",
    );
  });

  it("skips empty conditions", () => {
    expect(allOf("", eq(COMPONENT_REF, "a"), "  ")).toBe("component_ref = 'a'");
    expect(allOf()).toBe("");
  });
});

describe("component selection", () => {
  it("componentRef selects one component by ref", () => {
    expect(componentRef("reachy_sim/head")).toBe("component_ref = 'reachy_sim/head'");
  });

  it("componentTypeUrn writes the profile identifier as a URN", () => {
    expect(componentTypeUrn({ authority: "OMG", code: "PersonDetection" })).toBe(
      "urn:x-rois:def:component:OMG::PersonDetection",
    );
  });

  it("componentType selects components by type", () => {
    expect(componentType({ authority: "OMG", code: "Navigation" })).toBe(
      "component_type = 'urn:x-rois:def:component:OMG::Navigation'",
    );
  });
});
