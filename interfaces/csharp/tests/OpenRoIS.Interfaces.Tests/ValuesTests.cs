using System;
using System.Collections.Generic;
using System.Linq;
using System.Numerics;
using System.Text.Json.Nodes;
using OpenRoIS.Interfaces.Common;
using Xunit;

namespace OpenRoIS.Interfaces.Tests
{
    /// <summary>
    /// Runs the vectors of interfaces/fixtures/values.json, and what does not fit a shared
    /// vector. ValueEdgeTests runs interfaces/fixtures/value-edges.json.
    /// </summary>
    public class ValuesTests
    {
    private static readonly JsonArray s_vectors = Fixtures.Load("values.json");

    private static readonly HashSet<string> s_integerTypes = new() { "int", "integer", "long", "short" };
    private static readonly HashSet<string> s_floatTypes = new() { "float", "double" };

    public static object[][] Vectors => Fixtures.Rows("values.json", "data_type", "text");

    internal static string ItemType(string dataType)
    {
        return dataType.Substring(0, dataType.Length - 2);
    }

    private static string BaseType(string dataType)
    {
        return dataType.ToLowerInvariant().Replace("[]", "");
    }

    /// <summary>
    /// The value a C# caller would pass. JSON keeps 2 and 2.0 apart in its text only, so
    /// the type comes from the data type, as it does for every other language.
    /// </summary>
    private static object? ToValue(string dataType, JsonNode? node)
    {
        if (node is JsonArray items)
            return items.Select(item => ToValue(ItemType(dataType), item)).ToArray();
        var text = node!.ToJsonString();
        if (s_integerTypes.Contains(BaseType(dataType)))
            return BigInteger.Parse(text);
        if (s_floatTypes.Contains(BaseType(dataType)))
            return node.GetValue<double>();
        if (BaseType(dataType) is "bool" or "boolean")
            return node.GetValue<bool>();
        return node.GetValue<string>();
    }

    /// <summary>
    /// Checks the decoded type as well as the value, so 2.0 for 2 and true for 1 fail. The
    /// bits decide a float, because Assert.Equal takes -0.0 and 0.0 as the same number, and
    /// a float that JSON cannot carry stands as its text.
    /// </summary>
    internal static void AssertDecoded(string dataType, JsonNode? expected, object actual)
    {
        if (expected is JsonArray items)
        {
            var decoded = Assert.IsType<object[]>(actual);
            Assert.Equal(items.Count, decoded.Length);
            for (var index = 0; index < decoded.Length; index++)
                AssertDecoded(ItemType(dataType), items[index], decoded[index]);
            return;
        }
        if (s_integerTypes.Contains(BaseType(dataType)))
        {
            Assert.True(actual is long || actual is BigInteger, $"Decoded a {actual.GetType().Name}");
            Assert.Equal(expected!.ToJsonString(), actual.ToString());
        }
        else if (s_floatTypes.Contains(BaseType(dataType)))
            AssertSameDouble(ValueEdgeTests.ToDouble(expected!), Assert.IsType<double>(actual));
        else if (BaseType(dataType) is "bool" or "boolean")
            Assert.Equal(expected!.GetValue<bool>(), Assert.IsType<bool>(actual));
        else if (BaseType(dataType) == "component_status")
            Assert.Equal(expected!.GetValue<string>(), Assert.IsType<ComponentStatus>(actual).ToString());
        else
            Assert.Equal(expected!.GetValue<string>(), Assert.IsType<string>(actual));
    }

    private static void AssertSameDouble(double expected, double actual)
    {
        if (double.IsNaN(expected))
            Assert.True(double.IsNaN(actual), $"Decoded {actual}");
        else
            Assert.Equal(BitConverter.DoubleToInt64Bits(expected), BitConverter.DoubleToInt64Bits(actual));
    }

    [Theory]
    [MemberData(nameof(Vectors))]
    public void Vector_Encodes(string dataType, string text, int index)
    {
        Assert.Equal(text, RoISValues.Encode(dataType, ToValue(dataType, s_vectors[index]!["value"])));
    }

    [Theory]
    [MemberData(nameof(Vectors))]
    public void Vector_Decodes(string dataType, string text, int index)
    {
        AssertDecoded(dataType, s_vectors[index]!["value"], RoISValues.Decode(dataType, text));
    }

    [Fact]
    public void Float_AcceptsAnInteger()
    {
        Assert.Equal("3.0", RoISValues.Encode("float", 3));
        Assert.Equal(3.0, RoISValues.Decode("float", "3"));
    }

    [Theory]
    [InlineData(0.1, "0.1")]
    [InlineData(1e22, "1e+22")]
    [InlineData(5e-324, "5e-324")]
    [InlineData(1.4901161193847656e-08, "1.4901161193847656e-08")]
    [InlineData(9.5367431640625e-07, "9.5367431640625e-07")]
    [InlineData(1.7976931348623157e308, "1.7976931348623157e+308")]
    [InlineData(-2.5, "-2.5")]
    [InlineData(double.NegativeInfinity, "-Infinity")]
    public void Float_WritesThePythonForm(double value, string text)
    {
        Assert.Equal(text, RoISValues.Encode("double", value));
    }

    public static IEnumerable<object[]> IntegersAsFloats => new[]
    {
        new object[] { 9007199254740993L, "9007199254740992.0" },
        new object[] { 9007199254740995L, "9007199254740996.0" },
        new object[] { -9007199254740995L, "-9007199254740996.0" },
        new object[] { long.MaxValue, "9.223372036854776e+18" },
        new object[] { long.MinValue, "-9.223372036854776e+18" },
        new object[] { ulong.MaxValue, "1.8446744073709552e+19" },
        new object[] { BigInteger.Pow(2, 1024) - BigInteger.Pow(2, 970) - 1, "1.7976931348623157e+308" },
    };

    [Theory]
    [MemberData(nameof(IntegersAsFloats))]
    public void Float_RoundsAnIntegerToTheNearestDouble(object value, string text)
    {
        Assert.Equal(text, RoISValues.Encode("float", value));
        Assert.Equal($"[{text}]", RoISValues.Encode("double[]", new[] { value }));
    }

    public static IEnumerable<object[]> IntegersBeyondADouble => new[]
    {
        new object[] { BigInteger.Pow(2, 1024) - BigInteger.Pow(2, 970) },
        new object[] { BigInteger.Pow(10, 400) },
        new object[] { -BigInteger.Pow(10, 400) },
    };

    [Theory]
    [MemberData(nameof(IntegersBeyondADouble))]
    public void Float_RefusesAnIntegerBeyondADouble(object value)
    {
        Assert.Throws<FormatException>(() => RoISValues.Encode("float", value));
        Assert.Throws<FormatException>(() => RoISValues.Encode("double[]", new[] { value }));
    }

    [Theory]
    [InlineData("float[]", "[NaN]")]
    [InlineData("float[]", "[Infinity]")]
    [InlineData("float[]", "[-Infinity]")]
    [InlineData("double[]", "[1.5, NaN]")]
    [InlineData("double[]", "[NaN, Infinity, -Infinity]")]
    [InlineData("Float[]", "[NaN]")]
    [InlineData("DOUBLE[]", "[-Infinity]")]
    [InlineData("float[][]", "[[NaN], [1.5, Infinity]]")]
    [InlineData("Double[][][]", "[[[-Infinity]]]")]
    public void FloatArray_CarriesNaNAndTheInfinitiesBare(string dataType, string text)
    {
        Assert.Equal(text, RoISValues.Encode(dataType, RoISValues.Decode(dataType, text)));
        Assert.Equal(text, RoISValues.Encode(dataType, text));
    }

    [Fact]
    public void FloatArray_ReadsEachBareTokenAsItsValue()
    {
        var items = Assert.IsType<object[]>(RoISValues.Decode("double[]", "[NaN, Infinity, -Infinity, 1.5]"));

        Assert.Equal(new object[] { double.NaN, double.PositiveInfinity, double.NegativeInfinity, 1.5 }, items);
    }

    [Fact]
    public void FloatArray_WritesTheInfinityThatAnOverflowReadsAs()
    {
        var items = RoISValues.Decode("float[]", "[1e400]");

        Assert.Equal("[Infinity]", RoISValues.Encode("float[]", items));
    }

    [Fact]
    public void FloatArray_WritesSingleValuesBareToo()
    {
        Assert.Equal("[NaN, Infinity]", RoISValues.Encode("float[]", new[] { float.NaN, float.PositiveInfinity }));
    }

    [Fact]
    public void UnknownType_WritesNaNAsPythonDoes()
    {
        Assert.Equal("[NaN, -Infinity]", RoISValues.Encode("polygon", new[] { double.NaN, double.NegativeInfinity }));
    }

    [Fact]
    public void StringArray_KeepsTheNamesAsText()
    {
        Assert.Equal(new object[] { "NaN", "Infinity" }, RoISValues.Decode("string[]", "[\"NaN\", \"Infinity\"]"));
    }

    /// <summary>
    /// Assert.Throws takes the exact type, so an ArgumentException that gets out fails here.
    /// The text stays in the body because an attribute cannot carry a lone surrogate.
    /// </summary>
    [Fact]
    public void Decode_RefusesALoneSurrogateAsAFormatError()
    {
        Assert.Throws<FormatException>(() => RoISValues.Decode("string[]", "[\"\ud800\"]"));
        Assert.Throws<FormatException>(() => RoISValues.Decode("string[]", "[\"\udc00 tail\"]"));
        Assert.Throws<FormatException>(() => RoISValues.Decode("int[]", "\ud800"));
        Assert.Throws<FormatException>(() => RoISValues.Decode("float[]", "[\ud800]"));
        Assert.Throws<FormatException>(() => RoISValues.Decode("float[]", "[NaN, \ud800]"));
        Assert.Throws<FormatException>(() => RoISValues.Encode("string[]", "[\"\ud800\"]"));
    }

    [Fact]
    public void Decode_RefusesALoneSurrogateEscapeAsAFormatError()
    {
        Assert.Throws<FormatException>(() => RoISValues.Decode("string[]", "[\"\\ud800\"]"));
    }

    [Fact]
    public void Integer_BeyondALongStaysExact()
    {
        var value = BigInteger.Pow(10, 30);

        Assert.Equal(value.ToString(), RoISValues.Encode("long", value));
        Assert.Equal(value, RoISValues.Decode("long", value.ToString()));
    }

    [Fact]
    public void Status_ReadsAsTheEnumeration()
    {
        Assert.Equal(ComponentStatus.BUSY, RoISValues.Decode("Component_Status", "BUSY"));
        Assert.Equal("BUSY", RoISValues.Encode("Component_Status", ComponentStatus.BUSY));
    }

    [Fact]
    public void DateTime_IsWrittenInIso8601()
    {
        var moment = new DateTimeOffset(2026, 10, 8, 4, 50, 0, TimeSpan.Zero);

        Assert.Equal("2026-10-08T04:50:00+00:00", RoISValues.Encode("DateTime", moment));
        Assert.Equal("2026-10-08T04:50:00+00:00", RoISValues.Encode("DateTime", moment.UtcDateTime));
        Assert.Equal("2026-10-08T04:50:00.250000+00:00", RoISValues.Encode("DateTime", moment.AddMilliseconds(250)));
        Assert.Equal("2026-10-08T04:50:00", RoISValues.Encode("DateTime", new DateTime(2026, 10, 8, 4, 50, 0)));
    }

    [Fact]
    public void AString_IsTakenAsTheStringForm()
    {
        Assert.Equal("[\"home\"]", RoISValues.Encode("string[]", "[\"home\"]"));
        Assert.Equal("42", RoISValues.Encode("int", "42"));
        Assert.Throws<FormatException>(() => RoISValues.Encode("int", "forty-two"));
    }

    [Fact]
    public void UnknownTypes_KeepTheirText()
    {
        var polygon = new[] { new[] { 0, 0 }, new[] { 1, 1 } };

        Assert.Equal("[[0, 0], [1, 1]]", RoISValues.Decode("polygon", "[[0, 0], [1, 1]]"));
        Assert.Equal("[[0, 0], [1, 1]]", RoISValues.Encode("polygon", polygon));
    }

    public static IEnumerable<object?[]> WrongValues => new[]
    {
        new object?[] { "int", 1.5 },
        new object?[] { "int", true },
        new object?[] { "float", "1.5x" },
        new object?[] { "float", true },
        new object?[] { "bool", 1 },
        new object?[] { "string", 3 },
        new object?[] { "string", null },
        new object?[] { "string[]", "kitchen" },
        new object?[] { "string[]", 3 },
        new object?[] { "int[]", new object[] { 1.5 } },
        new object?[] { "Component_Status", "IDLE" },
        new object?[] { "Component_Status", 1 },
    };

    [Theory]
    [MemberData(nameof(WrongValues))]
    public void Encode_RefusesValuesOfAnotherType(string dataType, object? value)
    {
        Assert.Throws<FormatException>(() => RoISValues.Encode(dataType, value));
    }
    }
}
