// GENERATED FROM interfaces/schema — DO NOT EDIT
// Source: SystemInformationEngineStatusResult.schema.json, SystemInformationRobotPositionResult.schema.json
// Generator: scripts/Generator/Program.cs

using System;
using System.Collections.Generic;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace OpenRoIS.Interfaces.Components.SystemInformation
{
    // ─── Shared type definitions ($defs) ─────────────────────────────




    /// <summary>
    /// Result payload for System_Information::Query::engine_status.
    /// 
    /// Maps to the engine_status query in SystemInformation.xml.
    /// 
    /// Attributes:
    ///     status: Current component status of the engine.
    ///     operable_time: List of ISO 8601 datetimes representing operable periods.
    /// </summary>
    [JsonUnmappedMemberHandling(JsonUnmappedMemberHandling.Disallow)]
    public sealed class SystemInformationEngineStatusResult : IEquatable<SystemInformationEngineStatusResult>, IJsonOnDeserialized
    {
        [JsonRequired]
        [JsonPropertyName("status")]
        public OpenRoIS.Interfaces.Common.ComponentStatus Status { get; init; }
        [JsonRequired]
        [JsonPropertyName("operable_time")]
        public IReadOnlyList<string> OperableTime { get; init; }

        public SystemInformationEngineStatusResult(OpenRoIS.Interfaces.Common.ComponentStatus status, IReadOnlyList<string> operableTime)
        {
            Status = status;
            OperableTime = operableTime;
        }

        void IJsonOnDeserialized.OnDeserialized()
        {
            if (OperableTime is null) throw new JsonException("SystemInformationEngineStatusResult.operable_time must not be null.");
            foreach (var item0 in OperableTime)
            {
                if (item0 is null) throw new JsonException("SystemInformationEngineStatusResult.operable_time item must not be null.");
            }
        }

        public bool Equals(SystemInformationEngineStatusResult? other)
        {
            if (ReferenceEquals(other, this)) return true;
            if (other is null) return false;
            return Equals(Status, other.Status) && Equals(OperableTime, other.OperableTime);
        }

        public override bool Equals(object? obj)
        {
            return Equals(obj as SystemInformationEngineStatusResult);
        }

        public override int GetHashCode()
        {
            return System.HashCode.Combine(Status, OperableTime);
        }

        public static bool operator ==(SystemInformationEngineStatusResult? left, SystemInformationEngineStatusResult? right)
            => ReferenceEquals(left, right) || (left is not null && left.Equals(right));
        public static bool operator !=(SystemInformationEngineStatusResult? left, SystemInformationEngineStatusResult? right)
            => !(left == right);
    }

    /// <summary>
    /// Result payload for System_Information::Query::robot_position.
    /// 
    /// Maps to the robot_position query in SystemInformation.xml.
    /// 
    /// Attributes:
    ///     timestamp: ISO 8601 datetime when the position was measured.
    ///     robot_ref: List of robot identifiers in the position data.
    ///     position_data: Positional/measurement data (RoLo Data sequence as strings).
    /// </summary>
    [JsonUnmappedMemberHandling(JsonUnmappedMemberHandling.Disallow)]
    public sealed class SystemInformationRobotPositionResult : IEquatable<SystemInformationRobotPositionResult>, IJsonOnDeserialized
    {
        [JsonRequired]
        [JsonPropertyName("timestamp")]
        public string Timestamp { get; init; }
        [JsonRequired]
        [JsonPropertyName("robot_ref")]
        public IReadOnlyList<string> RobotRef { get; init; }
        [JsonRequired]
        [JsonPropertyName("position_data")]
        public IReadOnlyList<string> PositionData { get; init; }

        public SystemInformationRobotPositionResult(string timestamp, IReadOnlyList<string> robotRef, IReadOnlyList<string> positionData)
        {
            Timestamp = timestamp;
            RobotRef = robotRef;
            PositionData = positionData;
        }

        void IJsonOnDeserialized.OnDeserialized()
        {
            if (Timestamp is null) throw new JsonException("SystemInformationRobotPositionResult.timestamp must not be null.");
            if (RobotRef is null) throw new JsonException("SystemInformationRobotPositionResult.robot_ref must not be null.");
            foreach (var item0 in RobotRef)
            {
                if (item0 is null) throw new JsonException("SystemInformationRobotPositionResult.robot_ref item must not be null.");
            }
            if (PositionData is null) throw new JsonException("SystemInformationRobotPositionResult.position_data must not be null.");
            foreach (var item0 in PositionData)
            {
                if (item0 is null) throw new JsonException("SystemInformationRobotPositionResult.position_data item must not be null.");
            }
        }

        public bool Equals(SystemInformationRobotPositionResult? other)
        {
            if (ReferenceEquals(other, this)) return true;
            if (other is null) return false;
            return Equals(Timestamp, other.Timestamp) && Equals(RobotRef, other.RobotRef) && Equals(PositionData, other.PositionData);
        }

        public override bool Equals(object? obj)
        {
            return Equals(obj as SystemInformationRobotPositionResult);
        }

        public override int GetHashCode()
        {
            return System.HashCode.Combine(Timestamp, RobotRef, PositionData);
        }

        public static bool operator ==(SystemInformationRobotPositionResult? left, SystemInformationRobotPositionResult? right)
            => ReferenceEquals(left, right) || (left is not null && left.Equals(right));
        public static bool operator !=(SystemInformationRobotPositionResult? left, SystemInformationRobotPositionResult? right)
            => !(left == right);
    }

}
