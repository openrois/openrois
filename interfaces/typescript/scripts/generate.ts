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
 * The `ComponentContract` interface and error classes are NOT generated here.
 * They are hand-written in `src/contract.ts` because JSON Schema cannot represent
 * behavioral interfaces.
 *
 * It also reads `interfaces/schema/profiles.json` and emits the profile constants of
 * the basic components into `src/components/profiles.ts`.
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
  additionalProperties?: boolean | JsonSchema;
  propertyNames?: JsonSchema;
  [key: string]: unknown;
}

interface Manifest {
  version: string;
  modules: Record<string, string[]>;
}

interface CatalogMethod {
  method: string;
  interface: string;
  operation: string;
  params: string;
  result: string;
}

interface CatalogNotification {
  method: string;
  interface: string;
  operation: string;
  params: string;
}

interface ProfilesDocument {
  profiles: { name: string; profile: Record<string, unknown> }[];
}

interface CatalogDocument {
  methods: CatalogMethod[];
  notifications: CatalogNotification[];
  standard_command_types: string[];
  json_rpc_error_codes: { name: string; code: number }[];
  unmodelled_method_prefixes: string[];
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
const CATALOG_PATH = path.resolve(SCHEMA_DIR, "catalog.json");
const PROFILES_PATH = path.resolve(SCHEMA_DIR, "profiles.json");
const PROFILES_OUT_FILE = path.join("components", "profiles.ts");

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

/**
 * The value schema of a map: an object with no fixed properties whose
 * `additionalProperties` is a schema. Pydantic writes a `dict[str, X]` field this way.
 */
function mapValueSchema(schema: JsonSchema): JsonSchema | undefined {
  if (schema.properties) return undefined;
  const value = schema.additionalProperties;
  return typeof value === "object" ? value : undefined;
}

/** The schema nodes directly nested in `schema` that may carry a $ref. */
function childSchemas(schema: JsonSchema): JsonSchema[] {
  const children: JsonSchema[] = [...(schema.anyOf ?? [])];
  if (schema.items) children.push(schema.items);
  if (schema.properties) children.push(...Object.values(schema.properties));
  const mapValue = mapValueSchema(schema);
  if (mapValue) children.push(mapValue);
  return children;
}

/**
 * Check if a $def is resolved inline instead of being emitted as its own schema:
 * a simple type, or an array alias such as ResultList or RoISIdentifierList. An
 * array alias adds no name worth importing across modules, and inlining it keeps a
 * module from depending on whichever other module happened to mention it first.
 * The C# generator inlines the same aliases.
 */
function isInlineType(schema: JsonSchema): boolean {
  if (isSimpleType(schema)) return true;
  return schema.type === "array" && !schema.properties;
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
    // If the referenced def is an inline type (primitive or array alias), resolve inline
    if (defSchema && isInlineType(defSchema)) {
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
  // Map keys are always strings on the wire, so propertyNames adds nothing to check.
  const mapValue = mapValueSchema(schema);
  if (mapValue) {
    return `z.record(z.string(), ${genZod(mapValue, defs, indent)})`;
  }
  if (!schema.properties) {
    return "z.record(z.string(), z.unknown())";
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
  if (fields.length === 0) return `z.object({})${strictSuffix}`;
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
    case "object": {
      const mapValue = mapValueSchema(schema);
      return mapValue
        ? `Record<string, ${jsonSchemaToTsType(mapValue, selfName)}>`
        : "Record<string, unknown>";
    }
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

  for (const child of childSchemas(schema)) {
    for (const r of collectRefs(child, allDefNames, depth + 1)) refs.add(r);
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

/**
 * Generate the $defs section: local zod schemas for the types this module owns.
 * `defs` holds every $def the module's schemas mention, so references resolve.
 * Types in `imported` belong to another module and are imported, not emitted.
 */
function genDefs(defs: Record<string, JsonSchema>, imported: Set<string>, indent = ""): string {
  const sortedNames = topoSortDefs(defs).filter((name) => !imported.has(name));
  if (sortedNames.length === 0) return "";
  const lines: string[] = [];

  for (const name of sortedNames) {
    const defSchema = defs[name];

    // Skip inline $defs (primitive aliases like RoISIdentifier, array aliases like
    // ResultList). These are resolved inline by genZod() and need no schema.
    if (isInlineType(defSchema)) continue;

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

  return childSchemas(schema).some((child) => isSelfReferencing(name, child, depth + 1));
}

// ---------------------------------------------------------------------------
// File generation
// ---------------------------------------------------------------------------

/** The output file of a module, relative to `src/`. */
function moduleOutFile(moduleName: string): string {
  // The contract data models get their own file, because the ComponentContract
  // interface itself is hand-written in src/contract.ts and re-exports them.
  if (moduleName === "contract") return path.join("generated", "contract-models.ts");
  return `${moduleName}.ts`;
}

/** The import specifier that reaches `toModule` from the file of `fromModule`. */
function importSpecifier(fromModule: string, toModule: string): string {
  const fromDir = path.dirname(moduleOutFile(fromModule));
  const target = moduleOutFile(toModule).replace(/\.ts$/, "");
  const relative = path.relative(fromDir, target).split(path.sep).join("/");
  return relative.startsWith(".") ? relative : `./${relative}`;
}

/** Read and parse one schema file. */
function readSchema(file: string): JsonSchema {
  return JSON.parse(fs.readFileSync(path.resolve(SCHEMA_DIR, file), "utf-8")) as JsonSchema;
}

/** The type name a schema file defines: its title, or its file name. */
function schemaName(file: string, schema: JsonSchema): string {
  return schema.title ?? file.replace(".schema.json", "");
}

/**
 * Decide which module emits each type, so every type is defined exactly once and
 * other modules import it. A top-level schema belongs to its own module. A type
 * that only appears in $defs belongs to the first module, in manifest order, whose
 * schemas mention it.
 */
function typeOwners(manifest: Manifest): Map<string, string> {
  const owners = new Map<string, string>();
  for (const [moduleName, files] of Object.entries(manifest.modules)) {
    for (const file of files) {
      owners.set(schemaName(file, readSchema(file)), moduleName);
    }
  }
  for (const [moduleName, files] of Object.entries(manifest.modules)) {
    for (const file of files) {
      for (const [name, defSchema] of Object.entries(readSchema(file).$defs ?? {})) {
        if (!isInlineType(defSchema) && !owners.has(name)) owners.set(name, moduleName);
      }
    }
  }
  return owners;
}

/** Convert a snake_case operation name to PascalCase (e.g. "get_profile" → "GetProfile"). */
function pascalCase(name: string): string {
  return name
    .split("_")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join("");
}

/** Generate the method name constants and the method to model map from catalog.json. */
function genCatalog(catalog: CatalogDocument): string {
  const lines: string[] = [];
  lines.push("// ─── Method catalog (from catalog.json) ──────────────────────────");
  lines.push("");
  lines.push("/** JSON-RPC method names of the RoIS method catalog, keyed by operation. */");
  lines.push("export const RoISMethods = {");
  for (const m of catalog.methods) {
    lines.push(`  ${pascalCase(m.operation)}: ${tsStr(m.method)},`);
  }
  lines.push("} as const;");
  lines.push("/** A JSON-RPC method name from the RoIS method catalog. */");
  lines.push("export type RoISMethod = (typeof RoISMethods)[keyof typeof RoISMethods];");
  lines.push("");
  lines.push("/** The params and result type of every catalog method. */");
  lines.push("export interface RoISMethodMap {");
  for (const m of catalog.methods) {
    lines.push(`  ${tsStr(m.method)}: { params: ${m.params}; result: ${m.result} };`);
  }
  lines.push("}");
  lines.push("");
  lines.push("/** The params and result schema of every catalog method, for validating messages. */");
  lines.push("export const RoISMethodSchemas = {");
  for (const m of catalog.methods) {
    lines.push(
      `  ${tsStr(m.method)}: { params: ${schemaVar(m.params)}, result: ${schemaVar(m.result)} },`,
    );
  }
  lines.push("} as const;");
  lines.push("");
  lines.push("/** JSON-RPC notification names an engine sends to a service application, keyed by operation. */");
  lines.push("export const RoISNotifications = {");
  for (const n of catalog.notifications) {
    lines.push(`  ${pascalCase(n.operation)}: ${tsStr(n.method)},`);
  }
  lines.push("} as const;");
  lines.push("/** A JSON-RPC notification name an engine sends to a service application. */");
  lines.push(
    "export type RoISNotification = (typeof RoISNotifications)[keyof typeof RoISNotifications];",
  );
  lines.push("");
  lines.push("/** The params type of every notification. */");
  lines.push("export interface RoISNotificationMap {");
  for (const n of catalog.notifications) {
    lines.push(`  ${tsStr(n.method)}: { params: ${n.params} };`);
  }
  lines.push("}");
  lines.push("");
  lines.push("/** The params schema of every notification, for validating messages. */");
  lines.push("export const RoISNotificationSchemas = {");
  for (const n of catalog.notifications) {
    lines.push(`  ${tsStr(n.method)}: { params: ${schemaVar(n.params)} },`);
  }
  lines.push("} as const;");
  lines.push("");
  lines.push(
    "/** Standard command names every component may accept. A component may define its own as well. */",
  );
  lines.push("export const RoISCommandTypes = {");
  for (const c of catalog.standard_command_types) {
    lines.push(`  ${pascalCase(c)}: ${tsStr(c)},`);
  }
  lines.push("} as const;");
  lines.push("");
  lines.push("/** JSON-RPC 2.0 error codes an engine returns for protocol faults. */");
  lines.push("export const JsonRpcErrorCode = {");
  for (const e of catalog.json_rpc_error_codes) {
    lines.push(`  ${e.name}: ${e.code},`);
  }
  lines.push("} as const;");
  lines.push("");
  lines.push("/** Method name prefixes the catalog does not model. Engines answer them with METHOD_NOT_FOUND. */");
  const prefixes = catalog.unmodelled_method_prefixes.map((p) => tsStr(p)).join(", ");
  lines.push(`export const UnmodelledMethodPrefixes = [${prefixes}] as const;`);
  lines.push("");
  return lines.join("\n");
}

/** Generate a single TS module file from one or more schema files. */
function generateModule(
  moduleName: string,
  schemaFiles: string[],
  owners: Map<string, string>,
  catalog: CatalogDocument | undefined,
): string {
  const parts: string[] = [];

  // Header
  parts.push(`// GENERATED FROM interfaces/schema — DO NOT EDIT`);
  parts.push(`// Source: ${schemaFiles.join(", ")}`);
  parts.push(`// Generator: scripts/generate.ts`);
  parts.push("");
  parts.push(`import { z } from "zod";`);
  const importsAt = parts.length;
  parts.push("");

  // HRI module gets semantic type aliases (matching Python hri.py)
  if (moduleName === "hri") {
    parts.push("// ─── Semantic type aliases (from RoIS_HRI.idl) ──────────────────");
    parts.push("");
    parts.push("/** Unique identifier for a component, sub-engine, or other RoIS entity. */");
    parts.push("export type RoISIdentifier = string;");
    parts.push("/** Ordered list of RoIS identifiers. */");
    parts.push("export type RoISIdentifierList = RoISIdentifier[];");
    parts.push("/** A condition in the OpenRoIS subset of CQL2-Text. Empty means no filter. */");
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
    parts.push("/** Ordered list of Result values. */");
    parts.push("export type ResultList = Result[];");
    parts.push("/** Ordered list of Parameter values. */");
    parts.push("export type ParameterList = Parameter[];");
    // Array aliases are inlined wherever they are used (see isInlineType), so
    // ArgumentList gets a hardcoded alias like the other lists. CommandUnitSequenceItem
    // is a union, so it is still generated below as a zod schema and inferred type.
    parts.push("/** Ordered list of Argument values. */");
    parts.push("export type ArgumentList = Argument[];");
    parts.push("");
  }

  // Common module gets numeric type aliases
  if (moduleName === "common") {
    parts.push("// ─── Numeric type aliases (from RoIS_Common.idl) ────────────────");
    parts.push("");
    parts.push("/** Numeric representation of StreamStatus for wire compatibility. */");
    parts.push("export type StreamStatusT = number;");
    parts.push("");
  }

  // Collect all $defs across all schema files in this module
  // to emit them once at the top (avoiding duplicates)
  const allDefs: Record<string, JsonSchema> = {};
  const topLevelSchemas: { name: string; schema: JsonSchema }[] = [];

  for (const file of schemaFiles) {
    const schema = readSchema(file);

    // Collect $defs
    if (schema.$defs) {
      for (const [name, defSchema] of Object.entries(schema.$defs)) {
        if (!allDefs[name]) {
          allDefs[name] = defSchema;
        }
      }
    }

    // Top-level schema name comes from the title or filename
    topLevelSchemas.push({ name: schemaName(file, schema), schema });
  }

  // Types another module owns are imported from it instead of being emitted again.
  const imported = new Set(
    Object.keys(allDefs).filter((name) => {
      const owner = owners.get(name);
      return owner !== undefined && owner !== moduleName;
    }),
  );

  // Import only the types this module's own code references. References through an
  // inline alias count, because the alias expands to its item type in place.
  const used = new Set<string>();
  const collectUsed = (schema: JsonSchema, seen: Set<string>): void => {
    for (const ref of collectRefs(schema, new Set(Object.keys(allDefs)))) {
      if (imported.has(ref)) {
        used.add(ref);
      } else if (isInlineType(allDefs[ref]) && !seen.has(ref)) {
        collectUsed(allDefs[ref], new Set([...seen, ref]));
      }
    }
  };
  for (const [name, defSchema] of Object.entries(allDefs)) {
    if (imported.has(name) || isInlineType(defSchema)) continue;
    collectUsed(defSchema, new Set([name]));
  }
  for (const { schema } of topLevelSchemas) {
    collectUsed({ ...schema, $defs: undefined }, new Set());
  }
  // The notification table names the params models of another module by type and by
  // schema, so they are imported as well.
  const catalogTypes = new Set<string>();
  if (moduleName === "catalog" && catalog) {
    for (const n of catalog.notifications) {
      const owner = owners.get(n.params);
      if (owner !== undefined && owner !== moduleName) {
        used.add(n.params);
        catalogTypes.add(n.params);
      }
    }
  }
  const importsByModule = new Map<string, string[]>();
  for (const name of [...used].sort()) {
    const owner = owners.get(name)!;
    importsByModule.set(owner, [...(importsByModule.get(owner) ?? []), name]);
  }
  // A recursive type is written as a TS interface, which names other types directly,
  // so those types are imported as well as their schemas.
  const typesNeeded = new Set<string>(catalogTypes);
  for (const [name, defSchema] of Object.entries(allDefs)) {
    if (imported.has(name) || !isSelfReferencing(name, defSchema)) continue;
    for (const ref of collectRefs(defSchema, imported)) typesNeeded.add(ref);
  }
  const importLines = [...importsByModule.entries()]
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([owner, names]) => {
      const specifiers = names
        .map((n) => (typesNeeded.has(n) ? `${schemaVar(n)}, type ${n}` : schemaVar(n)))
        .join(", ");
      return `import { ${specifiers} } from ${tsStr(importSpecifier(moduleName, owner))};`;
    });
  parts.splice(importsAt, 0, ...importLines);

  // Emit $defs first (shared types)
  const ownedDefs = genDefs(allDefs, imported);
  if (ownedDefs) {
    parts.push("// ─── Shared type definitions ($defs) ─────────────────────────────");
    parts.push("");
    parts.push(ownedDefs);
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

  if (moduleName === "catalog" && catalog) {
    parts.push(genCatalog(catalog));
  }

  return parts.join("\n");
}

/**
 * Write a JSON value as a TS literal, with object keys unquoted where they are
 * identifiers, indented to sit at `indent`.
 */
function tsLiteral(value: unknown, indent: string): string {
  const inner = `${indent}  `;
  if (Array.isArray(value)) {
    if (value.length === 0) return "[]";
    return `[\n${value.map((item) => `${inner}${tsLiteral(item, inner)},`).join("\n")}\n${indent}]`;
  }
  if (value !== null && typeof value === "object") {
    const entries = Object.entries(value);
    if (entries.length === 0) return "{}";
    const lines = entries.map(([key, item]) => {
      const name = /^[A-Za-z_$][\w$]*$/.test(key) ? key : tsStr(key);
      return `${inner}${name}: ${tsLiteral(item, inner)},`;
    });
    return `{\n${lines.join("\n")}\n${indent}}`;
  }
  return typeof value === "string" ? tsStr(value) : JSON.stringify(value);
}

/** Generate the profile constants of the basic components from profiles.json. */
function genProfiles(document: ProfilesDocument): string {
  const lines: string[] = [];
  lines.push("// GENERATED FROM interfaces/schema — DO NOT EDIT");
  lines.push("// Source: profiles.json");
  lines.push("// Generator: scripts/generate.ts");
  lines.push("//");
  lines.push("// The full profile of each basic component type: its XML profile with the");
  lines.push("// RoIS_Common messages it includes, and its RoSO function. A component declares");
  lines.push("// the profile of its type and implements a part of it, and the engine serves");
  lines.push("// the part the component implements.");
  lines.push("");
  lines.push('import type { HRIComponentProfile } from "../profiles";');
  for (const { name, profile } of document.profiles) {
    const identifier = profile.identifier as { authority: string; code: string };
    lines.push("");
    lines.push(`/** The ${identifier.authority} ${identifier.code} profile. */`);
    lines.push(`export const ${name}: HRIComponentProfile = ${tsLiteral(profile, "")};`);
  }
  lines.push("");
  return lines.join("\n");
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

  const owners = typeOwners(manifest);
  const catalog = fs.existsSync(CATALOG_PATH)
    ? (JSON.parse(fs.readFileSync(CATALOG_PATH, "utf-8")) as CatalogDocument)
    : undefined;

  // Generate each module
  for (const [moduleName, schemaFiles] of Object.entries(manifest.modules)) {
    const output = generateModule(moduleName, schemaFiles, owners, catalog);
    const outFile = moduleOutFile(moduleName);
    writeFile(path.resolve(SRC_DIR, outFile), output);
    console.log(`  ${outFile.split(path.sep).join("/")} (${schemaFiles.length} schemas)`);
  }

  if (fs.existsSync(PROFILES_PATH)) {
    const profiles = JSON.parse(fs.readFileSync(PROFILES_PATH, "utf-8")) as ProfilesDocument;
    writeFile(path.resolve(SRC_DIR, PROFILES_OUT_FILE), genProfiles(profiles));
    console.log(`  components/profiles.ts (${profiles.profiles.length} profiles)`);
  }

  console.log("\nDone. ComponentContract interface is hand-written in src/contract.ts.");
}

main();