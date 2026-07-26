#nullable enable
using System.Text.Json;
using System.Text.Json.Serialization;

namespace OpenRoIS.Sdk.JsonRpc
{

  /// <summary>
  /// Constants for the JSON-RPC 2.0 protocol.
  /// </summary>
  public static class JsonRpcConstants
  {
    /// <summary>
    /// The only valid JSON-RPC version string per the spec.
    /// </summary>
    public const string Version = "2.0";
  }

  /// <summary>
  /// Standard JSON-RPC 2.0 error codes.
  /// </summary>
  /// <remarks>
  /// Codes from -32768 to -32000 are reserved by the spec.
  /// Application-level errors from the RoIS layer (BAD_PARAMETER,
  /// UNSUPPORTED, etc.) are carried in the <c>data</c> field of the
  /// error object, not as JSON-RPC error codes.
  /// </remarks>
  public enum JsonRpcErrorCode
  {
    /// <summary>Invalid JSON was received.</summary>
    ParseError = -32700,

    /// <summary>The JSON is not a valid Request object.</summary>
    InvalidRequest = -32600,

    /// <summary>The method does not exist or is not available.</summary>
    MethodNotFound = -32601,

    /// <summary>Invalid method parameters.</summary>
    InvalidParams = -32602,

    /// <summary>Internal JSON-RPC error in the gateway.</summary>
    InternalError = -32603,
  }

  /// <summary>
  /// The error object carried inside a <see cref="JsonRpcError"/>.
  /// </summary>
  public sealed class JsonRpcErrorObject
  {
    /// <summary>Numeric error code. See <see cref="JsonRpcErrorCode"/>.</summary>
    [JsonPropertyName("code")]
    public int Code { get; set; }

    /// <summary>Short human-readable summary of the error.</summary>
    [JsonPropertyName("message")]
    public string Message { get; set; } = string.Empty;

    /// <summary>
    /// Optional additional error data. For RoIS operations, the gateway
    /// places the ReturnCode and component error details here. Treated
    /// as opaque by the JSON-RPC layer.
    /// </summary>
    [JsonPropertyName("data")]
    public JsonElement? Data { get; set; }
  }

  /// <summary>
  /// A JSON-RPC 2.0 Request. Sent by the client to call a method.
  /// Always carries an <c>id</c> so the gateway can correlate its
  /// response.
  /// </summary>
  public sealed class JsonRpcRequest
  {
    /// <summary>The JSON-RPC version string, always "2.0".</summary>
    [JsonPropertyName("jsonrpc")]
    public string JsonRpc { get; set; } = JsonRpcConstants.Version;

    /// <summary>Unique identifier chosen by the caller.</summary>
    [JsonPropertyName("id")]
    [JsonConverter(typeof(JsonRpcIdConverter))]
    public string Id { get; set; } = string.Empty;

    /// <summary>Namespaced method name, e.g. "rois.command.search".</summary>
    [JsonPropertyName("method")]
    public string Method { get; set; } = string.Empty;

    /// <summary>
    /// Named parameter object for the method. Omit if the method takes
    /// no args. Opaque to the JSON-RPC layer.
    /// </summary>
    [JsonPropertyName("params")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public JsonElement? Params { get; set; }
  }

  /// <summary>
  /// A JSON-RPC 2.0 Success Response. The <c>id</c> matches the
  /// originating request. The <c>result</c> carries the return value.
  /// </summary>
  public sealed class JsonRpcResponse
  {
    /// <summary>The JSON-RPC version string, always "2.0".</summary>
    [JsonPropertyName("jsonrpc")]
    public string JsonRpc { get; set; } = JsonRpcConstants.Version;

    /// <summary>Matches the <c>id</c> of the originating request.</summary>
    [JsonPropertyName("id")]
    [JsonConverter(typeof(JsonRpcIdConverter))]
    public string Id { get; set; } = string.Empty;

    /// <summary>
    /// Return value of the method. Shape is method-specific. Opaque
    /// to the JSON-RPC layer. The caller deserializes to the specific
    /// response type (e.g. <c>DiscoverResponse</c>).
    /// </summary>
    [JsonPropertyName("result")]
    public JsonElement Result { get; set; } = default;
  }

  /// <summary>
  /// A JSON-RPC 2.0 Error Response. The <c>id</c> matches the
  /// originating request, or is null for parse-level failures.
  /// </summary>
  public sealed class JsonRpcError
  {
    /// <summary>The JSON-RPC version string, always "2.0".</summary>
    [JsonPropertyName("jsonrpc")]
    public string JsonRpc { get; set; } = JsonRpcConstants.Version;

    /// <summary>Matches the originating request <c>id</c>, or null.</summary>
    [JsonPropertyName("id")]
    [JsonConverter(typeof(JsonRpcIdConverter))]
    public string? Id { get; set; }

    /// <summary>Structured error payload.</summary>
    [JsonPropertyName("error")]
    public JsonRpcErrorObject Error { get; set; } = new();
  }

  /// <summary>
  /// A JSON-RPC 2.0 Notification. Server-to-client push with no reply
  /// expected. Has no <c>id</c> field.
  /// </summary>
  public sealed class JsonRpcNotification
  {
    /// <summary>The JSON-RPC version string, always "2.0".</summary>
    [JsonPropertyName("jsonrpc")]
    public string JsonRpc { get; set; } = JsonRpcConstants.Version;

    /// <summary>Namespaced push method name, e.g. "rois.event.notify".</summary>
    [JsonPropertyName("method")]
    public string Method { get; set; } = string.Empty;

    /// <summary>
    /// Event payload. Shape depends on the method. Opaque to the
    /// JSON-RPC layer.
    /// </summary>
    [JsonPropertyName("params")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public JsonElement? Params { get; set; }
  }

  /// <summary>
  /// Message type discriminator for parsed JSON-RPC messages.
  /// </summary>
  public enum JsonRpcMessageType
  {
    /// <summary>Unrecognized or unparseable message.</summary>
    Unknown,

    /// <summary>A request (has <c>id</c> and <c>method</c>).</summary>
    Request,

    /// <summary>A success response (has <c>id</c> and <c>result</c>).</summary>
    Response,

    /// <summary>An error response (has <c>id</c> and <c>error</c>).</summary>
    Error,

    /// <summary>A notification (has <c>method</c>, no <c>id</c>).</summary>
    Notification,
  }

  /// <summary>
  /// Parsed JSON-RPC message. The <see cref="Type"/> field determines
  /// which payload property is populated.
  /// </summary>
  public sealed class JsonRpcMessage
  {
    /// <summary>The message type (Request, Response, Error, Notification).</summary>
    public JsonRpcMessageType Type { get; set; }

    /// <summary>The raw JSON string.</summary>
    public string RawJson { get; set; } = string.Empty;

    /// <summary>Populated when <see cref="Type"/> is Request.</summary>
    public JsonRpcRequest? Request { get; set; }

    /// <summary>Populated when <see cref="Type"/> is Response.</summary>
    public JsonRpcResponse? Response { get; set; }

    /// <summary>Populated when <see cref="Type"/> is Error.</summary>
    public JsonRpcError? Error { get; set; }

    /// <summary>Populated when <see cref="Type"/> is Notification.</summary>
    public JsonRpcNotification? Notification { get; set; }
  }

}  // namespace OpenRoIS.Sdk.JsonRpc