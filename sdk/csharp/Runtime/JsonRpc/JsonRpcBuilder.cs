#nullable enable
using System.Text.Json;

namespace OpenRoIS.Sdk.JsonRpc
{

  /// <summary>
  /// Build JSON-RPC 2.0 request and notification strings.
  /// </summary>
  /// <remarks>
  /// Stateless static methods. The caller manages ID generation.
  /// The <c>params</c> argument is serialized as-is. The caller passes
  /// a typed object (e.g. <c>CommandRequest</c>,
  /// <c>DiscoverRequest</c>) or an anonymous object.
  /// </remarks>
  public static class JsonRpcBuilder
  {

    private static readonly JsonSerializerOptions _options = new()
    {
      // Match the wire format: no indentation, no extra whitespace.
      WriteIndented = false,
    };

    /// <summary>
    /// Build a JSON-RPC 2.0 request string.
    /// </summary>
    /// <param name="id">Unique identifier for this request. The
    /// gateway echoes it back in the response.</param>
    /// <param name="method">Namespaced method name, e.g.
    /// "rois.command.search".</param>
    /// <param name="params">Parameter object, or null if the method
    /// takes no args. Serialized as-is.</param>
    /// <returns>JSON string ready to send.</returns>
    /// <example>
    /// <code>
    /// var json = JsonRpcBuilder.CreateRequest("1", "rois.command.search",
    ///     new { condition = "" });
    /// </code>
    /// </example>
    public static string CreateRequest(
        string id, string method, object? parameters = null)
    {
      var request = new JsonRpcRequest
      {
        Id = id,
        Method = method,
        Params = ToJsonElement(parameters),
      };
      return JsonSerializer.Serialize(request, _options);
    }

    /// <summary>
    /// Build a JSON-RPC 2.0 notification string.
    /// </summary>
    /// <remarks>
    /// Notifications have no <c>id</c> field. The receiver never sends
    /// a response. Used for server-to-client push events.
    /// </remarks>
    /// <param name="method">Namespaced push method name, e.g.
    /// "rois.event.notify".</param>
    /// <param name="params">Event payload, or null.</param>
    /// <returns>JSON string ready to send.</returns>
    public static string CreateNotification(
        string method, object? parameters = null)
    {
      var notification = new JsonRpcNotification
      {
        Method = method,
        Params = ToJsonElement(parameters),
      };
      return JsonSerializer.Serialize(notification, _options);
    }

    /// <summary>
    /// Serialize an object to a <see cref="JsonElement"/>, or return
    /// null if the object is null.
    /// </summary>
    private static JsonElement? ToJsonElement(object? obj)
    {
      if (obj == null)
      {
        return null;
      }

      // If the object is already a JsonElement, pass it through.
      if (obj is JsonElement element)
      {
        return element;
      }

      // Serialize to JSON, then parse back to a JsonElement.
      // This ensures the params field is a proper JSON value, not a
      // nested serialized string.
      var json = JsonSerializer.Serialize(obj, obj.GetType(), _options);
      return JsonDocument.Parse(json).RootElement.Clone();
    }
  }

}  // namespace OpenRoIS.Sdk.JsonRpc