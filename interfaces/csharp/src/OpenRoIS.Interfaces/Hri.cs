// GENERATED FROM interfaces/schema — DO NOT EDIT
// Source: Argument.schema.json, CommandUnit.schema.json, CommandUnitSequence.schema.json, ConcurrentCommands.schema.json, Parameter.schema.json, Result.schema.json, ReturnCode.schema.json
// Generator: scripts/Generator/Program.cs

using System;
using System.Collections.Generic;
using System.Text.Json.Serialization;

namespace OpenRoIS.Interfaces.Hri
{
    /// <summary>Marker interface for CommandUnitSequence items (CommandUnit or ConcurrentCommands).</summary>
    public interface ICommandUnitSequenceItem { }

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
    public sealed class Argument : IEquatable<Argument>
    {
        [JsonPropertyName("name")]
        public string Name { get; }
        [JsonPropertyName("data_type_ref")]
        public string DataTypeRef { get; }
        [JsonPropertyName("value")]
        public string Value { get; }

        public Argument(string name, string dataTypeRef, string value)
        {
            Name = name;
            DataTypeRef = dataTypeRef;
            Value = value;
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
    /// A single command within a CommandUnitSequence.
    /// 
    /// Maps to CommandMessageType in XML-Profiles.xsd (CommandBaseType subtype).
    /// 
    /// Attributes:
    ///     component_ref: The component to send the command to.
    ///     command_type: The command operation (e.g., 'start', 'stop',
    ///         'set_parameter', 'execute').
    ///     command_id: Unique identifier for this command instance.
    ///     arguments: Optional list of arguments for the command.
    ///     delay_time: Optional delay in milliseconds before executing this command.
    /// </summary>
    public sealed class CommandUnit : IEquatable<CommandUnit>, ICommandUnitSequenceItem
    {
        [JsonPropertyName("component_ref")]
        public string ComponentRef { get; }
        [JsonPropertyName("command_type")]
        public CommandType CommandType { get; }
        [JsonPropertyName("command_id")]
        public string CommandId { get; }
        [JsonPropertyName("arguments")]
        public IReadOnlyList<Argument>? Arguments { get; }
        [JsonPropertyName("delay_time")]
        public int? DelayTime { get; }

        public CommandUnit(string componentRef, CommandType commandType, string commandId, IReadOnlyList<Argument>? arguments = null, int? delayTime = null)
        {
            ComponentRef = componentRef;
            CommandType = commandType;
            CommandId = commandId;
            Arguments = arguments;
            DelayTime = delayTime;
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
    /// A group of commands to be executed concurrently.
    /// 
    /// Maps to ConcurrentCommandsType in XML-Profiles.xsd.
    /// 
    /// Attributes:
    ///     command_list: The commands to execute in parallel.
    ///     delay_time: Optional delay in milliseconds before executing this group.
    /// </summary>
    public sealed class ConcurrentCommands : IEquatable<ConcurrentCommands>, ICommandUnitSequenceItem
    {
        [JsonPropertyName("command_list")]
        public IReadOnlyList<CommandUnit> CommandList { get; }
        [JsonPropertyName("delay_time")]
        public int? DelayTime { get; }

        public ConcurrentCommands(IReadOnlyList<CommandUnit> commandList, int? delayTime = null)
        {
            CommandList = commandList;
            DelayTime = delayTime;
        }

        public bool Equals(ConcurrentCommands? other)
        {
            if (ReferenceEquals(other, this)) return true;
            if (other is null) return false;
            return Equals(CommandList, other.CommandList) && Equals(DelayTime, other.DelayTime);
        }

        public override bool Equals(object? obj)
        {
            return Equals(obj as ConcurrentCommands);
        }

        public override int GetHashCode()
        {
            return System.HashCode.Combine(CommandList, DelayTime);
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
    public sealed class CommandUnitSequence : IEquatable<CommandUnitSequence>
    {
        [JsonPropertyName("command_unit_list")]
        public IReadOnlyList<ICommandUnitSequenceItem> CommandUnitList { get; }

        public CommandUnitSequence(IReadOnlyList<ICommandUnitSequenceItem> commandUnitList)
        {
            CommandUnitList = commandUnitList;
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
    public sealed class Parameter : IEquatable<Parameter>
    {
        [JsonPropertyName("name")]
        public string Name { get; }
        [JsonPropertyName("data_type_ref")]
        public string DataTypeRef { get; }
        [JsonPropertyName("value")]
        public string Value { get; }

        public Parameter(string name, string dataTypeRef, string value)
        {
            Name = name;
            DataTypeRef = dataTypeRef;
            Value = value;
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
    public sealed class Result : IEquatable<Result>
    {
        [JsonPropertyName("name")]
        public string Name { get; }
        [JsonPropertyName("data_type_ref")]
        public string DataTypeRef { get; }
        [JsonPropertyName("value")]
        public string Value { get; }

        public Result(string name, string dataTypeRef, string value)
        {
            Name = name;
            DataTypeRef = dataTypeRef;
            Value = value;
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
