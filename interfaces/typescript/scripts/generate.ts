/**
 * Generate TypeScript source files from JSON Schema.
 *
 * Reads `interfaces/schema/manifest.json` + `interfaces/schema/*.schema.json`
 * and emits one `.ts` file per module into `src/`.
 *
 * Each generated file exports:
 *   - A zod schema (e.g. `ResultSchema`)
 *   - An inferred type (e.g. `type Result = z.infer<typeof ResultSchema>`)
 *
 * The `BusAdapter` interface and error classes are NOT generated here —
 * they are hand-written in `src/bus.ts` because JSON Schema cannot represent
 * behavioral interfaces.
 *
 * Usage:
 *   npx tsx scripts/generate.ts
 *   OPENROIS_SCHEMA_DIR=/path/to/schema npx tsx scripts/generate.ts
 */

import * as fs from "node:fs";
import * as path from "node:path";
import { fileURLToPath } from "node:url";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface JsonSchema {
  $defs?: Record<string, JsonSchema>;
  $ref?: string;
  type?: string;
  enum?: (string | number)[];
  title?: string;
  description?: string;
  default?: unknown;
  properties?: Record<string, JsonSchema>;
  required?: string[];
  items?: JsonSchema;
  anyOf?: JsonSchema[];
  additionalProperties?: boolean;
  [key: string]: unknown;
}

interface Manifest {
  version: string;
  modules: Record<string, string[]>;
}

// ---------------------------------------------------------------------------
// Paths
// ---------------------------------------------------------------------------

const SCRIPT_DIR = path.dirname(fileURLToPath(import.meta.url));
const TS_ROOT = path.resolve(SCRIPT_DIR, "..");
const SCHEMA_DIR = process.env.OPENROIS_SCHEMA_DIR
  ? path.resolve(process.env.OPENROIS_SCHEMA_DIR)
  : path.resolve(TS_ROOT, "..", "schema");
const SRC_DIR = path.resolve(TS_ROOT, "src");
const MANIFEST_PATH = path.resolve(SCHEMA_DIR, "manifest.json");

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Convert a schema title or filename to a valid TS identifier. */
function toIdentifier(title: string): string {
  return title;
}

/** Convert a schema name to a zod schema variable name (e.g. "Result" → "ResultSchema"). */
function schemaVar(name: string): string {
  return `${name}Schema`;
}

/** Extract the referenced type name from a $ref string like "#/$defs/Argument". */
function refName(ref: string): string {
  return ref.replace("#/$defs/", "");
}

/** Format a description as a JSDoc comment. */
function jsdoc(desc: string | undefined): string {
  if (!desc) return "";
  const lines = desc.split("\n");
  if (lines.length === 1) {
    return `/** ${lines[0]} */\n`;
  }
  return `/**\n${lines.map((l) => ` * ${l}`).join("\n")}\n */\n`;
}

/** Escape a string for use in a TS string literal. */
function tsStr(s: string): string {
  return `"${s.replace(/\\/g, "\\\\").replace(/"/g, '\\"')}"`;
}

/**
 * Check if a JSON Schema node is a "simple type" — a primitive (string, integer,
 * number, boolean) with no properties, anyOf, enum, or $ref. These are the
 * type aliases (RoISIdentifier, ConditionT, DateTime, Integer, etc.) that
 * PEP 695 emits as $defs entries. They should be resolved inline rather than
 * emitted as separate zod schemas.
 */
function isSimpleType(schema: JsonSchema): boolean {
  if (schema.properties || schema.anyOf || schema.enum || schema.$ref) return false;
  return ["string", "integer", "number", "boolean"].includes(schema.type ?? "");
}

// ---------------------------------------------------------------------------
// Schema → zod code generation
// ---------------------------------------------------------------------------

/**
 * Generate zod code for a JSON Schema node.
 * Returns the zod expression string (without trailing `.default()` —
 * that's applied by the caller for the property context).
 */
function genZod(schema: JsonSchema, defs: Record<string, JsonSchema>, indent = ""): string {
  // $ref → resolve simple types inline, reference complex types by variable
  if (schema.$ref) {
    const name = refName(schema.$ref);
    const defSchema = defs[name];
    // If the referenced def is a simple type (primitive alias), resolve inline
    if (defSchema && isSimpleType(defSchema)) {
      return genZod(defSchema, defs, indent);
    }
    // Complex type — reference the schema variable
    return schemaVar(name);
  }

  // anyOf → z.union
  if (schema.anyOf) {
    const parts = schema.anyOf.map((s) => genZod(s, defs, indent));
    // Special case: anyOf [X, {type: "null"}] → X.nullish() or X.optional()
    if (schema.anyOf.length === 2 && schema.anyOf.some((s) => s.type === "null")) {
      const nonNull = schema.anyOf.find((s) => s.type !== "null");
      if (nonNull) {
        const inner = genZod(nonNull, defs, indent);
        return `${inner}.nullable()`;
      }
    }
    return `z.union([${parts.join(", ")}])`;
  }

  // enum → z.enum
  if (schema.enum) {
    const values = schema.enum.map((v) => tsStr(String(v))).join(", ");
    return `z.enum([${values}])`;
  }

  switch (schema.type) {
    case "string":
      return "z.string()";
    case "integer":
      return "z.number().int()";
    case "number":
      return "z.number()";
    case "boolean":
      return "z.boolean()";
    case "array":
      if (schema.items) {
        const itemZod = genZod(schema.items, defs, indent);
        return `z.array(${itemZod})`;
      }
      return "z.array(z.unknown())";
    case "object":
      return genObject(schema, defs, indent);
    case "null":
      return "z.null()";
    default:
      return "z.unknown()";
  }
}

/** Generate a z.object from a JSON Schema object definition. */
function genObject(schema: JsonSchema, defs: Record<string, JsonSchema>, indent: string): string {
  if (!schema.properties) {
    return "z.record(z.unknown())";
  }

  const required = new Set(schema.required ?? []);
  const fields: string[] = [];

  for (const [propName, propSchema] of Object.entries(schema.properties)) {
    const isRequired = required.has(propName);
    const baseZod = genZod(propSchema, defs, indent + "  ");

    // Apply default if present
    let fieldExpr: string;
    if (propSchema.default !== undefined) {
      const defaultVal = JSON.stringify(propSchema.default);
      fieldExpr = `${baseZod}.default(${defaultVal})`;
    } else if (!isRequired) {
      fieldExpr = `${baseZod}.optional()`;
    } else {
      fieldExpr = baseZod;
    }

    // Add description as inline comment
    const desc = propSchema.description;
    if (desc) {
      fields.push(`${indent}  ${propName}: ${fieldExpr}, // ${desc.replace(/\n/g, " ")}`);
    } else {
      fields.push(`${indent}  ${propName}: ${fieldExpr},`);
    }
  }

  const strictSuffix = schema.additionalProperties === false ? ".strict()" : "";
  return `z.object({\n${fields.join("\n")}\n${indent}})${strictSuffix}`;
}

/** Convert a JSON Schema node to a TS type string (for interface generation). */
function jsonSchemaToTsType(schema: JsonSchema, selfName?: string): string {
  if (schema.$ref) {
    const name = refName(schema.$ref);
    return name;
  }

  if (schema.anyOf) {
    // anyOf with null → T | null
    const parts = schema.anyOf.map((s) => jsonSchemaToTsType(s, selfName));
    return parts.join(" | ");
  }

  if (schema.enum) {
    return schema.enum.map((v) => tsStr(String(v))).join(" | ");
  }

  switch (schema.type) {
    case "string":
      return "string";
    case "integer":
    case "number":
      return "number";
    case "boolean":
      return "boolean";
    case "array":
      if (schema.items) {
        return `${jsonSchemaToTsType(schema.items, selfName)}[]`;
      }
      return "unknown[]";
    case "null":
      return "null";
    case "object":
      return "Record<string, unknown>";
    default:
      return "unknown";
  }
}

/** Collect all type names referenced by a schema (for topological sorting). */
function collectRefs(schema: JsonSchema, allDefNames: Set<string>, depth = 0): Set<string> {
  const refs = new Set<string>();
  if (depth > 20) return refs;

  if (schema.$ref) {
    const name = refName(schema.$ref);
    if (allDefNames.has(name)) refs.add(name);
    return refs;
  }

  if (schema.anyOf) {
    for (const s of schema.anyOf) {
      for (const r of collectRefs(s, allDefNames, depth + 1)) refs.add(r);
    }
  }

  if (schema.items) {
    for (const r of collectRefs(schema.items, allDefNames, depth + 1)) refs.add(r);
  }

  if (schema.properties) {
    for (const prop of Object.values(schema.properties)) {
      for (const r of collectRefs(prop, allDefNames, depth + 1)) refs.add(r);
    }
  }

  return refs;
}

/** Topologically sort $defs so that referenced types come before referencing types. */
function topoSortDefs(defs: Record<string, JsonSchema>): string[] {
  const allDefNames = new Set(Object.keys(defs));
  const deps: Record<string, Set<string>> = {};
  for (const [name, schema] of Object.entries(defs)) {
    deps[name] = collectRefs(schema, allDefNames);
    // Remove self-references (handled by z.lazy)
    deps[name].delete(name);
  }

  const sorted: string[] = [];
  const visited = new Set<string>();
  const visiting = new Set<string>();

  function visit(name: string): void {
    if (visited.has(name)) return;
    if (visiting.has(name)) return; // Circular — will be handled by z.lazy
    visiting.add(name);
    for (const dep of deps[name] ?? []) {
      visit(dep);
    }
    visiting.delete(name);
    visited.add(name);
    sorted.push(name);
  }

  for (const name of Object.keys(defs)) {
    visit(name);
  }

  return sorted;
}

/** Generate the $defs section: local zod schemas for referenced types. */
function genDefs(defs: Record<string, JsonSchema> | undefined, indent = ""): string {
  if (!defs || Object.keys(defs).length === 0) return "";

  const sortedNames = topoSortDefs(defs);
  const lines: string[] = [];

  for (const name of sortedNames) {
    const defSchema = defs[name];

    // Skip simple-type $defs (primitive aliases like RoISIdentifier, Integer).
    // These are resolved inline by genZod() and don't need separate schemas.
    if (isSimpleType(defSchema)) continue;

    const varName = schemaVar(name);
    const desc = defSchema.description;
    if (desc) {
      lines.push(`${jsdoc(desc)}`);
    }

    // Handle recursive refs: if a $def references itself, use z.lazy
    const isRecursive = isSelfReferencing(name, defSchema);
    if (isRecursive) {
      const innerZod = genZod(defSchema, { ...defs }, indent + "  ");
      // For recursive types, use z.lazy with an explicit type annotation
      // and define the type as an interface to break the circular reference
      lines.push(`export interface ${name} {`);
      // Generate the interface fields from the schema properties
      const required = new Set(defSchema.required ?? []);
      if (defSchema.properties) {
        for (const [propName, propSchema] of Object.entries(defSchema.properties)) {
          const isRequired = required.has(propName);
          const tsType = jsonSchemaToTsType(propSchema, name);
          const optional = isRequired ? "" : "?";
          lines.push(`${indent}  ${propName}${optional}: ${tsType};`);
        }
      }
      lines.push(`}`);
      lines.push(`export const ${varName}: z.ZodType<any> = z.lazy(() => ${innerZod});`);
      // Don't emit `export type` — the interface already defines it above
    } else {
      const zodExpr = genZod(defSchema, defs, indent);
      lines.push(`export const ${varName} = ${zodExpr};`);
      lines.push(`export type ${name} = z.infer<typeof ${varName}>;`);
    }
    lines.push("");
  }

  return lines.join("\n");
}

/** Check if a schema definition references itself (directly or transitively). */
function isSelfReferencing(name: string, schema: JsonSchema, depth = 0): boolean {
  if (depth > 10) return false; // Prevent infinite recursion

  if (schema.$ref) {
    return refName(schema.$ref) === name;
  }

  if (schema.anyOf) {
    return schema.anyOf.some((s) => isSelfReferencing(name, s, depth + 1));
  }

  if (schema.items) {
    return isSelfReferencing(name, schema.items, depth + 1);
  }

  if (schema.properties) {
    return Object.values(schema.properties).some((p) => isSelfReferencing(name, p, depth + 1));
  }

  return false;
}

// ---------------------------------------------------------------------------
// File generation
// ---------------------------------------------------------------------------

/** Generate a single TS module file from one or more schema files. */
function generateModule(
  moduleName: string,
  schemaFiles: string[],
): string {
  const parts: string[] = [];

  // Header
  parts.push(`// GENERATED FROM interfaces/schema — DO NOT EDIT`);
  parts.push(`// Source: ${schemaFiles.join(", ")}`);
  parts.push(`// Generator: scripts/generate.ts`);
  parts.push("");
  parts.push(`import { z } from "zod";`);
  parts.push("");

  // HRI module gets semantic type aliases (matching Python hri.py)
  if (moduleName === "hri") {
    parts.push("// ─── Semantic type aliases (from RoIS_HRI.idl) ──────────────────");
    parts.push("");
    parts.push("/** Unique identifier for a component, sub-engine, or other RoIS entity. */");
    parts.push("export type RoISIdentifier = string;");
    parts.push("/** Ordered list of RoIS identifiers. */");
    parts.push("export type RoISIdentifierList = RoISIdentifier[];");
    parts.push("/** ISO 19143 filter expression used by search(), query(), subscribe(). */");
    parts.push("export type ConditionT = string;");
    parts.push("/** XML profile document describing an HRI Engine's capabilities. */");
    parts.push("export type HRIEngineProfile = string;");
    parts.push("/** ISO 8601 datetime string. */");
    parts.push("export type DateTime = string;");
    parts.push("/**");
    parts.push(" * IDL `typedef long Integer` — 32-bit signed integer.");
    parts.push(" *");
    parts.push(" * Note: The zod schema validates that the value is an integer but does not");
    parts.push(" * enforce the 32-bit range (±2^31). Values outside this range will pass");
    parts.push(" * TypeScript validation but may overflow in C# consumers (where `int` is");
    parts.push(" * 32-bit). This is a known limitation to be addressed in a future release.");
    parts.push(" */");
    parts.push("export type Integer = number;");
    parts.push("/** Positional or measurement data from the RoLo Architecture module. */");
    parts.push("export type RoLoData = string;");
    // ResultList, ParameterList are not used as field types in any hri-module
    // model, so they don't appear in $defs — keep them as hardcoded aliases.
    parts.push("/** Ordered list of Result values. */");
    parts.push("export type ResultList = Result[];");
    parts.push("/** Ordered list of Parameter values. */");
    parts.push("export type ParameterList = Parameter[];");
    // ArgumentList and CommandUnitSequenceItem ARE used as field types in
    // hri-module models, so they appear in $defs and are auto-generated as
    // zod schemas + inferred types below. Don't hardcode them here.
    parts.push("");
  }

  // Common module gets numeric type aliases
  if (moduleName === "common") {
    parts.push("// ─── Numeric type aliases (from RoIS_Common.idl) ────────────────");
    parts.push("");
    parts.push("/** Numeric representation of ComponentStatus for wire compatibility. */");
    parts.push("export type ComponentStatusT = number;");
    parts.push("/** Numeric representation of StreamStatus for wire compatibility. */");
    parts.push("export type StreamStatusT = number;");
    parts.push("");
  }

  // Collect all $defs across all schema files in this module
  // to emit them once at the top (avoiding duplicates)
  const allDefs: Record<string, JsonSchema> = {};
  const topLevelSchemas: { name: string; schema: JsonSchema }[] = [];

  for (const file of schemaFiles) {
    const filePath = path.resolve(SCHEMA_DIR, file);
    const content = fs.readFileSync(filePath, "utf-8");
    const schema = JSON.parse(content) as JsonSchema;

    // Collect $defs
    if (schema.$defs) {
      for (const [name, defSchema] of Object.entries(schema.$defs)) {
        if (!allDefs[name]) {
          allDefs[name] = defSchema;
        }
      }
    }

    // Top-level schema name comes from the title or filename
    const name = schema.title ?? file.replace(".schema.json", "");
    topLevelSchemas.push({ name, schema });
  }

  // Emit $defs first (shared types)
  if (Object.keys(allDefs).length > 0) {
    parts.push("// ─── Shared type definitions ($defs) ─────────────────────────────");
    parts.push("");
    parts.push(genDefs(allDefs));
    parts.push("");
  }

  // Emit top-level schemas (skip any whose name is already in $defs to avoid duplicates)
  for (const { name, schema } of topLevelSchemas) {
    if (allDefs[name]) {
      continue; // Already emitted as a $def
    }

    const varName = schemaVar(name);
    const desc = schema.description;

    if (desc) {
      parts.push(jsdoc(desc));
    }

    // For top-level schemas with $defs, the $defs are already emitted above.
    // Generate the object schema without re-emitting $defs.
    const schemaForGen: JsonSchema = { ...schema, $defs: undefined };
    const zodExpr = genZod(schemaForGen, allDefs);

    parts.push(`export const ${varName} = ${zodExpr};`);
    parts.push(`export type ${name} = z.infer<typeof ${varName}>;`);
    parts.push("");
  }

  // Build the export list for the module
  const exportNames: string[] = [];
  for (const name of Object.keys(allDefs)) {
    exportNames.push(schemaVar(name), name);
  }
  for (const { name } of topLevelSchemas) {
    exportNames.push(schemaVar(name), name);
  }

  return parts.join("\n");
}

/** Write a file, creating parent directories as needed. */
function writeFile(filePath: string, content: string): void {
  fs.mkdirSync(path.dirname(filePath), { recursive: true });
  fs.writeFileSync(filePath, content);
}

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------

function main(): void {
  // Read manifest
  const manifestContent = fs.readFileSync(MANIFEST_PATH, "utf-8");
  const manifest = JSON.parse(manifestContent) as Manifest;

  console.log(`Schema dir: ${SCHEMA_DIR}`);
  console.log(`Output dir:  ${SRC_DIR}`);
  console.log(`Manifest:    ${MANIFEST_PATH}`);
  console.log("");

  // Generate each module
  for (const [moduleName, schemaFiles] of Object.entries(manifest.modules)) {
    // Skip bus module — it's hand-written (but we generate the data models part)
    // Actually, bus data models ARE generated; the BusAdapter interface is hand-written
    // and merged in src/bus.ts. So we generate bus data models to a separate file.

    if (moduleName === "bus") {
      // Generate bus data models to src/generated/bus-models.ts
      const output = generateModule(moduleName, schemaFiles);
      const outPath = path.resolve(SRC_DIR, "generated", "bus-models.ts");
      writeFile(outPath, output);
      console.log(`  generated/bus-models.ts (${schemaFiles.length} schemas)`);
      continue;
    }

    const output = generateModule(moduleName, schemaFiles);

    // Determine output path
    const outPath = path.resolve(SRC_DIR, `${moduleName}.ts`);
    writeFile(outPath, output);
    console.log(`  ${moduleName}.ts (${schemaFiles.length} schemas)`);
  }

  console.log("\nDone. BusAdapter interface is hand-written in src/bus.ts.");
}

main();