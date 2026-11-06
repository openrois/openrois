// GENERATED FROM interfaces/schema — DO NOT EDIT
// Source: PersonDetectedEvent.schema.json, PersonDetectionStatusResult.schema.json
// Generator: scripts/Generator/Program.cs

using System;
using System.Collections.Generic;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace OpenRoIS.Interfaces.Components.PersonDetection
{
    // ─── Shared type definitions ($defs) ─────────────────────────────



    /// <summary>
    /// Event payload for Person_Detection::Event::person_detected.
    /// 
    /// Maps to the person_detected event in PersonDetection.xml.
    /// 
    /// Attributes:
    ///     timestamp: ISO 8601 datetime when the detection was measured.
    ///     number: Number of detected persons in the current frame/observation.
    /// </summary>
    [JsonUnmappedMemberHandling(JsonUnmappedMemberHandling.Disallow)]
    public sealed class PersonDetectedEvent : IEquatable<PersonDetectedEvent>, IJsonOnDeserialized
    {
        [JsonRequired]
        [JsonPropertyName("timestamp")]
        public string Timestamp { get; init; }
        [JsonRequired]
        [JsonPropertyName("number")]
        public int Number { get; init; }

        public PersonDetectedEvent(string timestamp, int number)
        {
            Timestamp = timestamp;
            Number = number;
        }

        void IJsonOnDeserialized.OnDeserialized()
        {
            if (Timestamp is null) throw new JsonException("PersonDetectedEvent.timestamp must not be null.");
        }

        public bool Equals(PersonDetectedEvent? other)
        {
            if (ReferenceEquals(other, this)) return true;
            if (other is null) return false;
            return Equals(Timestamp, other.Timestamp) && Equals(Number, other.Number);
        }

        public override bool Equals(object? obj)
        {
            return Equals(obj as PersonDetectedEvent);
        }

        public override int GetHashCode()
        {
            return System.HashCode.Combine(Timestamp, Number);
        }

        public static bool operator ==(PersonDetectedEvent? left, PersonDetectedEvent? right)
            => ReferenceEquals(left, right) || (left is not null && left.Equals(right));
        public static bool operator !=(PersonDetectedEvent? left, PersonDetectedEvent? right)
            => !(left == right);
    }

    /// <summary>
    /// Result model for PersonDetection component_status query.
    /// 
    /// Attributes:
    ///     status: Current status of the PersonDetection component.
    /// </summary>
    [JsonUnmappedMemberHandling(JsonUnmappedMemberHandling.Disallow)]
    public sealed class PersonDetectionStatusResult : IEquatable<PersonDetectionStatusResult>
    {
        [JsonRequired]
        [JsonPropertyName("status")]
        public OpenRoIS.Interfaces.Common.ComponentStatus Status { get; init; }

        public PersonDetectionStatusResult(OpenRoIS.Interfaces.Common.ComponentStatus status)
        {
            Status = status;
        }

        public bool Equals(PersonDetectionStatusResult? other)
        {
            if (ReferenceEquals(other, this)) return true;
            if (other is null) return false;
            return Equals(Status, other.Status);
        }

        public override bool Equals(object? obj)
        {
            return Equals(obj as PersonDetectionStatusResult);
        }

        public override int GetHashCode()
        {
            return System.HashCode.Combine(Status);
        }

        public static bool operator ==(PersonDetectionStatusResult? left, PersonDetectionStatusResult? right)
            => ReferenceEquals(left, right) || (left is not null && left.Equals(right));
        public static bool operator !=(PersonDetectionStatusResult? left, PersonDetectionStatusResult? right)
            => !(left == right);
    }

}
