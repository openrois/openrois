using System;
using System.Collections;
using System.Collections.Generic;
using System.Globalization;
using System.Linq;
using System.Numerics;
using System.Text;
using System.Text.Json;
using System.Text.RegularExpressions;
using OpenRoIS.Interfaces.Common;

namespace OpenRoIS.Interfaces
{
    /// <summary>
    /// How a typed RoIS value travels as a string, in <c>Result.Value</c>,
    /// <c>Parameter.Value</c> and <c>Argument.Value</c>.
    /// </summary>
    /// <remarks>
    /// <para>
    /// Hand-written, not generated: JSON Schema describes data, not functions. This class
    /// mirrors the Python module <c>openrois.interfaces.values</c>, and the vectors in
    /// interfaces/fixtures/values.json and interfaces/fixtures/value-edges.json keep the two
    /// the same. Section 17 of docs/rois-reference.md describes the string forms.
    /// </para>
    /// <list type="table">
    /// <item><term>int, integer, long, short</term><description>A <see cref="long"/>, or a <see cref="BigInteger"/> beyond its range, written in decimal.</description></item>
    /// <item><term>float, double</term><description>A <see cref="double"/>, written as the shortest text that reads back as the same number, always with a fraction or an exponent (<c>2.0</c>, <c>1e-05</c>).</description></item>
    /// <item><term>bool, boolean</term><description>A <see cref="bool"/>, written <c>true</c> or <c>false</c>.</description></item>
    /// <item><term>Component_Status</term><description>A <see cref="ComponentStatus"/>, written as its name.</description></item>
    /// <item><term>string, RoISIdentifier, DateTime and any other type</term><description>A <see cref="string"/>, written as the text itself. A <see cref="DateTime"/> or a <see cref="DateTimeOffset"/> is written in ISO 8601.</description></item>
    /// <item><term>&lt;type&gt;[]</term><description>An <c>object[]</c> of that type, written as a JSON array.</description></item>
    /// </list>
    /// <para>
    /// Type names are matched without regard to case. An array holds its items as JSON
    /// values: numbers for the numeric types, true and false for the boolean types, and
    /// strings for every other type. NaN, Infinity and -Infinity stand bare in a float
    /// array, as Python writes them.
    /// </para>
    /// <para>
    /// This class differs from Python on text that no writer produces. A number is read in
    /// ASCII digits only, where Python also reads other Unicode digits. An array item with a
    /// lone surrogate is refused, because System.Text.Json has no string for it. The item -0
    /// of a float array reads as negative zero, where Python reads it as an integer and gives
    /// positive zero.
    /// </para>
    /// </remarks>
    public static class RoISValues
    {
        private const string ArraySuffix = "[]";
        private const string StatusType = "component_status";

        // The binary exponents of a double whose mantissa is a whole number of 53 bits.
        private const int MinPower = -1074;
        private const int MaxPower = 971;
        private const long ImplicitBit = 1L << 52;

        private static readonly BigInteger s_mantissaLimit = BigInteger.One << 53;

        // The text of Python's float(), which allows an underscore between two digits.
        private static readonly Regex s_floatText = new Regex(
            @"\A([+-]?)([0-9]+(?:_[0-9]+)*)?(?:\.([0-9]+(?:_[0-9]+)*)?)?(?:[eE]([+-]?[0-9]+(?:_[0-9]+)*))?\z",
            RegexOptions.CultureInvariant);

        // Python writes these three bare in a JSON array, and JsonDocument refuses them. A float
        // array holds no strings, so they can be quoted before parsing and restored item by item.
        private static readonly Regex s_nonFiniteToken = new Regex("-?Infinity|NaN", RegexOptions.CultureInvariant);
        private static readonly HashSet<string> s_nonFiniteItems = new HashSet<string> { "\"NaN\"", "\"Infinity\"", "\"-Infinity\"" };

        private static readonly HashSet<string> s_integerTypes = new HashSet<string> { "int", "integer", "long", "short" };
        private static readonly HashSet<string> s_floatTypes = new HashSet<string> { "float", "double" };
        private static readonly HashSet<string> s_booleanTypes = new HashSet<string> { "bool", "boolean" };
        private static readonly HashSet<string> s_textTypes = new HashSet<string> { "string", "roisidentifier", "datetime" };

        /// <summary>Writes a value of the type <paramref name="dataType"/> as its string form.</summary>
        /// <remarks>
        /// A <see cref="string"/> is taken as the string form itself and is checked against
        /// the type. A value of a type this class does not know is written as JSON, unless
        /// it is already a string.
        /// </remarks>
        /// <param name="dataType">The <c>data_type_ref</c> code, for example <c>int</c> or <c>string[]</c>.</param>
        /// <param name="value">The value to write.</param>
        /// <returns>The string form of the value.</returns>
        /// <exception cref="FormatException">The value does not fit the type.</exception>
        public static string Encode(string dataType, object? value)
        {
            if (value is string text)
            {
                Decode(dataType, text);
                return text;
            }
            if (!IsArrayType(dataType))
            {
                switch (ToJson(dataType, value))
                {
                    case bool flag:
                        return flag ? "true" : "false";
                    case string written:
                        return written;
                    case double number:
                        return FormatDouble(number);
                }
            }
            var output = new StringBuilder();
            WriteJson(output, ToJson(dataType, value));
            return output.ToString();
        }

        /// <summary>Reads the string form of a value of the type <paramref name="dataType"/>.</summary>
        /// <param name="dataType">The <c>data_type_ref</c> code, for example <c>int</c> or <c>string[]</c>.</param>
        /// <param name="text">The string form, as it travels in <c>Result.Value</c>.</param>
        /// <returns>
        /// The value: a <see cref="long"/> or <see cref="BigInteger"/>, <see cref="double"/>,
        /// <see cref="bool"/>, <see cref="ComponentStatus"/>, <see cref="string"/>, or an
        /// <c>object[]</c> of those for an array type.
        /// </returns>
        /// <exception cref="FormatException">The text is not a value of the type.</exception>
        public static object Decode(string dataType, string text)
        {
            var typeName = dataType.ToLowerInvariant();
            if (IsArrayType(dataType))
            {
                var json = s_floatTypes.Contains(ElementType(dataType)) ? s_nonFiniteToken.Replace(text, "\"$&\"") : text;
                try
                {
                    using var document = JsonDocument.Parse(json);
                    return FromJson(dataType, document.RootElement);
                }
                // The parser turns the text into UTF-8 before it reads it, and a lone surrogate
                // in the text fails that step with an ArgumentException.
                catch (Exception exception) when (exception is JsonException || exception is ArgumentException)
                {
                    throw new FormatException($"A {dataType} value must be a JSON array: {text}", exception);
                }
            }
            if (s_integerTypes.Contains(typeName))
            {
                if (!IsIntegerText(text))
                    throw new FormatException($"Not a {dataType} value: {text}");
                return ParseInteger(text);
            }
            if (s_floatTypes.Contains(typeName))
                return ParseDouble(dataType, text);
            if (s_booleanTypes.Contains(typeName))
            {
                if (text != "true" && text != "false")
                    throw new FormatException($"A {dataType} value must be true or false: {text}");
                return text == "true";
            }
            if (typeName == StatusType)
                return ParseStatus(dataType, text);
            return text;
        }

        private static bool IsArrayType(string dataType)
        {
            return dataType.EndsWith(ArraySuffix, StringComparison.Ordinal);
        }

        private static string ItemType(string dataType)
        {
            return dataType.Substring(0, dataType.Length - ArraySuffix.Length);
        }

        /// <summary>The type of the innermost items of an array type, lowercased.</summary>
        private static string ElementType(string dataType)
        {
            while (IsArrayType(dataType))
                dataType = ItemType(dataType);
            return dataType.ToLowerInvariant();
        }

        /// <summary>The JSON value that stands for <paramref name="value"/>, as one item or one scalar.</summary>
        private static object? ToJson(string dataType, object? value)
        {
            var typeName = dataType.ToLowerInvariant();
            if (IsArrayType(dataType))
            {
                if (!(value is IEnumerable items) || value is string || value is IDictionary)
                    throw new FormatException($"A {dataType} value must be a list, not {Describe(value)}");
                var itemType = ItemType(dataType);
                return items.Cast<object?>().Select(item => ToJson(itemType, item)).ToArray();
            }
            if (s_integerTypes.Contains(typeName))
            {
                if (!TryGetInteger(value, out var integer))
                    throw new FormatException($"A {dataType} value must be an integer, not {Describe(value)}");
                return integer;
            }
            if (s_floatTypes.Contains(typeName))
            {
                if (!TryGetDouble(value, out var number))
                    throw new FormatException($"A {dataType} value must be a number that a double can hold, not {Describe(value)}");
                return number;
            }
            if (s_booleanTypes.Contains(typeName))
            {
                if (!(value is bool))
                    throw new FormatException($"A {dataType} value must be a bool, not {Describe(value)}");
                return value;
            }
            if (typeName == StatusType)
            {
                if (value is ComponentStatus || value is string)
                    return ParseStatus(dataType, value.ToString()!).ToString();
                throw new FormatException($"A {dataType} value must be a ComponentStatus, not {Describe(value)}");
            }
            switch (value)
            {
                case DateTime moment:
                    return FormatDateTime(moment);
                case DateTimeOffset moment:
                    return FormatDateTime(moment);
                case string _:
                    return value;
            }
            if (s_textTypes.Contains(typeName))
                throw new FormatException($"A {dataType} value must be a string, not {Describe(value)}");
            return value;
        }

        /// <summary>The value that one JSON item of an array stands for.</summary>
        private static object FromJson(string dataType, JsonElement item)
        {
            var typeName = dataType.ToLowerInvariant();
            if (IsArrayType(dataType))
            {
                if (item.ValueKind != JsonValueKind.Array)
                    throw new FormatException($"A {dataType} value must be a JSON array: {item.GetRawText()}");
                var itemType = ItemType(dataType);
                return item.EnumerateArray().Select(inner => FromJson(itemType, inner)).ToArray();
            }
            if (s_integerTypes.Contains(typeName))
            {
                // The raw text decides, because 1.0 and 1e2 are JSON numbers but not integers.
                if (item.ValueKind != JsonValueKind.Number || !IsIntegerText(item.GetRawText()))
                    throw new FormatException($"A {dataType} item must be a JSON integer: {item.GetRawText()}");
                return ParseInteger(item.GetRawText());
            }
            if (s_floatTypes.Contains(typeName))
            {
                // The raw text decides, because an escape such as \u004e spells the same string
                // without being a token that Decode quoted, and Python refuses every string.
                var raw = item.GetRawText();
                if (item.ValueKind == JsonValueKind.String && s_nonFiniteItems.Contains(raw))
                    return ParseDouble(dataType, item.GetString()!);
                if (item.ValueKind != JsonValueKind.Number)
                    throw new FormatException($"A {dataType} item must be a JSON number: {raw}");
                return ParseDouble(dataType, raw);
            }
            if (s_booleanTypes.Contains(typeName))
            {
                if (item.ValueKind != JsonValueKind.True && item.ValueKind != JsonValueKind.False)
                    throw new FormatException($"A {dataType} item must be true or false: {item.GetRawText()}");
                return item.ValueKind == JsonValueKind.True;
            }
            if (item.ValueKind != JsonValueKind.String)
                throw new FormatException($"A {dataType} item must be a JSON string: {item.GetRawText()}");
            try
            {
                return Decode(dataType, item.GetString()!);
            }
            catch (InvalidOperationException exception)
            {
                // A lone surrogate escape is valid JSON and has no .NET string.
                throw new FormatException($"A {dataType} item is not valid text: {item.GetRawText()}", exception);
            }
        }

        private static string Describe(object? value)
        {
            return value is null ? "null" : value.GetType().Name;
        }

        private static bool IsIntegerText(string text)
        {
            var digits = text.StartsWith("-", StringComparison.Ordinal) ? text.Substring(1) : text;
            return digits.Length > 0 && digits.All(character => character >= '0' && character <= '9');
        }

        private static object ParseInteger(string text)
        {
            var value = BigInteger.Parse(text, CultureInfo.InvariantCulture);
            if (value < long.MinValue || value > long.MaxValue)
                return value;
            return (long)value;
        }

        private static double ParseDouble(string dataType, string text)
        {
            // Spelled out, because the runtimes that Unity uses do not all read these names.
            var trimmed = text.Trim();
            switch (trimmed.ToLowerInvariant())
            {
                case "inf":
                case "+inf":
                case "infinity":
                case "+infinity":
                    return double.PositiveInfinity;
                case "-inf":
                case "-infinity":
                    return double.NegativeInfinity;
                case "nan":
                case "+nan":
                case "-nan":
                    return double.NaN;
            }
            var match = s_floatText.Match(trimmed);
            if (!match.Success || (!match.Groups[2].Success && !match.Groups[3].Success))
                throw new FormatException($"Not a {dataType} value: {text}");

            var fraction = match.Groups[3].Value.Replace("_", "");
            var digits = BigInteger.Parse(match.Groups[2].Value.Replace("_", "") + fraction, CultureInfo.InvariantCulture);
            var exponent = match.Groups[4].Success
                ? BigInteger.Parse(match.Groups[4].Value.Replace("_", ""), NumberStyles.AllowLeadingSign, CultureInfo.InvariantCulture)
                : BigInteger.Zero;
            var magnitude = ReadDecimal(digits, exponent - fraction.Length);
            return match.Groups[1].Value == "-" ? -magnitude : magnitude;
        }

        /// <summary>
        /// The double nearest to digits times ten to the exponent, with ties to the even
        /// neighbor. The arithmetic is exact because double.Parse on the runtimes that Unity
        /// uses is off in the last bit for some text, and overflows on some valid text.
        /// </summary>
        private static double ReadDecimal(BigInteger digits, BigInteger exponent)
        {
            if (digits.IsZero)
                return 0.0;

            var integerDigits = exponent + digits.ToString(CultureInfo.InvariantCulture).Length;
            if (integerDigits > 309)
                return double.PositiveInfinity;
            if (integerDigits < -330)
                return 0.0;

            var scale = (int)exponent;
            var numerator = scale > 0 ? digits * BigInteger.Pow(10, scale) : digits;
            var denominator = scale < 0 ? BigInteger.Pow(10, -scale) : BigInteger.One;

            // The quotient holds the 53 bits of a double, or fewer at the subnormal floor.
            var power = Math.Max(BitLength(numerator) - BitLength(denominator) - 53, MinPower);
            BigInteger quotient, remainder, divisor;
            while (true)
            {
                var dividend = power < 0 ? numerator << -power : numerator;
                divisor = power > 0 ? denominator << power : denominator;
                quotient = BigInteger.DivRem(dividend, divisor, out remainder);
                if (quotient < s_mantissaLimit)
                    break;
                power++;
            }

            var half = (remainder * 2).CompareTo(divisor);
            if (half > 0 || (half == 0 && !quotient.IsEven))
                quotient += 1;
            if (quotient == s_mantissaLimit)
            {
                quotient /= 2;
                power++;
            }

            if (power > MaxPower)
                return double.PositiveInfinity;
            var mantissa = (long)quotient;
            if (mantissa < ImplicitBit)
                return BitConverter.Int64BitsToDouble(mantissa);
            return BitConverter.Int64BitsToDouble(((long)(power - MinPower + 1) << 52) | (mantissa - ImplicitBit));
        }

        private static int BitLength(BigInteger value)
        {
            var bytes = value.ToByteArray();
            var length = (bytes.Length - 1) * 8;
            for (int top = bytes[bytes.Length - 1]; top != 0; top >>= 1)
                length++;
            return length;
        }

        private static ComponentStatus ParseStatus(string dataType, string text)
        {
            // Enum.IsDefined takes the exact name, where Enum.Parse would also read a number.
            if (!Enum.IsDefined(typeof(ComponentStatus), text))
                throw new FormatException($"Not a {dataType} name: {text}");
            return (ComponentStatus)Enum.Parse(typeof(ComponentStatus), text);
        }

        private static bool TryGetInteger(object? value, out BigInteger integer)
        {
            switch (value)
            {
                case sbyte number: integer = number; return true;
                case byte number: integer = number; return true;
                case short number: integer = number; return true;
                case ushort number: integer = number; return true;
                case int number: integer = number; return true;
                case uint number: integer = number; return true;
                case long number: integer = number; return true;
                case ulong number: integer = number; return true;
                case BigInteger number: integer = number; return true;
                default: integer = default; return false;
            }
        }

        private static bool TryGetDouble(object? value, out double number)
        {
            switch (value)
            {
                case double exact: number = exact; return true;
                case float single: number = single; return true;
                case decimal fixedPoint: number = (double)fixedPoint; return true;
            }
            if (!TryGetInteger(value, out var integer))
            {
                number = default;
                return false;
            }
            // The explicit conversion of a BigInteger truncates, where Python and JavaScript
            // round to the nearest double. Python also refuses what would round to infinity.
            var magnitude = ReadDecimal(BigInteger.Abs(integer), BigInteger.Zero);
            number = integer.Sign < 0 ? -magnitude : magnitude;
            return !double.IsInfinity(number);
        }

        /// <summary>
        /// Writes a double in the form of Python's <c>repr</c>, which is what the vectors and
        /// the engine use.
        /// </summary>
        private static string FormatDouble(double value)
        {
            if (double.IsNaN(value))
                return "NaN";
            if (double.IsInfinity(value))
                return value > 0 ? "Infinity" : "-Infinity";
            if (value == 0)
                return double.IsNegative(value) ? "-0.0" : "0.0";

            var (digits, exponent) = ShortestDigits(Math.Abs(value));
            var sign = value < 0 ? "-" : "";
            if (exponent < -4 || exponent >= 16)
            {
                var fraction = digits.Length > 1 ? "." + digits.Substring(1) : "";
                var exponentSign = exponent < 0 ? "-" : "+";
                return $"{sign}{digits[0]}{fraction}e{exponentSign}{Math.Abs(exponent):00}";
            }
            var pointAt = exponent + 1;
            if (pointAt <= 0)
                return $"{sign}0.{new string('0', -pointAt)}{digits}";
            if (pointAt >= digits.Length)
                return $"{sign}{digits}{new string('0', pointAt - digits.Length)}.0";
            return $"{sign}{digits.Substring(0, pointAt)}.{digits.Substring(pointAt)}";
        }

        /// <summary>
        /// The shortest significant digits that read back as a positive double, nearest to
        /// it, and the decimal exponent of the first digit. This is the free-format algorithm
        /// of Burger and Dybvig in exact arithmetic, because the text and the parsing of
        /// doubles on the runtimes that Unity uses are not exact enough to search with.
        /// </summary>
        private static (string Digits, int Exponent) ShortestDigits(double value)
        {
            var bits = BitConverter.DoubleToInt64Bits(value);
            var field = (int)((bits >> 52) & 0x7FF);
            var fraction = bits & (ImplicitBit - 1);
            var mantissa = field == 0 ? fraction : fraction | ImplicitBit;
            var power = Math.Max(field, 1) + MinPower - 1;

            // Value is rest over scale. The neighbors sit above by high and below by low, both
            // over scale, and below a power of two the lower neighbor is half as far away.
            var narrowBelow = fraction == 0 && field > 1;
            var scale = (BigInteger)(narrowBelow ? 4 : 2);
            var rest = mantissa * scale;
            BigInteger high = narrowBelow ? 2 : 1;
            BigInteger low = BigInteger.One;
            if (power > 0)
            {
                rest <<= power;
                high <<= power;
                low <<= power;
            }
            else
            {
                scale <<= -power;
            }

            var exponent = (int)Math.Ceiling(Math.Log10(value));
            if (exponent > 0)
            {
                scale *= BigInteger.Pow(10, exponent);
            }
            else
            {
                var factor = BigInteger.Pow(10, -exponent);
                rest *= factor;
                high *= factor;
                low *= factor;
            }

            // Text exactly halfway to a neighbor reads as this double when its mantissa is even,
            // because ties go to the even neighbor.
            var inReach = (mantissa & 1) == 0;
            bool AtTop(BigInteger total) => inReach ? total >= scale : total > scale;

            while (AtTop(rest + high))
            {
                scale *= 10;
                exponent++;
            }
            while (!AtTop((rest + high) * 10))
            {
                rest *= 10;
                high *= 10;
                low *= 10;
                exponent--;
            }

            var digits = new StringBuilder();
            while (true)
            {
                var digit = (int)BigInteger.DivRem(rest * 10, scale, out rest);
                high *= 10;
                low *= 10;
                var closeBelow = inReach ? rest <= low : rest < low;
                var closeAbove = AtTop(rest + high);
                if (!closeBelow && !closeAbove)
                {
                    digits.Append((char)('0' + digit));
                    continue;
                }

                var half = (rest * 2).CompareTo(scale);
                var roundUp = closeAbove && (!closeBelow || half > 0 || (half == 0 && digit % 2 == 1));
                digits.Append((char)('0' + digit + (roundUp ? 1 : 0)));
                return (digits.ToString(), exponent - 1);
            }
        }

        private static string FormatDateTime(DateTime value)
        {
            return value.ToString(IsoFormat(value.Ticks, value.Kind != DateTimeKind.Unspecified), CultureInfo.InvariantCulture);
        }

        private static string FormatDateTime(DateTimeOffset value)
        {
            return value.ToString(IsoFormat(value.Ticks, true), CultureInfo.InvariantCulture);
        }

        /// <summary>The form of Python's <c>isoformat</c>: microseconds appear only when they are not zero.</summary>
        private static string IsoFormat(long ticks, bool hasOffset)
        {
            var hasMicroseconds = ticks % TimeSpan.TicksPerSecond / 10 != 0;
            return "yyyy-MM-dd'T'HH:mm:ss" + (hasMicroseconds ? ".ffffff" : "") + (hasOffset ? "zzz" : "");
        }

        /// <summary>Writes JSON with the separators of Python's <c>json.dumps</c>, which keep the text the same in every language.</summary>
        private static void WriteJson(StringBuilder output, object? value)
        {
            switch (value)
            {
                case null:
                    output.Append("null");
                    return;
                case bool flag:
                    output.Append(flag ? "true" : "false");
                    return;
                case string text:
                    WriteJsonString(output, text);
                    return;
                case IDictionary map:
                    WriteJsonObject(output, map);
                    return;
                case IEnumerable items:
                    WriteJsonArray(output, items);
                    return;
            }
            if (TryGetInteger(value, out var integer))
            {
                output.Append(integer.ToString(CultureInfo.InvariantCulture));
                return;
            }
            if (TryGetDouble(value, out var number))
            {
                output.Append(FormatDouble(number));
                return;
            }
            throw new FormatException($"A {Describe(value)} cannot be written as JSON.");
        }

        private static void WriteJsonArray(StringBuilder output, IEnumerable items)
        {
            output.Append('[');
            var first = true;
            foreach (var item in items)
            {
                if (!first)
                    output.Append(", ");
                first = false;
                WriteJson(output, item);
            }
            output.Append(']');
        }

        private static void WriteJsonObject(StringBuilder output, IDictionary map)
        {
            output.Append('{');
            var first = true;
            foreach (DictionaryEntry entry in map)
            {
                if (!(entry.Key is string key))
                    throw new FormatException($"A JSON key must be a string, not {Describe(entry.Key)}");
                if (!first)
                    output.Append(", ");
                first = false;
                WriteJsonString(output, key);
                output.Append(": ");
                WriteJson(output, entry.Value);
            }
            output.Append('}');
        }

        private static void WriteJsonString(StringBuilder output, string text)
        {
            output.Append('"');
            foreach (var character in text)
            {
                switch (character)
                {
                    case '"': output.Append("\\\""); break;
                    case '\\': output.Append("\\\\"); break;
                    case '\b': output.Append("\\b"); break;
                    case '\f': output.Append("\\f"); break;
                    case '\n': output.Append("\\n"); break;
                    case '\r': output.Append("\\r"); break;
                    case '\t': output.Append("\\t"); break;
                    default:
                        if (character < ' ')
                            output.Append("\\u").Append(((int)character).ToString("x4", CultureInfo.InvariantCulture));
                        else
                            output.Append(character);
                        break;
                }
            }
            output.Append('"');
        }
    }
}
