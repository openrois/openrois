// GENERATED FROM interfaces/schema — DO NOT EDIT
// Source: CommandRequest.schema.json, DiscoverRequest.schema.json, DiscoverResponse.schema.json, EventEnvelope.schema.json, InvokeResponse.schema.json, QueryRequest.schema.json, QueryResponse.schema.json, SubscribeRequest.schema.json, SubscribeResponse.schema.json
// Generator: scripts/Generator/Program.cs

using System;
using System.Collections.Generic;
using System.Text.Json.Serialization;

namespace OpenRoIS.Interfaces.Bus.Models
{
    // ─── Shared type definitions ($defs) ─────────────────────────────



    /// <summary>
    /// Command operation type for RoIS commands.
    /// 
    /// Not an IDL enum: the IDL uses plain `string` for command_type. OpenRoIS
    /// defines this enum for compile-time safety. The wire values match the
    /// RoIS_Common::Command method names plus `set_parameter` and `execute`, and
    /// the stream control commands of the Audio and Video Streaming profiles.
    /// </summary>
    public enum CommandType
    {
        start,
        stop,
        suspend,
        resume,
        set_parameter,
        execute,
        connect_stream,
        disconnect_stream,
        suspend_stream,
        resume_stream
    }












    /// <summary>
    /// Generic command request sent via ComponentContract.invoke().
    /// 
    /// Carries the same information as a CommandUnit plus the target component_ref.
    /// Typed component models (e.g., NavigationSetParameter) serialize their fields
    /// into arguments/parameters and are wrapped in this generic container.
    /// </summary>
    public sealed class CommandRequest : IEquatable<CommandRequest>
    {
        [JsonPropertyName("component_ref")]
        public string ComponentRef { get; }
        [JsonPropertyName("command_type")]
        public CommandType CommandType { get; }
        [JsonPropertyName("command_id")]
        public string CommandId { get; }
        [JsonPropertyName("arguments")]
        public IReadOnlyList<OpenRoIS.Interfaces.Hri.Argument>? Arguments { get; }
        [JsonPropertyName("parameters")]
        public IReadOnlyList<OpenRoIS.Interfaces.Hri.Parameter>? Parameters { get; }
        [JsonPropertyName("command_unit_sequence")]
        public OpenRoIS.Interfaces.Hri.CommandUnitSequence? CommandUnitSequence { get; }

        public CommandRequest(string componentRef, CommandType commandType, string commandId, IReadOnlyList<OpenRoIS.Interfaces.Hri.Argument>? arguments = null, IReadOnlyList<OpenRoIS.Interfaces.Hri.Parameter>? parameters = null, OpenRoIS.Interfaces.Hri.CommandUnitSequence? commandUnitSequence = null)
        {
            ComponentRef = componentRef;
            CommandType = commandType;
            CommandId = commandId;
            Arguments = arguments;
            Parameters = parameters;
            CommandUnitSequence = commandUnitSequence;
        }

        public bool Equals(CommandRequest? other)
        {
            if (ReferenceEquals(other, this)) return true;
            if (other is null) return false;
            return Equals(ComponentRef, other.ComponentRef) && Equals(CommandType, other.CommandType) && Equals(CommandId, other.CommandId) && Equals(Arguments, other.Arguments) && Equals(Parameters, other.Parameters) && Equals(CommandUnitSequence, other.CommandUnitSequence);
        }

        public override bool Equals(object? obj)
        {
            return Equals(obj as CommandRequest);
        }

        public override int GetHashCode()
        {
            return System.HashCode.Combine(ComponentRef, CommandType, CommandId, Arguments, Parameters, CommandUnitSequence);
        }

        public static bool operator ==(CommandRequest? left, CommandRequest? right)
            => ReferenceEquals(left, right) || (left is not null && left.Equals(right));
        public static bool operator !=(CommandRequest? left, CommandRequest? right)
            => !(left == right);
    }

    /// <summary>
    /// Request to discover components matching a condition.
    /// 
    /// Maps to CommandIF.search(condition, component_ref_list).
    /// </summary>
    public sealed class DiscoverRequest : IEquatable<DiscoverRequest>
    {
        [JsonPropertyName("condition")]
        public string Condition { get; }

        public DiscoverRequest(string condition = "")
        {
            Condition = condition;
        }

        public bool Equals(DiscoverRequest? other)
        {
            if (ReferenceEquals(other, this)) return true;
            if (other is null) return false;
            return Equals(Condition, other.Condition);
        }

        public override bool Equals(object? obj)
        {
            return Equals(obj as DiscoverRequest);
        }

        public override int GetHashCode()
        {
            return System.HashCode.Combine(Condition);
        }

        public static bool operator ==(DiscoverRequest? left, DiscoverRequest? right)
            => ReferenceEquals(left, right) || (left is not null && left.Equals(right));
        public static bool operator !=(DiscoverRequest? left, DiscoverRequest? right)
            => !(left == right);
    }

    /// <summary>Response from discover() carrying matching component references.</summary>
    public sealed class DiscoverResponse : IEquatable<DiscoverResponse>
    {
        [JsonPropertyName("return_code")]
        public OpenRoIS.Interfaces.Hri.ReturnCode ReturnCode { get; }
        [JsonPropertyName("component_ref_list")]
        public IReadOnlyList<string>? ComponentRefList { get; }

        public DiscoverResponse(OpenRoIS.Interfaces.Hri.ReturnCode returnCode = OpenRoIS.Interfaces.Hri.ReturnCode.OK, IReadOnlyList<string>? componentRefList = null)
        {
            ReturnCode = returnCode;
            ComponentRefList = componentRefList;
        }

        public bool Equals(DiscoverResponse? other)
        {
            if (ReferenceEquals(other, this)) return true;
            if (other is null) return false;
            return Equals(ReturnCode, other.ReturnCode) && Equals(ComponentRefList, other.ComponentRefList);
        }

        public override bool Equals(object? obj)
        {
            return Equals(obj as DiscoverResponse);
        }

        public override int GetHashCode()
        {
            return System.HashCode.Combine(ReturnCode, ComponentRefList);
        }

        public static bool operator ==(DiscoverResponse? left, DiscoverResponse? right)
            => ReferenceEquals(left, right) || (left is not null && left.Equals(right));
        public static bool operator !=(DiscoverResponse? left, DiscoverResponse? right)
            => !(left == right);
    }

    /// <summary>
    /// Generic event envelope delivered to an EventSink.
    /// 
    /// The ComponentContract emits this for every async notification: component events,
    /// command completion, errors, and stream status changes. The engine/gateway
    /// inspects event_type and dispatches to the appropriate ServiceApplicationBase
    /// callback.
    /// </summary>
    public sealed class EventEnvelope : IEquatable<EventEnvelope>
    {
        [JsonPropertyName("event_id")]
        public string EventId { get; }
        [JsonPropertyName("event_type")]
        public string EventType { get; }
        [JsonPropertyName("subscribe_id")]
        public string SubscribeId { get; }
        [JsonPropertyName("component_ref")]
        public string ComponentRef { get; }
        [JsonPropertyName("expire")]
        public string Expire { get; }
        [JsonPropertyName("payload")]
        public IReadOnlyList<OpenRoIS.Interfaces.Hri.Result>? Payload { get; }
        [JsonPropertyName("error_type")]
        public OpenRoIS.Interfaces.Service.ErrorType? ErrorType { get; }
        [JsonPropertyName("completed_status")]
        public OpenRoIS.Interfaces.Service.CompletedStatus? CompletedStatus { get; }
        [JsonPropertyName("stream_status")]
        public OpenRoIS.Interfaces.Common.StreamStatus? StreamStatus { get; }
        [JsonPropertyName("component_status")]
        public OpenRoIS.Interfaces.Common.ComponentStatus? ComponentStatus { get; }

        public EventEnvelope(string eventId, string eventType, string subscribeId = "", string componentRef = "", string expire = "", IReadOnlyList<OpenRoIS.Interfaces.Hri.Result>? payload = null, OpenRoIS.Interfaces.Service.ErrorType? errorType = null, OpenRoIS.Interfaces.Service.CompletedStatus? completedStatus = null, OpenRoIS.Interfaces.Common.StreamStatus? streamStatus = null, OpenRoIS.Interfaces.Common.ComponentStatus? componentStatus = null)
        {
            EventId = eventId;
            EventType = eventType;
            SubscribeId = subscribeId;
            ComponentRef = componentRef;
            Expire = expire;
            Payload = payload;
            ErrorType = errorType;
            CompletedStatus = completedStatus;
            StreamStatus = streamStatus;
            ComponentStatus = componentStatus;
        }

        public bool Equals(EventEnvelope? other)
        {
            if (ReferenceEquals(other, this)) return true;
            if (other is null) return false;
            return Equals(EventId, other.EventId) && Equals(EventType, other.EventType) && Equals(SubscribeId, other.SubscribeId) && Equals(ComponentRef, other.ComponentRef) && Equals(Expire, other.Expire) && Equals(Payload, other.Payload) && Equals(ErrorType, other.ErrorType) && Equals(CompletedStatus, other.CompletedStatus) && Equals(StreamStatus, other.StreamStatus) && Equals(ComponentStatus, other.ComponentStatus);
        }

        public override bool Equals(object? obj)
        {
            return Equals(obj as EventEnvelope);
        }

        public override int GetHashCode()
        {
            return System.HashCode.Combine(System.HashCode.Combine(EventId, EventType, SubscribeId, ComponentRef, Expire, Payload, ErrorType, CompletedStatus), StreamStatus, ComponentStatus);
        }

        public static bool operator ==(EventEnvelope? left, EventEnvelope? right)
            => ReferenceEquals(left, right) || (left is not null && left.Equals(right));
        public static bool operator !=(EventEnvelope? left, EventEnvelope? right)
            => !(left == right);
    }

    /// <summary>Response from ComponentContract.invoke().</summary>
    public sealed class InvokeResponse : IEquatable<InvokeResponse>
    {
        [JsonPropertyName("return_code")]
        public OpenRoIS.Interfaces.Hri.ReturnCode ReturnCode { get; }
        [JsonPropertyName("command_id")]
        public string CommandId { get; }
        [JsonPropertyName("results")]
        public IReadOnlyList<OpenRoIS.Interfaces.Hri.Result>? Results { get; }

        public InvokeResponse(OpenRoIS.Interfaces.Hri.ReturnCode returnCode = OpenRoIS.Interfaces.Hri.ReturnCode.OK, string commandId = "", IReadOnlyList<OpenRoIS.Interfaces.Hri.Result>? results = null)
        {
            ReturnCode = returnCode;
            CommandId = commandId;
            Results = results;
        }

        public bool Equals(InvokeResponse? other)
        {
            if (ReferenceEquals(other, this)) return true;
            if (other is null) return false;
            return Equals(ReturnCode, other.ReturnCode) && Equals(CommandId, other.CommandId) && Equals(Results, other.Results);
        }

        public override bool Equals(object? obj)
        {
            return Equals(obj as InvokeResponse);
        }

        public override int GetHashCode()
        {
            return System.HashCode.Combine(ReturnCode, CommandId, Results);
        }

        public static bool operator ==(InvokeResponse? left, InvokeResponse? right)
            => ReferenceEquals(left, right) || (left is not null && left.Equals(right));
        public static bool operator !=(InvokeResponse? left, InvokeResponse? right)
            => !(left == right);
    }

    /// <summary>
    /// Generic query request sent via ComponentContract.query().
    /// 
    /// Maps to QueryIF.query(query_type, condition, results) and
    /// RoIS_Common.component_status(status).
    /// </summary>
    public sealed class QueryRequest : IEquatable<QueryRequest>
    {
        [JsonPropertyName("component_ref")]
        public string ComponentRef { get; }
        [JsonPropertyName("query_type")]
        public string QueryType { get; }
        [JsonPropertyName("condition")]
        public string Condition { get; }

        public QueryRequest(string componentRef, string queryType, string condition = "")
        {
            ComponentRef = componentRef;
            QueryType = queryType;
            Condition = condition;
        }

        public bool Equals(QueryRequest? other)
        {
            if (ReferenceEquals(other, this)) return true;
            if (other is null) return false;
            return Equals(ComponentRef, other.ComponentRef) && Equals(QueryType, other.QueryType) && Equals(Condition, other.Condition);
        }

        public override bool Equals(object? obj)
        {
            return Equals(obj as QueryRequest);
        }

        public override int GetHashCode()
        {
            return System.HashCode.Combine(ComponentRef, QueryType, Condition);
        }

        public static bool operator ==(QueryRequest? left, QueryRequest? right)
            => ReferenceEquals(left, right) || (left is not null && left.Equals(right));
        public static bool operator !=(QueryRequest? left, QueryRequest? right)
            => !(left == right);
    }

    /// <summary>Response from ComponentContract.query().</summary>
    public sealed class QueryResponse : IEquatable<QueryResponse>
    {
        [JsonPropertyName("return_code")]
        public OpenRoIS.Interfaces.Hri.ReturnCode ReturnCode { get; }
        [JsonPropertyName("results")]
        public IReadOnlyList<OpenRoIS.Interfaces.Hri.Result>? Results { get; }

        public QueryResponse(OpenRoIS.Interfaces.Hri.ReturnCode returnCode = OpenRoIS.Interfaces.Hri.ReturnCode.OK, IReadOnlyList<OpenRoIS.Interfaces.Hri.Result>? results = null)
        {
            ReturnCode = returnCode;
            Results = results;
        }

        public bool Equals(QueryResponse? other)
        {
            if (ReferenceEquals(other, this)) return true;
            if (other is null) return false;
            return Equals(ReturnCode, other.ReturnCode) && Equals(Results, other.Results);
        }

        public override bool Equals(object? obj)
        {
            return Equals(obj as QueryResponse);
        }

        public override int GetHashCode()
        {
            return System.HashCode.Combine(ReturnCode, Results);
        }

        public static bool operator ==(QueryResponse? left, QueryResponse? right)
            => ReferenceEquals(left, right) || (left is not null && left.Equals(right));
        public static bool operator !=(QueryResponse? left, QueryResponse? right)
            => !(left == right);
    }

    /// <summary>
    /// Request to subscribe to events matching a condition.
    /// 
    /// Maps to EventIF.subscribe(event_type, condition, subscribe_id).
    /// </summary>
    public sealed class SubscribeRequest : IEquatable<SubscribeRequest>
    {
        [JsonPropertyName("component_ref")]
        public string ComponentRef { get; }
        [JsonPropertyName("event_type")]
        public string EventType { get; }
        [JsonPropertyName("condition")]
        public string Condition { get; }

        public SubscribeRequest(string componentRef, string eventType, string condition = "")
        {
            ComponentRef = componentRef;
            EventType = eventType;
            Condition = condition;
        }

        public bool Equals(SubscribeRequest? other)
        {
            if (ReferenceEquals(other, this)) return true;
            if (other is null) return false;
            return Equals(ComponentRef, other.ComponentRef) && Equals(EventType, other.EventType) && Equals(Condition, other.Condition);
        }

        public override bool Equals(object? obj)
        {
            return Equals(obj as SubscribeRequest);
        }

        public override int GetHashCode()
        {
            return System.HashCode.Combine(ComponentRef, EventType, Condition);
        }

        public static bool operator ==(SubscribeRequest? left, SubscribeRequest? right)
            => ReferenceEquals(left, right) || (left is not null && left.Equals(right));
        public static bool operator !=(SubscribeRequest? left, SubscribeRequest? right)
            => !(left == right);
    }

    /// <summary>Response from ComponentContract.subscribe().</summary>
    public sealed class SubscribeResponse : IEquatable<SubscribeResponse>
    {
        [JsonPropertyName("return_code")]
        public OpenRoIS.Interfaces.Hri.ReturnCode ReturnCode { get; }
        [JsonPropertyName("subscribe_id")]
        public string SubscribeId { get; }

        public SubscribeResponse(OpenRoIS.Interfaces.Hri.ReturnCode returnCode = OpenRoIS.Interfaces.Hri.ReturnCode.OK, string subscribeId = "")
        {
            ReturnCode = returnCode;
            SubscribeId = subscribeId;
        }

        public bool Equals(SubscribeResponse? other)
        {
            if (ReferenceEquals(other, this)) return true;
            if (other is null) return false;
            return Equals(ReturnCode, other.ReturnCode) && Equals(SubscribeId, other.SubscribeId);
        }

        public override bool Equals(object? obj)
        {
            return Equals(obj as SubscribeResponse);
        }

        public override int GetHashCode()
        {
            return System.HashCode.Combine(ReturnCode, SubscribeId);
        }

        public static bool operator ==(SubscribeResponse? left, SubscribeResponse? right)
            => ReferenceEquals(left, right) || (left is not null && left.Equals(right));
        public static bool operator !=(SubscribeResponse? left, SubscribeResponse? right)
            => !(left == right);
    }

}
