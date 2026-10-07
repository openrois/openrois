/**
 * Builders for the `condition` strings of the RoIS methods.
 *
 * Every condition is a string in the OpenRoIS subset of CQL2-Text: comparisons
 * with `=` or `LIKE`, joined by `AND`, over the properties `component_ref` and
 * `component_type`. An empty string is no filter. Section 17.4 of
 * docs/rois-reference.md defines the subset, and the Python module
 * `openrois.interfaces.condition` parses it.
 *
 * The builders quote every value, so a ref or a URN never has to be escaped by
 * hand:
 *
 *   componentRef("reachy_real/head")
 *     → component_ref = 'reachy_real/head'
 *   allOf(like(COMPONENT_REF, "reachy_real/%"), componentType({ authority: "OMG", code: "Reaction" }))
 *     → component_ref LIKE 'reachy_real/%' AND component_type = 'urn:x-rois:def:component:OMG::Reaction'
 */

/** The property that selects a component by its fully qualified ref, `engine_id/ref`. */
export const COMPONENT_REF = "component_ref";

/** The property that selects components by the URN of their profile identifier. */
export const COMPONENT_TYPE = "component_type";

/**
 * Write `value` as a CQL2 string literal. A single quote inside the value is
 * written twice, as CQL2-Text requires.
 */
export function quote(value: string): string {
  return `'${value.replace(/'/g, "''")}'`;
}

/** Build `property = 'value'`. */
export function eq(property: string, value: string): string {
  return `${property} = ${quote(value)}`;
}

/**
 * Build `property LIKE 'pattern'`. In the pattern, `%` matches any run of
 * characters, `_` matches one character, and a backslash makes the next
 * character literal.
 */
export function like(property: string, pattern: string): string {
  return `${property} LIKE ${quote(pattern)}`;
}

/** Join conditions with AND, skipping empty ones. */
export function allOf(...conditions: string[]): string {
  return conditions.filter((condition) => condition.trim() !== "").join(" AND ");
}

/** Select the one component with this fully qualified ref, for example `reachy_real/head`. */
export function componentRef(ref: string): string {
  return eq(COMPONENT_REF, ref);
}

/** The parts of a component profile identifier that name the component type. */
export interface ComponentTypeIdentifier {
  /** The naming authority, for example `OMG`. */
  authority: string;
  /** The type code, for example `PersonDetection`. */
  code: string;
}

/**
 * The `component_type` value of a component profile identifier, the URN form the
 * specification's component profiles use:
 * `urn:x-rois:def:component:OMG::PersonDetection`.
 */
export function componentTypeUrn(identifier: ComponentTypeIdentifier): string {
  return `urn:x-rois:def:component:${identifier.authority}::${identifier.code}`;
}

/** Select every component of this type, for example `{ authority: "OMG", code: "Navigation" }`. */
export function componentType(identifier: ComponentTypeIdentifier): string {
  return eq(COMPONENT_TYPE, componentTypeUrn(identifier));
}
