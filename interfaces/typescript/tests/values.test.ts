/**
 * Tests for the string forms of typed values (values.ts).
 *
 * They mirror tests/test_values.py of the Python package. interfaces/fixtures/values.json
 * and value-edges.json hold the vectors all three languages share, read in fixtures.test.ts.
 * These cover what does not fit a vector: the refused values of this API, and the places
 * where JavaScript numbers differ from Python's.
 */

import { describe, it, expect } from "vitest";
import { RoISValueError, decodeValue, encodeValue } from "../src/values";

describe("encodeValue", () => {
  it("takes the type from the data type, since 2 and 2.0 are one number here", () => {
    expect(encodeValue("int", 2)).toBe("2");
    expect(encodeValue("float", 2)).toBe("2.0");
    expect(encodeValue("float[]", [2, 2.5])).toBe("[2.0, 2.5]");
    expect(encodeValue("double[][]", [[1], []])).toBe("[[1.0], []]");
  });

  it("writes floats as Python does at every point where the notation changes", () => {
    expect(encodeValue("float", 123456789012345680)).toBe("1.2345678901234568e+17");
    expect(encodeValue("float", 9999999999999998)).toBe("9999999999999998.0");
    expect(encodeValue("float", 0.00012)).toBe("0.00012");
    expect(encodeValue("float", 0.000012)).toBe("1.2e-05");
    expect(encodeValue("float", -1e16)).toBe("-1e+16");
    expect(encodeValue("float", 1e100)).toBe("1e+100");
    expect(encodeValue("float", 5e-324)).toBe("5e-324");
    expect(encodeValue("float", -0)).toBe("-0.0");
  });

  it("writes the numbers JSON has no form for as Python does", () => {
    expect(encodeValue("float", Number.NaN)).toBe("NaN");
    expect(encodeValue("float[]", [Infinity, -Infinity])).toBe("[Infinity, -Infinity]");
  });

  it("writes a date in ISO 8601", () => {
    const moment = new Date(Date.UTC(2026, 9, 8, 4, 50));
    expect(encodeValue("DateTime", moment)).toBe("2026-10-08T04:50:00.000Z");
    expect(encodeValue("DateTime[]", [moment])).toBe('["2026-10-08T04:50:00.000Z"]');
  });

  it("takes a string as the string form", () => {
    expect(encodeValue("string[]", '["home"]')).toBe('["home"]');
    expect(encodeValue("int", "42")).toBe("42");
    expect(() => encodeValue("int", "forty-two")).toThrow(RoISValueError);
  });

  it("writes a value of an unknown type as JSON", () => {
    expect(encodeValue("polygon", [[0, 0], [1, 1]])).toBe("[[0, 0], [1, 1]]");
    expect(encodeValue("pose", { x: 1, y: 1.5, name: "a" })).toBe('{"x": 1, "y": 1.5, "name": "a"}');
    expect(encodeValue("pose", null)).toBe("null");
    expect(encodeValue("pose", true)).toBe("true");
  });

  it.each<[string, unknown]>([
    ["int", 1.5],
    ["int", true],
    ["int", Number.MAX_SAFE_INTEGER + 1],
    ["float", "1.5x"],
    ["float", true],
    ["bool", 1],
    ["string", 3],
    ["string[]", "kitchen"],
    ["string[]", 3],
    ["int[]", [1.5]],
    ["Component_Status", "IDLE"],
    ["Component_Status", 3],
    ["Component_Status[]", ["IDLE"]],
    ["DateTime", new Date(Number.NaN)],
    ["pose", undefined],
    ["pose", new Map()],
  ])("refuses %s %j", (dataType, value) => {
    expect(() => encodeValue(dataType, value)).toThrow(RoISValueError);
  });
});

describe("decodeValue", () => {
  it("reads a float in every form Python's writer and reader use", () => {
    expect(decodeValue("float", "3")).toBe(3);
    expect(decodeValue("float", "-.5")).toBe(-0.5);
    expect(decodeValue("float", "5.")).toBe(5);
    expect(decodeValue("float", " 1E3 ")).toBe(1000);
    expect(decodeValue("float", "1_000.5")).toBe(1000.5);
    expect(decodeValue("float", "NaN")).toBeNaN();
    expect(decodeValue("float", "Infinity")).toBe(Infinity);
    expect(decodeValue("float", "-inf")).toBe(-Infinity);
  });

  it("reads NaN and Infinity in a float array", () => {
    expect(decodeValue("float[]", "[NaN, Infinity, -Infinity, 1.5]")).toEqual([
      Number.NaN,
      Infinity,
      -Infinity,
      1.5,
    ]);
    expect(decodeValue("double[][]", "[[Infinity]]")).toEqual([[Infinity]]);
  });

  it.each([
    ["float[]", '["\\u004eaN"]'],
    ["float[]", '["\\u0049nfinity"]'],
    ["float[]", '["-\\u0049nfinity"]'],
    ["double[]", '["\\u004eaN"]'],
    ["float[]", '[1.5, "\\u004eaN"]'],
    ["float[][]", '[["\\u004eaN"]]'],
  ])("refuses %s %s, a name spelled with an escape", (dataType, text) => {
    expect(() => decodeValue(dataType, text)).toThrow(RoISValueError);
  });

  it("keeps an escaped name as text in a string array", () => {
    expect(decodeValue("string[]", '["\\u004eaN"]')).toEqual(["NaN"]);
  });

  it("reads -0 as the integer 0", () => {
    expect(decodeValue("int", "-0")).toBe(0);
    expect(decodeValue("int[]", "[-0]")).toEqual([0]);
  });

  it("keeps the text of an unknown type", () => {
    expect(decodeValue("polygon", "[[0, 0], [1, 1]]")).toBe("[[0, 0], [1, 1]]");
  });

  it("refuses an integer it could not hold exactly", () => {
    expect(decodeValue("long", "9007199254740991")).toBe(Number.MAX_SAFE_INTEGER);
    expect(() => decodeValue("long", "9007199254740992")).toThrow(RoISValueError);
    expect(() => decodeValue("long[]", "[9007199254740993]")).toThrow(RoISValueError);
  });
});
