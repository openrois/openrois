using System;
using System.Collections.Generic;
using System.Text.Json;
using OpenRoIS.Interfaces.Hri;
using OpenRoIS.Interfaces.Common;
using OpenRoIS.Interfaces.Service;
using OpenRoIS.Interfaces.Components.PersonDetection;
using OpenRoIS.Interfaces.Components.Navigation;
using OpenRoIS.Interfaces.Components.SystemInformation;
using Xunit;
using Result = OpenRoIS.Interfaces.Hri.Result;
using ReturnCode = OpenRoIS.Interfaces.Hri.ReturnCode;
using ComponentStatus = OpenRoIS.Interfaces.Common.ComponentStatus;
using CompletedStatus = OpenRoIS.Interfaces.Service.CompletedStatus;
using ErrorType = OpenRoIS.Interfaces.Service.ErrorType;

namespace OpenRoIS.Interfaces.Tests
{
    public class SchemaRoundtripTests
    {
    private static readonly JsonSerializerOptions s_jsonOpts = new()
    {
        PropertyNamingPolicy = JsonNamingPolicy.SnakeCaseLower,
        Converters = { new System.Text.Json.Serialization.JsonStringEnumConverter() },
    };

    [Fact]
    public void Result_JsonRoundtrip()
    {
        var data = new Result("number", "int", "3");
        var json = JsonSerializer.Serialize(data, s_jsonOpts);
        var parsed = JsonSerializer.Deserialize<Result>(json, s_jsonOpts)!;
        Assert.Equal(data, parsed);
    }

    [Fact]
    public void ReturnCode_JsonRoundtrip()
    {
        // C# enum member name (not wire value) — JsonStringEnumConverter uses member names
        var json = "\"OK\"";
        var parsed = JsonSerializer.Deserialize<ReturnCode>(json, s_jsonOpts)!;
        Assert.Equal(ReturnCode.OK, parsed);
    }

    [Fact]
    public void ComponentStatus_JsonRoundtrip()
    {
        var json = "\"READY\"";
        var parsed = JsonSerializer.Deserialize<ComponentStatus>(json, s_jsonOpts)!;
        Assert.Equal(ComponentStatus.READY, parsed);
    }

    [Fact]
    public void CompletedStatus_JsonRoundtrip()
    {
        var json = "\"ABORT\"";
        var parsed = JsonSerializer.Deserialize<CompletedStatus>(json, s_jsonOpts)!;
        Assert.Equal(CompletedStatus.ABORT, parsed);
    }

    [Fact]
    public void ErrorType_JsonRoundtrip()
    {
        // Wire value for COMPONENT_NOT_RESPONDING
        var json = "\"COMPONENT_NOT_RESPONDING\"";
        var parsed = JsonSerializer.Deserialize<ErrorType>(json, s_jsonOpts)!;
        Assert.Equal(ErrorType.COMPONENT_NOT_RESPONDING, parsed);
    }

    [Fact]
    public void PersonDetectedEvent_Construction()
    {
        var evt = new PersonDetectedEvent("2025-01-15T10:30:00Z", 3);
        Assert.Equal("2025-01-15T10:30:00Z", evt.Timestamp);
        Assert.Equal(3, evt.Number);
    }

    [Fact]
    public void NavigationSetParameter_Defaults()
    {
        var cmd = new NavigationSetParameter(new List<string> { "1.0,2.0,0.0" });
        Assert.Single(cmd.TargetPositions!);
        Assert.Equal(0, cmd.TimeLimit);
        Assert.Equal(RoutingPolicy.time, cmd.RoutingPolicy);
    }

    [Fact]
    public void DiscoverRequest_DefaultCondition()
    {
        var req = new OpenRoIS.Interfaces.Contract.Models.DiscoverRequest("");
        Assert.Equal("", req.Condition);
    }

    [Fact]
    public void DiscoverResponse_WithComponentRefs()
    {
        var resp = new OpenRoIS.Interfaces.Contract.Models.DiscoverResponse(
            ReturnCode.OK, new List<string> { "robot/nav" });
        Assert.Equal(ReturnCode.OK, resp.ReturnCode);
        Assert.Single(resp.ComponentRefList!);
    }

    [Fact]
    public void SystemInformationRobotPosition_Construction()
    {
        var result = new SystemInformationRobotPositionResult(
            "2025-01-15T10:30:00Z",
            new List<string> { "robot-a1", "robot-a2" },
            new List<string> { "1.0,2.0,0.0", "3.0,4.0,1.5" });
        Assert.Equal("2025-01-15T10:30:00Z", result.Timestamp);
        Assert.Equal(2, result.RobotRef!.Count);
        Assert.Equal(2, result.PositionData!.Count);
    }

    [Fact]
    public void SystemInformationEngineStatus_Construction()
    {
        var result = new SystemInformationEngineStatusResult(
            ComponentStatus.READY,
            new List<string> { "2025-01-15T08:00:00Z", "2025-01-15T12:00:00Z" });
        Assert.Equal(ComponentStatus.READY, result.Status);
        Assert.Equal(2, result.OperableTime!.Count);
    }
    }
}