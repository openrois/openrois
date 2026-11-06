// GENERATED FROM interfaces/schema — DO NOT EDIT
// Source: Argument.schema.json, Branch.schema.json, CommandUnit.schema.json, CommandUnitSequence.schema.json, ConcurrentCommands.schema.json, Parameter.schema.json, Result.schema.json, ReturnCode.schema.json
// Generator: scripts/Generator/Program.cs

using System;
using System.Collections.Generic;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace OpenRoIS.Interfaces.Hri
{
    /// <summary>Marker interface for CommandUnitSequence items (CommandUnit or ConcurrentCommands).</summary>
    [JsonConverter(typeof(CommandUnitSequenceItemConverter))]
    public interface ICommandUnitSequenceItem { }

    /// <summary>
    /// Reads a sequence item as ConcurrentCommands when it has branch_list and as
    /// CommandUnit otherwise, and writes the concrete type of the item.
    /// </summary>
    public sealed class CommandUnitSequenceItemConverter : JsonConverter<ICommandUnitSequenceItem>
    {
        // Without this the serializer skips the converter for null and a list can hold a
        // null item, which no language's model allows.
        public override bool HandleNull => true;

        public override ICommandUnitSequenceItem Read(ref Utf8JsonReader reader, Type typeToConvert, JsonSerializerOptions options)
        {
            using var document = JsonDocument.ParseValue(ref reader);
            var element = document.RootElement;
            if (element.ValueKind != JsonValueKind.Object)
                throw new JsonException($"A sequence item must be an object, not {element.ValueKind}.");
            if (element.TryGetProperty("branch_list", out _))
                return element.Deserialize<ConcurrentCommands>(options)!;
            return element.Deserialize<CommandUnit>(options)!;
        }

        public override void Write(Utf8JsonWriter writer, ICommandUnitSequenceItem value, JsonSerializerOptions options)
        {
            switch (value)
            {
                case ConcurrentCommands group:
                    JsonSerializer.Serialize(writer, group, options);
                    break;
                case CommandUnit command:
                    JsonSerializer.Serialize(writer, command, options);
                    break;
                default:
                    throw new JsonException("A sequence item must be a CommandUnit or a ConcurrentCommands.");
            }
        }
    }

    /// <summary>
    /// Reads an enumeration by its exact name and nothing else, as the other two languages
    /// do. JsonStringEnumConverter also takes other casing, lists of names and numbers in
    /// a string, and it cannot be told not to.
    /// </summary>
    public sealed class RoISEnumConverter<T> : JsonConverter<T> where T : struct, Enum
    {
        public override T Read(ref Utf8JsonReader reader, Type typeToConvert, JsonSerializerOptions options)
        {
            var name = reader.TokenType == JsonTokenType.String ? reader.GetString() : null;
            if (name is not null && Enum.IsDefined(typeof(T), name))
                return (T)Enum.Parse(typeof(T), name);
            throw new JsonException($"Not a name of {typeof(T).Name}.");
        }

        public override void Write(Utf8JsonWriter writer, T value, JsonSerializerOptions options)
        {
            writer.WriteStringValue(value.ToString());
        }
    }

    /// <summary>The serializer settings of the wire format.</summary>
    public static class RoISJson
    {
        /// <summary>
        /// Options for every read and write of a RoIS message. Unset fields stay out of
        /// the message, because the engine refuses a null such as "arguments": null. An
        /// enumeration travels as its name. Each one is listed so that an IL2CPP player
        /// compiles its converter, which a player cannot create at run time.
        /// </summary>
        public static readonly JsonSerializerOptions Options = new JsonSerializerOptions
        {
            DefaultIgnoreCondition = JsonIgnoreCondition.WhenWritingNull,
            Converters =
            {
                new RoISEnumConverter<OpenRoIS.Interfaces.Common.ComponentStatus>(),
                new RoISEnumConverter<OpenRoIS.Interfaces.Common.StreamStatus>(),
                new RoISEnumConverter<OpenRoIS.Interfaces.Components.Navigation.RoutingPolicy>(),
                new RoISEnumConverter<OpenRoIS.Interfaces.Hri.ReturnCode>(),
                new RoISEnumConverter<OpenRoIS.Interfaces.Profiles.ComponentFunction>(),
                new RoISEnumConverter<OpenRoIS.Interfaces.Service.CompletedStatus>(),
                new RoISEnumConverter<OpenRoIS.Interfaces.Service.ErrorType>(),
            },
        };
    }

    // ─── Shared type definitions ($defs) ─────────────────────────────


    /// <summary>
    /// A named argument for command execution.
    /// 
    /// Maps to RoIS_HRI::Argument in the IDL.
    /// 
    /// Attributes:
    ///     name: The argument name.
    ///     data_type_ref: Reference to the data type.
    ///     value: The argument value as a string.
    /// </summary>
    [JsonUnmappedMemberHandling(JsonUnmappedMemberHandling.Disallow)]
    public sealed class Argument : IEquatable<Argument>, IJsonOnDeserialized
    {
        [JsonRequired]
        [JsonPropertyName("name")]
        public string Name { get; init; }
        [JsonRequired]
        [JsonPropertyName("data_type_ref")]
        public string DataTypeRef { get; init; }
        [JsonRequired]
        [JsonPropertyName("value")]
        public string Value { get; init; }

        public Argument(string name, string dataTypeRef, string value)
        {
            Name = name;
            DataTypeRef = dataTypeRef;
            Value = value;
        }

        void IJsonOnDeserialized.OnDeserialized()
        {
            if (Name is null) throw new JsonException("Argument.name must not be null.");
            if (DataTypeRef is null) throw new JsonException("Argument.data_type_ref must not be null.");
            if (Value is null) throw new JsonException("Argument.value must not be null.");
        }

        public bool Equals(Argument? other)
        {
            if (ReferenceEquals(other, this)) return true;
            if (other is null) return false;
            return Equals(Name, other.Name) && Equals(DataTypeRef, other.DataTypeRef) && Equals(Value, other.Value);
        }

        public override bool Equals(object? obj)
        {
            return Equals(obj as Argument);
        }

        public override int GetHashCode()
        {
            return System.HashCode.Combine(Name, DataTypeRef, Value);
        }

        public static bool operator ==(Argument? left, Argument? right)
            => ReferenceEquals(left, right) || (left is not null && left.Equals(right));
        public static bool operator !=(Argument? left, Argument? right)
            => !(left == right);
    }




    /// <summary>
    /// A single command within a CommandUnitSequence.
    /// 
    /// Maps to CommandMessageType in XML-Profiles.xsd (CommandBaseType subtype).
    /// 
    /// Attributes:
    ///     component_ref: The component to send the command to.
    ///     command_type: The command name: a standard one (start, stop, suspend, resume,
    ///         set_parameter) or one the component profile defines.
    ///     command_id: Unique identifier for this command instance. The engine a client
    ///         calls assigns it and ignores one the client sends. An engine passes the ids
    ///         it assigned on to the engines below it.
    ///     arguments: Optional list of arguments for the command.
    ///     delay_time: Optional delay in milliseconds before executing this command.
    /// </summary>
    [JsonUnmappedMemberHandling(JsonUnmappedMemberHandling.Disallow)]
    public sealed class CommandUnit : IEquatable<CommandUnit>, ICommandUnitSequenceItem, IJsonOnDeserialized
    {
        [JsonRequired]
        [JsonPropertyName("component_ref")]
        public string ComponentRef { get; init; }
        [JsonRequired]
        [JsonPropertyName("command_type")]
        public string CommandType { get; init; }
        [JsonPropertyName("command_id")]
        public string CommandId { get; init; }
        [JsonPropertyName("arguments")]
        public IReadOnlyList<Argument>? Arguments { get; init; }
        [JsonPropertyName("delay_time")]
        public int? DelayTime { get; init; }

        public CommandUnit(string componentRef, string commandType, string commandId = "", IReadOnlyList<Argument>? arguments = null, int? delayTime = null)
        {
            ComponentRef = componentRef;
            CommandType = commandType;
            CommandId = commandId;
            Arguments = arguments;
            DelayTime = delayTime;
        }

        void IJsonOnDeserialized.OnDeserialized()
        {
            if (ComponentRef is null) throw new JsonException("CommandUnit.component_ref must not be null.");
            if (CommandType is null) throw new JsonException("CommandUnit.command_type must not be null.");
            if (CommandId is null) throw new JsonException("CommandUnit.command_id must not be null.");
            if (Arguments is not null)
            {
                foreach (var item0 in Arguments)
                {
                    if (item0 is null) throw new JsonException("CommandUnit.arguments item must not be null.");
                }
            }
        }

        public bool Equals(CommandUnit? other)
        {
            if (ReferenceEquals(other, this)) return true;
            if (other is null) return false;
            return Equals(ComponentRef, other.ComponentRef) && Equals(CommandType, other.CommandType) && Equals(CommandId, other.CommandId) && Equals(Arguments, other.Arguments) && Equals(DelayTime, other.DelayTime);
        }

        public override bool Equals(object? obj)
        {
            return Equals(obj as CommandUnit);
        }

        public override int GetHashCode()
        {
            return System.HashCode.Combine(ComponentRef, CommandType, CommandId, Arguments, DelayTime);
        }

        public static bool operator ==(CommandUnit? left, CommandUnit? right)
            => ReferenceEquals(left, right) || (left is not null && left.Equals(right));
        public static bool operator !=(CommandUnit? left, CommandUnit? right)
            => !(left == right);
    }

    /// <summary>
    /// One branch of a ConcurrentCommands group: commands that run in order.
    /// 
    /// Maps to BranchType in XML-Profiles.xsd, which ConcurrentCommandsType does not use.
    /// Annex B.1 and Tables 8.15 and 8.16 of the specification give ConcurrentCommands a
    /// branch_list of branches, and OpenRoIS follows them (docs/rois-reference.md, section
    /// 16).
    /// 
    /// Attributes:
    ///     command_list: The commands of the branch, run one after the other.
    /// </summary>
    [JsonUnmappedMemberHandling(JsonUnmappedMemberHandling.Disallow)]
    public sealed class Branch : IEquatable<Branch>, IJsonOnDeserialized
    {
        [JsonRequired]
        [JsonPropertyName("command_list")]
        public IReadOnlyList<CommandUnit> CommandList { get; init; }

        public Branch(IReadOnlyList<CommandUnit> commandList)
        {
            CommandList = commandList;
        }

        void IJsonOnDeserialized.OnDeserialized()
        {
            if (CommandList is null) throw new JsonException("Branch.command_list must not be null.");
            if (CommandList.Count < 1) throw new JsonException("Branch.command_list must have a length of at least 1.");
            foreach (var item0 in CommandList)
            {
                if (item0 is null) throw new JsonException("Branch.command_list item must not be null.");
            }
        }

        public bool Equals(Branch? other)
        {
            if (ReferenceEquals(other, this)) return true;
            if (other is null) return false;
            return Equals(CommandList, other.CommandList);
        }

        public override bool Equals(object? obj)
        {
            return Equals(obj as Branch);
        }

        public override int GetHashCode()
        {
            return System.HashCode.Combine(CommandList);
        }

        public static bool operator ==(Branch? left, Branch? right)
            => ReferenceEquals(left, right) || (left is not null && left.Equals(right));
        public static bool operator !=(Branch? left, Branch? right)
            => !(left == right);
    }

    /// <summary>
    /// A group of branches executed in parallel.
    /// 
    /// Maps to ConcurrentCommandsType in XML-Profiles.xsd, with the branch_list of Annex
    /// B.1. The branches run at the same time, each branch runs its commands in order, and
    /// the next unit of the sequence waits for every branch.
    /// 
    /// The XSD form, a flat command_list, is read as one-command branches.
    /// 
    /// Attributes:
    ///     branch_list: The branches to run in parallel.
    ///     delay_time: Optional delay in milliseconds before executing this group.
    /// </summary>
    [JsonUnmappedMemberHandling(JsonUnmappedMemberHandling.Disallow)]
    public sealed class ConcurrentCommands : IEquatable<ConcurrentCommands>, ICommandUnitSequenceItem, IJsonOnDeserialized
    {
        [JsonRequired]
        [JsonPropertyName("branch_list")]
        public IReadOnlyList<Branch> BranchList { get; init; }
        [JsonPropertyName("delay_time")]
        public int? DelayTime { get; init; }

        public ConcurrentCommands(IReadOnlyList<Branch> branchList, int? delayTime = null)
        {
            BranchList = branchList;
            DelayTime = delayTime;
        }

        void IJsonOnDeserialized.OnDeserialized()
        {
            if (BranchList is null) throw new JsonException("ConcurrentCommands.branch_list must not be null.");
            foreach (var item0 in BranchList)
            {
                if (item0 is null) throw new JsonException("ConcurrentCommands.branch_list item must not be null.");
            }
        }

        public bool Equals(ConcurrentCommands? other)
        {
            if (ReferenceEquals(other, this)) return true;
            if (other is null) return false;
            return Equals(BranchList, other.BranchList) && Equals(DelayTime, other.DelayTime);
        }

        public override bool Equals(object? obj)
        {
            return Equals(obj as ConcurrentCommands);
        }

        public override int GetHashCode()
        {
            return System.HashCode.Combine(BranchList, DelayTime);
        }

        public static bool operator ==(ConcurrentCommands? left, ConcurrentCommands? right)
            => ReferenceEquals(left, right) || (left is not null && left.Equals(right));
        public static bool operator !=(ConcurrentCommands? left, ConcurrentCommands? right)
            => !(left == right);
    }


    /// <summary>
    /// An ordered sequence of command units (sequential and/or concurrent).
    /// 
    /// Maps to CommandUnitSequenceType in XML-Profiles.xsd. The IDL typedefs this
    /// as `string`, but the XSD defines a rich structure with sequential and
    /// concurrent branches. We model the structured form; the string representation
    /// is the wire serialization format.
    /// 
    /// Attributes:
    ///     command_unit_list: Ordered list of command units and/or concurrent groups.
    /// </summary>
    [JsonUnmappedMemberHandling(JsonUnmappedMemberHandling.Disallow)]
    public sealed class CommandUnitSequence : IEquatable<CommandUnitSequence>, IJsonOnDeserialized
    {
        [JsonRequired]
        [JsonPropertyName("command_unit_list")]
        public IReadOnlyList<ICommandUnitSequenceItem> CommandUnitList { get; init; }

        public CommandUnitSequence(IReadOnlyList<ICommandUnitSequenceItem> commandUnitList)
        {
            CommandUnitList = commandUnitList;
        }

        void IJsonOnDeserialized.OnDeserialized()
        {
            if (CommandUnitList is null) throw new JsonException("CommandUnitSequence.command_unit_list must not be null.");
            foreach (var item0 in CommandUnitList)
            {
                if (item0 is null) throw new JsonException("CommandUnitSequence.command_unit_list item must not be null.");
            }
        }

        public bool Equals(CommandUnitSequence? other)
        {
            if (ReferenceEquals(other, this)) return true;
            if (other is null) return false;
            return Equals(CommandUnitList, other.CommandUnitList);
        }

        public override bool Equals(object? obj)
        {
            return Equals(obj as CommandUnitSequence);
        }

        public override int GetHashCode()
        {
            return System.HashCode.Combine(CommandUnitList);
        }

        public static bool operator ==(CommandUnitSequence? left, CommandUnitSequence? right)
            => ReferenceEquals(left, right) || (left is not null && left.Equals(right));
        public static bool operator !=(CommandUnitSequence? left, CommandUnitSequence? right)
            => !(left == right);
    }

    /// <summary>
    /// A named parameter for command operations (set_parameter, execute).
    /// 
    /// Maps to RoIS_HRI::Parameter in the IDL.
    /// 
    /// Attributes:
    ///     name: The parameter name (e.g., 'target_position', 'time_limit').
    ///     data_type_ref: Reference to the data type.
    ///     value: The parameter value as a string.
    /// </summary>
    [JsonUnmappedMemberHandling(JsonUnmappedMemberHandling.Disallow)]
    public sealed class Parameter : IEquatable<Parameter>, IJsonOnDeserialized
    {
        [JsonRequired]
        [JsonPropertyName("name")]
        public string Name { get; init; }
        [JsonRequired]
        [JsonPropertyName("data_type_ref")]
        public string DataTypeRef { get; init; }
        [JsonRequired]
        [JsonPropertyName("value")]
        public string Value { get; init; }

        public Parameter(string name, string dataTypeRef, string value)
        {
            Name = name;
            DataTypeRef = dataTypeRef;
            Value = value;
        }

        void IJsonOnDeserialized.OnDeserialized()
        {
            if (Name is null) throw new JsonException("Parameter.name must not be null.");
            if (DataTypeRef is null) throw new JsonException("Parameter.data_type_ref must not be null.");
            if (Value is null) throw new JsonException("Parameter.value must not be null.");
        }

        public bool Equals(Parameter? other)
        {
            if (ReferenceEquals(other, this)) return true;
            if (other is null) return false;
            return Equals(Name, other.Name) && Equals(DataTypeRef, other.DataTypeRef) && Equals(Value, other.Value);
        }

        public override bool Equals(object? obj)
        {
            return Equals(obj as Parameter);
        }

        public override int GetHashCode()
        {
            return System.HashCode.Combine(Name, DataTypeRef, Value);
        }

        public static bool operator ==(Parameter? left, Parameter? right)
            => ReferenceEquals(left, right) || (left is not null && left.Equals(right));
        public static bool operator !=(Parameter? left, Parameter? right)
            => !(left == right);
    }

    /// <summary>
    /// A named result value returned by query or event operations.
    /// 
    /// Maps to RoIS_HRI::Result in the IDL.
    /// 
    /// Attributes:
    ///     name: The result parameter name (e.g., 'number', 'timestamp').
    ///     data_type_ref: Reference to the data type (e.g., 'int', 'DateTime').
    ///     value: The result value as a string. Component-specific typed models
    ///         provide structured access.
    /// </summary>
    [JsonUnmappedMemberHandling(JsonUnmappedMemberHandling.Disallow)]
    public sealed class Result : IEquatable<Result>, IJsonOnDeserialized
    {
        [JsonRequired]
        [JsonPropertyName("name")]
        public string Name { get; init; }
        [JsonRequired]
        [JsonPropertyName("data_type_ref")]
        public string DataTypeRef { get; init; }
        [JsonRequired]
        [JsonPropertyName("value")]
        public string Value { get; init; }

        public Result(string name, string dataTypeRef, string value)
        {
            Name = name;
            DataTypeRef = dataTypeRef;
            Value = value;
        }

        void IJsonOnDeserialized.OnDeserialized()
        {
            if (Name is null) throw new JsonException("Result.name must not be null.");
            if (DataTypeRef is null) throw new JsonException("Result.data_type_ref must not be null.");
            if (Value is null) throw new JsonException("Result.value must not be null.");
        }

        public bool Equals(Result? other)
        {
            if (ReferenceEquals(other, this)) return true;
            if (other is null) return false;
            return Equals(Name, other.Name) && Equals(DataTypeRef, other.DataTypeRef) && Equals(Value, other.Value);
        }

        public override bool Equals(object? obj)
        {
            return Equals(obj as Result);
        }

        public override int GetHashCode()
        {
            return System.HashCode.Combine(Name, DataTypeRef, Value);
        }

        public static bool operator ==(Result? left, Result? right)
            => ReferenceEquals(left, right) || (left is not null && left.Equals(right));
        public static bool operator !=(Result? left, Result? right)
            => !(left == right);
    }

    /// <summary>
    /// Return code for all RoIS operations.
    /// 
    /// Maps to RoIS_HRI::ReturnCode_t in the IDL.
    /// </summary>
    public enum ReturnCode
    {
        OK,
        ERROR,
        BAD_PARAMETER,
        UNSUPPORTED,
        OUT_OF_RESOURCES,
        TIMEOUT
    }

}
