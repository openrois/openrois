/**
 * The filter language of every `condition` parameter.
 *
 * Hand-written, not generated: JSON Schema describes data, not a parser. This
 * module mirrors the Python module `openrois.interfaces.condition`, so an engine
 * written in either language reads conditions the same way.
 *
 * RoIS types a condition as `Condition_t`, a string that carries an ISO 19143
 * filter expression. OpenRoIS keeps it a string and writes the filter in a subset
 * of CQL2-Text, the text encoding of the OGC Common Query Language
 * (OGC 21-065r2):
 *
 *     condition   = [ comparison *( "AND" comparison ) ]
 *     comparison  = property ( "=" / "LIKE" ) literal
 *     property    = identifier / DQUOTE identifier DQUOTE
 *     literal     = "'" *( character / "''" ) "'"
 *
 *   - An empty condition is no filter.
 *   - Keywords are accepted in any case and written in upper case.
 *   - Inside a literal, a single quote is written twice: `'it''s'`.
 *   - In a LIKE pattern, `%` matches any run of characters, `_` matches one
 *     character, and a backslash makes the next character literal. Matching is
 *     case-sensitive.
 *   - OR, NOT, parentheses and the other CQL2 operators are outside the subset.
 *
 * Properties a condition may use:
 *
 *   - `component_ref`: the fully qualified ref of a component, `engine_id/ref`.
 *   - `component_type`: the URN of the component's profile identifier, for
 *     example `urn:x-rois:def:component:OMG::PersonDetection`.
 *
 * Both select components, in search, bind_any, get_profile, query and subscribe.
 * The result filters of get_error_detail, get_command_result and get_event_detail
 * take an empty condition for now. An engine answers a condition it cannot parse,
 * or one that uses a property the method does not support, with BAD_PARAMETER.
 *
 * Section 17.4 of docs/rois-reference.md describes the subset.
 */

import type { RoISIdentifierType } from "./profiles";

/** The property that selects a component by its fully qualified ref. */
export const COMPONENT_REF = "component_ref";

/** The property that selects components by the URN of their profile identifier. */
export const COMPONENT_TYPE = "component_type";

/** The properties a component selection may use. */
export const SELECTION_PROPERTIES: ReadonlySet<string> = new Set([COMPONENT_REF, COMPONENT_TYPE]);

/** A comparison operator of the subset. */
export type ConditionOperator = "=" | "LIKE";

/** Raised when a condition is not valid in the OpenRoIS subset of CQL2-Text. */
export class ConditionError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "ConditionError";
  }
}

/** One comparison of a property with a literal. */
export class Comparison {
  /** The property name. */
  readonly property: string;
  /** `=` or `LIKE`. */
  readonly operator: ConditionOperator;
  /** The literal, or the LIKE pattern, without its quotes. */
  readonly value: string;

  constructor(property: string, operator: ConditionOperator, value: string) {
    this.property = property;
    this.operator = operator;
    this.value = value;
  }

  /** Whether the property values satisfy this comparison. A missing property never matches. */
  matches(properties: Readonly<Record<string, string>>): boolean {
    const actual = properties[this.property];
    if (actual === undefined) {
      return false;
    }
    if (this.operator === "=") {
      return actual === this.value;
    }
    return likeRegExp(this.value).test(actual);
  }

  toString(): string {
    return `${this.property} ${this.operator} ${quote(this.value)}`;
  }
}

/** A parsed condition: every comparison must hold. */
export class Condition {
  /** The comparisons joined by AND. Empty means no filter. */
  readonly comparisons: readonly Comparison[];

  constructor(comparisons: readonly Comparison[] = []) {
    this.comparisons = comparisons;
  }

  /** Whether the property values satisfy every comparison. */
  matches(properties: Readonly<Record<string, string>>): boolean {
    return this.comparisons.every((comparison) => comparison.matches(properties));
  }

  /**
   * The values the condition requires `property` to equal. An engine uses them
   * to go straight to the components a condition names.
   */
  equalValues(property: string): Set<string> {
    return new Set(
      this.comparisons
        .filter((c) => c.property === property && c.operator === "=")
        .map((c) => c.value),
    );
  }

  toString(): string {
    return this.comparisons.map((comparison) => comparison.toString()).join(" AND ");
  }
}

// ---------------------------------------------------------------------------
// Parsing
// ---------------------------------------------------------------------------

type TokenKind = "string" | "quoted" | "word" | "equals" | "other";

interface Token {
  kind: TokenKind;
  text: string;
  position: number;
}

const TOKEN_PATTERN =
  /\s*(?:(?<string>'(?:[^']|'')*')|(?<quoted>"[A-Za-z_:][A-Za-z0-9_.:]*")|(?<word>[A-Za-z_:][A-Za-z0-9_.:]*)|(?<equals>=)|(?<other>\S))/y;

const KEYWORDS: ReadonlySet<string> = new Set(["AND", "LIKE", "OR", "NOT"]);

/** Split a condition into tokens with their positions. */
function tokenize(text: string): Token[] {
  const tokens: Token[] = [];
  let position = 0;
  while (position < text.length && text.slice(position).trim() !== "") {
    TOKEN_PATTERN.lastIndex = position;
    const match = TOKEN_PATTERN.exec(text);
    const groups = match?.groups;
    if (!match || !groups) {
      throw new ConditionError(`Cannot read the condition at position ${position}.`);
    }
    const kind = (Object.keys(groups) as TokenKind[]).find((name) => groups[name] !== undefined);
    if (!kind) {
      throw new ConditionError(`Cannot read the condition at position ${position}.`);
    }
    const value = groups[kind];
    const start = TOKEN_PATTERN.lastIndex - value.length;
    if (kind === "other") {
      if (value === "'") {
        throw new ConditionError(`Unterminated string literal at position ${start}.`);
      }
      throw new ConditionError(`Unexpected character ${JSON.stringify(value)} at position ${start}.`);
    }
    tokens.push({ kind, text: value, position: start });
    position = TOKEN_PATTERN.lastIndex;
  }
  return tokens;
}

/**
 * Parse a condition in the OpenRoIS subset of CQL2-Text.
 *
 * @param text - The condition. Empty or blank means no filter.
 * @param allowedProperties - The properties the calling method supports.
 * @throws ConditionError if the text is outside the subset, or names a property
 *   that is not in `allowedProperties`.
 */
export function parseCondition(
  text: string,
  allowedProperties: ReadonlySet<string> = SELECTION_PROPERTIES,
): Condition {
  const tokens = tokenize(text);
  const comparisons: Comparison[] = [];
  let index = 0;
  while (index < tokens.length) {
    if (comparisons.length > 0) {
      const joiner = tokens[index];
      const keyword = joiner.text.toUpperCase();
      if (joiner.kind === "word" && (keyword === "OR" || keyword === "NOT")) {
        throw new ConditionError(
          `${keyword} at position ${joiner.position} is outside the OpenRoIS subset. ` +
            "Only AND joins comparisons.",
        );
      }
      if (joiner.kind !== "word" || keyword !== "AND") {
        throw new ConditionError(
          `Expected AND at position ${joiner.position}. Only AND joins comparisons.`,
        );
      }
      index += 1;
    }
    if (index + 3 > tokens.length) {
      throw new ConditionError("A comparison needs a property, an operator and a literal.");
    }
    const [property, operator, literal] = tokens.slice(index, index + 3);

    let name: string;
    if (property.kind === "quoted") {
      name = property.text.slice(1, -1);
    } else if (property.kind === "word" && !KEYWORDS.has(property.text.toUpperCase())) {
      name = property.text;
    } else {
      throw new ConditionError(`Expected a property name at position ${property.position}.`);
    }
    if (!allowedProperties.has(name)) {
      const supported = [...allowedProperties].sort().join(", ") || "none";
      throw new ConditionError(`Unsupported property '${name}'. Supported: ${supported}.`);
    }

    let op: ConditionOperator;
    if (operator.kind === "equals") {
      op = "=";
    } else if (operator.kind === "word" && operator.text.toUpperCase() === "LIKE") {
      op = "LIKE";
    } else {
      throw new ConditionError(`Expected = or LIKE at position ${operator.position}.`);
    }

    if (literal.kind !== "string") {
      throw new ConditionError(`Expected a quoted literal at position ${literal.position}.`);
    }
    const value = literal.text.slice(1, -1).replace(/''/g, "'");
    if (op === "LIKE") {
      likeRegExp(value);
    }
    comparisons.push(new Comparison(name, op, value));
    index += 3;
  }
  return new Condition(comparisons);
}

/** Translate a LIKE pattern into an anchored regular expression. */
function likeRegExp(pattern: string): RegExp {
  let source = "";
  let escaped = false;
  for (const character of pattern) {
    if (escaped) {
      source += escapeRegExp(character);
      escaped = false;
    } else if (character === "\\") {
      escaped = true;
    } else if (character === "%") {
      source += ".*";
    } else if (character === "_") {
      source += ".";
    } else {
      source += escapeRegExp(character);
    }
  }
  if (escaped) {
    throw new ConditionError("A LIKE pattern cannot end with an escape character.");
  }
  return new RegExp(`^${source}$`, "su");
}

function escapeRegExp(character: string): string {
  return character.replace(/[.*+?^${}()|[\]\\/]/g, "\\$&");
}

// ---------------------------------------------------------------------------
// Building
// ---------------------------------------------------------------------------

/** Write `value` as a CQL2 string literal, doubling any single quote. */
export function quote(value: string): string {
  return `'${value.replace(/'/g, "''")}'`;
}

/** Build `property = 'value'`. */
export function eq(property: string, value: string): string {
  return new Comparison(property, "=", value).toString();
}

/** Build `property LIKE 'pattern'`. The pattern keeps its wildcards. */
export function like(property: string, pattern: string): string {
  return new Comparison(property, "LIKE", pattern).toString();
}

/** Join conditions with AND, skipping empty ones. */
export function allOf(...conditions: string[]): string {
  return conditions.filter((condition) => condition.trim() !== "").join(" AND ");
}

/** Select the one component with this fully qualified ref, for example `reachy_real/head`. */
export function componentRef(ref: string): string {
  return eq(COMPONENT_REF, ref);
}

/**
 * The `component_type` value of a component profile identifier.
 *
 * `{ authority: "OMG", code: "PersonDetection" }` gives
 * `urn:x-rois:def:component:OMG::PersonDetection`, the form the specification's
 * component profiles use.
 */
export function componentTypeUrn(identifier: Pick<RoISIdentifierType, "authority" | "code">): string {
  return `urn:x-rois:def:component:${identifier.authority}::${identifier.code}`;
}

/** Select every component of a type, for example `{ authority: "OMG", code: "Navigation" }`. */
export function componentType(identifier: Pick<RoISIdentifierType, "authority" | "code">): string {
  return eq(COMPONENT_TYPE, componentTypeUrn(identifier));
}
