/**
 * Tests for the CQL2-Text subset of conditions (condition.ts).
 *
 * They mirror tests/test_condition.py of the Python package, so both languages
 * read and write conditions the same way.
 */

import { describe, it, expect } from "vitest";
import {
  COMPONENT_REF,
  COMPONENT_TYPE,
  Comparison,
  Condition,
  ConditionError,
  allOf,
  componentRef,
  componentType,
  componentTypeUrn,
  eq,
  like,
  parseCondition,
  quote,
} from "../src/condition";

const HEAD = {
  [COMPONENT_REF]: "reachy_real/head",
  [COMPONENT_TYPE]: "urn:x-rois:def:component:OpenRoIS::Head",
};

function rejects(text: string, allowed?: ReadonlySet<string>): ConditionError {
  try {
    parseCondition(text, allowed);
  } catch (error) {
    expect(error instanceof ConditionError).toBe(true);
    return error as ConditionError;
  }
  throw new Error(`expected ${JSON.stringify(text)} to be rejected`);
}

describe("parseCondition", () => {
  it("reads an empty or blank condition as no filter", () => {
    for (const text of ["", "   ", "\n"]) {
      expect(parseCondition(text).comparisons).toHaveLength(0);
    }
  });

  it("reads an equality", () => {
    expect(parseCondition("component_ref = 'reachy_real/head'").comparisons).toEqual([
      new Comparison(COMPONENT_REF, "=", "reachy_real/head"),
    ]);
  });

  it("reads LIKE and AND", () => {
    const parsed = parseCondition("component_ref LIKE 'reachy_real/%' AND component_type = 'urn:t'");
    expect(parsed.comparisons.map((c) => c.operator)).toEqual(["LIKE", "="]);
  });

  it("accepts keywords in any case", () => {
    expect(parseCondition("component_ref like 'r/%' and component_type = 'x'").toString()).toBe(
      "component_ref LIKE 'r/%' AND component_type = 'x'",
    );
  });

  it("accepts a double-quoted property", () => {
    expect(parseCondition(`"component_ref" = 'r/head'`).comparisons[0].property).toBe(COMPONENT_REF);
  });

  it("reads a doubled quote inside a literal", () => {
    expect(parseCondition("component_ref = 'it''s'").comparisons[0].value).toBe("it's");
  });

  it("treats whitespace freely", () => {
    expect(parseCondition("  component_ref='r/head'  ").toString()).toBe("component_ref = 'r/head'");
  });

  it("rejects text outside the subset", () => {
    for (const text of [
      "component_ref = 'a' OR component_ref = 'b'",
      "NOT component_ref = 'a'",
      "(component_ref = 'a')",
      "component_ref <> 'a'",
      "component_ref = 'unterminated",
      "component_ref = reachy_real",
      "component_ref 'a'",
      "component_ref = 'a' component_type = 'b'",
      "component_ref = 'a' AND",
      "AND component_ref = 'a'",
      "component_ref LIKE 'trailing\\'",
    ]) {
      rejects(text);
    }
  });

  it("rejects an unknown property", () => {
    expect(rejects("robot = 'reachy'").message).toContain("Unsupported property 'robot'");
  });

  it("accepts no property for result filters", () => {
    expect(parseCondition("", new Set()).comparisons).toHaveLength(0);
    expect(rejects("component_ref = 'a'", new Set()).message).toContain("Supported: none");
  });
});

describe("matching", () => {
  it("compares equality exactly", () => {
    expect(parseCondition("component_ref = 'reachy_real/head'").matches(HEAD)).toBe(true);
    expect(parseCondition("component_ref = 'reachy_real/Head'").matches(HEAD)).toBe(false);
  });

  it("applies the LIKE wildcards and escapes", () => {
    const cases: [string, boolean][] = [
      ["reachy_real/%", true],
      ["%/head", true],
      ["reachy_real/hea_", true],
      ["reachy_sim/%", false],
      ["reachy\\_real/head", true],
      ["reachy\\%real/head", false],
      ["REACHY_REAL/%", false],
    ];
    for (const [pattern, expected] of cases) {
      expect(new Comparison(COMPONENT_REF, "LIKE", pattern).matches(HEAD)).toBe(expected);
    }
  });

  it("treats regular expression characters literally", () => {
    const comparison = new Comparison(COMPONENT_REF, "LIKE", "a.b");
    expect(comparison.matches({ [COMPONENT_REF]: "a.b" })).toBe(true);
    expect(comparison.matches({ [COMPONENT_REF]: "axb" })).toBe(false);
  });

  it("needs every comparison of an AND", () => {
    expect(parseCondition("component_ref LIKE 'reachy_real/%' AND component_type = 'x'").matches(HEAD)).toBe(false);
  });

  it("never matches a missing property", () => {
    expect(parseCondition("component_type = 'x'").matches({ [COMPONENT_REF]: "a" })).toBe(false);
  });

  it("matches everything with an empty condition", () => {
    expect(new Condition().matches({})).toBe(true);
  });

  it("lists the values a condition requires a property to equal", () => {
    const parsed = parseCondition("component_ref = 'reachy_real/head' AND component_type LIKE 'urn:%'");
    expect([...parsed.equalValues(COMPONENT_REF)]).toEqual(["reachy_real/head"]);
    expect([...parsed.equalValues(COMPONENT_TYPE)]).toEqual([]);
  });
});

describe("building", () => {
  it("writes comparisons", () => {
    expect(eq(COMPONENT_REF, "reachy_real/head")).toBe("component_ref = 'reachy_real/head'");
    expect(like(COMPONENT_REF, "reachy_real/%")).toBe("component_ref LIKE 'reachy_real/%'");
  });

  it("doubles single quotes", () => {
    expect(quote("it's")).toBe("'it''s'");
  });

  it("joins with AND and skips empty conditions", () => {
    expect(allOf(eq(COMPONENT_REF, "a"), "", like(COMPONENT_TYPE, "u%"))).toBe(
      "component_ref = 'a' AND component_type LIKE 'u%'",
    );
  });

  it("round-trips any value through parse", () => {
    for (const value of ["plain", "it's", "''", "a = 'b' AND c", "%_\\"]) {
      expect(parseCondition(eq(COMPONENT_REF, value)).comparisons).toEqual([
        new Comparison(COMPONENT_REF, "=", value),
      ]);
    }
  });

  it("writes canonical text", () => {
    expect(parseCondition("component_ref like 'r/%'   and component_type='t'").toString()).toBe(
      "component_ref LIKE 'r/%' AND component_type = 't'",
    );
  });

  it("selects by ref and by type", () => {
    expect(componentRef("reachy_sim/head")).toBe("component_ref = 'reachy_sim/head'");
    expect(componentTypeUrn({ authority: "OMG", code: "PersonDetection" })).toBe(
      "urn:x-rois:def:component:OMG::PersonDetection",
    );
    expect(componentType({ authority: "OMG", code: "Navigation" })).toBe(
      "component_type = 'urn:x-rois:def:component:OMG::Navigation'",
    );
  });
});
