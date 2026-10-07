using System;
using System.Collections.Generic;
using System.Text.Json;
using OpenRoIS.Interfaces.Hri;
using Xunit;

namespace OpenRoIS.Interfaces.Tests
{
    public class HriTests
    {
    [Fact]
    public void Result_Construction()
    {
        var result = new Result("number", "int", "3");
        Assert.Equal("number", result.Name);
        Assert.Equal("int", result.DataTypeRef);
        Assert.Equal("3", result.Value);
    }

    [Fact]
    public void Result_Equality()
    {
        var r1 = new Result("number", "int", "3");
        var r2 = new Result("number", "int", "3");
        Assert.Equal(r1, r2);
    }

    [Fact]
    public void Result_OperatorEquality()
    {
        var r1 = new Result("number", "int", "3");
        var r2 = new Result("number", "int", "3");
        var r3 = new Result("number", "int", "5");
        Assert.True(r1 == r2);
        Assert.False(r1 != r2);
        Assert.True(r1 != r3);
        Assert.False(r1 == r3);
    }

    [Fact]
    public void Result_WithExpression()
    {
        var r1 = new Result("number", "int", "3");
        var r2 = new Result(r1.Name, r1.DataTypeRef, "5");
        Assert.Equal("5", r2.Value);
        Assert.Equal("3", r1.Value);
    }

    [Fact]
    public void Result_JsonRoundtrip()
    {
        var result = new Result("number", "int", "3");
        var json = JsonSerializer.Serialize(result);
        var parsed = JsonSerializer.Deserialize<Result>(json)!;
        Assert.Equal(result, parsed);
    }

    [Fact]
    public void CommandUnit_Defaults()
    {
        var cmd = new CommandUnit("robot/nav", "start", "cmd-1");
        Assert.Equal("robot/nav", cmd.ComponentRef);
        Assert.Null(cmd.DelayTime);
    }

    [Fact]
    public void CommandUnit_WithArguments()
    {
        var cmd = new CommandUnit(
            "robot/nav", "set_parameter", "cmd-2",
            new List<Argument> { new("x", "int", "1") },
            100);
        Assert.Single(cmd.Arguments!);
        Assert.Equal(100, cmd.DelayTime);
    }

    [Fact]
    public void ReturnCode_EnumValues()
    {
        Assert.Equal(ReturnCode.OK, ReturnCode.OK);
        Assert.NotEqual(ReturnCode.OK, ReturnCode.ERROR);
    }

    [Fact]
    public void Parameter_Construction()
    {
        var param = new Parameter("target", "string", "1,2,3");
        Assert.Equal("target", param.Name);
    }

    [Fact]
    public void Argument_Construction()
    {
        var arg = new Argument("timeout", "int", "5000");
        Assert.Equal("5000", arg.Value);
    }
    }
}