using System;
using System.Linq;
using System.Text.Json.Nodes;
using OpenRoIS.Interfaces.Profiles;
using Xunit;

namespace OpenRoIS.Interfaces.Tests
{
    /// <summary>Runs the vectors of interfaces/fixtures/conditions.json.</summary>
    public class ConditionTests
    {
    private static readonly JsonArray s_vectors = Fixtures.Load("conditions.json");

    public static object[][] Vectors => Fixtures.Rows("conditions.json", "builder", "expected");

    private static RoISIdentifierType Identifier(JsonNode node)
    {
        return new RoISIdentifierType(authority: (string)node["authority"]!, code: (string)node["code"]!);
    }

    // The vectors name the Python builders, because the Python package is where types start.
    internal static string Build(string builder, JsonArray args)
    {
        var text = args.Select(arg => arg is JsonValue ? (string)arg! : "").ToArray();
        switch (builder)
        {
            case "quote":
                return Condition.Quote(text[0]);
            case "eq":
                return Condition.Eq(text[0], text[1]);
            case "like":
                return Condition.Like(text[0], text[1]);
            case "all_of":
                return Condition.AllOf(text);
            case "component_ref":
                return Condition.ComponentRef(text[0]);
            case "component_type":
                return Condition.ComponentType(Identifier(args[0]!));
            case "component_type_urn":
                return Condition.ComponentTypeUrn(Identifier(args[0]!));
            default:
                throw new ArgumentException($"Unknown builder: {builder}");
        }
    }

    [Theory]
    [MemberData(nameof(Vectors))]
    public void Vector_BuildsItsExactText(string builder, string expected, int index)
    {
        Assert.Equal(expected, Build(builder, s_vectors[index]!["args"]!.AsArray()));
    }

    [Fact]
    public void Vectors_CoverEveryBuilder()
    {
        var builders = s_vectors.Select(vector => (string)vector!["builder"]!).ToHashSet();
        Assert.Equal(
            new[] { "all_of", "component_ref", "component_type", "component_type_urn", "eq", "like", "quote" },
            builders.OrderBy(name => name, StringComparer.Ordinal));
    }

    [Fact]
    public void Properties_AreTheWireNames()
    {
        Assert.Equal("component_ref", Condition.ComponentRefProperty);
        Assert.Equal("component_type", Condition.ComponentTypeProperty);
    }
    }
}
