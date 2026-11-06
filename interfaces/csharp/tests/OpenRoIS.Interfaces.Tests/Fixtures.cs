using System;
using System.IO;
using System.Linq;
using System.Text.Json.Nodes;

namespace OpenRoIS.Interfaces.Tests
{
    /// <summary>Reads interfaces/fixtures, the data the Python and TypeScript packages read too.</summary>
    internal static class Fixtures
    {
    public static JsonArray Load(string name)
    {
        return Read(name).AsArray();
    }

    public static JsonObject LoadObject(string name)
    {
        return Read(name).AsObject();
    }

    private static JsonNode Read(string name)
    {
        var path = Path.Combine(AppContext.BaseDirectory, "fixtures", name);
        return JsonNode.Parse(File.ReadAllText(path))!;
    }

    public static object[][] Rows(string name, params string[] columns)
    {
        return Load(name)
            .Select((entry, index) => columns
                .Select(column => (object)entry![column]!.GetValue<string>())
                .Append(index)
                .ToArray())
            .ToArray();
    }
    }
}
