using System;
using System.Collections;
using System.Collections.Generic;
using System.Linq;
using System.Reflection;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Text.Json.Serialization;
using OpenRoIS.Interfaces.Catalog;
using OpenRoIS.Interfaces.Hri;
using OpenRoIS.Interfaces.Service;
using Xunit;

namespace OpenRoIS.Interfaces.Tests
{
    /// <summary>
    /// Runs every message of interfaces/fixtures/wire.json, which is real gateway traffic,
    /// through the generated models. See testing/conformance/capture.py.
    /// </summary>
    public class WireFixtureTests
    {
    private static readonly JsonArray s_wire = Fixtures.Load("wire.json");

    public static object[][] Entries => Fixtures.Rows("wire.json", "kind", "method");

    private static JsonObject Body(int index)
    {
        return s_wire[index]!["body"]!.DeepClone().AsObject();
    }

    internal static Type ModelType(string kind, string method)
    {
        switch (kind)
        {
            case "params":
                return RoISMethodTypes.ByMethod[method].Params;
            case "result":
                return RoISMethodTypes.ByMethod[method].Result;
            case "notification":
                return RoISNotificationTypes.ByMethod[method];
            default:
                throw new ArgumentException($"Unknown kind: {kind}");
        }
    }

    private static object Parse(JsonNode body, Type type)
    {
        return JsonSerializer.Deserialize(body.ToJsonString(), type, RoISJson.Options)!;
    }

    private static T Entry<T>(string kind, string method)
    {
        var entry = s_wire.First(item => (string)item!["kind"]! == kind && (string)item["method"]! == method)!;
        return JsonSerializer.Deserialize<T>(entry["body"]!.ToJsonString(), RoISJson.Options)!;
    }

    /// <summary>The body as it reads once RoISJson.Options has dropped its nulls.</summary>
    private static JsonNode? WithoutNulls(JsonNode? node)
    {
        switch (node)
        {
            case JsonObject map:
                var kept = new JsonObject();
                foreach (var (key, value) in map)
                {
                    if (value is not null)
                        kept[key] = WithoutNulls(value);
                }
                return kept;
            case JsonArray list:
                return new JsonArray(list.Select(WithoutNulls).ToArray());
            default:
                return node?.DeepClone();
        }
    }

    [Theory]
    [MemberData(nameof(Entries))]
    public void Entry_ParsesWritesBackAndReparses(string kind, string method, int index)
    {
        var type = ModelType(kind, method);
        var body = Body(index);

        var model = Parse(body, type);
        Assert.IsType(type, model);

        var written = JsonSerializer.Serialize(model, type, RoISJson.Options);
        Assert.True(
            JsonNode.DeepEquals(WithoutNulls(body), JsonNode.Parse(written)),
            $"{kind} {method} wrote {written}");

        var again = JsonSerializer.Deserialize(written, type, RoISJson.Options)!;
        Assert.Equal(written, JsonSerializer.Serialize(again, type, RoISJson.Options));
    }

    [Fact]
    public void Fixture_CoversEveryCatalogMethodAndNotification()
    {
        var seen = s_wire
            .Select(entry => ((string)entry!["kind"]!, (string)entry["method"]!))
            .ToHashSet();
        foreach (var method in RoISMethodTypes.ByMethod.Keys)
        {
            Assert.Contains(("params", method), seen);
            Assert.Contains(("result", method), seen);
        }
        foreach (var notification in RoISNotificationTypes.ByMethod.Keys)
            Assert.Contains(("notification", notification), seen);
    }

    [Fact]
    public void ExecuteParams_ItemsAreTheirConcreteTypes()
    {
        var items = Entry<ExecuteParams>("params", RoISMethods.Execute).CommandUnitList;

        var command = Assert.IsType<CommandUnit>(items[0]);
        Assert.Equal(RoISCommandTypes.Start, command.CommandType);
        var group = Assert.IsType<ConcurrentCommands>(items[1]);
        Assert.Equal(2, group.BranchList.Count);
        Assert.Equal(2, group.BranchList[0].CommandList.Count);
    }

    [Fact]
    public void ExecuteResult_ItemsCarryTheEngineIds()
    {
        var items = Entry<ExecuteResult>("result", RoISMethods.Execute).CommandUnitList!;

        Assert.NotEmpty(Assert.IsType<CommandUnit>(items[0]).CommandId);
        var group = Assert.IsType<ConcurrentCommands>(items[1]);
        Assert.All(
            group.BranchList.SelectMany(branch => branch.CommandList),
            command => Assert.NotEmpty(command.CommandId));
    }

    [Fact]
    public void ExecuteParams_WritesEachItemInFull()
    {
        var sequence = new ICommandUnitSequenceItem[]
        {
            new CommandUnit("mock/navigation", RoISCommandTypes.Start),
            new ConcurrentCommands(new[] { new Branch(new[] { new CommandUnit("mock/navigation", RoISCommandTypes.Stop) }) }),
        };

        var written = JsonSerializer.Serialize(new ExecuteParams(sequence), RoISJson.Options);

        Assert.Equal(
            "{\"command_unit_list\":["
            + "{\"component_ref\":\"mock/navigation\",\"command_type\":\"start\",\"command_id\":\"\"},"
            + "{\"branch_list\":[{\"command_list\":["
            + "{\"component_ref\":\"mock/navigation\",\"command_type\":\"stop\",\"command_id\":\"\"}]}]}]}",
            written);
    }

    [Fact]
    public void Options_WriteEnumsAsNames()
    {
        var written = JsonSerializer.Serialize(new BindResult(ReturnCode.BAD_PARAMETER), RoISJson.Options);

        Assert.Equal("{\"return_code\":\"BAD_PARAMETER\"}", written);
    }

    [Theory]
    [InlineData("null")]
    [InlineData("1")]
    [InlineData("\"start\"")]
    [InlineData("[]")]
    [InlineData("{}")]
    [InlineData("{\"branch_list\":[],\"component_ref\":\"a/b\"}")]
    [InlineData("{\"component_ref\":\"a/b\",\"command_type\":\"start\",\"surprise\":1}")]
    public void SequenceItem_RefusesWhatIsNeitherType(string item)
    {
        Assert.Throws<JsonException>(() =>
            JsonSerializer.Deserialize<ExecuteParams>($"{{\"command_unit_list\":[{item}]}}", RoISJson.Options));
    }

    [Theory]
    [InlineData("\"NOPE\"")]
    [InlineData("\"ok\"")]
    [InlineData("\"OK, ERROR\"")]
    [InlineData("\"0\"")]
    [InlineData("\"9\"")]
    [InlineData("0")]
    [InlineData("true")]
    public void Enum_RefusesAnUnknownNameAndANumber(string value)
    {
        Assert.Throws<JsonException>(() =>
            JsonSerializer.Deserialize<BindResult>($"{{\"return_code\":{value}}}", RoISJson.Options));
    }

    [Theory]
    [MemberData(nameof(Entries))]
    public void Entry_RefusesAMissingRequiredField(string kind, string method, int index)
    {
        Refuses(kind, method, index, (model, type) =>
            Properties(type).Where(property => property.GetCustomAttribute<JsonRequiredAttribute>() is not null)
                .Select(property => (Action)(() => model.Remove(WireName(property)))));
    }

    [Theory]
    [MemberData(nameof(Entries))]
    public void Entry_RefusesAnUnknownField(string kind, string method, int index)
    {
        Refuses(kind, method, index, (model, type) =>
            new[] { (Action)(() => model["surprise"] = 1) });
    }

    [Theory]
    [MemberData(nameof(Entries))]
    public void Entry_RefusesAWrongType(string kind, string method, int index)
    {
        Refuses(kind, method, index, (model, type) =>
            Properties(type).SelectMany(property => WrongValues(property.PropertyType)
                .Select(wrong => (Action)(() => model[WireName(property)] = wrong.DeepClone()))));
    }

    [Theory]
    [MemberData(nameof(Entries))]
    public void Entry_RefusesNullWhereTheCSharpTypeIsNotNullable(string kind, string method, int index)
    {
        var nullability = new NullabilityInfoContext();
        Refuses(kind, method, index, (model, type) =>
            Properties(type)
                .Where(property => !property.PropertyType.IsValueType
                    && nullability.Create(property).ReadState == NullabilityState.NotNull)
                .Select(property => (Action)(() => model[WireName(property)] = null)));
    }

    [Theory]
    [MemberData(nameof(Entries))]
    public void Entry_RefusesANullListItemOrMapValue(string kind, string method, int index)
    {
        Refuses(kind, method, index, (model, type) =>
            Properties(type).SelectMany(property =>
                model.TryGetPropertyValue(WireName(property), out var value)
                    ? NullSlots(value, property.PropertyType)
                    : Enumerable.Empty<Action>()));
    }

    [Theory]
    [InlineData(typeof(CommandUnit), "{\"component_ref\":\"a/b\",\"command_type\":\"start\",\"arguments\":[null]}")]
    [InlineData(typeof(Branch), "{\"command_list\":[null]}")]
    [InlineData(typeof(ConcurrentCommands), "{\"branch_list\":[null]}")]
    [InlineData(typeof(ExecuteParams), "{\"command_unit_list\":[null]}")]
    [InlineData(typeof(ExecuteResult), "{\"return_code\":\"OK\",\"command_unit_list\":[{\"branch_list\":[{\"command_list\":[null]}]}]}")]
    [InlineData(typeof(SearchResult), "{\"return_code\":\"OK\",\"component_ref_list\":[null]}")]
    [InlineData(typeof(GetParameterResult), "{\"return_code\":\"OK\",\"parameters\":[null]}")]
    [InlineData(typeof(GetEventDetailResult), "{\"return_code\":\"OK\",\"results\":[null]}")]
    [InlineData(typeof(GetProfileResult), "{\"return_code\":\"OK\",\"component_profiles\":{\"a/b\":null}}")]
    public void Model_RefusesANullListItemOrMapValue(Type type, string body)
    {
        Assert.Throws<JsonException>(() => JsonSerializer.Deserialize(body, type, RoISJson.Options));
    }

    [Theory]
    [InlineData(typeof(ExecuteParams), "{\"command_unit_list\":[]}")]
    [InlineData(typeof(Branch), "{\"command_list\":[]}")]
    [InlineData(typeof(ConcurrentCommands), "{\"branch_list\":[{\"command_list\":[]}]}")]
    [InlineData(typeof(ExecuteParams), "{\"command_unit_list\":[{\"branch_list\":[{\"command_list\":[]}]}]}")]
    [InlineData(typeof(ExecuteResult), "{\"return_code\":\"OK\",\"command_unit_list\":[{\"branch_list\":[{\"command_list\":[]}]}]}")]
    public void Model_RefusesAListShorterThanMinItems(Type type, string body)
    {
        Assert.Throws<JsonException>(() => JsonSerializer.Deserialize(body, type, RoISJson.Options));
    }

    [Theory]
    [InlineData(typeof(ConcurrentCommands), "{\"branch_list\":[]}")]
    [InlineData(typeof(CommandUnitSequence), "{\"command_unit_list\":[]}")]
    [InlineData(typeof(ExecuteResult), "{\"return_code\":\"OK\",\"command_unit_list\":[]}")]
    public void Model_AcceptsAnEmptyListTheSchemaAllows(Type type, string body)
    {
        Assert.NotNull(JsonSerializer.Deserialize(body, type, RoISJson.Options));
    }

    [Theory]
    [InlineData("{\"return_code\":\"OK\",\"command_unit_list\":null}")]
    [InlineData("{\"return_code\":\"OK\"}")]
    public void OptionalList_ReadsAnExplicitNullAsAbsent(string body)
    {
        var parsed = JsonSerializer.Deserialize<ExecuteResult>(body, RoISJson.Options)!;

        Assert.Null(parsed.CommandUnitList);
        Assert.Equal("{\"return_code\":\"OK\"}", JsonSerializer.Serialize(parsed, RoISJson.Options));
    }

    [Theory]
    [InlineData("{\"return_code\":\"OK\",\"component_profiles\":null}")]
    [InlineData("{\"return_code\":\"OK\"}")]
    public void OptionalMap_ReadsAnExplicitNullAsAbsent(string body)
    {
        var parsed = JsonSerializer.Deserialize<GetProfileResult>(body, RoISJson.Options)!;

        Assert.Null(parsed.ComponentProfiles);
        Assert.Equal("{\"return_code\":\"OK\"}", JsonSerializer.Serialize(parsed, RoISJson.Options));
    }

    /// <summary>
    /// Applies each change that <paramref name="changes"/> gives for an object of the
    /// message, at any depth, to a fresh copy of the body, and expects a refusal.
    /// </summary>
    private static void Refuses(string kind, string method, int index, Func<JsonObject, Type, IEnumerable<Action>> changes)
    {
        var type = ModelType(kind, method);
        var objects = Models(Body(index), type).Count();
        for (var position = 0; position < objects; position++)
        {
            var (json, modelType) = Models(Body(index), type).ElementAt(position);
            var changeCount = changes(json, modelType).Count();
            for (var change = 0; change < changeCount; change++)
            {
                var body = Body(index);
                var (target, _) = Models(body, type).ElementAt(position);
                changes(target, modelType).ElementAt(change)();
                var exception = Record.Exception(() => Parse(body, type));
                Assert.True(exception is JsonException, $"{kind} {method} accepted {body.ToJsonString()}");
            }
        }
    }

    /// <summary>Every object of a body with the model it parses into, outermost first.</summary>
    private static IEnumerable<(JsonObject Json, Type Model)> Models(JsonNode? node, Type type)
    {
        if (node is null)
            yield break;
        type = Nullable.GetUnderlyingType(type) ?? type;

        if (node is JsonArray list)
        {
            var itemType = type.GetGenericArguments()[0];
            foreach (var found in list.SelectMany(item => Models(item, itemType)))
                yield return found;
            yield break;
        }
        if (node is not JsonObject json)
            yield break;

        if (IsMap(type))
        {
            var valueType = type.GetGenericArguments()[1];
            foreach (var found in json.SelectMany(pair => Models(pair.Value, valueType)))
                yield return found;
            yield break;
        }

        if (type == typeof(ICommandUnitSequenceItem))
            type = json.ContainsKey("branch_list") ? typeof(ConcurrentCommands) : typeof(CommandUnit);
        yield return (json, type);
        foreach (var property in Properties(type))
        {
            if (!json.TryGetPropertyValue(WireName(property), out var value))
                continue;
            foreach (var found in Models(value, property.PropertyType))
                yield return found;
        }
    }

    /// <summary>
    /// One action for each list item and map value of a field, at any depth, that puts a
    /// null there. A nested model is left out, because Models reaches it on its own.
    /// </summary>
    private static IEnumerable<Action> NullSlots(JsonNode? node, Type type)
    {
        if (node is JsonArray list)
        {
            var itemType = type.GetGenericArguments()[0];
            for (var position = 0; position < list.Count; position++)
            {
                var slot = position;
                yield return () => list[slot] = null;
                foreach (var nested in NullSlots(list[slot], itemType))
                    yield return nested;
            }
        }
        else if (node is JsonObject map && IsMap(type))
        {
            var valueType = type.GetGenericArguments()[1];
            foreach (var key in map.Select(pair => pair.Key).ToList())
            {
                yield return () => map[key] = null;
                foreach (var nested in NullSlots(map[key], valueType))
                    yield return nested;
            }
        }
    }

    private static bool IsMap(Type type)
    {
        return type.IsGenericType && type.GetGenericTypeDefinition() == typeof(IReadOnlyDictionary<,>);
    }

    private static IEnumerable<PropertyInfo> Properties(Type model)
    {
        return model.GetProperties(BindingFlags.Public | BindingFlags.Instance)
            .Where(property => property.GetCustomAttribute<JsonPropertyNameAttribute>() is not null);
    }

    private static string WireName(PropertyInfo property)
    {
        return property.GetCustomAttribute<JsonPropertyNameAttribute>()!.Name;
    }

    private static JsonNode[] WrongValues(Type type)
    {
        type = Nullable.GetUnderlyingType(type) ?? type;
        if (type == typeof(string))
            return new JsonNode[] { 1, true, new JsonArray(), new JsonObject() };
        if (type == typeof(int))
            return new JsonNode[] { "1", 1.5, true, 2147483648L };
        if (type == typeof(bool))
            return new JsonNode[] { "true", 1 };
        if (type.IsEnum)
            return new JsonNode[] { "NOPE", 0, true };
        if (typeof(IEnumerable).IsAssignableFrom(type) && type.IsGenericType
            && type.GetGenericTypeDefinition() == typeof(IReadOnlyList<>))
            return new JsonNode[] { 1, "x", new JsonObject() };
        return new JsonNode[] { 1, "x", new JsonArray() };
    }
    }
}
