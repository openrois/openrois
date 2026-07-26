#nullable enable
using System;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace OpenRoIS.Sdk.JsonRpc
{

  /// <summary>
  /// JSON converter that deserializes a JSON-RPC <c>id</c> field to
  /// a C# <see cref="string"/>.
  /// </summary>
  /// <remarks>
  /// The JSON-RPC 2.0 spec allows <c>id</c> to be a string, number, or
  /// null. This converter reads any of these and normalizes to string:
  /// <list type="bullet">
  /// <item>JSON string "abc" -> C# "abc"</item>
  /// <item>JSON number 42 -> C# "42"</item>
  /// <item>JSON null -> C# null</item>
  /// </list>
  /// This keeps the <c>Id</c> property as a simple <c>string?</c> while
  /// accepting any spec-compliant <c>id</c> value from the wire.
  /// </remarks>
  internal class JsonRpcIdConverter : JsonConverter<string?>
  {
    /// <inheritdoc/>
    public override string? Read(
        ref Utf8JsonReader reader,
        Type typeToConvert,
        JsonSerializerOptions options)
    {
      return reader.TokenType switch
      {
        JsonTokenType.String => reader.GetString(),
        JsonTokenType.Number when reader.TryGetInt64(out var l) => l.ToString(),
        JsonTokenType.Number when reader.TryGetDouble(out var d) => d.ToString(),
        JsonTokenType.Null => null,
        _ => null,
      };
    }

    /// <inheritdoc/>
    public override void Write(
        Utf8JsonWriter writer,
        string? value,
        JsonSerializerOptions options)
    {
      if (value == null)
      {
        writer.WriteNullValue();
      }
      else
      {
        writer.WriteStringValue(value);
      }
    }
  }

}  // namespace OpenRoIS.Sdk.JsonRpc