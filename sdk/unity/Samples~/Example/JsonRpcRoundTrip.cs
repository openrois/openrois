using OpenRoIS.Sdk.JsonRpc;
using UnityEngine;

namespace OpenRoIS.Sdk.Samples
{
  /// <summary>
  /// Builds a RoIS request and parses a gateway response, then logs both.
  /// Attach it to a GameObject and enter Play mode. It needs no gateway,
  /// since the response is a literal string.
  /// </summary>
  public sealed class JsonRpcRoundTrip : MonoBehaviour
  {
    private void Start()
    {
      string request = JsonRpcBuilder.CreateRequest(
          id: "1",
          method: "rois.command.search",
          parameters: new { condition = "" });
      Debug.Log($"Request: {request}");

      JsonRpcMessage message = JsonRpcParser.Parse(
          "{\"jsonrpc\":\"2.0\",\"id\":\"1\",\"result\":{\"status\":\"OK\"}}");
      Debug.Log($"Response {message.Type}: {message.Response?.Result}");
    }
  }
}  // namespace OpenRoIS.Sdk.Samples
