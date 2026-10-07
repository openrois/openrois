// GENERATED FROM interfaces/schema — DO NOT EDIT
// Source: BindAnyParams.schema.json, BindAnyResult.schema.json, BindParams.schema.json, BindResult.schema.json, ConnectParams.schema.json, ConnectResult.schema.json, DisconnectParams.schema.json, DisconnectResult.schema.json, ExecuteParams.schema.json, ExecuteResult.schema.json, GetCommandResultParams.schema.json, GetCommandResultResult.schema.json, GetErrorDetailParams.schema.json, GetErrorDetailResult.schema.json, GetEventDetailParams.schema.json, GetEventDetailResult.schema.json, GetParameterParams.schema.json, GetParameterResult.schema.json, GetProfileParams.schema.json, GetProfileResult.schema.json, QueryParams.schema.json, QueryResult.schema.json, ReleaseParams.schema.json, ReleaseResult.schema.json, SearchParams.schema.json, SearchResult.schema.json, SetParameterParams.schema.json, SetParameterResult.schema.json, SubscribeParams.schema.json, SubscribeResult.schema.json, UnsubscribeParams.schema.json, UnsubscribeResult.schema.json
// Generator: scripts/Generator/Program.cs

using System;
using System.Collections.Generic;
using System.Text.Json.Serialization;

namespace OpenRoIS.Interfaces.Catalog
{
    // ─── Shared type definitions ($defs) ─────────────────────────────





    /// <summary>
    /// Command operation type for RoIS commands.
    /// 
    /// Not an IDL enum — the IDL uses plain `string` for command_type. OpenRoIS
    /// defines this enum for compile-time safety. The wire values match the
    /// RoIS_Common::Command method names plus `set_parameter` and `execute`.
    /// </summary>
    public enum CommandType
    {
        start,
        stop,
        suspend,
        resume,
        set_parameter,
        execute
    }









    /// <summary>
    /// Params of rois.command.bind_any.
    /// 
    /// Maps to CommandIF::bind_any(in condition, out component_ref).
    /// 
    /// Attributes:
    ///     condition: Filter on the components the engine may choose from.
    /// </summary>
    public sealed class BindAnyParams : IEquatable<BindAnyParams>
    {
        [JsonPropertyName("condition")]
        public string Condition { get; }

        public BindAnyParams(string condition = "")
        {
            Condition = condition;
        }

        public bool Equals(BindAnyParams? other)
        {
            if (ReferenceEquals(other, this)) return true;
            if (other is null) return false;
            return Equals(Condition, other.Condition);
        }

        public override bool Equals(object? obj)
        {
            return Equals(obj as BindAnyParams);
        }

        public override int GetHashCode()
        {
            return System.HashCode.Combine(Condition);
        }

        public static bool operator ==(BindAnyParams? left, BindAnyParams? right)
            => ReferenceEquals(left, right) || (left is not null && left.Equals(right));
        public static bool operator !=(BindAnyParams? left, BindAnyParams? right)
            => !(left == right);
    }

    /// <summary>
    /// Result of rois.command.bind_any.
    /// 
    /// Maps to CommandIF::bind_any(in condition, out component_ref).
    /// 
    /// Attributes:
    ///     return_code: Outcome of the operation.
    ///     component_ref: The component the engine reserved. Empty when return_code is
    ///         not OK.
    /// </summary>
    public sealed class BindAnyResult : IEquatable<BindAnyResult>
    {
        [JsonPropertyName("return_code")]
        public OpenRoIS.Interfaces.Hri.ReturnCode ReturnCode { get; }
        [JsonPropertyName("component_ref")]
        public string ComponentRef { get; }

        public BindAnyResult(OpenRoIS.Interfaces.Hri.ReturnCode returnCode, string componentRef = "")
        {
            ReturnCode = returnCode;
            ComponentRef = componentRef;
        }

        public bool Equals(BindAnyResult? other)
        {
            if (ReferenceEquals(other, this)) return true;
            if (other is null) return false;
            return Equals(ReturnCode, other.ReturnCode) && Equals(ComponentRef, other.ComponentRef);
        }

        public override bool Equals(object? obj)
        {
            return Equals(obj as BindAnyResult);
        }

        public override int GetHashCode()
        {
            return System.HashCode.Combine(ReturnCode, ComponentRef);
        }

        public static bool operator ==(BindAnyResult? left, BindAnyResult? right)
            => ReferenceEquals(left, right) || (left is not null && left.Equals(right));
        public static bool operator !=(BindAnyResult? left, BindAnyResult? right)
            => !(left == right);
    }

    /// <summary>
    /// Params of rois.command.bind.
    /// 
    /// Maps to CommandIF::bind(in component_ref).
    /// 
    /// Attributes:
    ///     component_ref: The component to reserve for this client.
    /// </summary>
    public sealed class BindParams : IEquatable<BindParams>
    {
        [JsonPropertyName("component_ref")]
        public string ComponentRef { get; }

        public BindParams(string componentRef)
        {
            ComponentRef = componentRef;
        }

        public bool Equals(BindParams? other)
        {
            if (ReferenceEquals(other, this)) return true;
            if (other is null) return false;
            return Equals(ComponentRef, other.ComponentRef);
        }

        public override bool Equals(object? obj)
        {
            return Equals(obj as BindParams);
        }

        public override int GetHashCode()
        {
            return System.HashCode.Combine(ComponentRef);
        }

        public static bool operator ==(BindParams? left, BindParams? right)
            => ReferenceEquals(left, right) || (left is not null && left.Equals(right));
        public static bool operator !=(BindParams? left, BindParams? right)
            => !(left == right);
    }

    /// <summary>
    /// Result of rois.command.bind.
    /// 
    /// Maps to CommandIF::bind(in component_ref).
    /// 
    /// Attributes:
    ///     return_code: Outcome of the operation. OUT_OF_RESOURCES when another client
    ///         holds the component.
    /// </summary>
    public sealed class BindResult : IEquatable<BindResult>
    {
        [JsonPropertyName("return_code")]
        public OpenRoIS.Interfaces.Hri.ReturnCode ReturnCode { get; }

        public BindResult(OpenRoIS.Interfaces.Hri.ReturnCode returnCode)
        {
            ReturnCode = returnCode;
        }

        public bool Equals(BindResult? other)
        {
            if (ReferenceEquals(other, this)) return true;
            if (other is null) return false;
            return Equals(ReturnCode, other.ReturnCode);
        }

        public override bool Equals(object? obj)
        {
            return Equals(obj as BindResult);
        }

        public override int GetHashCode()
        {
            return System.HashCode.Combine(ReturnCode);
        }

        public static bool operator ==(BindResult? left, BindResult? right)
            => ReferenceEquals(left, right) || (left is not null && left.Equals(right));
        public static bool operator !=(BindResult? left, BindResult? right)
            => !(left == right);
    }

    /// <summary>
    /// Params of rois.system.connect.
    /// 
    /// Maps to SystemIF::connect(), which takes no arguments. A request may omit params.
    /// </summary>
    public sealed class ConnectParams { }

    /// <summary>
    /// Result of rois.system.connect.
    /// 
    /// Maps to SystemIF::connect().
    /// 
    /// Attributes:
    ///     return_code: Outcome of the operation.
    /// </summary>
    public sealed class ConnectResult : IEquatable<ConnectResult>
    {
        [JsonPropertyName("return_code")]
        public OpenRoIS.Interfaces.Hri.ReturnCode ReturnCode { get; }

        public ConnectResult(OpenRoIS.Interfaces.Hri.ReturnCode returnCode)
        {
            ReturnCode = returnCode;
        }

        public bool Equals(ConnectResult? other)
        {
            if (ReferenceEquals(other, this)) return true;
            if (other is null) return false;
            return Equals(ReturnCode, other.ReturnCode);
        }

        public override bool Equals(object? obj)
        {
            return Equals(obj as ConnectResult);
        }

        public override int GetHashCode()
        {
            return System.HashCode.Combine(ReturnCode);
        }

        public static bool operator ==(ConnectResult? left, ConnectResult? right)
            => ReferenceEquals(left, right) || (left is not null && left.Equals(right));
        public static bool operator !=(ConnectResult? left, ConnectResult? right)
            => !(left == right);
    }

    /// <summary>
    /// Params of rois.system.disconnect.
    /// 
    /// Maps to SystemIF::disconnect(), which takes no arguments. A request may omit params.
    /// </summary>
    public sealed class DisconnectParams { }

    /// <summary>
    /// Result of rois.system.disconnect.
    /// 
    /// Maps to SystemIF::disconnect().
    /// 
    /// Attributes:
    ///     return_code: Outcome of the operation.
    /// </summary>
    public sealed class DisconnectResult : IEquatable<DisconnectResult>
    {
        [JsonPropertyName("return_code")]
        public OpenRoIS.Interfaces.Hri.ReturnCode ReturnCode { get; }

        public DisconnectResult(OpenRoIS.Interfaces.Hri.ReturnCode returnCode)
        {
            ReturnCode = returnCode;
        }

        public bool Equals(DisconnectResult? other)
        {
            if (ReferenceEquals(other, this)) return true;
            if (other is null) return false;
            return Equals(ReturnCode, other.ReturnCode);
        }

        public override bool Equals(object? obj)
        {
            return Equals(obj as DisconnectResult);
        }

        public override int GetHashCode()
        {
            return System.HashCode.Combine(ReturnCode);
        }

        public static bool operator ==(DisconnectResult? left, DisconnectResult? right)
            => ReferenceEquals(left, right) || (left is not null && left.Equals(right));
        public static bool operator !=(DisconnectResult? left, DisconnectResult? right)
            => !(left == right);
    }

    /// <summary>
    /// Params of rois.command.execute.
    /// 
    /// Maps to CommandIF::execute(in command_unit_list). The application names every
    /// command with its own command_id, and completed notifications report each one.
    /// The engine rejects a command_id it already tracks with BAD_PARAMETER.
    /// 
    /// Attributes:
    ///     command_unit_list: Commands to run in order. A ConcurrentCommands item runs
    ///         its commands at the same time.
    /// </summary>
    public sealed class ExecuteParams : IEquatable<ExecuteParams>
    {
        [JsonPropertyName("command_unit_list")]
        public IReadOnlyList<OpenRoIS.Interfaces.Hri.ICommandUnitSequenceItem> CommandUnitList { get; }

        public ExecuteParams(IReadOnlyList<OpenRoIS.Interfaces.Hri.ICommandUnitSequenceItem> commandUnitList)
        {
            CommandUnitList = commandUnitList;
        }

        public bool Equals(ExecuteParams? other)
        {
            if (ReferenceEquals(other, this)) return true;
            if (other is null) return false;
            return Equals(CommandUnitList, other.CommandUnitList);
        }

        public override bool Equals(object? obj)
        {
            return Equals(obj as ExecuteParams);
        }

        public override int GetHashCode()
        {
            return System.HashCode.Combine(CommandUnitList);
        }

        public static bool operator ==(ExecuteParams? left, ExecuteParams? right)
            => ReferenceEquals(left, right) || (left is not null && left.Equals(right));
        public static bool operator !=(ExecuteParams? left, ExecuteParams? right)
            => !(left == right);
    }

    /// <summary>
    /// Result of rois.command.execute.
    /// 
    /// Maps to CommandIF::execute(in command_unit_list), which has no out parameters.
    /// 
    /// Attributes:
    ///     return_code: Whether the engine accepted the commands. Completed
    ///         notifications report how each command ended.
    /// </summary>
    public sealed class ExecuteResult : IEquatable<ExecuteResult>
    {
        [JsonPropertyName("return_code")]
        public OpenRoIS.Interfaces.Hri.ReturnCode ReturnCode { get; }

        public ExecuteResult(OpenRoIS.Interfaces.Hri.ReturnCode returnCode)
        {
            ReturnCode = returnCode;
        }

        public bool Equals(ExecuteResult? other)
        {
            if (ReferenceEquals(other, this)) return true;
            if (other is null) return false;
            return Equals(ReturnCode, other.ReturnCode);
        }

        public override bool Equals(object? obj)
        {
            return Equals(obj as ExecuteResult);
        }

        public override int GetHashCode()
        {
            return System.HashCode.Combine(ReturnCode);
        }

        public static bool operator ==(ExecuteResult? left, ExecuteResult? right)
            => ReferenceEquals(left, right) || (left is not null && left.Equals(right));
        public static bool operator !=(ExecuteResult? left, ExecuteResult? right)
            => !(left == right);
    }

    /// <summary>
    /// Params of rois.command.get_command_result.
    /// 
    /// Maps to CommandIF::get_command_result(in command_id, in condition, out results).
    /// 
    /// Attributes:
    ///     command_id: The command whose results to read.
    ///     condition: Filter on the results. Empty means no filter.
    /// </summary>
    public sealed class GetCommandResultParams : IEquatable<GetCommandResultParams>
    {
        [JsonPropertyName("command_id")]
        public string CommandId { get; }
        [JsonPropertyName("condition")]
        public string Condition { get; }

        public GetCommandResultParams(string commandId, string condition = "")
        {
            CommandId = commandId;
            Condition = condition;
        }

        public bool Equals(GetCommandResultParams? other)
        {
            if (ReferenceEquals(other, this)) return true;
            if (other is null) return false;
            return Equals(CommandId, other.CommandId) && Equals(Condition, other.Condition);
        }

        public override bool Equals(object? obj)
        {
            return Equals(obj as GetCommandResultParams);
        }

        public override int GetHashCode()
        {
            return System.HashCode.Combine(CommandId, Condition);
        }

        public static bool operator ==(GetCommandResultParams? left, GetCommandResultParams? right)
            => ReferenceEquals(left, right) || (left is not null && left.Equals(right));
        public static bool operator !=(GetCommandResultParams? left, GetCommandResultParams? right)
            => !(left == right);
    }

    /// <summary>
    /// Result of rois.command.get_command_result.
    /// 
    /// Maps to CommandIF::get_command_result(in command_id, in condition, out results).
    /// 
    /// Attributes:
    ///     return_code: Outcome of the operation.
    ///     results: Results of the command.
    /// </summary>
    public sealed class GetCommandResultResult : IEquatable<GetCommandResultResult>
    {
        [JsonPropertyName("return_code")]
        public OpenRoIS.Interfaces.Hri.ReturnCode ReturnCode { get; }
        [JsonPropertyName("results")]
        public IReadOnlyList<OpenRoIS.Interfaces.Hri.Result>? Results { get; }

        public GetCommandResultResult(OpenRoIS.Interfaces.Hri.ReturnCode returnCode, IReadOnlyList<OpenRoIS.Interfaces.Hri.Result>? results = null)
        {
            ReturnCode = returnCode;
            Results = results;
        }

        public bool Equals(GetCommandResultResult? other)
        {
            if (ReferenceEquals(other, this)) return true;
            if (other is null) return false;
            return Equals(ReturnCode, other.ReturnCode) && Equals(Results, other.Results);
        }

        public override bool Equals(object? obj)
        {
            return Equals(obj as GetCommandResultResult);
        }

        public override int GetHashCode()
        {
            return System.HashCode.Combine(ReturnCode, Results);
        }

        public static bool operator ==(GetCommandResultResult? left, GetCommandResultResult? right)
            => ReferenceEquals(left, right) || (left is not null && left.Equals(right));
        public static bool operator !=(GetCommandResultResult? left, GetCommandResultResult? right)
            => !(left == right);
    }

    /// <summary>
    /// Params of rois.system.get_error_detail.
    /// 
    /// Maps to SystemIF::get_error_detail(in error_id, in condition, out results).
    /// 
    /// Attributes:
    ///     error_id: The error_id from a notify_error notification.
    ///     condition: Filter on the results. Empty means no filter.
    /// </summary>
    public sealed class GetErrorDetailParams : IEquatable<GetErrorDetailParams>
    {
        [JsonPropertyName("error_id")]
        public string ErrorId { get; }
        [JsonPropertyName("condition")]
        public string Condition { get; }

        public GetErrorDetailParams(string errorId, string condition = "")
        {
            ErrorId = errorId;
            Condition = condition;
        }

        public bool Equals(GetErrorDetailParams? other)
        {
            if (ReferenceEquals(other, this)) return true;
            if (other is null) return false;
            return Equals(ErrorId, other.ErrorId) && Equals(Condition, other.Condition);
        }

        public override bool Equals(object? obj)
        {
            return Equals(obj as GetErrorDetailParams);
        }

        public override int GetHashCode()
        {
            return System.HashCode.Combine(ErrorId, Condition);
        }

        public static bool operator ==(GetErrorDetailParams? left, GetErrorDetailParams? right)
            => ReferenceEquals(left, right) || (left is not null && left.Equals(right));
        public static bool operator !=(GetErrorDetailParams? left, GetErrorDetailParams? right)
            => !(left == right);
    }

    /// <summary>
    /// Result of rois.system.get_error_detail.
    /// 
    /// Maps to SystemIF::get_error_detail(in error_id, in condition, out results).
    /// 
    /// Attributes:
    ///     return_code: Outcome of the operation.
    ///     results: Details of the error.
    /// </summary>
    public sealed class GetErrorDetailResult : IEquatable<GetErrorDetailResult>
    {
        [JsonPropertyName("return_code")]
        public OpenRoIS.Interfaces.Hri.ReturnCode ReturnCode { get; }
        [JsonPropertyName("results")]
        public IReadOnlyList<OpenRoIS.Interfaces.Hri.Result>? Results { get; }

        public GetErrorDetailResult(OpenRoIS.Interfaces.Hri.ReturnCode returnCode, IReadOnlyList<OpenRoIS.Interfaces.Hri.Result>? results = null)
        {
            ReturnCode = returnCode;
            Results = results;
        }

        public bool Equals(GetErrorDetailResult? other)
        {
            if (ReferenceEquals(other, this)) return true;
            if (other is null) return false;
            return Equals(ReturnCode, other.ReturnCode) && Equals(Results, other.Results);
        }

        public override bool Equals(object? obj)
        {
            return Equals(obj as GetErrorDetailResult);
        }

        public override int GetHashCode()
        {
            return System.HashCode.Combine(ReturnCode, Results);
        }

        public static bool operator ==(GetErrorDetailResult? left, GetErrorDetailResult? right)
            => ReferenceEquals(left, right) || (left is not null && left.Equals(right));
        public static bool operator !=(GetErrorDetailResult? left, GetErrorDetailResult? right)
            => !(left == right);
    }

    /// <summary>
    /// Params of rois.event.get_event_detail.
    /// 
    /// Maps to EventIF::get_event_detail(in event_id, in condition, out results).
    /// 
    /// Attributes:
    ///     event_id: The event_id from a notify_event notification.
    ///     condition: Filter on the results. Empty means no filter.
    /// </summary>
    public sealed class GetEventDetailParams : IEquatable<GetEventDetailParams>
    {
        [JsonPropertyName("event_id")]
        public string EventId { get; }
        [JsonPropertyName("condition")]
        public string Condition { get; }

        public GetEventDetailParams(string eventId, string condition = "")
        {
            EventId = eventId;
            Condition = condition;
        }

        public bool Equals(GetEventDetailParams? other)
        {
            if (ReferenceEquals(other, this)) return true;
            if (other is null) return false;
            return Equals(EventId, other.EventId) && Equals(Condition, other.Condition);
        }

        public override bool Equals(object? obj)
        {
            return Equals(obj as GetEventDetailParams);
        }

        public override int GetHashCode()
        {
            return System.HashCode.Combine(EventId, Condition);
        }

        public static bool operator ==(GetEventDetailParams? left, GetEventDetailParams? right)
            => ReferenceEquals(left, right) || (left is not null && left.Equals(right));
        public static bool operator !=(GetEventDetailParams? left, GetEventDetailParams? right)
            => !(left == right);
    }

    /// <summary>
    /// Result of rois.event.get_event_detail.
    /// 
    /// Maps to EventIF::get_event_detail(in event_id, in condition, out results).
    /// 
    /// Attributes:
    ///     return_code: Outcome of the operation.
    ///     results: The event payload.
    /// </summary>
    public sealed class GetEventDetailResult : IEquatable<GetEventDetailResult>
    {
        [JsonPropertyName("return_code")]
        public OpenRoIS.Interfaces.Hri.ReturnCode ReturnCode { get; }
        [JsonPropertyName("results")]
        public IReadOnlyList<OpenRoIS.Interfaces.Hri.Result>? Results { get; }

        public GetEventDetailResult(OpenRoIS.Interfaces.Hri.ReturnCode returnCode, IReadOnlyList<OpenRoIS.Interfaces.Hri.Result>? results = null)
        {
            ReturnCode = returnCode;
            Results = results;
        }

        public bool Equals(GetEventDetailResult? other)
        {
            if (ReferenceEquals(other, this)) return true;
            if (other is null) return false;
            return Equals(ReturnCode, other.ReturnCode) && Equals(Results, other.Results);
        }

        public override bool Equals(object? obj)
        {
            return Equals(obj as GetEventDetailResult);
        }

        public override int GetHashCode()
        {
            return System.HashCode.Combine(ReturnCode, Results);
        }

        public static bool operator ==(GetEventDetailResult? left, GetEventDetailResult? right)
            => ReferenceEquals(left, right) || (left is not null && left.Equals(right));
        public static bool operator !=(GetEventDetailResult? left, GetEventDetailResult? right)
            => !(left == right);
    }

    /// <summary>
    /// Params of rois.command.get_parameter.
    /// 
    /// Maps to CommandIF::get_parameter(in component_ref, out parameters).
    /// 
    /// Attributes:
    ///     component_ref: The component whose parameters to read.
    /// </summary>
    public sealed class GetParameterParams : IEquatable<GetParameterParams>
    {
        [JsonPropertyName("component_ref")]
        public string ComponentRef { get; }

        public GetParameterParams(string componentRef)
        {
            ComponentRef = componentRef;
        }

        public bool Equals(GetParameterParams? other)
        {
            if (ReferenceEquals(other, this)) return true;
            if (other is null) return false;
            return Equals(ComponentRef, other.ComponentRef);
        }

        public override bool Equals(object? obj)
        {
            return Equals(obj as GetParameterParams);
        }

        public override int GetHashCode()
        {
            return System.HashCode.Combine(ComponentRef);
        }

        public static bool operator ==(GetParameterParams? left, GetParameterParams? right)
            => ReferenceEquals(left, right) || (left is not null && left.Equals(right));
        public static bool operator !=(GetParameterParams? left, GetParameterParams? right)
            => !(left == right);
    }

    /// <summary>
    /// Result of rois.command.get_parameter.
    /// 
    /// Maps to CommandIF::get_parameter(in component_ref, out parameters).
    /// 
    /// Attributes:
    ///     return_code: Outcome of the operation.
    ///     parameters: The current value of every parameter of the component.
    /// </summary>
    public sealed class GetParameterResult : IEquatable<GetParameterResult>
    {
        [JsonPropertyName("return_code")]
        public OpenRoIS.Interfaces.Hri.ReturnCode ReturnCode { get; }
        [JsonPropertyName("parameters")]
        public IReadOnlyList<OpenRoIS.Interfaces.Hri.Parameter>? Parameters { get; }

        public GetParameterResult(OpenRoIS.Interfaces.Hri.ReturnCode returnCode, IReadOnlyList<OpenRoIS.Interfaces.Hri.Parameter>? parameters = null)
        {
            ReturnCode = returnCode;
            Parameters = parameters;
        }

        public bool Equals(GetParameterResult? other)
        {
            if (ReferenceEquals(other, this)) return true;
            if (other is null) return false;
            return Equals(ReturnCode, other.ReturnCode) && Equals(Parameters, other.Parameters);
        }

        public override bool Equals(object? obj)
        {
            return Equals(obj as GetParameterResult);
        }

        public override int GetHashCode()
        {
            return System.HashCode.Combine(ReturnCode, Parameters);
        }

        public static bool operator ==(GetParameterResult? left, GetParameterResult? right)
            => ReferenceEquals(left, right) || (left is not null && left.Equals(right));
        public static bool operator !=(GetParameterResult? left, GetParameterResult? right)
            => !(left == right);
    }

    /// <summary>
    /// Params of rois.system.get_profile.
    /// 
    /// Maps to SystemIF::get_profile(in condition, out profile).
    /// 
    /// Attributes:
    ///     condition: Filter on the profile. Empty means no filter.
    /// </summary>
    public sealed class GetProfileParams : IEquatable<GetProfileParams>
    {
        [JsonPropertyName("condition")]
        public string Condition { get; }

        public GetProfileParams(string condition = "")
        {
            Condition = condition;
        }

        public bool Equals(GetProfileParams? other)
        {
            if (ReferenceEquals(other, this)) return true;
            if (other is null) return false;
            return Equals(Condition, other.Condition);
        }

        public override bool Equals(object? obj)
        {
            return Equals(obj as GetProfileParams);
        }

        public override int GetHashCode()
        {
            return System.HashCode.Combine(Condition);
        }

        public static bool operator ==(GetProfileParams? left, GetProfileParams? right)
            => ReferenceEquals(left, right) || (left is not null && left.Equals(right));
        public static bool operator !=(GetProfileParams? left, GetProfileParams? right)
            => !(left == right);
    }

    /// <summary>
    /// Result of rois.system.get_profile.
    /// 
    /// Maps to SystemIF::get_profile(in condition, out profile). The IDL carries the
    /// profile as an XML document in a string. OpenRoIS sends the structured form of
    /// the same XSD type.
    /// 
    /// Attributes:
    ///     return_code: Outcome of the operation.
    ///     profile: The engine profile. Null when return_code is not OK.
    /// </summary>
    public sealed class GetProfileResult : IEquatable<GetProfileResult>
    {
        [JsonPropertyName("return_code")]
        public OpenRoIS.Interfaces.Hri.ReturnCode ReturnCode { get; }
        [JsonPropertyName("profile")]
        public OpenRoIS.Interfaces.Profiles.HRIEngineProfileType? Profile { get; }

        public GetProfileResult(OpenRoIS.Interfaces.Hri.ReturnCode returnCode, OpenRoIS.Interfaces.Profiles.HRIEngineProfileType? profile = null)
        {
            ReturnCode = returnCode;
            Profile = profile;
        }

        public bool Equals(GetProfileResult? other)
        {
            if (ReferenceEquals(other, this)) return true;
            if (other is null) return false;
            return Equals(ReturnCode, other.ReturnCode) && Equals(Profile, other.Profile);
        }

        public override bool Equals(object? obj)
        {
            return Equals(obj as GetProfileResult);
        }

        public override int GetHashCode()
        {
            return System.HashCode.Combine(ReturnCode, Profile);
        }

        public static bool operator ==(GetProfileResult? left, GetProfileResult? right)
            => ReferenceEquals(left, right) || (left is not null && left.Equals(right));
        public static bool operator !=(GetProfileResult? left, GetProfileResult? right)
            => !(left == right);
    }

    /// <summary>
    /// Params of rois.query.query.
    /// 
    /// Maps to QueryIF::query(in query_type, in condition, out results).
    /// 
    /// Attributes:
    ///     query_type: Name of the query, from a component profile.
    ///     condition: Filter that selects the component and narrows the results.
    /// </summary>
    public sealed class QueryParams : IEquatable<QueryParams>
    {
        [JsonPropertyName("query_type")]
        public string QueryType { get; }
        [JsonPropertyName("condition")]
        public string Condition { get; }

        public QueryParams(string queryType, string condition = "")
        {
            QueryType = queryType;
            Condition = condition;
        }

        public bool Equals(QueryParams? other)
        {
            if (ReferenceEquals(other, this)) return true;
            if (other is null) return false;
            return Equals(QueryType, other.QueryType) && Equals(Condition, other.Condition);
        }

        public override bool Equals(object? obj)
        {
            return Equals(obj as QueryParams);
        }

        public override int GetHashCode()
        {
            return System.HashCode.Combine(QueryType, Condition);
        }

        public static bool operator ==(QueryParams? left, QueryParams? right)
            => ReferenceEquals(left, right) || (left is not null && left.Equals(right));
        public static bool operator !=(QueryParams? left, QueryParams? right)
            => !(left == right);
    }

    /// <summary>
    /// Result of rois.query.query.
    /// 
    /// Maps to QueryIF::query(in query_type, in condition, out results).
    /// 
    /// Attributes:
    ///     return_code: Outcome of the operation.
    ///     results: Results of the query.
    /// </summary>
    public sealed class QueryResult : IEquatable<QueryResult>
    {
        [JsonPropertyName("return_code")]
        public OpenRoIS.Interfaces.Hri.ReturnCode ReturnCode { get; }
        [JsonPropertyName("results")]
        public IReadOnlyList<OpenRoIS.Interfaces.Hri.Result>? Results { get; }

        public QueryResult(OpenRoIS.Interfaces.Hri.ReturnCode returnCode, IReadOnlyList<OpenRoIS.Interfaces.Hri.Result>? results = null)
        {
            ReturnCode = returnCode;
            Results = results;
        }

        public bool Equals(QueryResult? other)
        {
            if (ReferenceEquals(other, this)) return true;
            if (other is null) return false;
            return Equals(ReturnCode, other.ReturnCode) && Equals(Results, other.Results);
        }

        public override bool Equals(object? obj)
        {
            return Equals(obj as QueryResult);
        }

        public override int GetHashCode()
        {
            return System.HashCode.Combine(ReturnCode, Results);
        }

        public static bool operator ==(QueryResult? left, QueryResult? right)
            => ReferenceEquals(left, right) || (left is not null && left.Equals(right));
        public static bool operator !=(QueryResult? left, QueryResult? right)
            => !(left == right);
    }

    /// <summary>
    /// Params of rois.command.release.
    /// 
    /// Maps to CommandIF::release(in component_ref).
    /// 
    /// Attributes:
    ///     component_ref: The component to release.
    /// </summary>
    public sealed class ReleaseParams : IEquatable<ReleaseParams>
    {
        [JsonPropertyName("component_ref")]
        public string ComponentRef { get; }

        public ReleaseParams(string componentRef)
        {
            ComponentRef = componentRef;
        }

        public bool Equals(ReleaseParams? other)
        {
            if (ReferenceEquals(other, this)) return true;
            if (other is null) return false;
            return Equals(ComponentRef, other.ComponentRef);
        }

        public override bool Equals(object? obj)
        {
            return Equals(obj as ReleaseParams);
        }

        public override int GetHashCode()
        {
            return System.HashCode.Combine(ComponentRef);
        }

        public static bool operator ==(ReleaseParams? left, ReleaseParams? right)
            => ReferenceEquals(left, right) || (left is not null && left.Equals(right));
        public static bool operator !=(ReleaseParams? left, ReleaseParams? right)
            => !(left == right);
    }

    /// <summary>
    /// Result of rois.command.release.
    /// 
    /// Maps to CommandIF::release(in component_ref).
    /// 
    /// Attributes:
    ///     return_code: Outcome of the operation.
    /// </summary>
    public sealed class ReleaseResult : IEquatable<ReleaseResult>
    {
        [JsonPropertyName("return_code")]
        public OpenRoIS.Interfaces.Hri.ReturnCode ReturnCode { get; }

        public ReleaseResult(OpenRoIS.Interfaces.Hri.ReturnCode returnCode)
        {
            ReturnCode = returnCode;
        }

        public bool Equals(ReleaseResult? other)
        {
            if (ReferenceEquals(other, this)) return true;
            if (other is null) return false;
            return Equals(ReturnCode, other.ReturnCode);
        }

        public override bool Equals(object? obj)
        {
            return Equals(obj as ReleaseResult);
        }

        public override int GetHashCode()
        {
            return System.HashCode.Combine(ReturnCode);
        }

        public static bool operator ==(ReleaseResult? left, ReleaseResult? right)
            => ReferenceEquals(left, right) || (left is not null && left.Equals(right));
        public static bool operator !=(ReleaseResult? left, ReleaseResult? right)
            => !(left == right);
    }

    /// <summary>
    /// Params of rois.command.search.
    /// 
    /// Maps to CommandIF::search(in condition, out component_ref_list).
    /// 
    /// Attributes:
    ///     condition: Filter on the components. Empty matches every component.
    /// </summary>
    public sealed class SearchParams : IEquatable<SearchParams>
    {
        [JsonPropertyName("condition")]
        public string Condition { get; }

        public SearchParams(string condition = "")
        {
            Condition = condition;
        }

        public bool Equals(SearchParams? other)
        {
            if (ReferenceEquals(other, this)) return true;
            if (other is null) return false;
            return Equals(Condition, other.Condition);
        }

        public override bool Equals(object? obj)
        {
            return Equals(obj as SearchParams);
        }

        public override int GetHashCode()
        {
            return System.HashCode.Combine(Condition);
        }

        public static bool operator ==(SearchParams? left, SearchParams? right)
            => ReferenceEquals(left, right) || (left is not null && left.Equals(right));
        public static bool operator !=(SearchParams? left, SearchParams? right)
            => !(left == right);
    }

    /// <summary>
    /// Result of rois.command.search.
    /// 
    /// Maps to CommandIF::search(in condition, out component_ref_list).
    /// 
    /// Attributes:
    ///     return_code: Outcome of the operation.
    ///     component_ref_list: Refs of the matching components.
    /// </summary>
    public sealed class SearchResult : IEquatable<SearchResult>
    {
        [JsonPropertyName("return_code")]
        public OpenRoIS.Interfaces.Hri.ReturnCode ReturnCode { get; }
        [JsonPropertyName("component_ref_list")]
        public IReadOnlyList<string>? ComponentRefList { get; }

        public SearchResult(OpenRoIS.Interfaces.Hri.ReturnCode returnCode, IReadOnlyList<string>? componentRefList = null)
        {
            ReturnCode = returnCode;
            ComponentRefList = componentRefList;
        }

        public bool Equals(SearchResult? other)
        {
            if (ReferenceEquals(other, this)) return true;
            if (other is null) return false;
            return Equals(ReturnCode, other.ReturnCode) && Equals(ComponentRefList, other.ComponentRefList);
        }

        public override bool Equals(object? obj)
        {
            return Equals(obj as SearchResult);
        }

        public override int GetHashCode()
        {
            return System.HashCode.Combine(ReturnCode, ComponentRefList);
        }

        public static bool operator ==(SearchResult? left, SearchResult? right)
            => ReferenceEquals(left, right) || (left is not null && left.Equals(right));
        public static bool operator !=(SearchResult? left, SearchResult? right)
            => !(left == right);
    }

    /// <summary>
    /// Params of rois.command.set_parameter.
    /// 
    /// Maps to CommandIF::set_parameter(in component_ref, in parameters, out command_id).
    /// 
    /// Attributes:
    ///     component_ref: The component to configure.
    ///     parameters: The parameters to set.
    /// </summary>
    public sealed class SetParameterParams : IEquatable<SetParameterParams>
    {
        [JsonPropertyName("component_ref")]
        public string ComponentRef { get; }
        [JsonPropertyName("parameters")]
        public IReadOnlyList<OpenRoIS.Interfaces.Hri.Parameter> Parameters { get; }

        public SetParameterParams(string componentRef, IReadOnlyList<OpenRoIS.Interfaces.Hri.Parameter> parameters)
        {
            ComponentRef = componentRef;
            Parameters = parameters;
        }

        public bool Equals(SetParameterParams? other)
        {
            if (ReferenceEquals(other, this)) return true;
            if (other is null) return false;
            return Equals(ComponentRef, other.ComponentRef) && Equals(Parameters, other.Parameters);
        }

        public override bool Equals(object? obj)
        {
            return Equals(obj as SetParameterParams);
        }

        public override int GetHashCode()
        {
            return System.HashCode.Combine(ComponentRef, Parameters);
        }

        public static bool operator ==(SetParameterParams? left, SetParameterParams? right)
            => ReferenceEquals(left, right) || (left is not null && left.Equals(right));
        public static bool operator !=(SetParameterParams? left, SetParameterParams? right)
            => !(left == right);
    }

    /// <summary>
    /// Result of rois.command.set_parameter.
    /// 
    /// Maps to CommandIF::set_parameter(in component_ref, in parameters, out command_id).
    /// The engine assigns the command_id. A completed notification reports the outcome.
    /// 
    /// Attributes:
    ///     return_code: Outcome of the request.
    ///     command_id: Identifier of the parameter change, assigned by the engine.
    /// </summary>
    public sealed class SetParameterResult : IEquatable<SetParameterResult>
    {
        [JsonPropertyName("return_code")]
        public OpenRoIS.Interfaces.Hri.ReturnCode ReturnCode { get; }
        [JsonPropertyName("command_id")]
        public string CommandId { get; }

        public SetParameterResult(OpenRoIS.Interfaces.Hri.ReturnCode returnCode, string commandId = "")
        {
            ReturnCode = returnCode;
            CommandId = commandId;
        }

        public bool Equals(SetParameterResult? other)
        {
            if (ReferenceEquals(other, this)) return true;
            if (other is null) return false;
            return Equals(ReturnCode, other.ReturnCode) && Equals(CommandId, other.CommandId);
        }

        public override bool Equals(object? obj)
        {
            return Equals(obj as SetParameterResult);
        }

        public override int GetHashCode()
        {
            return System.HashCode.Combine(ReturnCode, CommandId);
        }

        public static bool operator ==(SetParameterResult? left, SetParameterResult? right)
            => ReferenceEquals(left, right) || (left is not null && left.Equals(right));
        public static bool operator !=(SetParameterResult? left, SetParameterResult? right)
            => !(left == right);
    }

    /// <summary>
    /// Params of rois.event.subscribe.
    /// 
    /// Maps to EventIF::subscribe(in event_type, in condition, out subscribe_id).
    /// 
    /// Attributes:
    ///     event_type: Name of the event, from a component profile.
    ///     condition: Filter that selects the component and narrows the events.
    /// </summary>
    public sealed class SubscribeParams : IEquatable<SubscribeParams>
    {
        [JsonPropertyName("event_type")]
        public string EventType { get; }
        [JsonPropertyName("condition")]
        public string Condition { get; }

        public SubscribeParams(string eventType, string condition = "")
        {
            EventType = eventType;
            Condition = condition;
        }

        public bool Equals(SubscribeParams? other)
        {
            if (ReferenceEquals(other, this)) return true;
            if (other is null) return false;
            return Equals(EventType, other.EventType) && Equals(Condition, other.Condition);
        }

        public override bool Equals(object? obj)
        {
            return Equals(obj as SubscribeParams);
        }

        public override int GetHashCode()
        {
            return System.HashCode.Combine(EventType, Condition);
        }

        public static bool operator ==(SubscribeParams? left, SubscribeParams? right)
            => ReferenceEquals(left, right) || (left is not null && left.Equals(right));
        public static bool operator !=(SubscribeParams? left, SubscribeParams? right)
            => !(left == right);
    }

    /// <summary>
    /// Result of rois.event.subscribe.
    /// 
    /// Maps to EventIF::subscribe(in event_type, in condition, out subscribe_id).
    /// 
    /// Attributes:
    ///     return_code: Outcome of the operation.
    ///     subscribe_id: Identifier of the subscription. Empty when return_code is not OK.
    /// </summary>
    public sealed class SubscribeResult : IEquatable<SubscribeResult>
    {
        [JsonPropertyName("return_code")]
        public OpenRoIS.Interfaces.Hri.ReturnCode ReturnCode { get; }
        [JsonPropertyName("subscribe_id")]
        public string SubscribeId { get; }

        public SubscribeResult(OpenRoIS.Interfaces.Hri.ReturnCode returnCode, string subscribeId = "")
        {
            ReturnCode = returnCode;
            SubscribeId = subscribeId;
        }

        public bool Equals(SubscribeResult? other)
        {
            if (ReferenceEquals(other, this)) return true;
            if (other is null) return false;
            return Equals(ReturnCode, other.ReturnCode) && Equals(SubscribeId, other.SubscribeId);
        }

        public override bool Equals(object? obj)
        {
            return Equals(obj as SubscribeResult);
        }

        public override int GetHashCode()
        {
            return System.HashCode.Combine(ReturnCode, SubscribeId);
        }

        public static bool operator ==(SubscribeResult? left, SubscribeResult? right)
            => ReferenceEquals(left, right) || (left is not null && left.Equals(right));
        public static bool operator !=(SubscribeResult? left, SubscribeResult? right)
            => !(left == right);
    }

    /// <summary>
    /// Params of rois.event.unsubscribe.
    /// 
    /// Maps to EventIF::unsubscribe(in subscribe_id). Unsubscribing twice is not an error.
    /// 
    /// Attributes:
    ///     subscribe_id: The subscription to cancel.
    /// </summary>
    public sealed class UnsubscribeParams : IEquatable<UnsubscribeParams>
    {
        [JsonPropertyName("subscribe_id")]
        public string SubscribeId { get; }

        public UnsubscribeParams(string subscribeId)
        {
            SubscribeId = subscribeId;
        }

        public bool Equals(UnsubscribeParams? other)
        {
            if (ReferenceEquals(other, this)) return true;
            if (other is null) return false;
            return Equals(SubscribeId, other.SubscribeId);
        }

        public override bool Equals(object? obj)
        {
            return Equals(obj as UnsubscribeParams);
        }

        public override int GetHashCode()
        {
            return System.HashCode.Combine(SubscribeId);
        }

        public static bool operator ==(UnsubscribeParams? left, UnsubscribeParams? right)
            => ReferenceEquals(left, right) || (left is not null && left.Equals(right));
        public static bool operator !=(UnsubscribeParams? left, UnsubscribeParams? right)
            => !(left == right);
    }

    /// <summary>
    /// Result of rois.event.unsubscribe.
    /// 
    /// Maps to EventIF::unsubscribe(in subscribe_id).
    /// 
    /// Attributes:
    ///     return_code: Outcome of the operation.
    /// </summary>
    public sealed class UnsubscribeResult : IEquatable<UnsubscribeResult>
    {
        [JsonPropertyName("return_code")]
        public OpenRoIS.Interfaces.Hri.ReturnCode ReturnCode { get; }

        public UnsubscribeResult(OpenRoIS.Interfaces.Hri.ReturnCode returnCode)
        {
            ReturnCode = returnCode;
        }

        public bool Equals(UnsubscribeResult? other)
        {
            if (ReferenceEquals(other, this)) return true;
            if (other is null) return false;
            return Equals(ReturnCode, other.ReturnCode);
        }

        public override bool Equals(object? obj)
        {
            return Equals(obj as UnsubscribeResult);
        }

        public override int GetHashCode()
        {
            return System.HashCode.Combine(ReturnCode);
        }

        public static bool operator ==(UnsubscribeResult? left, UnsubscribeResult? right)
            => ReferenceEquals(left, right) || (left is not null && left.Equals(right));
        public static bool operator !=(UnsubscribeResult? left, UnsubscribeResult? right)
            => !(left == right);
    }

    // ─── Method catalog (from catalog.json) ──────────────────────────

    /// <summary>JSON-RPC method names of the RoIS method catalog, keyed by operation.</summary>
    public static class RoISMethods
    {
        public const string Connect = "rois.system.connect";
        public const string Disconnect = "rois.system.disconnect";
        public const string GetProfile = "rois.system.get_profile";
        public const string GetErrorDetail = "rois.system.get_error_detail";
        public const string Search = "rois.command.search";
        public const string Bind = "rois.command.bind";
        public const string BindAny = "rois.command.bind_any";
        public const string Release = "rois.command.release";
        public const string GetParameter = "rois.command.get_parameter";
        public const string SetParameter = "rois.command.set_parameter";
        public const string Execute = "rois.command.execute";
        public const string GetCommandResult = "rois.command.get_command_result";
        public const string Query = "rois.query.query";
        public const string Subscribe = "rois.event.subscribe";
        public const string Unsubscribe = "rois.event.unsubscribe";
        public const string GetEventDetail = "rois.event.get_event_detail";
    }

    /// <summary>The params and result type of every catalog method.</summary>
    public static class RoISMethodTypes
    {
        /// <summary>Params and result type, keyed by JSON-RPC method name.</summary>
        public static readonly IReadOnlyDictionary<string, (Type Params, Type Result)> ByMethod =
            new Dictionary<string, (Type Params, Type Result)>
            {
                [RoISMethods.Connect] = (typeof(ConnectParams), typeof(ConnectResult)),
                [RoISMethods.Disconnect] = (typeof(DisconnectParams), typeof(DisconnectResult)),
                [RoISMethods.GetProfile] = (typeof(GetProfileParams), typeof(GetProfileResult)),
                [RoISMethods.GetErrorDetail] = (typeof(GetErrorDetailParams), typeof(GetErrorDetailResult)),
                [RoISMethods.Search] = (typeof(SearchParams), typeof(SearchResult)),
                [RoISMethods.Bind] = (typeof(BindParams), typeof(BindResult)),
                [RoISMethods.BindAny] = (typeof(BindAnyParams), typeof(BindAnyResult)),
                [RoISMethods.Release] = (typeof(ReleaseParams), typeof(ReleaseResult)),
                [RoISMethods.GetParameter] = (typeof(GetParameterParams), typeof(GetParameterResult)),
                [RoISMethods.SetParameter] = (typeof(SetParameterParams), typeof(SetParameterResult)),
                [RoISMethods.Execute] = (typeof(ExecuteParams), typeof(ExecuteResult)),
                [RoISMethods.GetCommandResult] = (typeof(GetCommandResultParams), typeof(GetCommandResultResult)),
                [RoISMethods.Query] = (typeof(QueryParams), typeof(QueryResult)),
                [RoISMethods.Subscribe] = (typeof(SubscribeParams), typeof(SubscribeResult)),
                [RoISMethods.Unsubscribe] = (typeof(UnsubscribeParams), typeof(UnsubscribeResult)),
                [RoISMethods.GetEventDetail] = (typeof(GetEventDetailParams), typeof(GetEventDetailResult)),
            };
    }

    /// <summary>JSON-RPC 2.0 error codes an engine returns for protocol faults.</summary>
    public static class JsonRpcErrorCodes
    {
        public const int ParseError = -32700;
        public const int InvalidRequest = -32600;
        public const int MethodNotFound = -32601;
        public const int InvalidParams = -32602;
        public const int InternalError = -32603;
    }

    /// <summary>Method name prefixes the catalog does not model. Engines answer them with METHOD_NOT_FOUND.</summary>
    public static class UnmodelledMethodPrefixes
    {
        /// <summary>Every unmodelled prefix.</summary>
        public static readonly IReadOnlyList<string> All = new[] { "rois.stream." };
    }

}
