/**
 * Tests that read interfaces/fixtures, the data the Python and C# packages read too.
 *
 * `wire.json` holds real gateway traffic. See testing/conformance/capture.py.
 */

import { readFileSync } from "node:fs";
import { describe, it, expect } from "vitest";
import {
  RoISMethodSchemas,
  RoISMethods,
  RoISNotificationSchemas,
  RoISNotifications,
  type RoISMethod,
  type RoISNotification,
} from "../src/catalog";
import { allOf, componentRef, componentType, componentTypeUrn, eq, like, quote } from "../src/condition";
import { CommandUnitSchema, ConcurrentCommandsSchema } from "../src/hri";
import { RoISValueError, decodeValue, encodeValue } from "../src/values";

interface WireEntry {
  kind: "params" | "result" | "notification";
  method: string;
  body: Record<string, unknown>;
}

interface ConditionVector {
  builder: string;
  args: unknown[];
  expected: string;
}

interface ValueVector {
  data_type: string;
  value: unknown;
  text: string;
}

interface RefusedEdge {
  data_type: string;
  text: string;
}

interface DecodedEdge extends RefusedEdge {
  value: unknown;
}

interface EncodedEdge extends RefusedEdge {
  value_text: string;
}

interface ModelEdge {
  name: string;
  kind: WireEntry["kind"];
  method: string;
  refused: boolean;
  body: Record<string, unknown>;
}

interface ConditionEdge extends ConditionVector {
  name: string;
}

interface ValueEdges {
  refused: RefusedEdge[];
  decoded: DecodedEdge[];
  encoded: EncodedEdge[];
  doubles: { bits: string; text: string }[];
  models: ModelEdge[];
  conditions: ConditionEdge[];
  exceptions: {
    language: string;
    why: string;
    cases: ({ list: "refused" | "decoded" | "encoded" | "models" | "conditions" } & Partial<
      EncodedEdge & ModelEdge
    >)[];
  }[];
}

function read(name: string): unknown {
  return JSON.parse(readFileSync(new URL(`../../fixtures/${name}`, import.meta.url), "utf-8"));
}

const WIRE = read("wire.json") as WireEntry[];
const CONDITIONS = read("conditions.json") as ConditionVector[];
const VALUES = read("values.json") as ValueVector[];
const EDGES = read("value-edges.json") as ValueEdges;

const LANGUAGE = "typescript";

/** The fields of a case or of an exception's reference, compared as one text. */
function caseKey(entry: Partial<EncodedEdge & ModelEdge>): string {
  return JSON.stringify([entry.data_type, entry.text, entry.value_text, entry.name]);
}

/** The cases of a list that value-edges.json records as a difference of this language. */
function excepted(list: string): Set<string> {
  const own = EDGES.exceptions.filter((exception) => exception.language === LANGUAGE);
  const cases = own.flatMap((exception) => exception.cases).filter((entry) => entry.list === list);
  return new Set(cases.map(caseKey));
}

/** The cases of a list that hold in this language. */
function edgeCases<T extends Partial<EncodedEdge & ModelEdge>>(list: string, cases: T[]): T[] {
  const skipped = excepted(list);
  return cases.filter((entry) => !skipped.has(caseKey(entry)));
}

/** A `value` column as a JavaScript value. A float JSON cannot carry is its text there. */
function typed(dataType: string, value: unknown): unknown {
  if (Array.isArray(value)) {
    return value.map((item) => typed(dataType.slice(0, -2), item));
  }
  const float = ["float", "double"].includes(dataType.toLowerCase());
  return float && typeof value === "string" ? Number(value) : value;
}

/** A `value_text` column as the number or array a JavaScript caller would pass. */
function readValueText(text: string): unknown {
  const quoted = text.replace(/-?Infinity|NaN/g, '"$&"');
  return JSON.parse(quoted, (_key, value: unknown) =>
    typeof value === "string" ? Number(value) : value,
  );
}

function checkRefused(entry: RefusedEdge): void {
  expect(() => decodeValue(entry.data_type, entry.text)).toThrow(RoISValueError);
}

function checkDecoded(entry: DecodedEdge): void {
  expect(decodeValue(entry.data_type, entry.text)).toEqual(typed(entry.data_type, entry.value));
}

function checkEncoded(entry: EncodedEdge): void {
  expect(encodeValue(entry.data_type, readValueText(entry.value_text))).toBe(entry.text);
}

function checkModel(entry: ModelEdge): void {
  expect(wireSchema(entry).safeParse(entry.body).success).toBe(!entry.refused);
}

function checkCondition(entry: ConditionVector): void {
  expect(BUILDERS[entry.builder]?.(...(entry.args as never[]))).toBe(entry.expected);
}

const bitsView = new DataView(new ArrayBuffer(8));

function fromBits(bits: string): number {
  bitsView.setBigUint64(0, BigInt(`0x${bits}`));
  return bitsView.getFloat64(0);
}

function toBits(value: number): string {
  bitsView.setFloat64(0, value);
  return bitsView.getBigUint64(0).toString(16).padStart(16, "0");
}

// The vectors name the Python builders, because the Python package is where types start.
const BUILDERS: Record<string, (...args: never[]) => string> = {
  quote,
  eq,
  like,
  all_of: allOf,
  component_ref: componentRef,
  component_type: componentType,
  component_type_urn: componentTypeUrn,
};

/** The catalog schema of a recorded body. */
function wireSchema(entry: Pick<WireEntry, "kind" | "method">) {
  if (entry.kind === "notification") {
    return RoISNotificationSchemas[entry.method as RoISNotification].params;
  }
  return RoISMethodSchemas[entry.method as RoISMethod][entry.kind];
}

describe("Wire fixture", () => {
  it.each(WIRE.map((entry, index) => [`${index} ${entry.kind} ${entry.method}`, entry] as const))(
    "%s round trips",
    (_name, entry) => {
      expect(wireSchema(entry).parse(entry.body)).toEqual(entry.body);
    },
  );

  it.each(["params", "result"])("records the %s of every method", (kind) => {
    const recorded = new Set(WIRE.filter((e) => e.kind === kind).map((e) => e.method));
    expect(recorded).toEqual(new Set(Object.values(RoISMethods)));
  });

  it("records every notification", () => {
    const recorded = new Set(WIRE.filter((e) => e.kind === "notification").map((e) => e.method));
    expect(recorded).toEqual(new Set(Object.values(RoISNotifications)));
  });

  it("execute params hold a command and a group", () => {
    const [entry] = WIRE.filter((e) => e.kind === "params" && e.method === RoISMethods.Execute);
    const params = RoISMethodSchemas[RoISMethods.Execute].params.parse(entry?.body);
    const [command, group] = params.command_unit_list;
    expect(CommandUnitSchema.safeParse(command).success).toBe(true);
    expect(ConcurrentCommandsSchema.safeParse(group).success).toBe(true);
  });
});

describe("Condition vectors", () => {
  it.each(CONDITIONS.map((vector) => [vector.builder, vector.expected, vector] as const))(
    "%s gives %j",
    (_builder, _expected, vector) => {
      checkCondition(vector);
    },
  );

  it("cover every builder", () => {
    expect(new Set(CONDITIONS.map((v) => v.builder))).toEqual(new Set(Object.keys(BUILDERS)));
  });
});

describe("Value vectors", () => {
  const cases = VALUES.map((vector) => [vector.data_type, vector.text, vector] as const);

  it.each(cases)("%s encodes to %j", (_dataType, _text, vector) => {
    expect(encodeValue(vector.data_type, vector.value)).toBe(vector.text);
  });

  it.each(cases)("%s decodes %j", (_dataType, _text, vector) => {
    expect(decodeValue(vector.data_type, vector.text)).toEqual(vector.value);
  });

  it("cover every type family", () => {
    const names = new Set(VALUES.map((v) => v.data_type.replace(/\[\]$/, "").toLowerCase()));
    for (const name of [
      "int",
      "integer",
      "long",
      "short",
      "float",
      "double",
      "bool",
      "boolean",
      "component_status",
      "string",
      "roisidentifier",
      "datetime",
    ]) {
      expect(names).toContain(name);
    }
  });
});

describe("Value edges", () => {
  const refused = edgeCases("refused", EDGES.refused);
  const decoded = edgeCases("decoded", EDGES.decoded);
  const encoded = edgeCases("encoded", EDGES.encoded);
  const references = EDGES.exceptions.flatMap((exception) => exception.cases);

  it.each(refused.map((entry) => [entry.data_type, entry.text, entry] as const))(
    "%s refuses %j",
    (_dataType, _text, entry) => {
      checkRefused(entry);
    },
  );

  it.each(decoded.map((entry) => [entry.data_type, entry.text, entry] as const))(
    "%s decodes %j",
    (_dataType, _text, entry) => {
      checkDecoded(entry);
    },
  );

  it.each(encoded.map((entry) => [entry.data_type, entry.value_text, entry] as const))(
    "%s encodes %j",
    (_dataType, _valueText, entry) => {
      checkEncoded(entry);
    },
  );

  it.each(edgeCases("models", EDGES.models).map((entry) => [entry.name, entry] as const))(
    "%s",
    (_name, entry) => {
      checkModel(entry);
    },
  );

  it.each(edgeCases("conditions", EDGES.conditions).map((entry) => [entry.name, entry] as const))(
    "%s",
    (_name, entry) => {
      checkCondition(entry);
    },
  );

  it.each(EDGES.doubles.map((entry) => [entry.text, entry] as const))(
    "double round trips %s",
    (text, entry) => {
      expect(encodeValue("double", fromBits(entry.bits))).toBe(text);
      expect(toBits(decodeValue("double", text) as number)).toBe(entry.bits);
    },
  );

  it.each(references.map((entry) => [entry.list, caseKey(entry)] as const))(
    "exception names a case of %s: %s",
    (list, key) => {
      expect((EDGES[list] as Partial<EncodedEdge & ModelEdge>[]).map(caseKey)).toContain(key);
    },
  );

  // A difference that went away must leave the file, or it would hide a regression.
  describe("exceptions are still differences", () => {
    function stale<T extends Partial<EncodedEdge & ModelEdge>>(list: string, cases: T[]) {
      const skipped = excepted(list);
      return cases
        .filter((entry) => skipped.has(caseKey(entry)))
        .map((entry) => [caseKey(entry), entry] as const);
    }

    it.each(stale("refused", EDGES.refused))("refused %s", (_key, entry) => {
      expect(() => {
        checkRefused(entry);
      }).toThrow();
    });

    it.each(stale("decoded", EDGES.decoded))("decoded %s", (_key, entry) => {
      expect(() => {
        checkDecoded(entry);
      }).toThrow();
    });

    it.each(stale("encoded", EDGES.encoded))("encoded %s", (_key, entry) => {
      expect(() => {
        checkEncoded(entry);
      }).toThrow();
    });

    it.each(stale("models", EDGES.models))("model %s", (_key, entry) => {
      expect(() => {
        checkModel(entry);
      }).toThrow();
    });

    it.each(stale("conditions", EDGES.conditions))("condition %s", (_key, entry) => {
      expect(() => {
        checkCondition(entry);
      }).toThrow();
    });
  });
});
