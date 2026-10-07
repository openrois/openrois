// GENERATED FROM interfaces/schema — DO NOT EDIT
// Source: CompletedParams.schema.json, CompletedStatus.schema.json, ErrorType.schema.json, NotifyErrorParams.schema.json, NotifyEventParams.schema.json, ProfileChangedParams.schema.json
// Generator: scripts/Generator/Program.cs

using System;
using System.Collections.Generic;
using System.Text.Json.Serialization;

namespace OpenRoIS.Interfaces.Service
{
    // ─── Shared type definitions ($defs) ─────────────────────────────


    /// <summary>
    /// Status of a completed command execution.
    /// 
    /// Maps to RoIS_Service::Completed_Status in the IDL.
    /// 
    /// OK: Command completed successfully.
    /// ERROR: Command completed with an error.
    /// ABORT: Command was aborted.
    /// OUT_OF_RESOURCES: Command failed due to resource exhaustion.
    /// TIMEOUT: Command timed out before completion.
    /// </summary>
    public enum CompletedStatus
    {
        OK,
        ERROR,
        ABORT,
        OUT_OF_RESOURCES,
        TIMEOUT
    }

    /// <summary>
    /// Classification of error notifications.
    /// 
    /// Maps to RoIS_Service::ErrorType in the IDL.
    /// 
    /// ENGINE_INTERNAL_ERROR: Error originating from the HRI Engine itself.
    /// COMPONENT_INTERNAL_ERROR: Error originating from a component.
    /// COMPONENT_NOT_RESPONDING: A component failed to respond within timeout.
    /// USER_DEFINED_ERROR: Application-specific error.
    /// </summary>
    public enum ErrorType
    {
        ENGINE_INTERNAL_ERROR,
        COMPONENT_INTERNAL_ERROR,
        COMPONENT_NOT_RESPONDING,
        USER_DEFINED_ERROR
    }






    /// <summary>
    /// Params of the rois.command.completed notification.
    /// 
    /// Maps to ServiceApplicationBase::completed(in command_id, in status). The results
    /// come from CommandIF::get_command_result(command_id).
    /// 
    /// Attributes:
    ///     command_id: The command that ended, as the application named it.
    ///     status: How the command ended.
    /// </summary>
    public sealed class CompletedParams : IEquatable<CompletedParams>
    {
        [JsonPropertyName("command_id")]
        public string CommandId { get; }
        [JsonPropertyName("status")]
        public CompletedStatus Status { get; }

        public CompletedParams(string commandId, CompletedStatus status)
        {
            CommandId = commandId;
            Status = status;
        }

        public bool Equals(CompletedParams? other)
        {
            if (ReferenceEquals(other, this)) return true;
            if (other is null) return false;
            return Equals(CommandId, other.CommandId) && Equals(Status, other.Status);
        }

        public override bool Equals(object? obj)
        {
            return Equals(obj as CompletedParams);
        }

        public override int GetHashCode()
        {
            return System.HashCode.Combine(CommandId, Status);
        }

        public static bool operator ==(CompletedParams? left, CompletedParams? right)
            => ReferenceEquals(left, right) || (left is not null && left.Equals(right));
        public static bool operator !=(CompletedParams? left, CompletedParams? right)
            => !(left == right);
    }

    /// <summary>
    /// Params of the rois.system.notify_error notification.
    /// 
    /// Maps to ServiceApplicationBase::notify_error(in error_id, in error_type). The
    /// details come from SystemIF::get_error_detail(error_id).
    /// 
    /// Attributes:
    ///     error_id: Identifier of this error, for get_error_detail.
    ///     error_type: Classification of the error.
    /// </summary>
    public sealed class NotifyErrorParams : IEquatable<NotifyErrorParams>
    {
        [JsonPropertyName("error_id")]
        public string ErrorId { get; }
        [JsonPropertyName("error_type")]
        public ErrorType ErrorType { get; }

        public NotifyErrorParams(string errorId, ErrorType errorType)
        {
            ErrorId = errorId;
            ErrorType = errorType;
        }

        public bool Equals(NotifyErrorParams? other)
        {
            if (ReferenceEquals(other, this)) return true;
            if (other is null) return false;
            return Equals(ErrorId, other.ErrorId) && Equals(ErrorType, other.ErrorType);
        }

        public override bool Equals(object? obj)
        {
            return Equals(obj as NotifyErrorParams);
        }

        public override int GetHashCode()
        {
            return System.HashCode.Combine(ErrorId, ErrorType);
        }

        public static bool operator ==(NotifyErrorParams? left, NotifyErrorParams? right)
            => ReferenceEquals(left, right) || (left is not null && left.Equals(right));
        public static bool operator !=(NotifyErrorParams? left, NotifyErrorParams? right)
            => !(left == right);
    }

    /// <summary>
    /// Params of the rois.event.notify_event notification.
    /// 
    /// Maps to ServiceApplicationBase::notify_event(in event_id, in event_type,
    /// in subscribe_id, in expire). The payload also comes from
    /// EventIF::get_event_detail(event_id) until the event expires.
    /// 
    /// Attributes:
    ///     event_id: Identifier of this event, for get_event_detail.
    ///     event_type: The type of event (e.g., 'person_detected').
    ///     subscribe_id: The subscription this event matches.
    ///     expire: ISO 8601 datetime after which get_event_detail no longer has the
    ///         event, or empty if it does not expire.
    ///     results: The event payload. An OpenRoIS extension that saves one
    ///         get_event_detail round trip per event.
    /// </summary>
    public sealed class NotifyEventParams : IEquatable<NotifyEventParams>
    {
        [JsonPropertyName("event_id")]
        public string EventId { get; }
        [JsonPropertyName("event_type")]
        public string EventType { get; }
        [JsonPropertyName("subscribe_id")]
        public string SubscribeId { get; }
        [JsonPropertyName("expire")]
        public string Expire { get; }
        [JsonPropertyName("results")]
        public IReadOnlyList<OpenRoIS.Interfaces.Hri.Result>? Results { get; }

        public NotifyEventParams(string eventId, string eventType, string subscribeId, string expire = "", IReadOnlyList<OpenRoIS.Interfaces.Hri.Result>? results = null)
        {
            EventId = eventId;
            EventType = eventType;
            SubscribeId = subscribeId;
            Expire = expire;
            Results = results;
        }

        public bool Equals(NotifyEventParams? other)
        {
            if (ReferenceEquals(other, this)) return true;
            if (other is null) return false;
            return Equals(EventId, other.EventId) && Equals(EventType, other.EventType) && Equals(SubscribeId, other.SubscribeId) && Equals(Expire, other.Expire) && Equals(Results, other.Results);
        }

        public override bool Equals(object? obj)
        {
            return Equals(obj as NotifyEventParams);
        }

        public override int GetHashCode()
        {
            return System.HashCode.Combine(EventId, EventType, SubscribeId, Expire, Results);
        }

        public static bool operator ==(NotifyEventParams? left, NotifyEventParams? right)
            => ReferenceEquals(left, right) || (left is not null && left.Equals(right));
        public static bool operator !=(NotifyEventParams? left, NotifyEventParams? right)
            => !(left == right);
    }

    /// <summary>
    /// Params of the rois.system.profile_changed notification.
    /// 
    /// Not part of RoIS: an OpenRoIS extension. The engine sends it when its profile
    /// changes, for example when a child engine connects or disconnects, so a client
    /// calls get_profile again instead of polling it. It carries no params.
    /// </summary>
    public sealed class ProfileChangedParams { }

}
