import { decodeValue, encodeValue, type Result } from "@openrois/interfaces";

/** Whether a data type holds a list, such as `string[]`. */
export function isArrayType(dataType: string): boolean {
  return dataType.endsWith("[]");
}

/** The kind of input a value of this type takes. */
export function inputKind(dataType: string): "boolean" | "number" | "list" | "text" {
  const base = dataType.toLowerCase();
  if (isArrayType(base)) return "list";
  if (base === "bool" || base === "boolean") return "boolean";
  if (["int", "integer", "long", "short", "float", "double"].includes(base)) return "number";
  return "text";
}

/**
 * The wire form of what a user typed for a value of `dataType`.
 *
 * A list takes one item per line, and every other type takes its own text. Throws a
 * RoISValueError, with a message for the form, when the text does not fit the type.
 */
export function toWire(dataType: string, input: string): string {
  if (!isArrayType(dataType)) {
    return encodeValue(dataType, input.trim());
  }
  const itemType = dataType.slice(0, -2);
  const items = input
    .split("\n")
    .map((line) => line.trim())
    .filter((line) => line !== "")
    .map((line) => decodeValue(itemType, line));
  return encodeValue(dataType, items);
}

/** The form text of a value that travels as `wire`: one item per line for a list. */
export function fromWire(dataType: string, wire: string | null | undefined): string {
  if (wire === null || wire === undefined || wire === "") return "";
  try {
    const value = decodeValue(dataType, wire);
    return Array.isArray(value) ? value.map(String).join("\n") : String(value);
  } catch {
    return wire;
  }
}

/** A result value for display: its typed form when it decodes, the raw text otherwise. */
export function showResult(result: Result): string {
  try {
    const value = decodeValue(result.data_type_ref, result.value);
    return Array.isArray(value) ? JSON.stringify(value) : String(value);
  } catch {
    return result.value;
  }
}
