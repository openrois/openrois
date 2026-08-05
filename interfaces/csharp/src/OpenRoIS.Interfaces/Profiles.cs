// GENERATED FROM interfaces/schema — DO NOT EDIT
// Source: CommandMessageProfile.schema.json, EventMessageProfile.schema.json, HRIComponentProfile.schema.json, HRIEngineProfileType.schema.json, MessageProfile.schema.json, ParameterProfile.schema.json, QueryMessageProfile.schema.json, RoISIdentifierType.schema.json
// Generator: scripts/Generator/Program.cs

using System;
using System.Collections.Generic;
using System.Text.Json.Serialization;

namespace OpenRoIS.Interfaces.Profiles
{
    // ─── Shared type definitions ($defs) ─────────────────────────────

    /// <summary>
    /// A structured RoIS identifier with optional metadata.
    /// 
    /// Maps to RoISIdentifierType in XML-Profiles.xsd.
    /// 
    /// Attributes:
    ///     authority: Optional naming authority (e.g., 'OMG').
    ///     code: The identifier code (e.g., 'PersonDetection').
    ///     codebook_ref: Optional reference to a codebook or ontology.
    ///     version: Optional version string.
    /// </summary>
    public sealed class RoISIdentifierType : IEquatable<RoISIdentifierType>
    {
        [JsonPropertyName("code")]
        public string Code { get; }
        [JsonPropertyName("authority")]
        public string Authority { get; }
        [JsonPropertyName("codebook_ref")]
        public string CodebookRef { get; }
        [JsonPropertyName("version")]
        public string Version { get; }

        public RoISIdentifierType(string code, string authority = "", string codebookRef = "", string version = "")
        {
            Code = code;
            Authority = authority;
            CodebookRef = codebookRef;
            Version = version;
        }

        public bool Equals(RoISIdentifierType? other)
        {
            if (ReferenceEquals(other, this)) return true;
            if (other is null) return false;
            return Equals(Code, other.Code) && Equals(Authority, other.Authority) && Equals(CodebookRef, other.CodebookRef) && Equals(Version, other.Version);
        }

        public override bool Equals(object? obj)
        {
            return Equals(obj as RoISIdentifierType);
        }

        public override int GetHashCode()
        {
            return System.HashCode.Combine(Code, Authority, CodebookRef, Version);
        }

        public static bool operator ==(RoISIdentifierType? left, RoISIdentifierType? right)
            => ReferenceEquals(left, right) || (left is not null && left.Equals(right));
        public static bool operator !=(RoISIdentifierType? left, RoISIdentifierType? right)
            => !(left == right);
    }

    /// <summary>
    /// Describes a parameter's data type and metadata.
    /// 
    /// Maps to ParameterProfileType in XML-Profiles.xsd.
    /// 
    /// Used in both message profiles (Arguments/Results) and component-level
    /// parameter declarations.
    /// 
    /// Attributes:
    ///     name: The parameter name.
    ///     data_type_ref: Reference to the data type (e.g., 'int', 'DateTime',
    ///         'RoISIdentifier[]').
    ///     default_value: Optional default value as a string.
    ///     description: Optional human-readable description.
    /// </summary>
    public sealed class ParameterProfile : IEquatable<ParameterProfile>
    {
        [JsonPropertyName("name")]
        public string Name { get; }
        [JsonPropertyName("data_type_ref")]
        public RoISIdentifierType DataTypeRef { get; }
        [JsonPropertyName("default_value")]
        public string DefaultValue { get; }
        [JsonPropertyName("description")]
        public string Description { get; }

        public ParameterProfile(string name, RoISIdentifierType dataTypeRef, string defaultValue = "", string description = "")
        {
            Name = name;
            DataTypeRef = dataTypeRef;
            DefaultValue = defaultValue;
            Description = description;
        }

        public bool Equals(ParameterProfile? other)
        {
            if (ReferenceEquals(other, this)) return true;
            if (other is null) return false;
            return Equals(Name, other.Name) && Equals(DataTypeRef, other.DataTypeRef) && Equals(DefaultValue, other.DefaultValue) && Equals(Description, other.Description);
        }

        public override bool Equals(object? obj)
        {
            return Equals(obj as ParameterProfile);
        }

        public override int GetHashCode()
        {
            return System.HashCode.Combine(Name, DataTypeRef, DefaultValue, Description);
        }

        public static bool operator ==(ParameterProfile? left, ParameterProfile? right)
            => ReferenceEquals(left, right) || (left is not null && left.Equals(right));
        public static bool operator !=(ParameterProfile? left, ParameterProfile? right)
            => !(left == right);
    }

    /// <summary>
    /// A command message profile with arguments and optional timeout.
    /// 
    /// Maps to CommandMessageProfileType in XML-Profiles.xsd.
    /// 
    /// Attributes:
    ///     arguments: The input arguments for this command.
    ///     timeout: Optional timeout in milliseconds.
    /// </summary>
    public sealed class CommandMessageProfile : IEquatable<CommandMessageProfile>
    {
        [JsonPropertyName("name")]
        public string Name { get; }
        [JsonPropertyName("results")]
        public IReadOnlyList<ParameterProfile>? Results { get; }
        [JsonPropertyName("arguments")]
        public IReadOnlyList<ParameterProfile>? Arguments { get; }
        [JsonPropertyName("timeout")]
        public int? Timeout { get; }

        public CommandMessageProfile(string name, IReadOnlyList<ParameterProfile>? results = null, IReadOnlyList<ParameterProfile>? arguments = null, int? timeout = null)
        {
            Name = name;
            Results = results;
            Arguments = arguments;
            Timeout = timeout;
        }

        public bool Equals(CommandMessageProfile? other)
        {
            if (ReferenceEquals(other, this)) return true;
            if (other is null) return false;
            return Equals(Name, other.Name) && Equals(Results, other.Results) && Equals(Arguments, other.Arguments) && Equals(Timeout, other.Timeout);
        }

        public override bool Equals(object? obj)
        {
            return Equals(obj as CommandMessageProfile);
        }

        public override int GetHashCode()
        {
            return System.HashCode.Combine(Name, Results, Arguments, Timeout);
        }

        public static bool operator ==(CommandMessageProfile? left, CommandMessageProfile? right)
            => ReferenceEquals(left, right) || (left is not null && left.Equals(right));
        public static bool operator !=(CommandMessageProfile? left, CommandMessageProfile? right)
            => !(left == right);
    }

    /// <summary>
    /// An event message profile.
    /// 
    /// Maps to EventMessageProfileType in XML-Profiles.xsd.
    /// 
    /// Events have results (the event payload) but no arguments.
    /// </summary>
    public sealed class EventMessageProfile : IEquatable<EventMessageProfile>
    {
        [JsonPropertyName("name")]
        public string Name { get; }
        [JsonPropertyName("results")]
        public IReadOnlyList<ParameterProfile>? Results { get; }

        public EventMessageProfile(string name, IReadOnlyList<ParameterProfile>? results = null)
        {
            Name = name;
            Results = results;
        }

        public bool Equals(EventMessageProfile? other)
        {
            if (ReferenceEquals(other, this)) return true;
            if (other is null) return false;
            return Equals(Name, other.Name) && Equals(Results, other.Results);
        }

        public override bool Equals(object? obj)
        {
            return Equals(obj as EventMessageProfile);
        }

        public override int GetHashCode()
        {
            return System.HashCode.Combine(Name, Results);
        }

        public static bool operator ==(EventMessageProfile? left, EventMessageProfile? right)
            => ReferenceEquals(left, right) || (left is not null && left.Equals(right));
        public static bool operator !=(EventMessageProfile? left, EventMessageProfile? right)
            => !(left == right);
    }

    /// <summary>
    /// A query message profile.
    /// 
    /// Maps to QueryMessageProfileType in XML-Profiles.xsd.
    /// 
    /// Queries have results but no arguments (the query_type and condition
    /// are passed separately, not as message arguments).
    /// </summary>
    public sealed class QueryMessageProfile : IEquatable<QueryMessageProfile>
    {
        [JsonPropertyName("name")]
        public string Name { get; }
        [JsonPropertyName("results")]
        public IReadOnlyList<ParameterProfile>? Results { get; }

        public QueryMessageProfile(string name, IReadOnlyList<ParameterProfile>? results = null)
        {
            Name = name;
            Results = results;
        }

        public bool Equals(QueryMessageProfile? other)
        {
            if (ReferenceEquals(other, this)) return true;
            if (other is null) return false;
            return Equals(Name, other.Name) && Equals(Results, other.Results);
        }

        public override bool Equals(object? obj)
        {
            return Equals(obj as QueryMessageProfile);
        }

        public override int GetHashCode()
        {
            return System.HashCode.Combine(Name, Results);
        }

        public static bool operator ==(QueryMessageProfile? left, QueryMessageProfile? right)
            => ReferenceEquals(left, right) || (left is not null && left.Equals(right));
        public static bool operator !=(QueryMessageProfile? left, QueryMessageProfile? right)
            => !(left == right);
    }

    /// <summary>
    /// Describes a RoIS component's capabilities, messages, and parameters.
    /// 
    /// Maps to HRIComponentProfileType in XML-Profiles.xsd.
    /// 
    /// Attributes:
    ///     identifier: The component's structured identifier (URN).
    ///     name: A short human-readable name (e.g., 'person_detecter').
    ///     sub_component_profiles: URNs of sub-component profiles (e.g., RoISCommon).
    ///     command_profiles: Command message profiles this component supports.
    ///     query_profiles: Query message profiles this component supports.
    ///     event_profiles: Event message profiles this component supports.
    ///     parameter_profiles: Parameter declarations for this component.
    /// </summary>
    public sealed class HRIComponentProfile : IEquatable<HRIComponentProfile>
    {
        [JsonPropertyName("identifier")]
        public RoISIdentifierType Identifier { get; }
        [JsonPropertyName("name")]
        public string Name { get; }
        [JsonPropertyName("sub_component_profiles")]
        public IReadOnlyList<string>? SubComponentProfiles { get; }
        [JsonPropertyName("command_profiles")]
        public IReadOnlyList<CommandMessageProfile>? CommandProfiles { get; }
        [JsonPropertyName("query_profiles")]
        public IReadOnlyList<QueryMessageProfile>? QueryProfiles { get; }
        [JsonPropertyName("event_profiles")]
        public IReadOnlyList<EventMessageProfile>? EventProfiles { get; }
        [JsonPropertyName("parameter_profiles")]
        public IReadOnlyList<ParameterProfile>? ParameterProfiles { get; }

        public HRIComponentProfile(RoISIdentifierType identifier, string name, IReadOnlyList<string>? subComponentProfiles = null, IReadOnlyList<CommandMessageProfile>? commandProfiles = null, IReadOnlyList<QueryMessageProfile>? queryProfiles = null, IReadOnlyList<EventMessageProfile>? eventProfiles = null, IReadOnlyList<ParameterProfile>? parameterProfiles = null)
        {
            Identifier = identifier;
            Name = name;
            SubComponentProfiles = subComponentProfiles;
            CommandProfiles = commandProfiles;
            QueryProfiles = queryProfiles;
            EventProfiles = eventProfiles;
            ParameterProfiles = parameterProfiles;
        }

        public bool Equals(HRIComponentProfile? other)
        {
            if (ReferenceEquals(other, this)) return true;
            if (other is null) return false;
            return Equals(Identifier, other.Identifier) && Equals(Name, other.Name) && Equals(SubComponentProfiles, other.SubComponentProfiles) && Equals(CommandProfiles, other.CommandProfiles) && Equals(QueryProfiles, other.QueryProfiles) && Equals(EventProfiles, other.EventProfiles) && Equals(ParameterProfiles, other.ParameterProfiles);
        }

        public override bool Equals(object? obj)
        {
            return Equals(obj as HRIComponentProfile);
        }

        public override int GetHashCode()
        {
            return System.HashCode.Combine(Identifier, Name, SubComponentProfiles, CommandProfiles, QueryProfiles, EventProfiles, ParameterProfiles);
        }

        public static bool operator ==(HRIComponentProfile? left, HRIComponentProfile? right)
            => ReferenceEquals(left, right) || (left is not null && left.Equals(right));
        public static bool operator !=(HRIComponentProfile? left, HRIComponentProfile? right)
            => !(left == right);
    }

    /// <summary>
    /// Describes an HRI Engine's composition of sub-engines and components.
    /// 
    /// Maps to HRIEngineProfileType in XML-Profiles.xsd.
    /// 
    /// Attributes:
    ///     identifier: The engine's structured identifier.
    ///     sub_profiles: Nested sub-engine profiles.
    ///     component_ids: IDs of components hosted by this engine.
    ///     component_profiles: Full capability profiles for each component.
    ///         Populated from adapter registration data. Optional (default
    ///         empty) for backward compatibility with engines that only
    ///         return component_ids.
    ///     parameter_profiles: Engine-level parameter declarations.
    /// </summary>
    public sealed class HRIEngineProfileType : IEquatable<HRIEngineProfileType>
    {
        [JsonPropertyName("identifier")]
        public RoISIdentifierType Identifier { get; }
        [JsonPropertyName("sub_profiles")]
        public IReadOnlyList<HRIEngineProfileType>? SubProfiles { get; }
        [JsonPropertyName("component_ids")]
        public IReadOnlyList<string>? ComponentIds { get; }
        [JsonPropertyName("component_profiles")]
        public IReadOnlyList<HRIComponentProfile>? ComponentProfiles { get; }
        [JsonPropertyName("parameter_profiles")]
        public IReadOnlyList<ParameterProfile>? ParameterProfiles { get; }

        public HRIEngineProfileType(RoISIdentifierType identifier, IReadOnlyList<HRIEngineProfileType>? subProfiles = null, IReadOnlyList<string>? componentIds = null, IReadOnlyList<HRIComponentProfile>? componentProfiles = null, IReadOnlyList<ParameterProfile>? parameterProfiles = null)
        {
            Identifier = identifier;
            SubProfiles = subProfiles;
            ComponentIds = componentIds;
            ComponentProfiles = componentProfiles;
            ParameterProfiles = parameterProfiles;
        }

        public bool Equals(HRIEngineProfileType? other)
        {
            if (ReferenceEquals(other, this)) return true;
            if (other is null) return false;
            return Equals(Identifier, other.Identifier) && Equals(SubProfiles, other.SubProfiles) && Equals(ComponentIds, other.ComponentIds) && Equals(ComponentProfiles, other.ComponentProfiles) && Equals(ParameterProfiles, other.ParameterProfiles);
        }

        public override bool Equals(object? obj)
        {
            return Equals(obj as HRIEngineProfileType);
        }

        public override int GetHashCode()
        {
            return System.HashCode.Combine(Identifier, SubProfiles, ComponentIds, ComponentProfiles, ParameterProfiles);
        }

        public static bool operator ==(HRIEngineProfileType? left, HRIEngineProfileType? right)
            => ReferenceEquals(left, right) || (left is not null && left.Equals(right));
        public static bool operator !=(HRIEngineProfileType? left, HRIEngineProfileType? right)
            => !(left == right);
    }

    /// <summary>
    /// Base message profile describing a command, query, or event message.
    /// 
    /// Maps to MessageProfileType in XML-Profiles.xsd.
    /// 
    /// Attributes:
    ///     name: The message name (e.g., 'person_detected', 'set_parameter').
    ///     results: The result parameters of this message.
    /// </summary>
    public sealed class MessageProfile : IEquatable<MessageProfile>
    {
        [JsonPropertyName("name")]
        public string Name { get; }
        [JsonPropertyName("results")]
        public IReadOnlyList<ParameterProfile>? Results { get; }

        public MessageProfile(string name, IReadOnlyList<ParameterProfile>? results = null)
        {
            Name = name;
            Results = results;
        }

        public bool Equals(MessageProfile? other)
        {
            if (ReferenceEquals(other, this)) return true;
            if (other is null) return false;
            return Equals(Name, other.Name) && Equals(Results, other.Results);
        }

        public override bool Equals(object? obj)
        {
            return Equals(obj as MessageProfile);
        }

        public override int GetHashCode()
        {
            return System.HashCode.Combine(Name, Results);
        }

        public static bool operator ==(MessageProfile? left, MessageProfile? right)
            => ReferenceEquals(left, right) || (left is not null && left.Equals(right));
        public static bool operator !=(MessageProfile? left, MessageProfile? right)
            => !(left == right);
    }

}
