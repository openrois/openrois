using System;
using System.Collections.Generic;
using System.Globalization;
using System.Linq;
using System.Numerics;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Text.RegularExpressions;
using OpenRoIS.Interfaces.Hri;
using Xunit;

namespace OpenRoIS.Interfaces.Tests
{
    /// <summary>
    /// Runs interfaces/fixtures/value-edges.json, the edges of the string forms, of the models
    /// and of the condition builders that the Python and TypeScript packages run too. A case
    /// that the file records as a difference of C# is left out of the list it belongs to.
    /// </summary>
    public class ValueEdgeTests
    {
    private const string Language = "csharp";

    private static readonly JsonObject s_edges = Fixtures.LoadObject("value-edges.json");
    private static readonly string[] s_keyFields = { "data_type", "text", "value_text", "name" };
    private static readonly Dictionary<string, Action<JsonNode>> s_checks = new()
    {
        ["refused"] = CheckRefused,
        ["decoded"] = CheckDecoded,
        ["encoded"] = CheckEncoded,
        ["models"] = CheckModel,
        ["conditions"] = CheckCondition,
    };

    private static JsonArray List(string name)
    {
        return s_edges[name]!.AsArray();
    }

    /// <summary>The fields of a case or of an exception's reference, compared as one text.</summary>
    private static string CaseKey(JsonNode entry)
    {
        return string.Join(" ", s_keyFields.Select(field => entry[field]?.ToJsonString()).Where(text => text is not null));
    }

    /// <summary>The cases of a list that value-edges.json records as a difference of this language.</summary>
    private static HashSet<string> Excepted(string list)
    {
        return s_edges["exceptions"]!.AsArray()
            .Where(exception => (string)exception!["language"]! == Language)
            .SelectMany(exception => exception!["cases"]!.AsArray())
            .Where(reference => (string)reference!["list"]! == list)
            .Select(reference => CaseKey(reference!))
            .ToHashSet();
    }

    /// <summary>Theory rows of the cases that hold in this language, or of those that do not.</summary>
    private static IEnumerable<object[]> Rows(bool excepted)
    {
        foreach (var list in s_checks.Keys)
        {
            var skipped = Excepted(list);
            foreach (var (entry, index) in List(list).Select((entry, index) => (entry!, index)))
            {
                if (skipped.Contains(CaseKey(entry)) == excepted)
                    yield return new object[] { list, CaseKey(entry), index };
            }
        }
    }

    public static IEnumerable<object[]> Holding => Rows(excepted: false);

    public static IEnumerable<object[]> Differences => Rows(excepted: true);

    public static IEnumerable<object[]> Doubles =>
        List("doubles").Select(entry => new object[] { (string)entry!["text"]!, (string)entry["bits"]! });

    public static IEnumerable<object[]> References =>
        s_edges["exceptions"]!.AsArray()
            .SelectMany(exception => exception!["cases"]!.AsArray().Select(reference => new object[]
            {
                (string)exception["language"]!,
                (string)reference!["list"]!,
                CaseKey(reference),
            }));

    /// <summary>A number of a <c>value</c> column, where a float JSON cannot carry stands as its text.</summary>
    internal static double ToDouble(JsonNode node)
    {
        if (node.GetValueKind() != JsonValueKind.String)
            return node.GetValue<double>();
        switch (node.GetValue<string>())
        {
            case "NaN":
                return double.NaN;
            case "Infinity":
                return double.PositiveInfinity;
            case "-Infinity":
                return double.NegativeInfinity;
            case "-0.0":
                return -0.0;
            default:
                throw new ArgumentException($"Not a float text: {node}");
        }
    }

    /// <summary>The value of a <c>value_text</c> column, as a C# caller would pass it.</summary>
    private static object ToValue(JsonNode node)
    {
        if (node is JsonArray items)
            return items.Select(item => ToValue(item!)).ToArray();
        if (node.GetValueKind() == JsonValueKind.String)
            return ToDouble(node);
        var text = node.ToJsonString();
        if (text.All(character => character == '-' || char.IsAsciiDigit(character)))
            return BigInteger.Parse(text, CultureInfo.InvariantCulture);
        return double.Parse(text, CultureInfo.InvariantCulture);
    }

    /// <summary>Reads the column as JSON, with the names that JSON does not have quoted.</summary>
    private static object ReadValueText(string text)
    {
        return ToValue(JsonNode.Parse(Regex.Replace(text, "-?Infinity|NaN", "\"$0\""))!);
    }

    private static void CheckRefused(JsonNode entry)
    {
        Assert.Throws<FormatException>(() => RoISValues.Decode((string)entry["data_type"]!, (string)entry["text"]!));
    }

    private static void CheckDecoded(JsonNode entry)
    {
        var dataType = (string)entry["data_type"]!;
        ValuesTests.AssertDecoded(dataType, entry["value"], RoISValues.Decode(dataType, (string)entry["text"]!));
    }

    private static void CheckEncoded(JsonNode entry)
    {
        var value = ReadValueText((string)entry["value_text"]!);
        Assert.Equal((string)entry["text"]!, RoISValues.Encode((string)entry["data_type"]!, value));
    }

    private static void CheckModel(JsonNode entry)
    {
        var type = WireFixtureTests.ModelType((string)entry["kind"]!, (string)entry["method"]!);
        var refused = (bool)entry["refused"]!;
        try
        {
            JsonSerializer.Deserialize(entry["body"]!.ToJsonString(), type, RoISJson.Options);
        }
        catch (JsonException)
        {
            Assert.True(refused, "Refused a body the file accepts.");
            return;
        }
        Assert.False(refused, "Accepted a body the file refuses.");
    }

    private static void CheckCondition(JsonNode entry)
    {
        var text = ConditionTests.Build((string)entry["builder"]!, entry["args"]!.AsArray());

        Assert.Equal((string)entry["expected"]!, text);
    }

    /// <summary>The row names its case, so a list that moved fails here and not as a wrong result.</summary>
    private static JsonNode Case(string list, string key, int index)
    {
        var entry = List(list)[index]!;
        Assert.Equal(key, CaseKey(entry));
        return entry;
    }

    [Theory]
    [MemberData(nameof(Holding))]
    public void Edge_Holds(string list, string key, int index)
    {
        s_checks[list](Case(list, key, index));
    }

    /// <summary>A difference that went away must leave the file, or it would hide a regression.</summary>
    [Theory]
    [MemberData(nameof(Differences))]
    public void Exception_IsStillADifference(string list, string key, int index)
    {
        var entry = Case(list, key, index);

        Assert.ThrowsAny<Exception>(() => s_checks[list](entry));
    }

    [Theory]
    [MemberData(nameof(References))]
    public void Exception_NamesACase(string language, string list, string key)
    {
        Assert.Contains(language, new[] { "python", "typescript", "csharp" });
        Assert.Contains(key, List(list).Select(entry => CaseKey(entry!)));
    }

    private static double FromBits(string bits)
    {
        return BitConverter.Int64BitsToDouble(Convert.ToInt64(bits, 16));
    }

    [Theory]
    [MemberData(nameof(Doubles))]
    public void Double_Encodes(string text, string bits)
    {
        Assert.Equal(text, RoISValues.Encode("double", FromBits(bits)));
    }

    [Theory]
    [MemberData(nameof(Doubles))]
    public void Double_Decodes(string text, string bits)
    {
        var decoded = (double)RoISValues.Decode("double", text);

        Assert.Equal(BitConverter.DoubleToInt64Bits(FromBits(bits)), BitConverter.DoubleToInt64Bits(decoded));
    }
    }
}
