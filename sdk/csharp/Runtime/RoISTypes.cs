// The values the client exchanges with a gateway, in the shapes the RoIS wire
// protocol uses. They are plain classes so they work in Unity and in any .NET
// runtime without further dependencies; the generated OpenRoIS.Interfaces models
// can be layered on top by applications that want them.

#nullable enable

using System;
using System.Collections.Generic;
using System.Text.Json;

namespace OpenRoIS.Sdk
{
    /// <summary>The RoIS return codes, as the gateway spells them.</summary>
    public static class ReturnCodes
    {
        public const string OK = "OK";
        public const string ERROR = "ERROR";
        public const string BAD_PARAMETER = "BAD_PARAMETER";
        public const string UNSUPPORTED = "UNSUPPORTED";
        public const string OUT_OF_RESOURCES = "OUT_OF_RESOURCES";
        public const string TIMEOUT = "TIMEOUT";
    }

    /// <summary>A RoIS Result or Parameter: a named, typed, string-encoded value.</summary>
    public sealed class RoISValue
    {
        public string Name { get; set; } = string.Empty;
        public string DataTypeRef { get; set; } = string.Empty;
        public string Value { get; set; } = string.Empty;

        public RoISValue() { }

        public RoISValue(string name, string dataTypeRef, string value)
        {
            Name = name;
            DataTypeRef = dataTypeRef;
            Value = value;
        }

        internal static RoISValue From(JsonElement element)
        {
            return new RoISValue(
                Json.String(element, "name"),
                Json.String(element, "data_type_ref"),
                Json.String(element, "value"));
        }

        internal Dictionary<string, string> ToWire()
        {
            return new Dictionary<string, string>
            {
                ["name"] = Name,
                ["data_type_ref"] = DataTypeRef,
                ["value"] = Value,
            };
        }
    }

    /// <summary>What execute() answers: the return code, the command id, and immediate results.</summary>
    public sealed class ExecuteResult
    {
        public string ReturnCode { get; set; } = ReturnCodes.OK;
        public string CommandId { get; set; } = string.Empty;
        public List<RoISValue> Results { get; set; } = new List<RoISValue>();
    }

    /// <summary>A component event delivered as rois.event.notify.</summary>
    public sealed class EventNotification
    {
        public string EventId { get; set; } = string.Empty;
        public string SubscribeId { get; set; } = string.Empty;
        public string ComponentRef { get; set; } = string.Empty;
        public string EventType { get; set; } = string.Empty;
        public List<RoISValue> Results { get; set; } = new List<RoISValue>();
    }

    /// <summary>A command completion delivered as rois.command.completed.</summary>
    public sealed class CommandCompletion
    {
        public string CommandId { get; set; } = string.Empty;
        public string Status { get; set; } = string.Empty;
        public List<RoISValue> Results { get; set; } = new List<RoISValue>();
    }

    /// <summary>An engine error delivered as rois.system.notify_error.</summary>
    public sealed class ErrorNotification
    {
        public string ErrorId { get; set; } = string.Empty;
        public string ErrorType { get; set; } = string.Empty;
        public string CommandId { get; set; } = string.Empty;
        public string Message { get; set; } = string.Empty;
    }

    /// <summary>Raised when a RoIS operation answers a return code other than OK.</summary>
    public sealed class RoISException : Exception
    {
        public string ReturnCode { get; }
        public string Method { get; }

        public RoISException(string returnCode, string method)
            : base($"{method} failed with {returnCode}")
        {
            ReturnCode = returnCode;
            Method = method;
        }
    }

    /// <summary>Raised when the gateway answers a JSON-RPC error object.</summary>
    public sealed class RpcException : Exception
    {
        public int Code { get; }

        public RpcException(int code, string message) : base(message)
        {
            Code = code;
        }
    }

    /// <summary>Options for <see cref="RoISClient.ConnectAsync"/>.</summary>
    public sealed class ClientOptions
    {
        /// <summary>
        /// Token presented at the WebSocket upgrade when the gateway authenticates,
        /// as an Authorization: Bearer header.
        /// </summary>
        public string? Token { get; set; }

        /// <summary>How long a request may wait for its response. Default 30 seconds.</summary>
        public TimeSpan RequestTimeout { get; set; } = TimeSpan.FromSeconds(30);

        /// <summary>
        /// Where callbacks (events, completions, errors, close) are delivered. Defaults to
        /// the SynchronizationContext current when ConnectAsync is called, which on Unity's
        /// main thread is the main thread. Null delivers them on the receive thread.
        /// </summary>
        public System.Threading.SynchronizationContext? CallbackContext { get; set; }
            = System.Threading.SynchronizationContext.Current;
    }

    internal static class Json
    {
        public static string String(JsonElement element, string name)
        {
            if (element.ValueKind == JsonValueKind.Object
                && element.TryGetProperty(name, out var value)
                && value.ValueKind == JsonValueKind.String)
            {
                return value.GetString() ?? string.Empty;
            }
            return string.Empty;
        }

        public static List<RoISValue> Values(JsonElement element, string name)
        {
            var list = new List<RoISValue>();
            if (element.ValueKind == JsonValueKind.Object
                && element.TryGetProperty(name, out var array)
                && array.ValueKind == JsonValueKind.Array)
            {
                foreach (var item in array.EnumerateArray())
                {
                    list.Add(RoISValue.From(item));
                }
            }
            return list;
        }

        public static List<string> Strings(JsonElement element, string name)
        {
            var list = new List<string>();
            if (element.ValueKind == JsonValueKind.Object
                && element.TryGetProperty(name, out var array)
                && array.ValueKind == JsonValueKind.Array)
            {
                foreach (var item in array.EnumerateArray())
                {
                    list.Add(item.GetString() ?? string.Empty);
                }
            }
            return list;
        }
    }
}
