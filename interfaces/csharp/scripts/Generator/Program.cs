// Generator: reads JSON Schema files and emits C# record/enum types.
//
// Usage:
//   dotnet run -- ../../schema
//   OPENROIS_SCHEMA_DIR=/path/to/schema dotnet run
//
// Reads manifest.json from the schema directory for module→file mapping,
// then emits one .cs file per module into src/OpenRoIS.Interfaces/.

using System.IO;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;

namespace OpenRoIS.Generator;

internal static class Program
{
    private static string s_schemaDir = "";
    private static string s_outputDir = "";

    // Namespace of every top-level schema type, built from the manifest, so a type
    // used outside its own module is written with its fully qualified name.
    private static readonly Dictionary<string, string> s_typeNamespaces = new();

    // Namespace of the module being generated.
    private static string s_currentNamespace = "";

    private static int Main(string[] args)
    {
        // Resolve schema directory
        // AppContext.BaseDirectory = scripts/Generator/bin/Debug/net10.0/
        // We need: interfaces/schema/ (6 levels up from bin output)
        s_schemaDir = Environment.GetEnvironmentVariable("OPENROIS_SCHEMA_DIR")
            ?? (args.Length > 0
                ? Path.GetFullPath(args[0])
                : Path.GetFullPath(Path.Combine(AppContext.BaseDirectory, "..", "..", "..", "..", "..", "..", "schema")));

        // Output directory: interfaces/csharp/src/OpenRoIS.Interfaces/
        // csharp root = interfaces/csharp/ (5 levels up from bin output, not 6)
        var csharpRoot = Path.GetFullPath(Path.Combine(AppContext.BaseDirectory, "..", "..", "..", "..", ".."));
        s_outputDir = Path.Combine(csharpRoot, "src", "OpenRoIS.Interfaces");

        Console.WriteLine($"Schema dir: {s_schemaDir}");
        Console.WriteLine($"Output dir:  {s_outputDir}");

        // Read manifest
        var manifestPath = Path.Combine(s_schemaDir, "manifest.json");
        var manifestJson = File.ReadAllText(manifestPath);
        var manifest = JsonNode.Parse(manifestJson)!;
        var modules = manifest["modules"]!.AsObject();

        foreach (var (moduleName, moduleNode) in modules)
        {
            var moduleNs = moduleName == "contract"
                ? "OpenRoIS.Interfaces.Contract.Models"
                : ModuleToNamespace(moduleName);
            foreach (var file in moduleNode!.AsArray())
                s_typeNamespaces[file!.GetValue<string>().Replace(".schema.json", "")] = moduleNs;
        }

        foreach (var (moduleName, moduleNode) in modules)
        {
            var schemaFiles = moduleNode!.AsArray()
                .Select(n => n!.GetValue<string>())
                .ToList();

            if (moduleName == "contract")
            {
                // Contract data models go to Generated/ContractModels.cs
                var output = GenerateModule("OpenRoIS.Interfaces.Contract.Models", schemaFiles, modules, moduleName);
                var outPath = Path.Combine(s_outputDir, "Generated", "ContractModels.cs");
                WriteFile(outPath, output);
                Console.WriteLine($"  Generated/ContractModels.cs ({schemaFiles.Count} schemas)");
                continue;
            }

            // Map module name to namespace and file path
            var ns = ModuleToNamespace(moduleName);
            var relativePath = ModuleToFilePath(moduleName);
            var fullPath = Path.Combine(s_outputDir, relativePath);

            var content = GenerateModule(ns, schemaFiles, modules, moduleName);
            WriteFile(fullPath, content);
            Console.WriteLine($"  {relativePath} ({schemaFiles.Count} schemas)");
        }

        Console.WriteLine("\nDone. IComponentContract interface is hand-written in Contract.cs.");
        return 0;
    }

    // -----------------------------------------------------------------------
    // Path/namespace helpers
    // -----------------------------------------------------------------------

    private static string ModuleToNamespace(string module)
    {
        // "components/person-detection" → "OpenRoIS.Interfaces.Components.PersonDetection"
        var parts = module.Split('/');
        var nsParts = parts.Select(p => ToPascalCase(p.Replace('-', '_')));
        return "OpenRoIS.Interfaces." + string.Join('.', nsParts);
    }

    private static string ModuleToFilePath(string module)
    {
        // "components/person-detection" → "Components/PersonDetection.cs"
        var parts = module.Split('/');
        var fileParts = parts.Select(p => ToPascalCase(p.Replace('-', '_')));
        return string.Join('/', fileParts) + ".cs";
    }

    // -----------------------------------------------------------------------
    // Module generation
    // -----------------------------------------------------------------------

    private static string GenerateModule(string ns, List<string> schemaFiles, JsonObject modules, string moduleName)
    {
        s_currentNamespace = ns;
        var sb = new StringBuilder();

        // Header
        sb.AppendLine("// GENERATED FROM interfaces/schema — DO NOT EDIT");
        sb.AppendLine($"// Source: {string.Join(", ", schemaFiles)}");
        sb.AppendLine("// Generator: scripts/Generator/Program.cs");
        sb.AppendLine();
        sb.AppendLine("using System;");
        sb.AppendLine("using System.Collections.Generic;");
        sb.AppendLine("using System.Text.Json.Serialization;");
        sb.AppendLine();
        sb.AppendLine($"namespace {ns}");
        sb.AppendLine("{");

        // Collect all $defs across all schema files (deduplicated)
        // But skip types that are already defined in other modules (hri, common, service)
        var allDefNames = new HashSet<string>();
        foreach (var (modName, modNode) in modules)
        {
            if (modName == moduleName) continue;
            if (modNode is JsonArray modFiles)
            {
                foreach (var f in modFiles)
                {
                    var fName = f!.GetValue<string>().Replace(".schema.json", "");
                    allDefNames.Add(fName);
                }
            }
        }

        var allDefs = new Dictionary<string, JsonNode>();
        var topLevelSchemas = new List<(string Name, JsonNode Schema)>();

        foreach (var file in schemaFiles)
        {
            var filePath = Path.Combine(s_schemaDir, file);
            var schema = JsonNode.Parse(File.ReadAllText(filePath))!;

            if (schema["$defs"] is JsonObject defs)
            {
                foreach (var (defName, defNode) in defs)
                {
                    // Skip $defs that are already top-level types in other modules
                    if (allDefNames.Contains(defName))
                        continue;
                    if (!allDefs.ContainsKey(defName))
                        allDefs[defName] = defNode!;
                }
            }

            var topLevelName = schema["title"]?.GetValue<string>()
                ?? file.Replace(".schema.json", "");
            topLevelSchemas.Add((topLevelName, schema));
        }

        // Emit $defs first (topologically sorted)
        if (allDefs.Count > 0)
        {
            // Emit marker interface for CommandUnit | ConcurrentCommands union (hri module)
            if (ns == "OpenRoIS.Interfaces.Hri" && allDefs.ContainsKey("CommandUnit") && allDefs.ContainsKey("ConcurrentCommands"))
            {
                sb.AppendLine("    /// <summary>Marker interface for CommandUnitSequence items (CommandUnit or ConcurrentCommands).</summary>");
                sb.AppendLine("    public interface ICommandUnitSequenceItem { }");
                sb.AppendLine();
            }

            sb.AppendLine("    // ─── Shared type definitions ($defs) ─────────────────────────────");
            sb.AppendLine();

            var sortedNames = TopoSortDefs(allDefs);
            foreach (var name in sortedNames)
            {
                var defSchema = allDefs[name];
                EmitType(sb, name, defSchema, allDefs);
                sb.AppendLine();
            }
        }

        // Build the set of external type names (types in other modules)
        var externalTypes = new HashSet<string>(allDefNames);

        // Emit top-level schemas (skip duplicates already in $defs)
        foreach (var (name, schema) in topLevelSchemas)
        {
            if (allDefs.ContainsKey(name))
                continue;

            // Strip $defs from the schema for generation (already emitted above)
            var schemaCopy = schema.DeepClone();
            if (schemaCopy["$defs"] is not null)
                schemaCopy.AsObject().Remove("$defs");

            EmitType(sb, name, schemaCopy, allDefs, externalTypes);
            sb.AppendLine();
        }

        // The catalog module also carries the method table from catalog.json.
        if (moduleName == "catalog")
            EmitCatalogTable(sb);

        // Close block-scoped namespace
        sb.AppendLine("}");

        return sb.ToString();
    }

    // -----------------------------------------------------------------------
    // Type emission
    // -----------------------------------------------------------------------

    private static void EmitType(StringBuilder sb, string name, JsonNode schema, Dictionary<string, JsonNode> allDefs, HashSet<string>? externalTypes = null)
    {
        // Skip inline-type $defs (primitive aliases, array aliases, union aliases).
        // These are resolved inline by JsonSchemaToCsType and don't need classes.
        if (IsInlineType(schema))
            return;

        // Enum?
        if (schema["enum"] is JsonArray enumValues)
        {
            EmitEnum(sb, name, schema, enumValues);
            return;
        }

        // Object → record
        if (schema["type"]?.GetValue<string>() == "object" || schema["properties"] is not null)
        {
            EmitRecord(sb, name, schema, allDefs, externalTypes);
            return;
        }

        // Fallback: emit as a type alias comment
        sb.AppendLine($"// TODO: {name} — unhandled schema type: {schema["type"]}");
    }

    private static void EmitEnum(StringBuilder sb, string name, JsonNode schema, JsonArray enumValues)
    {
        // XML doc
        EmitDocComment(sb, schema["description"]?.GetValue<string>());

        sb.AppendLine($"    public enum {name}");
        sb.AppendLine("    {");

        for (int i = 0; i < enumValues.Count; i++)
        {
            var value = enumValues[i]!.GetValue<string>();

            // Use the raw wire value as the C# enum member name.
            // This ensures JsonStringEnumConverter serializes/deserializes
            // using the exact IDL wire values without needing [JsonPropertyName].
            sb.Append($"        {value}");
            if (i < enumValues.Count - 1)
                sb.Append(",");
            sb.AppendLine();
        }

        sb.AppendLine("    }");
    }

    private static void EmitRecord(StringBuilder sb, string name, JsonNode schema, Dictionary<string, JsonNode> allDefs, HashSet<string>? externalTypes = null)
    {
        // XML doc
        EmitDocComment(sb, schema["description"]?.GetValue<string>());

        var properties = schema["properties"] as JsonObject;
        var required = new HashSet<string>();
        if (schema["required"] is JsonArray reqArray)
        {
            foreach (var r in reqArray)
                required.Add(r!.GetValue<string>());
        }

        if (properties == null || properties.Count == 0)
        {
            sb.AppendLine($"    public sealed class {name} {{ }}");
            return;
        }

        // Build field info — required first, then optional (C# constraint)
        // Tuple: (PropertyType, PropertyName, ParamName, ParamStr, IsRequired)
        var fields = new List<(string CsType, string CsName, string CamelName, string PropName, string ParamStr, bool IsRequired)>();;

        foreach (var (propName, propSchema) in properties)
        {
            var isRequired = required.Contains(propName);
            var csType = JsonSchemaToCsType(propSchema!, allDefs, isRequired, externalTypes);
            var csName = ToPascalCase(propName);

            var camelName = ToCamelCase(csName);

            string paramStr;
            if (propSchema!["default"] is not null)
            {
                var defaultVal = FormatDefault(propSchema["default"], csType);
                paramStr = $"{csType} {camelName} = {defaultVal}";
            }
            else if (!isRequired)
            {
                if (!csType.EndsWith('?'))
                    csType += '?';
                paramStr = $"{csType} {camelName} = null";
            }
            else
            {
                paramStr = $"{csType} {camelName}";
            }

            fields.Add((csType, csName, camelName, propName, paramStr, isRequired && propSchema!["default"] is null));;
        }

        // Sort: required first, then optional (C# constructor constraint)
        fields = fields.OrderBy(f => f.IsRequired ? 0 : 1).ToList();

        if (fields.Count == 0)
        {
            sb.AppendLine($"    public sealed class {name} {{ }}");
            return;
        }

        // Class declaration — add marker interface for union members
        var interfaces = new List<string> { $"IEquatable<{name}>" };
        if (name == "CommandUnit" || name == "ConcurrentCommands")
            interfaces.Add("ICommandUnitSequenceItem");
        sb.AppendLine($"    public sealed class {name} : {string.Join(", ", interfaces)}");
        sb.AppendLine("    {");

        // Properties
        foreach (var (csType, csName, _, propName, _, _) in fields)
        {
            sb.AppendLine($"        [JsonPropertyName(\"{propName}\")]");
            sb.AppendLine($"        public {csType} {csName} {{ get; }}");
        }

        sb.AppendLine();

        // Constructor (camelCase parameters, PascalCase properties)
        var paramList = fields.Select(f => f.ParamStr);
        sb.AppendLine($"        public {name}({string.Join(", ", paramList)})");
        sb.AppendLine("        {");
        foreach (var (_, csName, camelName, _, _, _) in fields)
        {
            sb.AppendLine($"            {csName} = {camelName};");
        }
        sb.AppendLine("        }");

        // Equals(T?) with reference equality fast path
        sb.AppendLine();
        sb.AppendLine($"        public bool Equals({name}? other)");
        sb.AppendLine("        {");
        sb.AppendLine("            if (ReferenceEquals(other, this)) return true;");
        sb.AppendLine("            if (other is null) return false;");
        var eqParts = fields.Select(f => $"Equals({f.CsName}, other.{f.CsName})");
        sb.AppendLine($"            return {string.Join(" && ", eqParts)};");
        sb.AppendLine("        }");

        // Equals(object?)
        sb.AppendLine();
        sb.AppendLine("        public override bool Equals(object? obj)");
        sb.AppendLine("        {");
        sb.AppendLine($"            return Equals(obj as {name});");
        sb.AppendLine("        }");

        // GetHashCode
        sb.AppendLine();
        sb.AppendLine("        public override int GetHashCode()");
        sb.AppendLine("        {");
        var hashParts = fields.Select(f => f.CsName).ToList();
        if (hashParts.Count == 0)
        {
            sb.AppendLine("            return 0;");
        }
        else if (hashParts.Count <= 8)
        {
            sb.AppendLine($"            return System.HashCode.Combine({string.Join(", ", hashParts)});");
        }
        else
        {
            // HashCode.Combine takes max 8 args — nest for >8 fields
            var first8 = string.Join(", ", hashParts.Take(8));
            var rest = string.Join(", ", hashParts.Skip(8));
            sb.AppendLine($"            return System.HashCode.Combine(System.HashCode.Combine({first8}), {rest});");
        }
        sb.AppendLine("        }");

        // == and != operators for value equality semantics
        sb.AppendLine();
        sb.AppendLine($"        public static bool operator ==({name}? left, {name}? right)");
        sb.AppendLine("            => ReferenceEquals(left, right) || (left is not null && left.Equals(right));");
        sb.AppendLine($"        public static bool operator !=({name}? left, {name}? right)");
        sb.AppendLine("            => !(left == right);");

        sb.AppendLine("    }");
    }

    // -----------------------------------------------------------------------
    // JSON Schema → C# type mapping
    // -----------------------------------------------------------------------

    private static string JsonSchemaToCsType(JsonNode schema, Dictionary<string, JsonNode> allDefs, bool isRequired, HashSet<string>? externalTypes = null, HashSet<string>? visitedRefs = null)
    {
        visitedRefs ??= new HashSet<string>();

        // $ref → resolve simple types inline, reference complex types by name
        if (schema["$ref"] is JsonNode refNode)
        {
            var refName = refNode.GetValue<string>().Replace("#/$defs/", "");

            // If this type is in an external module, use fully qualified name
            if (externalTypes is not null && externalTypes.Contains(refName) && !allDefs.ContainsKey(refName))
            {
                return ResolveExternalType(refName);
            }

            // If the referenced def is an inline type (primitive, array, or union alias),
            // resolve it inline rather than referencing a non-existent class.
            if (allDefs.TryGetValue(refName, out var refSchema) && IsInlineType(refSchema))
            {
                if (visitedRefs.Contains(refName))
                    return "object"; // Cycle guard
                visitedRefs.Add(refName);
                var result = JsonSchemaToCsType(refSchema, allDefs, isRequired, externalTypes, visitedRefs);
                visitedRefs.Remove(refName);
                return result;
            }

            return refName;
        }

        // anyOf
        if (schema["anyOf"] is JsonArray anyOf)
        {
            // anyOf [X, {type: "null"}] → nullable X
            if (anyOf.Count == 2)
            {
                var types = anyOf.Select(n => n!["type"]?.GetValue<string>()).ToList();
                if (types.Contains("null"))
                {
                    var nonNull = anyOf.First(n => n!["type"]?.GetValue<string>() != "null")!;
                    var inner = JsonSchemaToCsType(nonNull, allDefs, true, externalTypes);
                    return inner + "?";
                }
            }

            // anyOf with multiple $refs → marker interface (ICommandUnitSequenceItem)
            var hasRefs = anyOf.All(n => n!["$ref"] is not null);
            if (hasRefs && anyOf.Count > 1)
            {
                // Check if all refs point to types that implement a shared interface.
                // For CommandUnitSequence: CommandUnit + ConcurrentCommands → ICommandUnitSequenceItem
                var refNames = anyOf.Select(n => n!["$ref"]!.GetValue<string>().Replace("#/$defs/", "")).ToList();
                if (refNames.Contains("CommandUnit") && refNames.Contains("ConcurrentCommands"))
                {
                    // The marker interface lives in the Hri namespace.
                    return s_currentNamespace == "OpenRoIS.Interfaces.Hri"
                        ? "ICommandUnitSequenceItem"
                        : "OpenRoIS.Interfaces.Hri.ICommandUnitSequenceItem";
                }
                return "object"; // Fallback for unknown unions
            }

            return "object";
        }

        // enum
        if (schema["enum"] is not null)
        {
            // The enum type name comes from the title
            return schema["title"]?.GetValue<string>() ?? "string";
        }

        var type = schema["type"]?.GetValue<string>();

        // A map: an object whose values all share one schema. JSON object keys are
        // always strings, so the key type is string whatever propertyNames says.
        if (type == "object" && MapValueSchema(schema) is JsonNode mapValue)
            return $"IReadOnlyDictionary<string, {JsonSchemaToCsType(mapValue, allDefs, true, externalTypes)}>";

        return type switch
        {
            "string" => "string",
            "integer" => "int",
            "number" => "double",
            "boolean" => "bool",
            "array" => $"IReadOnlyList<{JsonSchemaToCsType(schema["items"]!, allDefs, true, externalTypes)}>",
            "null" => "object?",
            _ => "object",
        };
    }

    /// <summary>
    /// The value schema of a map: an object with no fixed properties whose
    /// additionalProperties is a schema. Pydantic writes a dict[str, X] field this way.
    /// </summary>
    private static JsonNode? MapValueSchema(JsonNode schema)
    {
        if (schema["properties"] is not null)
            return null;
        return schema["additionalProperties"] is JsonObject value ? value : null;
    }

    /// <summary>
    /// The name to write for a top-level schema type in the module being generated:
    /// the bare name inside its own namespace, the fully qualified name elsewhere.
    /// </summary>
    private static string QualifiedTypeName(string typeName)
    {
        return s_typeNamespaces.TryGetValue(typeName, out var ns) && ns != s_currentNamespace
            ? $"{ns}.{typeName}"
            : typeName;
    }

    /// <summary>
    /// Resolve an external type name to its fully qualified C# name, using the
    /// namespace of the module whose manifest entry defines it.
    /// </summary>
    private static string ResolveExternalType(string typeName)
    {
        return s_typeNamespaces.TryGetValue(typeName, out var ns)
            ? $"{ns}.{typeName}"
            : typeName;
    }

    // -----------------------------------------------------------------------
    // Method catalog
    // -----------------------------------------------------------------------

    /// <summary>
    /// Emit the method name constants, the method to type map and the JSON-RPC
    /// error codes from catalog.json, the table every language shares.
    /// </summary>
    private static void EmitCatalogTable(StringBuilder sb)
    {
        var catalogPath = Path.Combine(s_schemaDir, "catalog.json");
        var catalog = JsonNode.Parse(File.ReadAllText(catalogPath))!;
        var methods = catalog["methods"]!.AsArray();

        sb.AppendLine("    // ─── Method catalog (from catalog.json) ──────────────────────────");
        sb.AppendLine();
        sb.AppendLine("    /// <summary>JSON-RPC method names of the RoIS method catalog, keyed by operation.</summary>");
        sb.AppendLine("    public static class RoISMethods");
        sb.AppendLine("    {");
        foreach (var method in methods)
        {
            var operation = ToPascalCase(method!["operation"]!.GetValue<string>());
            var wireName = method["method"]!.GetValue<string>();
            sb.AppendLine($"        public const string {operation} = \"{wireName}\";");
        }
        sb.AppendLine("    }");
        sb.AppendLine();
        sb.AppendLine("    /// <summary>The params and result type of every catalog method.</summary>");
        sb.AppendLine("    public static class RoISMethodTypes");
        sb.AppendLine("    {");
        sb.AppendLine("        /// <summary>Params and result type, keyed by JSON-RPC method name.</summary>");
        sb.AppendLine("        public static readonly IReadOnlyDictionary<string, (Type Params, Type Result)> ByMethod =");
        sb.AppendLine("            new Dictionary<string, (Type Params, Type Result)>");
        sb.AppendLine("            {");
        foreach (var method in methods)
        {
            var operation = ToPascalCase(method!["operation"]!.GetValue<string>());
            var paramsType = method["params"]!.GetValue<string>();
            var resultType = method["result"]!.GetValue<string>();
            sb.AppendLine($"                [RoISMethods.{operation}] = (typeof({paramsType}), typeof({resultType})),");
        }
        sb.AppendLine("            };");
        sb.AppendLine("    }");
        sb.AppendLine();
        var notifications = catalog["notifications"]!.AsArray();
        sb.AppendLine("    /// <summary>JSON-RPC notification names an engine sends to a service application, keyed by operation.</summary>");
        sb.AppendLine("    public static class RoISNotifications");
        sb.AppendLine("    {");
        foreach (var notification in notifications)
        {
            var operation = ToPascalCase(notification!["operation"]!.GetValue<string>());
            var wireName = notification["method"]!.GetValue<string>();
            sb.AppendLine($"        public const string {operation} = \"{wireName}\";");
        }
        sb.AppendLine("    }");
        sb.AppendLine();
        sb.AppendLine("    /// <summary>The params type of every notification.</summary>");
        sb.AppendLine("    public static class RoISNotificationTypes");
        sb.AppendLine("    {");
        sb.AppendLine("        /// <summary>Params type, keyed by JSON-RPC notification name.</summary>");
        sb.AppendLine("        public static readonly IReadOnlyDictionary<string, Type> ByMethod =");
        sb.AppendLine("            new Dictionary<string, Type>");
        sb.AppendLine("            {");
        foreach (var notification in notifications)
        {
            var operation = ToPascalCase(notification!["operation"]!.GetValue<string>());
            var paramsType = QualifiedTypeName(notification["params"]!.GetValue<string>());
            sb.AppendLine($"                [RoISNotifications.{operation}] = typeof({paramsType}),");
        }
        sb.AppendLine("            };");
        sb.AppendLine("    }");
        sb.AppendLine();
        sb.AppendLine("    /// <summary>Standard command names every component may accept. A component may define its own as well.</summary>");
        sb.AppendLine("    public static class RoISCommandTypes");
        sb.AppendLine("    {");
        foreach (var commandType in catalog["standard_command_types"]!.AsArray())
        {
            var wireName = commandType!.GetValue<string>();
            sb.AppendLine($"        public const string {ToPascalCase(wireName)} = \"{wireName}\";");
        }
        sb.AppendLine("    }");
        sb.AppendLine();
        sb.AppendLine("    /// <summary>JSON-RPC 2.0 error codes an engine returns for protocol faults.</summary>");
        sb.AppendLine("    public static class JsonRpcErrorCodes");
        sb.AppendLine("    {");
        foreach (var code in catalog["json_rpc_error_codes"]!.AsArray())
        {
            var name = EnumValueToPascalCase(code!["name"]!.GetValue<string>());
            var value = code["code"]!.GetValue<int>();
            sb.AppendLine($"        public const int {name} = {value};");
        }
        sb.AppendLine("    }");
        sb.AppendLine();
        sb.AppendLine("    /// <summary>Method name prefixes the catalog does not model. Engines answer them with METHOD_NOT_FOUND.</summary>");
        sb.AppendLine("    public static class UnmodelledMethodPrefixes");
        sb.AppendLine("    {");
        var prefixes = catalog["unmodelled_method_prefixes"]!.AsArray()
            .Select(p => $"\"{p!.GetValue<string>()}\"");
        sb.AppendLine("        /// <summary>Every unmodelled prefix.</summary>");
        sb.AppendLine($"        public static readonly IReadOnlyList<string> All = new[] {{ {string.Join(", ", prefixes)} }};");
        sb.AppendLine("    }");
        sb.AppendLine();
    }

    // -----------------------------------------------------------------------
    // Helpers
    // -----------------------------------------------------------------------

    private static string FormatDefault(JsonNode? defaultNode, string csType)
    {
        if (defaultNode is null)
            return "default";

        // Enum defaults: "OK" → ReturnCode.Ok
        if (defaultNode is JsonValue jv && jv.TryGetValue<string>(out var strVal))
        {
            // Check if csType is an enum (not a primitive)
            if (csType != "string" && csType != "int" && csType != "double" && csType != "bool"
                && !csType.EndsWith("[]") && !csType.EndsWith('?'))
            {
                // It's an enum type — use the raw wire value as the enum member name.
                // The generator emits enum members using the exact wire values (e.g.,
                // "OK", "time", "start"), not PascalCase, so the default must match.
                return $"{csType}.{strVal}";
            }
            return $"\"{strVal}\"";
        }

        if (defaultNode is JsonValue jvInt && jvInt.TryGetValue<int>(out var intVal))
            return intVal.ToString();

        if (defaultNode is JsonValue jvBool && jvBool.TryGetValue<bool>(out var boolVal))
            return boolVal.ToString().ToLower();

        if (csType.EndsWith('?'))
            return "null";

        return defaultNode.ToJsonString();
    }

    private static void EmitDocComment(StringBuilder sb, string? description)
    {
        if (string.IsNullOrEmpty(description))
            return;

        var lines = description.Split('\n');
        if (lines.Length == 1)
        {
            sb.AppendLine($"    /// <summary>{EscapeXml(lines[0])}</summary>");
        }
        else
        {
            sb.AppendLine("    /// <summary>");
            foreach (var line in lines)
                sb.AppendLine($"    /// {EscapeXml(line)}");
            sb.AppendLine("    /// </summary>");
        }
    }

    private static string EscapeXml(string s) =>
        s.Replace("&", "&amp;").Replace("<", "&lt;").Replace(">", "&gt;");

    private static string ToPascalCase(string s)
    {
        if (string.IsNullOrEmpty(s)) return s;
        if (s.Length == 1) return s.ToUpper();

        // snake_case → PascalCase
        if (s.Contains('_'))
        {
            var parts = s.Split('_');
            return string.Join("", parts.Select(p =>
                p.Length == 0 ? "" : char.ToUpper(p[0]) + p[1..]));
        }

        return char.ToUpper(s[0]) + s[1..];
    }

    private static string ToCamelCase(string s)
    {
        // PascalCase → camelCase (first char lowercase)
        var pascal = ToPascalCase(s);
        if (string.IsNullOrEmpty(pascal)) return pascal;
        if (pascal.Length == 1) return pascal.ToLower();
        return char.ToLower(pascal[0]) + pascal[1..];
    }

    private static string EnumValueToPascalCase(string value)
    {
        // "BAD_PARAMETER" → "BadParameter", "OK" → "Ok"
        if (value.Contains('_'))
        {
            var parts = value.Split('_');
            return string.Join("", parts.Select(p =>
                p.Length == 0 ? "" : char.ToUpper(p[0]) + p[1..].ToLower()));
        }

        if (value.Length <= 2)
            return value.ToUpper();

        return char.ToUpper(value[0]) + value[1..].ToLower();
    }

    private static void WriteFile(string path, string content)
    {
        var dir = Path.GetDirectoryName(path);
        if (dir is not null)
            Directory.CreateDirectory(dir);
        File.WriteAllText(path, content);
    }

    // -----------------------------------------------------------------------
    // Topological sort for $defs
    // -----------------------------------------------------------------------

    private static List<string> TopoSortDefs(Dictionary<string, JsonNode> defs)
    {
        var allNames = defs.Keys.ToHashSet();
        var deps = new Dictionary<string, HashSet<string>>();

        foreach (var (name, schema) in defs)
        {
            var refs = new HashSet<string>();
            CollectRefs(schema, allNames, refs, 0);
            refs.Remove(name); // Self-refs are OK in C# (records can reference themselves)
            deps[name] = refs;
        }

        var sorted = new List<string>();
        var visited = new HashSet<string>();
        var visiting = new HashSet<string>();

        void Visit(string name)
        {
            if (visited.Contains(name)) return;
            if (visiting.Contains(name)) return;
            visiting.Add(name);
            if (deps.TryGetValue(name, out var d))
            {
                foreach (var dep in d)
                    Visit(dep);
            }
            visiting.Remove(name);
            visited.Add(name);
            sorted.Add(name);
        }

        foreach (var name in defs.Keys)
            Visit(name);

        return sorted;
    }

    private static void CollectRefs(JsonNode? schema, HashSet<string> allNames, HashSet<string> refs, int depth)
    {
        if (schema is null || depth > 20) return;

        if (schema["$ref"] is JsonNode refNode)
        {
            var name = refNode.GetValue<string>().Replace("#/$defs/", "");
            if (allNames.Contains(name))
                refs.Add(name);
            return;
        }

        if (schema["anyOf"] is JsonArray anyOf)
        {
            foreach (var n in anyOf)
                CollectRefs(n, allNames, refs, depth + 1);
        }

        if (schema["items"] is JsonNode items)
            CollectRefs(items, allNames, refs, depth + 1);

        if (schema["properties"] is JsonObject props)
        {
            foreach (var (_, propSchema) in props)
                CollectRefs(propSchema, allNames, refs, depth + 1);
        }

        if (MapValueSchema(schema) is JsonNode mapValue)
            CollectRefs(mapValue, allNames, refs, depth + 1);
    }

    /// <summary>
    /// Check if a JSON Schema node is a "simple type" — a primitive (string, integer,
    /// number, boolean) with no properties, anyOf, enum, or $ref. These are the
    /// type aliases (RoISIdentifier, ConditionT, DateTime, Integer, etc.) that
    /// PEP 695 emits as $defs entries. They should be resolved inline rather than
    /// emitted as separate C# classes.
    /// </summary>
    private static bool IsSimpleType(JsonNode schema)
    {
        if (schema["properties"] is not null || schema["enum"] is not null || schema["$ref"] is not null)
            return false;
        var type = schema["type"]?.GetValue<string>();
        return type is "string" or "integer" or "number" or "boolean";
    }

    /// <summary>
    /// Check if a JSON Schema $def is an "inline type" — a type that should be
    /// resolved inline by JsonSchemaToCsType rather than emitted as a C# class.
    /// This includes simple primitives (RoISIdentifier, Integer) and type aliases
    /// that are arrays (ResultList, ArgumentList) or unions (CommandUnitSequenceItem).
    /// These don't map to C# classes; they map to C# type expressions.
    /// </summary>
    private static bool IsInlineType(JsonNode schema)
    {
        if (IsSimpleType(schema))
            return true;
        // Array type aliases (e.g., ResultList, ArgumentList, RoISIdentifierList)
        if (schema["type"]?.GetValue<string>() == "array" && schema["properties"] is null)
            return true;
        // Union type aliases (e.g., CommandUnitSequenceItem = CommandUnit | ConcurrentCommands)
        if (schema["anyOf"] is not null && schema["properties"] is null)
            return true;
        return false;
    }
}