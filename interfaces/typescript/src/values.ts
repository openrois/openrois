/**
 * How a typed RoIS value travels as a string.
 *
 * The IDL types the value of a Result, a Parameter and an Argument as `any` and names its
 * type in `data_type_ref`. OpenRoIS carries every value as a string (`Result.value`,
 * `Parameter.value`, `Argument.value`) and writes it by the rules below, so an engine can
 * check a value against its profile and a client can read it as a typed value.
 *
 * - `int`, `integer`, `long`, `short`: a `number`, written in decimal (`42`).
 * - `float`, `double`: a `number`, written with a fraction or an exponent (`1.5`, `2.0`).
 * - `bool`, `boolean`: a `boolean`, written `true` or `false`.
 * - `Component_Status`: a `ComponentStatus`, written as its name (`READY`).
 * - `string`, `RoISIdentifier`, `DateTime` and any other type: a `string`, written as the
 *   text itself. A `Date` is written in ISO 8601.
 * - `<type>[]`: an array of `<type>`, written as a JSON array.
 *
 * Type names are matched without regard to case, so `String[]` and `string[]` are the same
 * type. An array holds its items as JSON values: numbers for the numeric types, `true` and
 * `false` for the boolean types, and strings for every other type, for example
 * `["kitchen", "hall"]` for `string[]`.
 *
 * This module mirrors the Python `openrois.interfaces.values` module and writes the same
 * text, down to the space after each comma of an array. A JavaScript number cannot hold every
 * integer, so where Python keeps the integer, this module refuses one outside the safe range of
 * `Number` instead of rounding it.
 *
 * This module also differs from Python on text that no writer produces. A number is read in
 * ASCII digits only, where Python also reads other Unicode digits. A float text is trimmed by
 * `String.prototype.trim`, which removes U+FEFF and keeps U+0085, the opposite of Python. The
 * item -0 of a float array reads as negative zero, where Python reads it as an integer and gives
 * positive zero.
 *
 * Section 17.6 of docs/rois-reference.md describes the forms.
 */

import { ComponentStatusSchema } from "./common.js";

/** A value in its typed form, as `decodeValue` returns it. */
export type RoISValue = number | boolean | string | RoISValue[];

/** Raised when a value or its string form does not fit its type. */
export class RoISValueError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "RoISValueError";
  }
}

// Type names by the value they carry, lowercased.
const INTEGER: ReadonlySet<string> = new Set(["int", "integer", "long", "short"]);
const FLOAT: ReadonlySet<string> = new Set(["float", "double"]);
const BOOLEAN: ReadonlySet<string> = new Set(["bool", "boolean"]);
const STATUS = "component_status";
const TEXT: ReadonlySet<string> = new Set(["string", "roisidentifier", "datetime"]);

const ARRAY_SUFFIX = "[]";

const INTEGER_TEXT = /^-?[0-9]+$/;

// The grammar of Python's float(), because an engine accepts whatever that reads, and a
// client must not refuse a value its engine sent. Number() alone would also take "" and "0x10".
const DIGITS = "[0-9]+(?:_[0-9]+)*";
const FLOAT_TEXT = new RegExp(
  `^[+-]?(?:(?:(?:${DIGITS})?\\.${DIGITS}|${DIGITS}\\.?)(?:e[+-]?${DIGITS})?|inf(?:inity)?|nan)$`,
  "i",
);

// Python writes these three bare in a JSON array, and JSON.parse refuses them. A float array
// holds no strings, so they can be quoted before parsing and restored item by item.
const NON_FINITE_TOKEN = /-?Infinity|NaN/g;
const NON_FINITE_NAMES: ReadonlySet<string> = new Set(["NaN", "Infinity", "-Infinity"]);

/**
 * Write a value of the type `dataType` as its string form.
 *
 * A string is taken as the string form itself and is checked against the type. A `Date` is
 * written in ISO 8601. A value of a type this module does not know is written as JSON,
 * unless it is already a string.
 *
 * @param dataType The `data_type_ref` code, for example `int` or `string[]`.
 * @param value The value to write.
 * @returns The string form of the value.
 * @throws {RoISValueError} The value does not fit the type.
 */
export function encodeValue(dataType: string, value: unknown): string {
  const item = value instanceof Date ? isoText(value) : value;
  if (typeof item === "string") {
    decodeValue(dataType, item);
    return item;
  }
  return jsonItem(dataType, item);
}

/**
 * Read the string form of a value of the type `dataType`.
 *
 * @param dataType The `data_type_ref` code, for example `int` or `string[]`.
 * @param text The string form, as it travels in `Result.value`.
 * @returns The value: a `number`, `boolean`, `ComponentStatus`, `string`, or an array of
 *   those for an array type.
 * @throws {RoISValueError} The text is not a value of the type.
 */
export function decodeValue(dataType: string, text: string): RoISValue {
  const base = dataType.toLowerCase();
  if (base.endsWith(ARRAY_SUFFIX)) {
    return fromJson(dataType, parseArray(dataType, text));
  }
  if (INTEGER.has(base)) {
    if (!INTEGER_TEXT.test(text)) {
      throw new RoISValueError(`Not a ${dataType} value: ${show(text)}`);
    }
    return safeInteger(dataType, Number(text));
  }
  if (FLOAT.has(base)) {
    return readFloat(dataType, text);
  }
  if (BOOLEAN.has(base)) {
    if (text !== "true" && text !== "false") {
      throw new RoISValueError(`A ${dataType} value must be true or false: ${show(text)}`);
    }
    return text === "true";
  }
  if (base === STATUS && !ComponentStatusSchema.safeParse(text).success) {
    throw new RoISValueError(`Not a ${dataType} name: ${show(text)}`);
  }
  return text;
}

/** The JSON text that stands for `raw`, as one item or one scalar. */
function jsonItem(dataType: string, raw: unknown): string {
  const value = raw instanceof Date ? isoText(raw) : raw;
  const base = dataType.toLowerCase();
  if (base.endsWith(ARRAY_SUFFIX)) {
    if (!Array.isArray(value)) {
      throw new RoISValueError(`A ${dataType} value must be an array, not ${show(value)}`);
    }
    const itemType = dataType.slice(0, -ARRAY_SUFFIX.length);
    return `[${value.map((item) => jsonItem(itemType, item)).join(", ")}]`;
  }
  if (INTEGER.has(base)) {
    if (!Number.isSafeInteger(value)) {
      throw new RoISValueError(`A ${dataType} value must be a safe integer, not ${show(value)}`);
    }
    return String(value);
  }
  if (FLOAT.has(base)) {
    if (typeof value !== "number") {
      throw new RoISValueError(`A ${dataType} value must be a number, not ${show(value)}`);
    }
    return floatText(value);
  }
  if (BOOLEAN.has(base)) {
    if (typeof value !== "boolean") {
      throw new RoISValueError(`A ${dataType} value must be a boolean, not ${show(value)}`);
    }
    return String(value);
  }
  if (base === STATUS) {
    const status = ComponentStatusSchema.safeParse(value);
    if (!status.success) {
      throw new RoISValueError(`A ${dataType} value must be a status name, not ${show(value)}`);
    }
    return JSON.stringify(status.data);
  }
  if (typeof value === "string") {
    return JSON.stringify(value);
  }
  if (TEXT.has(base)) {
    throw new RoISValueError(`A ${dataType} value must be a string, not ${show(value)}`);
  }
  return jsonText(value);
}

/** The value that one JSON item of an array stands for. */
function fromJson(dataType: string, item: unknown): RoISValue {
  const base = dataType.toLowerCase();
  if (base.endsWith(ARRAY_SUFFIX)) {
    if (!Array.isArray(item)) {
      throw new RoISValueError(`A ${dataType} item must be a JSON array: ${show(item)}`);
    }
    const itemType = dataType.slice(0, -ARRAY_SUFFIX.length);
    return item.map((inner) => fromJson(itemType, inner));
  }
  if (INTEGER.has(base)) {
    if (typeof item !== "number" || !Number.isInteger(item)) {
      throw new RoISValueError(`A ${dataType} item must be a JSON integer: ${show(item)}`);
    }
    return safeInteger(dataType, item);
  }
  if (FLOAT.has(base)) {
    if (typeof item === "string" && NON_FINITE_NAMES.has(item)) {
      return Number(item);
    }
    if (typeof item !== "number") {
      throw new RoISValueError(`A ${dataType} item must be a JSON number: ${show(item)}`);
    }
    return item;
  }
  if (BOOLEAN.has(base)) {
    if (typeof item !== "boolean") {
      throw new RoISValueError(`A ${dataType} item must be true or false: ${show(item)}`);
    }
    return item;
  }
  if (typeof item !== "string") {
    throw new RoISValueError(`A ${dataType} item must be a JSON string: ${show(item)}`);
  }
  return decodeValue(dataType, item);
}

/** Parse the JSON array of an array type, before its items are checked. */
function parseArray(dataType: string, text: string): unknown[] {
  const element = dataType.toLowerCase().replace(/(?:\[\])+$/, "");
  // A valid float array holds no strings, and once parsed a token quoted below looks the same
  // as a string that was already in the text, such as a name spelled with an escape.
  if (FLOAT.has(element) && text.includes('"')) {
    throw new RoISValueError(`A ${dataType} value must be a JSON array: ${show(text)}`);
  }
  let items: unknown;
  try {
    items = JSON.parse(FLOAT.has(element) ? text.replace(NON_FINITE_TOKEN, '"$&"') : text);
  } catch {
    throw new RoISValueError(`A ${dataType} value must be a JSON array: ${show(text)}`);
  }
  // JSON.parse reads 1.0 and 1e2 as integers, and a valid integer array holds no string
  // that could contain these characters, so the raw text is what tells them apart.
  if (!Array.isArray(items) || (INTEGER.has(element) && /[.eE]/.test(text))) {
    throw new RoISValueError(`A ${dataType} value must be a JSON array: ${show(text)}`);
  }
  return items;
}

/** The number a `float` text stands for. */
function readFloat(dataType: string, text: string): number {
  const number = text.trim().toLowerCase();
  if (!FLOAT_TEXT.test(number)) {
    throw new RoISValueError(`Not a ${dataType} value: ${show(text)}`);
  }
  if (number.endsWith("nan")) {
    return Number.NaN;
  }
  if (number.endsWith("inf") || number.endsWith("infinity")) {
    return number.startsWith("-") ? -Infinity : Infinity;
  }
  return Number(number.replaceAll("_", ""));
}

/** An integer checked against the range a `number` holds exactly. */
function safeInteger(dataType: string, value: number): number {
  if (!Number.isSafeInteger(value)) {
    throw new RoISValueError(`A ${dataType} value is outside the safe integer range: ${value}`);
  }
  // Adding zero turns -0, which the text "-0" reads as, into the 0 an integer means.
  return value + 0;
}

/**
 * The text of Python's `repr` of a float.
 *
 * JavaScript finds the same shortest digits, but moves to an exponent at other points and
 * writes no fraction on a whole number. The type of a value lives only in its text here,
 * since 2 and 2.0 are one JavaScript number, so `float` must always write the fraction.
 */
function floatText(value: number): string {
  if (Number.isNaN(value)) {
    return "NaN";
  }
  if (!Number.isFinite(value)) {
    return value > 0 ? "Infinity" : "-Infinity";
  }
  if (Object.is(value, -0)) {
    return "-0.0";
  }
  const [mantissa, exponentText] = value.toExponential().split("e") as [string, string];
  const exponent = Number(exponentText);
  if (exponent < -4 || exponent >= 16) {
    const digits = String(Math.abs(exponent)).padStart(2, "0");
    return `${mantissa}e${exponent < 0 ? "-" : "+"}${digits}`;
  }
  return Number.isInteger(value) ? `${value}.0` : String(value);
}

/** The JSON text of a value of an unknown type, spaced as Python's `json.dumps` spaces it. */
function jsonText(value: unknown): string {
  if (value === null || typeof value === "boolean") {
    return String(value);
  }
  if (typeof value === "number") {
    return Number.isSafeInteger(value) ? String(value) : floatText(value);
  }
  if (typeof value === "string") {
    return JSON.stringify(value);
  }
  if (Array.isArray(value)) {
    return `[${value.map(jsonText).join(", ")}]`;
  }
  if (typeof value === "object" && Object.getPrototypeOf(value) === Object.prototype) {
    const members = Object.entries(value).map(
      ([key, member]) => `${JSON.stringify(key)}: ${jsonText(member)}`,
    );
    return `{${members.join(", ")}}`;
  }
  throw new RoISValueError(`Not a JSON value: ${show(value)}`);
}

/** The ISO 8601 form of a date. */
function isoText(value: Date): string {
  if (Number.isNaN(value.getTime())) {
    throw new RoISValueError("An invalid Date has no ISO 8601 form");
  }
  return value.toISOString();
}

/** A value as it reads in an error message. */
function show(value: unknown): string {
  return typeof value === "string" ? JSON.stringify(value) : String(value);
}
