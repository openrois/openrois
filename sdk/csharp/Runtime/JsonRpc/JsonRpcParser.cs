#nullable enable
using System;
using System.Text.Json;

namespace OpenRoIS.Sdk.JsonRpc
{

  /// <summary>
  /// Parse and classify JSON-RPC 2.0 messages.
  /// </summary>
  /// <remarks>
  /// Stateless static methods. <see cref="Parse"/> inspects the presence
  /// of <c>id</c>, <c>result</c>, <c>error</c>, and <c>method</c> fields
  /// to classify the message as Request, Response, Error, or
  /// Notification, then deserializes to the matching type.
  /// </remarks>
  public static class JsonRpcParser
  {

    private static readonly JsonSerializerOptions _options = new()
    {
      PropertyNameCaseInsensitive = true,
    };

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
      JsonDocument doc;
      try
      {
        doc = JsonDocument.Parse(json);
      }
      catch (Exception)
      {
        return new JsonRpcMessage
        {
          Type = JsonRpcMessageType.Unknown,
          RawJson = json,
        };
      }

      using (doc)
      {
        var root = doc.RootElement;
        var hasId = root.TryGetProperty("id", out _);
        var hasResult = root.TryGetProperty("result", out _);
        var hasError = root.TryGetProperty("error", out _);
        var hasMethod = root.TryGetProperty("method", out _);

        // Response: has id + result
        if (hasId && hasResult)
        {
          var response = JsonSerializer.Deserialize<JsonRpcResponse>(
              json, _options);
          return new JsonRpcMessage
          {
            Type = JsonRpcMessageType.Response,
            RawJson = json,
            Response = response,
          };
        }

        // Error: has id + error
        if (hasId && hasError)
        {
          var error = JsonSerializer.Deserialize<JsonRpcError>(
              json, _options);
          return new JsonRpcMessage
          {
            Type = JsonRpcMessageType.Error,
            RawJson = json,
            Error = error,
          };
        }

        // Notification: has method, no id
        if (hasMethod && !hasId)
        {
          var notification = JsonSerializer.Deserialize<JsonRpcNotification>(
              json, _options);
          return new JsonRpcMessage
          {
            Type = JsonRpcMessageType.Notification,
            RawJson = json,
            Notification = notification,
          };
        }

        // Request: has method + id (should not come from gateway, but
        // classify it for completeness)
        if (hasMethod && hasId)
        {
          var request = JsonSerializer.Deserialize<JsonRpcRequest>(
              json, _options);
          return new JsonRpcMessage
          {
            Type = JsonRpcMessageType.Request,
            RawJson = json,
            Request = request,
          };
        }

        return new JsonRpcMessage
        {
          Type = JsonRpcMessageType.Unknown,
          RawJson = json,
        };
      }
    }
  }

}  // namespace OpenRoIS.Sdk.JsonRpc