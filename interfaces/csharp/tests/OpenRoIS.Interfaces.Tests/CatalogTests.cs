using System;
using System.Text.Json;
using OpenRoIS.Interfaces.Catalog;
using Xunit;
using ComponentFunction = OpenRoIS.Interfaces.Profiles.ComponentFunction;
using NotifyEventParams = OpenRoIS.Interfaces.Service.NotifyEventParams;
using Parameter = OpenRoIS.Interfaces.Hri.Parameter;
using ProfileChangedParams = OpenRoIS.Interfaces.Service.ProfileChangedParams;
using ReturnCode = OpenRoIS.Interfaces.Hri.ReturnCode;

namespace OpenRoIS.Interfaces.Tests
{
    public class CatalogTests
    {
    private static readonly JsonSerializerOptions s_jsonOpts = new()
    {
        Converters = { new System.Text.Json.Serialization.JsonStringEnumConverter() },
    };

    [Fact]
    public void MethodTable_HasSixteenMethods()
    {
        Assert.Equal(16, RoISMethodTypes.ByMethod.Count);
    }

    [Fact]
    public void MethodNames_AreTheWireNames()
    {
        Assert.Equal("rois.system.get_profile", RoISMethods.GetProfile);
        Assert.Equal("rois.command.execute", RoISMethods.Execute);
        Assert.Equal("rois.query.query", RoISMethods.Query);
        Assert.Equal("rois.event.subscribe", RoISMethods.Subscribe);
    }

    [Fact]
    public void MethodTypes_MapParamsAndResult()
    {
        var (paramsType, resultType) = RoISMethodTypes.ByMethod[RoISMethods.Execute];
        Assert.Equal(typeof(ExecuteParams), paramsType);
        Assert.Equal(typeof(ExecuteResult), resultType);
    }

    [Fact]
    public void Streaming_IsNotModelled()
    {
        Assert.Contains("rois.stream.", UnmodelledMethodPrefixes.All);
        Assert.DoesNotContain(
            RoISMethodTypes.ByMethod.Keys,
            name => name.StartsWith("rois.stream.", StringComparison.Ordinal));
    }

    [Fact]
    public void JsonRpcErrorCodes_AreTheStandardValues()
    {
        Assert.Equal(-32700, JsonRpcErrorCodes.ParseError);
        Assert.Equal(-32600, JsonRpcErrorCodes.InvalidRequest);
        Assert.Equal(-32601, JsonRpcErrorCodes.MethodNotFound);
        Assert.Equal(-32602, JsonRpcErrorCodes.InvalidParams);
        Assert.Equal(-32603, JsonRpcErrorCodes.InternalError);
    }

    [Fact]
    public void SearchResult_DeserializesFromTheWire()
    {
        var json = "{\"return_code\":\"OK\",\"component_ref_list\":[\"reachy_real/head\"]}";
        var result = JsonSerializer.Deserialize<SearchResult>(json, s_jsonOpts)!;
        Assert.Equal(ReturnCode.OK, result.ReturnCode);
        Assert.Equal(new[] { "reachy_real/head" }, result.ComponentRefList);
    }

    [Fact]
    public void GetParameterResult_CarriesParameters()
    {
        var json = "{\"return_code\":\"OK\",\"parameters\":"
            + "[{\"name\":\"time_limit\",\"data_type_ref\":\"int\",\"value\":\"30\"}]}";
        var result = JsonSerializer.Deserialize<GetParameterResult>(json, s_jsonOpts)!;
        Assert.NotNull(result.Parameters);
        Assert.Single(result.Parameters!);
        Assert.Equal(new Parameter("time_limit", "int", "30"), result.Parameters![0]);
    }

    [Fact]
    public void NotificationTable_HasFourNotifications()
    {
        Assert.Equal(4, RoISNotificationTypes.ByMethod.Count);
    }

    [Fact]
    public void NotificationNames_AreTheWireNames()
    {
        Assert.Equal("rois.system.notify_error", RoISNotifications.NotifyError);
        Assert.Equal("rois.command.completed", RoISNotifications.Completed);
        Assert.Equal("rois.event.notify_event", RoISNotifications.NotifyEvent);
        Assert.Equal("rois.system.profile_changed", RoISNotifications.ProfileChanged);
    }

    [Fact]
    public void NotificationTypes_MapParams()
    {
        Assert.Equal(typeof(NotifyEventParams), RoISNotificationTypes.ByMethod[RoISNotifications.NotifyEvent]);
        Assert.Equal(typeof(ProfileChangedParams), RoISNotificationTypes.ByMethod[RoISNotifications.ProfileChanged]);
    }

    [Fact]
    public void CommandTypes_AreTheStandardNames()
    {
        Assert.Equal("start", RoISCommandTypes.Start);
        Assert.Equal("stop", RoISCommandTypes.Stop);
        Assert.Equal("suspend", RoISCommandTypes.Suspend);
        Assert.Equal("resume", RoISCommandTypes.Resume);
        Assert.Equal("set_parameter", RoISCommandTypes.SetParameter);
    }

    [Fact]
    public void GetProfileResult_CarriesComponentProfilesByRef()
    {
        var json = "{\"return_code\":\"OK\","
            + "\"profile\":{\"identifier\":{\"authority\":\"OpenRoIS\",\"code\":\"reachy_real\"},"
            + "\"component_ids\":[\"reachy_real/head\"]},"
            + "\"component_profiles\":{\"reachy_real/head\":"
            + "{\"identifier\":{\"authority\":\"OpenRoIS\",\"code\":\"Head\"},"
            + "\"name\":\"head\",\"function\":\"actuation\"}}}";
        var result = JsonSerializer.Deserialize<GetProfileResult>(json, s_jsonOpts)!;
        Assert.Equal(new[] { "reachy_real/head" }, result.Profile!.ComponentIds);
        var head = result.ComponentProfiles!["reachy_real/head"];
        Assert.Equal("head", head.Name);
        Assert.Equal("Head", head.Identifier.Code);
        Assert.Equal(ComponentFunction.actuation, head.Function);
    }

    [Fact]
    public void FailureResult_NeedsOnlyTheReturnCode()
    {
        var result = JsonSerializer.Deserialize<GetProfileResult>(
            "{\"return_code\":\"ERROR\"}", s_jsonOpts)!;
        Assert.Equal(ReturnCode.ERROR, result.ReturnCode);
        Assert.Null(result.Profile);
        Assert.Null(result.ComponentProfiles);
    }
    }
}
