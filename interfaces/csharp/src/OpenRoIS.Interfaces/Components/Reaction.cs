// GENERATED FROM interfaces/schema — DO NOT EDIT
// Source: ReactionGetParameterResult.schema.json, ReactionSetParameter.schema.json, ReactionSetParameterResult.schema.json, ReactionStatusResult.schema.json
// Generator: scripts/Generator/Program.cs

using System;
using System.Collections.Generic;
using System.Text.Json.Serialization;

namespace OpenRoIS.Interfaces.Components.Reaction
{
    // ─── Shared type definitions ($defs) ─────────────────────────────




    /// <summary>
    /// Result payload for Reaction::Query::get_parameter.
    /// 
    /// Maps to the get_parameter operation in RoIS_Reaction.idl, which returns the
    /// list of available reactions and the currently selected reaction reference.
    /// 
    /// Attributes:
    ///     available_reactions: List of reaction identifiers this host can perform.
    ///     reaction_ref: Currently selected reaction identifier.
    /// </summary>
    public sealed class ReactionGetParameterResult : IEquatable<ReactionGetParameterResult>
    {
        [JsonPropertyName("available_reactions")]
        public IReadOnlyList<string> AvailableReactions { get; }
        [JsonPropertyName("reaction_ref")]
        public string ReactionRef { get; }

        public ReactionGetParameterResult(IReadOnlyList<string> availableReactions, string reactionRef)
        {
            AvailableReactions = availableReactions;
            ReactionRef = reactionRef;
        }

        public bool Equals(ReactionGetParameterResult? other)
        {
            if (ReferenceEquals(other, this)) return true;
            if (other is null) return false;
            return Equals(AvailableReactions, other.AvailableReactions) && Equals(ReactionRef, other.ReactionRef);
        }

        public override bool Equals(object? obj)
        {
            return Equals(obj as ReactionGetParameterResult);
        }

        public override int GetHashCode()
        {
            return System.HashCode.Combine(AvailableReactions, ReactionRef);
        }

        public static bool operator ==(ReactionGetParameterResult? left, ReactionGetParameterResult? right)
            => ReferenceEquals(left, right) || (left is not null && left.Equals(right));
        public static bool operator !=(ReactionGetParameterResult? left, ReactionGetParameterResult? right)
            => !(left == right);
    }

    /// <summary>
    /// Command payload for Reaction::Command::set_parameter.
    /// 
    /// Maps to the set_parameter operation in RoIS_Reaction.idl, which takes a
    /// ``RoIS_IdentifierList`` of reaction references. The XML profile declares
    /// ``reaction_ref`` as a single ``RoISIdentifier`` parameter, but the IDL
    /// operation signature accepts a list, so the model uses a list to match the
    /// operation contract.
    /// 
    /// Attributes:
    ///     reaction_ref: List of reaction identifiers to trigger. Each identifier
    ///         is an opaque string whose meaning is defined by the host backend
    ///         (e.g., "wave", "nod", "smile" for an avatar, or "led_green" for a
    ///         robot).
    /// </summary>
    public sealed class ReactionSetParameter : IEquatable<ReactionSetParameter>
    {
        [JsonPropertyName("reaction_ref")]
        public IReadOnlyList<string> ReactionRef { get; }

        public ReactionSetParameter(IReadOnlyList<string> reactionRef)
        {
            ReactionRef = reactionRef;
        }

        public bool Equals(ReactionSetParameter? other)
        {
            if (ReferenceEquals(other, this)) return true;
            if (other is null) return false;
            return Equals(ReactionRef, other.ReactionRef);
        }

        public override bool Equals(object? obj)
        {
            return Equals(obj as ReactionSetParameter);
        }

        public override int GetHashCode()
        {
            return System.HashCode.Combine(ReactionRef);
        }

        public static bool operator ==(ReactionSetParameter? left, ReactionSetParameter? right)
            => ReferenceEquals(left, right) || (left is not null && left.Equals(right));
        public static bool operator !=(ReactionSetParameter? left, ReactionSetParameter? right)
            => !(left == right);
    }

    /// <summary>
    /// Result of Reaction set_parameter command.
    /// 
    /// Attributes:
    ///     command_id: The assigned command identifier for this reaction command.
    /// </summary>
    public sealed class ReactionSetParameterResult : IEquatable<ReactionSetParameterResult>
    {
        [JsonPropertyName("command_id")]
        public string CommandId { get; }

        public ReactionSetParameterResult(string commandId)
        {
            CommandId = commandId;
        }

        public bool Equals(ReactionSetParameterResult? other)
        {
            if (ReferenceEquals(other, this)) return true;
            if (other is null) return false;
            return Equals(CommandId, other.CommandId);
        }

        public override bool Equals(object? obj)
        {
            return Equals(obj as ReactionSetParameterResult);
        }

        public override int GetHashCode()
        {
            return System.HashCode.Combine(CommandId);
        }

        public static bool operator ==(ReactionSetParameterResult? left, ReactionSetParameterResult? right)
            => ReferenceEquals(left, right) || (left is not null && left.Equals(right));
        public static bool operator !=(ReactionSetParameterResult? left, ReactionSetParameterResult? right)
            => !(left == right);
    }

    /// <summary>
    /// Result model for Reaction component_status query.
    /// 
    /// Attributes:
    ///     status: Current status of the Reaction component.
    /// </summary>
    public sealed class ReactionStatusResult : IEquatable<ReactionStatusResult>
    {
        [JsonPropertyName("status")]
        public OpenRoIS.Interfaces.Common.ComponentStatus Status { get; }

        public ReactionStatusResult(OpenRoIS.Interfaces.Common.ComponentStatus status)
        {
            Status = status;
        }

        public bool Equals(ReactionStatusResult? other)
        {
            if (ReferenceEquals(other, this)) return true;
            if (other is null) return false;
            return Equals(Status, other.Status);
        }

        public override bool Equals(object? obj)
        {
            return Equals(obj as ReactionStatusResult);
        }

        public override int GetHashCode()
        {
            return System.HashCode.Combine(Status);
        }

        public static bool operator ==(ReactionStatusResult? left, ReactionStatusResult? right)
            => ReferenceEquals(left, right) || (left is not null && left.Equals(right));
        public static bool operator !=(ReactionStatusResult? left, ReactionStatusResult? right)
            => !(left == right);
    }

}
