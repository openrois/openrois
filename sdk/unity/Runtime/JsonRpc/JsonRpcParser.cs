#nullable enable
using System;
using System.Linq;
using System.Text.Json;
using OpenRoIS.Interfaces.Hri;

namespace OpenRoIS.Sdk.JsonRpc
{

  /// <summary>
  /// Parse and classify JSON-RPC 2.0 messages.
  /// </summary>
  /// <remarks>
  /// Stateless static methods. <see cref="Parse"/> inspects the fields of
  /// a message to classify it as Request, Response, Error, or Notification,
  /// then deserializes to the matching type through
  /// <see cref="RoISJson.Options"/>. The rules are those of the JavaScript
  /// and Python clients, so a message they refuse is refused here too.
  /// </remarks>
  public static class JsonRpcParser
  {

    // The shortest method name a notification can have, as in the other
    // two clients.
    private const int MinMethodLength = 3;

    /// <summary>
    /// Parse a JSON string into a classified <see cref="JsonRpcMessage"/>.
    /// </summary>
    /// <param name="json">Raw JSON string from the WebSocket.</param>
    /// <returns>A <see cref="JsonRpcMessage"/> with the
    /// <see cref="JsonRpcMessage.Type"/> set and the matching payload
    /// property populated. Returns <see cref="JsonRpcMessageType.Unknown"/>
    /// if the JSON is invalid or does not match any known type.</returns>
    public static JsonRpcMessage Parse(string json)
    {
      try
      {
        using var document = JsonDocument.Parse(json);
        return Classify(document.RootElement, json);
      }
      catch (Exception error) when (error is JsonException || error is InvalidOperationException)
      {
        // A peer decides what arrives here, so a bad message is an answer
        // for the caller to handle and not a failure of this class. A string
        // with a lone surrogate is valid JSON, and only reading it throws,
        // with the second exception.
        return new JsonRpcMessage
        {
          Type = JsonRpcMessageType.Unknown,
          RawJson = json,
        };
      }
    }

    private static JsonRpcMessage Classify(JsonElement root, string json)
    {
      var message = new JsonRpcMessage
      {
        Type = JsonRpcMessageType.Unknown,
        RawJson = json,
      };
      if (root.ValueKind != JsonValueKind.Object
          || !root.TryGetProperty("jsonrpc", out var version)
          || version.ValueKind != JsonValueKind.String
          || version.GetString() != JsonRpcConstants.Version)
      {
        return message;
      }

      var fields = root.EnumerateObject().Count();
      var hasId = root.TryGetProperty("id", out var id);
      var hasMethod = root.TryGetProperty("method", out var method);
      var hasParams = root.TryGetProperty("params", out var parameters);
      if (hasId && !IsId(id))
      {
        return message;
      }

      if (hasId && fields == 3 && root.TryGetProperty("result", out _))
      {
        message.Type = JsonRpcMessageType.Response;
        message.Response = root.Deserialize<JsonRpcResponse>(RoISJson.Options);
      }
      else if (hasId && fields == 3
          && root.TryGetProperty("error", out var error) && IsErrorObject(error))
      {
        message.Type = JsonRpcMessageType.Error;
        message.Error = root.Deserialize<JsonRpcError>(RoISJson.Options);
      }
      else if (hasMethod && IsMethod(method) && (!hasParams || AreParams(parameters))
          && fields == (hasId ? 3 : 2) + (hasParams ? 1 : 0))
      {
        // Only a server-to-client notification is expected. A request is
        // classified as well, so the caller can report what it received.
        if (hasId)
        {
          message.Type = JsonRpcMessageType.Request;
          message.Request = root.Deserialize<JsonRpcRequest>(RoISJson.Options);
        }
        else
        {
          message.Type = JsonRpcMessageType.Notification;
          message.Notification =
              root.Deserialize<JsonRpcNotification>(RoISJson.Options);
        }
      }

      return message;
    }

    private static bool IsId(JsonElement id)
    {
      return id.ValueKind == JsonValueKind.String
          || id.ValueKind == JsonValueKind.Number
          || id.ValueKind == JsonValueKind.Null;
    }

    private static bool IsMethod(JsonElement method)
    {
      return method.ValueKind == JsonValueKind.String
          && method.GetString()!.Length >= MinMethodLength;
    }

    private static bool AreParams(JsonElement parameters)
    {
      return parameters.ValueKind == JsonValueKind.Object
          || parameters.ValueKind == JsonValueKind.Array;
    }

    private static bool IsErrorObject(JsonElement error)
    {
      return error.ValueKind == JsonValueKind.Object
          && error.EnumerateObject().All(
              field => field.Name == "code" || field.Name == "message" || field.Name == "data")
          && error.TryGetProperty("code", out var code)
          && code.ValueKind == JsonValueKind.Number
          && code.TryGetInt32(out _)
          && error.TryGetProperty("message", out var text)
          && text.ValueKind == JsonValueKind.String;
    }
  }

}  // namespace OpenRoIS.Sdk.JsonRpc
