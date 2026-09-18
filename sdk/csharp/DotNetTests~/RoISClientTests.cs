#nullable enable

using System;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using Xunit;

namespace OpenRoIS.Sdk.Tests
{
    public class RoISClientTests
    {
        private static ClientOptions OnSocketThread(string? token = null)
            => new ClientOptions { Token = token, CallbackContext = null, RequestTimeout = TimeSpan.FromSeconds(5) };

        [Fact]
        public async Task ConnectPerformsTheHandshakeAndSendsTheToken()
        {
            using var gateway = new FakeGateway();
            using var client = await RoISClient.ConnectAsync(gateway.Url, OnSocketThread("secret"));
            Assert.True(client.IsConnected);
            Assert.Equal("rois.system.connect", gateway.Methods[0]);
            Assert.Equal("Bearer secret", gateway.LastAuthorization);
        }

        [Fact]
        public async Task SearchProfileQueryAndCommands()
        {
            using var gateway = new FakeGateway();
            using var client = await RoISClient.ConnectAsync(gateway.Url, OnSocketThread());

            var refs = await client.SearchAsync();
            Assert.Equal(new List<string> { "robot_1/Navigation", "robot_1/SystemInformation" }, refs);

            var profile = await client.GetProfileAsync();
            Assert.Equal("fake", profile.GetProperty("identifier").GetProperty("code").GetString());

            var status = await client.QueryAsync("robot_1/Navigation", "component_status");
            Assert.Equal("x", status[0].Name);
            Assert.Equal("1.5", status[0].Value);

            await client.BindAsync("robot_1/Navigation");
            await client.SetParameterAsync("robot_1/Navigation", new[] { new RoISValue("target_positions", "string[]", "[\"kitchen\"]") });
            var parameters = await client.GetParameterAsync("robot_1/Navigation");
            Assert.Equal(2, parameters.Count);

            var executed = await client.ExecuteAsync("robot_1/Navigation");
            Assert.Equal("OK", executed.ReturnCode);
            Assert.Equal("cmd-1", executed.CommandId);
            var results = await client.GetCommandResultAsync("cmd-1");
            Assert.Equal("y", results[1].Name);

            Assert.Equal("robot_1/Navigation", await client.BindAnyAsync("Navigation"));
            await client.ReleaseAsync("robot_1/Navigation");
        }

        [Fact]
        public async Task NonOkReturnCodesRaise()
        {
            using var gateway = new FakeGateway();
            using var client = await RoISClient.ConnectAsync(gateway.Url, OnSocketThread());
            var ex = await Assert.ThrowsAsync<RoISException>(() => client.BindAsync("robot_1/SystemInformation"));
            Assert.Equal(ReturnCodes.OUT_OF_RESOURCES, ex.ReturnCode);
            Assert.Equal("rois.command.bind", ex.Method);
        }

        [Fact]
        public async Task NotificationsReachTheHandlers()
        {
            using var gateway = new FakeGateway();
            using var client = await RoISClient.ConnectAsync(gateway.Url, OnSocketThread());
            var subscribeId = await client.SubscribeAsync("robot_1/Navigation", "reached_target");
            Assert.Equal("sub-1", subscribeId);

            var gotEvent = new TaskCompletionSource<EventNotification>();
            var gotCompletion = new TaskCompletionSource<CommandCompletion>();
            var gotError = new TaskCompletionSource<ErrorNotification>();
            var gotProfileChange = new TaskCompletionSource<bool>();
            client.EventReceived += e => gotEvent.TrySetResult(e);
            client.CommandCompleted += c => gotCompletion.TrySetResult(c);
            client.ErrorNotified += e => gotError.TrySetResult(e);
            client.ProfileChanged += () => gotProfileChange.TrySetResult(true);

            await gateway.PushAsync(new
            {
                jsonrpc = "2.0", method = "rois.event.notify",
                @params = new { event_id = "e1", subscribe_id = "sub-1", component_ref = "robot_1/Navigation", event_type = "reached_target", expire = "", results = new[] { new { name = "target", data_type_ref = "string", value = "kitchen" } } },
            });
            await gateway.PushAsync(new { jsonrpc = "2.0", method = "rois.command.completed", @params = new { command_id = "cmd-1", status = "OK", results = Array.Empty<object>() } });
            await gateway.PushAsync(new { jsonrpc = "2.0", method = "rois.system.notify_error", @params = new { error_id = "err-1", error_type = "COMPONENT_INTERNAL_ERROR", command_id = "", message = "boom" } });
            await gateway.PushAsync(new { jsonrpc = "2.0", method = "rois.system.profile_changed", @params = new { } });

            var evt = await gotEvent.Task.WaitAsync(TimeSpan.FromSeconds(5));
            Assert.Equal("reached_target", evt.EventType);
            Assert.Equal("kitchen", evt.Results[0].Value);
            Assert.Equal("OK", (await gotCompletion.Task.WaitAsync(TimeSpan.FromSeconds(5))).Status);
            Assert.Equal("boom", (await gotError.Task.WaitAsync(TimeSpan.FromSeconds(5))).Message);
            Assert.True(await gotProfileChange.Task.WaitAsync(TimeSpan.FromSeconds(5)));

            await client.UnsubscribeAsync(subscribeId);
        }

        [Fact]
        public async Task CallbacksAreMarshaledToTheCapturedContext()
        {
            using var gateway = new FakeGateway();
            var context = new RecordingContext();
            var options = new ClientOptions { CallbackContext = context, RequestTimeout = TimeSpan.FromSeconds(5) };
            using var client = await RoISClient.ConnectAsync(gateway.Url, options);
            var got = new TaskCompletionSource<bool>();
            client.ProfileChanged += () => got.TrySetResult(true);
            await gateway.PushAsync(new { jsonrpc = "2.0", method = "rois.system.profile_changed", @params = new { } });
            await got.Task.WaitAsync(TimeSpan.FromSeconds(5));
            Assert.Equal(1, context.Posted);
        }

        [Fact]
        public async Task DisconnectClosesAndReportsIt()
        {
            using var gateway = new FakeGateway();
            using var client = await RoISClient.ConnectAsync(gateway.Url, OnSocketThread());
            var closed = new TaskCompletionSource<bool>();
            client.Closed += (_, _) => closed.TrySetResult(true);
            await client.DisconnectAsync();
            Assert.True(await closed.Task.WaitAsync(TimeSpan.FromSeconds(5)));
            Assert.False(client.IsConnected);
        }

        /// <summary>A SynchronizationContext that runs posted callbacks inline and counts them.</summary>
        private sealed class RecordingContext : SynchronizationContext
        {
            public int Posted;

            public override void Post(SendOrPostCallback d, object? state)
            {
                Interlocked.Increment(ref Posted);
                d(state);
            }
        }
    }
}
