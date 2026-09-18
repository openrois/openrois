using System;
using System.Collections.Generic;
using System.Threading.Tasks;
using OpenRoIS.Interfaces.Bus;
using OpenRoIS.Interfaces.Bus.Models;
using Xunit;
using ReturnCode = OpenRoIS.Interfaces.Hri.ReturnCode;
using Result = OpenRoIS.Interfaces.Hri.Result;

namespace OpenRoIS.Interfaces.Tests
{
    public class BusTests
    {
    [Fact]
    public void ComponentContractError_DefaultReturnCode()
    {
        var err = new ComponentContractError("something went wrong");
        Assert.Equal("something went wrong", err.Message);
        Assert.Equal(ReturnCode.ERROR, err.ReturnCode);
    }

    [Fact]
    public void ComponentContractError_CustomReturnCode()
    {
        var err = new ComponentContractError("bad param", ReturnCode.BAD_PARAMETER);
        Assert.Equal(ReturnCode.BAD_PARAMETER, err.ReturnCode);
    }

    [Fact]
    public void ComponentNotFoundError_InheritsComponentContractError()
    {
        var err = new ComponentNotFoundError("robot/missing");
        Assert.Equal("Component not found: robot/missing", err.Message);
        Assert.Equal(ReturnCode.UNSUPPORTED, err.ReturnCode);
        Assert.Equal("robot/missing", err.ComponentRef);
        Assert.IsAssignableFrom<ComponentContractError>(err);
    }

    [Fact]
    public void ComponentNotFoundError_StillCaughtAsBusAdapterError()
    {
        // The deprecated base stays in the hierarchy for one alpha, so existing
        // catch (BusAdapterError) blocks keep working.
#pragma warning disable CS0618
        Exception err = new ComponentNotFoundError("robot/missing");
        Assert.IsAssignableFrom<BusAdapterError>(err);
        Assert.IsAssignableFrom<ComponentContractError>(new BusAdapterError("old"));
#pragma warning restore CS0618
    }

    [Fact]
    public async Task ComponentContract_CanBeImplemented()
    {
        var adapter = new DummyAdapter();
        var discoverResult = await adapter.Discover(new DiscoverRequest(""));
        Assert.Equal(ReturnCode.OK, discoverResult.ReturnCode);
    }

    [Fact]
    public void EventSink_IsDelegate()
    {
        EventSink sink = async _ => await Task.CompletedTask;
        Assert.NotNull(sink);
    }

    private class DummyAdapter : IComponentContract
    {
        public Task<DiscoverResponse> Discover(DiscoverRequest request)
        {
            return Task.FromResult(new DiscoverResponse(ReturnCode.OK, new List<string>()));
        }

        public Task<InvokeResponse> Invoke(CommandRequest request)
        {
            return Task.FromResult(new InvokeResponse(ReturnCode.OK, "", new List<Result>()));
        }

        public Task<QueryResponse> Query(QueryRequest request)
        {
            return Task.FromResult(new QueryResponse(ReturnCode.OK, new List<Result>()));
        }

        public Task<SubscribeResponse> Subscribe(SubscribeRequest request, EventSink sink)
        {
            return Task.FromResult(new SubscribeResponse(ReturnCode.OK, "sub-1"));
        }

        public Task<ReturnCode> Unsubscribe(string subscribeId)
        {
            return Task.FromResult(ReturnCode.OK);
        }
    }
    }
}