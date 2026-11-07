#nullable enable
using System;
using System.Globalization;
using System.Text.Json;
using OpenRoIS.Interfaces.Hri;

namespace OpenRoIS.Sdk
{

  /// <summary>
  /// Raised when a RoIS operation returns a code other than OK.
  /// </summary>
  /// <remarks>
  /// A RoIS failure is a normal result on the wire, so this exception
  /// carries the return code for callers to branch on. Everything else that
  /// goes wrong between the client and the engine is a
  /// <see cref="TransportException"/> or one of its subclasses.
  /// </remarks>
  public sealed class RoISException : Exception
  {
    /// <summary>The return code of the result.</summary>
    public ReturnCode ReturnCode { get; }

    /// <summary>The JSON-RPC method that returned it.</summary>
    public string Method { get; }

    /// <summary>Create the exception for a result.</summary>
    public RoISException(ReturnCode returnCode, string method)
        : base($"{method} failed with {returnCode}")
    {
      ReturnCode = returnCode;
      Method = method;
    }
  }

  /// <summary>
  /// The base of every failure below the RoIS operations, and what a call on
  /// a closed client raises.
  /// </summary>
  public class TransportException : Exception
  {
    /// <summary>Create the exception with what went wrong.</summary>
    public TransportException(string message, Exception? innerException = null)
        : base(message, innerException)
    {
    }
  }

  /// <summary>
  /// Raised when the WebSocket cannot be opened or is lost.
  /// </summary>
  public sealed class RoISConnectionException : TransportException
  {
    /// <summary>The URL the transport tried to reach.</summary>
    public string Url { get; }

    /// <summary>Create the exception for a URL.</summary>
    public RoISConnectionException(
        string message, string url = "", Exception? innerException = null)
        : base(message, innerException)
    {
      Url = url;
    }
  }

  /// <summary>
  /// Raised when a request gets no reply in time.
  /// </summary>
  public sealed class RequestTimeoutException : TransportException
  {
    /// <summary>The JSON-RPC method that timed out.</summary>
    public string Method { get; }

    /// <summary>The id of the request.</summary>
    public string RequestId { get; }

    /// <summary>Create the exception for a request.</summary>
    public RequestTimeoutException(string method, string requestId, TimeSpan timeout)
        : base(string.Format(
            CultureInfo.InvariantCulture,
            "Request timed out after {0}s: {1} (id: {2})",
            timeout.TotalSeconds, method, requestId))
    {
      Method = method;
      RequestId = requestId;
    }
  }

  /// <summary>
  /// Raised when the engine answers with a JSON-RPC error object.
  /// </summary>
  /// <remarks>
  /// This reports a protocol fault: unparseable JSON, an invalid request, an
  /// unknown method, params that fail validation, or an internal error. A
  /// RoIS failure is not an RpcException: it is a normal result with a
  /// return code other than OK, which the client raises as
  /// <see cref="RoISException"/>.
  /// </remarks>
  public sealed class RpcException : TransportException
  {
    /// <summary>The JSON-RPC error code, for example -32601 for an unknown method.</summary>
    public int Code { get; }

    /// <summary>
    /// The additional data of the error, or null. This hides
    /// <see cref="Exception.Data"/>, so the name stays the one the other two
    /// clients use.
    /// </summary>
    public new JsonElement? Data { get; }

    /// <summary>Create the exception for an error object.</summary>
    public RpcException(int code, string message, JsonElement? data = null)
        : base($"RPC error {code}: {message}")
    {
      Code = code;
      Data = data;
    }
  }

}  // namespace OpenRoIS.Sdk
