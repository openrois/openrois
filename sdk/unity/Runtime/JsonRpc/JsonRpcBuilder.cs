#nullable enable
using System.Text.Json;
using OpenRoIS.Interfaces.Hri;

namespace OpenRoIS.Sdk.JsonRpc
{

  /// <summary>
  /// Build JSON-RPC 2.0 request and notification strings.
  /// </summary>
  /// <remarks>
  /// Stateless static methods. The caller manages ID generation.
  /// The <c>params</c> argument is serialized as-is. The caller passes
  /// a generated params object (e.g. <c>ExecuteParams</c>,
  /// <c>SearchParams</c>), or a <c>Dictionary&lt;string, object&gt;</c> for
  /// a method outside the catalog. An anonymous object does not work in a
  /// build: stripping at High removes its getters, and it is written as
  /// <c>{}</c>. Every message goes through <see cref="RoISJson.Options"/>,
  /// because the engine refuses the nulls and the enumeration numbers that
  /// default options write.
  /// </remarks>
  public static class JsonRpcBuilder
  {

    /// <summary>
    /// Build a JSON-RPC 2.0 request string.
    /// </summary>
    /// <param name="id">Unique identifier for this request. The
    /// gateway echoes it back in the response.</param>
    /// <param name="method">Namespaced method name, e.g.
    /// "rois.command.search".</param>
    /// <param name="parameters">Parameter object, or null if the method
    /// takes no args. Serialized as-is.</param>
    /// <returns>JSON string ready to send.</returns>
    /// <example>
    /// <code>
    /// var json = JsonRpcBuilder.CreateRequest("1", "rois.command.search",
    ///     new SearchParams(""));
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
      return JsonSerializer.Serialize(request, RoISJson.Options);
    }

    /// <summary>
    /// Build a JSON-RPC 2.0 notification string.
    /// </summary>
    /// <remarks>
    /// Notifications have no <c>id</c> field. The receiver never sends
    /// a response. Used for server-to-client push events.
    /// </remarks>
    /// <param name="method">Namespaced push method name, e.g.
    /// "rois.event.notify_event".</param>
    /// <param name="parameters">Event payload, or null.</param>
    /// <returns>JSON string ready to send.</returns>
    public static string CreateNotification(
        string method, object? parameters = null)
    {
      var notification = new JsonRpcNotification
      {
        Method = method,
        Params = ToJsonElement(parameters),
      };
      return JsonSerializer.Serialize(notification, RoISJson.Options);
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

      // An element, so the params field is a proper JSON value and not
      // a nested serialized string.
      return JsonSerializer.SerializeToElement(
          obj, obj.GetType(), RoISJson.Options);
    }
  }

}  // namespace OpenRoIS.Sdk.JsonRpc