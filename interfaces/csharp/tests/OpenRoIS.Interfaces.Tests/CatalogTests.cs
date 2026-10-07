using System;
using System.Text.Json;
using OpenRoIS.Interfaces.Catalog;
using Xunit;
using Parameter = OpenRoIS.Interfaces.Hri.Parameter;
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
    public void FailureResult_NeedsOnlyTheReturnCode()
    {
        var result = JsonSerializer.Deserialize<GetProfileResult>(
            "{\"return_code\":\"ERROR\"}", s_jsonOpts)!;
        Assert.Equal(ReturnCode.ERROR, result.ReturnCode);
        Assert.Null(result.Profile);
    }
    }
}
