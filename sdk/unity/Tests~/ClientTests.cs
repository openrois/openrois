#nullable enable
using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.Diagnostics;
using System.Linq;
using System.Reflection;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using NUnit.Framework;
using OpenRoIS.Interfaces.Catalog;
using OpenRoIS.Interfaces.Hri;
using OpenRoIS.Interfaces.Service;
using OpenRoIS.Sdk.JsonRpc;
using OpenRoIS.Sdk.Transport;

namespace OpenRoIS.Sdk.Core.Tests
{

  public sealed class ClientTests
  {
    private const string Connect = "rois.system.connect";
    private const string Disconnect = "rois.system.disconnect";
    private const string Search = "rois.command.search";

    private static Dictionary<string, Func<JsonElement, string>> Answer(
        string method, Func<JsonElement, string> answer)
    {
      return new Dictionary<string, Func<JsonElement, string>> { [method] = answer };
    }

    private static Task<(int Code, string Reason)> CloseOf(RoISClient client)
    {
      return Transports.CloseOf(client.Transport);
    }

    private static string Completed(string commandId)
    {
      return Wire.Notification(
          RoISNotifications.Completed, new { command_id = commandId, status = "OK" });
    }

    [Test]
    public async Task ConnectAsyncGivesAClient()
    {
      var client = await RoISClient.ConnectAsync(Transports.Scripted("/malformed"));

      Assert.That(client.Transport.State, Is.EqualTo(TransportState.Connected));
      await client.DisconnectAsync();
    }

    [Test]
    public async Task AwaitUsingDisconnectsWhenTheBlockEnds()
    {
      Task<(int Code, string Reason)> closed;
      await using (var client = await RoISClient.ConnectAsync(Transports.Scripted("/reverse")))
      {
        closed = CloseOf(client);
      }

      Assert.That(await closed.Soon(), Is.EqualTo((1000, "client closed")));
    }

    [Test]
    public async Task ConnectPassesOnTheTimeouts()
    {
      await using var client = await RoISClient.ConnectAsync(
          Transports.Scripted("/reverse"), requestTimeout: TimeSpan.FromSeconds(1));

      await Expect.Throws<RequestTimeoutException>(client.SearchAsync("alone"));
    }

    [Test]
    public async Task ARefusedConnectRaisesAndClosesTheConnection()
    {
      var ended = new TaskCompletionSource<int?>(TaskCreationOptions.RunContinuationsAsynchronously);
      await using var server = TestServer.Serving(async peer =>
      {
        var request = await peer.ReceiveAsync();
        await peer.SendAsync(Wire.Reply(request!.Value, ("return_code", "ERROR")));
        await peer.LeftAsync();
        ended.TrySetResult(peer.CloseCode);
      });

      var error = await Expect.Throws<RoISException>(RoISClient.ConnectAsync(server.Url));

      Assert.That(error.ReturnCode, Is.EqualTo(ReturnCode.ERROR));
      Assert.That(error.Method, Is.EqualTo(Connect));
      Assert.That(await ended.Task.Soon(), Is.EqualTo(1000));
    }

    [Test]
    public async Task ACancelledConnectDoesNotWaitForASilentPeer()
    {
      await using var server = TestServer.Deaf();
      using var cancel = new CancellationTokenSource(TimeSpan.FromMilliseconds(50));

      // Waiting for this peer would take the 10 seconds of the closing handshake.
      await Expect.Throws<OperationCanceledException>(
          RoISClient.ConnectAsync(server.Url, cancellationToken: cancel.Token));
    }

    [Test]
    public async Task ARequestTimeoutDuringConnectDoesNotWaitForASilentPeer()
    {
      await using var server = TestServer.Deaf();

      await Expect.Throws<RequestTimeoutException>(RoISClient.ConnectAsync(
          server.Url, requestTimeout: TimeSpan.FromMilliseconds(50)));
    }

    [Test]
    public async Task ConnectFailsWithAConnectionError()
    {
      await Expect.Throws<RoISConnectionException>(
          RoISClient.ConnectAsync($"ws://127.0.0.1:{Transports.FreePort()}"));
    }

    [Test]
    public async Task InvalidParamsGoToTheEngineThatRefusesThem()
    {
      // The generated classes do not describe their constraints, so unlike the other two
      // clients this one leaves the refusal to the engine.
      await using var engine = new TestEngine(Answer(
          "rois.command.execute",
          request => Wire.Failure(request, -32602, "Invalid params", null)));
      await using var client = await RoISClient.ConnectAsync(engine.Url);

      var error = await Expect.Throws<RpcException>(
          client.ExecuteAsync(Array.Empty<ICommandUnitSequenceItem>()));

      Assert.That(error.Code, Is.EqualTo(-32602));
    }

    [Test]
    public async Task AReturnCodeOtherThanOkRaisesRoISException()
    {
      await using var engine = new TestEngine(Answer(
          "rois.command.bind",
          request => Wire.Reply(request, ("return_code", "OUT_OF_RESOURCES"))));
      await using var client = await RoISClient.ConnectAsync(engine.Url);

      var error = await Expect.Throws<RoISException>(client.BindAsync("a/b"));

      Assert.That(error.ReturnCode, Is.EqualTo(ReturnCode.OUT_OF_RESOURCES));
      Assert.That(error.Method, Is.EqualTo("rois.command.bind"));
    }

    [TestCase("surprise", 1)]
    [TestCase("component_ref_list", 5)]
    public async Task AResultThatDoesNotMatchTheCatalogRaises(string field, int value)
    {
      await using var engine = new TestEngine(
          Answer(Search, request => Wire.Reply(request, (field, value))));
      await using var client = await RoISClient.ConnectAsync(engine.Url);

      var error = await Expect.Throws<TransportException>(
          client.SearchAsync(), "Invalid result of rois.command.search");

      Assert.That(error.InnerException, Is.InstanceOf<JsonException>());
    }

    [Test]
    public async Task ExecuteFlattensTheIdsOfTheReplyInOrder()
    {
      static object Unit(string id)
      {
        return new { component_ref = "a/b", command_type = "start", command_id = id };
      }

      await using var engine = new TestEngine(Answer(
          "rois.command.execute",
          request => Wire.Reply(request, ("command_unit_list", new object[]
          {
            Unit("a"),
            new
            {
              branch_list = new object[]
              {
                new { command_list = new[] { Unit("b"), Unit("c") } },
                new { command_list = new[] { Unit("d") } },
              },
            },
          }))));
      await using var client = await RoISClient.ConnectAsync(engine.Url);
      var unit = new CommandUnit("a/b", RoISCommandTypes.Start);

      var ids = await client.ExecuteAsync(new ICommandUnitSequenceItem[]
      {
        unit,
        new ConcurrentCommands(new[] { new Branch(new[] { unit }) }),
      });

      Assert.That(ids, Is.EqualTo(new[] { "a", "b", "c", "d" }));
      var sent = engine.Received[1].GetProperty("params").GetProperty("command_unit_list")[0];
      Assert.That(sent.GetProperty("command_id").GetString(), Is.Empty);
    }

    [Test]
    public async Task GetProfilePassesOnItsCondition()
    {
      await using var engine = new TestEngine();
      await using var client = await RoISClient.ConnectAsync(engine.Url);

      await Expect.Throws<TransportException>(client.GetProfileAsync("the condition"));

      var sent = engine.Received[1].GetProperty("params");
      Assert.That(sent.GetProperty("condition").GetString(), Is.EqualTo("the condition"));
    }

    [Test]
    public async Task GetProfileOkWithoutAProfileIsRefused()
    {
      await using var engine = new TestEngine();
      await using var client = await RoISClient.ConnectAsync(engine.Url);

      await Expect.Throws<TransportException>(client.GetProfileAsync(), "without a profile");
    }

    [Test]
    public async Task AListenerAddedBeforeTheMessageGetsModelParams()
    {
      await using var server = TestServer.Serving(async peer =>
      {
        await foreach (var request in peer.Requests())
        {
          if (request.Method() == Search)
          {
            await peer.SendAsync(Completed("c-1"));
          }
          await peer.SendAsync(Wire.Reply(request));
        }
      });
      await using var client = await RoISClient.ConnectAsync(server.Url);
      var seen = new ConcurrentQueue<CompletedParams>();
      client.On<CompletedParams>(RoISNotifications.Completed, seen.Enqueue);

      await client.SearchAsync();

      Assert.That(seen.Select(completed => completed.CommandId), Is.EqualTo(new[] { "c-1" }));
    }

    [Test]
    public async Task ANotificationWithBadParamsIsAFault()
    {
      await using var server = TestServer.Serving(async peer =>
      {
        await foreach (var request in peer.Requests())
        {
          if (request.Method() == Search)
          {
            await peer.SendAsync(Wire.Notification(RoISNotifications.Completed, new { unknown = 1 }));
          }
          await peer.SendAsync(Wire.Reply(request));
        }
      });
      await using var client = await RoISClient.ConnectAsync(server.Url);
      var faults = new Faults();
      var seen = new ConcurrentQueue<CompletedParams>();
      client.On<Exception>("error", faults.Add);
      client.On<CompletedParams>(RoISNotifications.Completed, seen.Enqueue);

      await client.SearchAsync();

      Assert.That((await faults.First()).Message, Does.Contain("Invalid params"));
      Assert.That(seen, Is.Empty);
    }

    [Test]
    public async Task ANotificationOutsideTheCatalogStaysOnTheTransport()
    {
      await using var server = TestServer.Serving(async peer =>
      {
        await foreach (var request in peer.Requests())
        {
          if (request.Method() == Search)
          {
            await peer.SendAsync(Wire.Notification("vendor.news", new { n = 1 }));
          }
          await peer.SendAsync(Wire.Reply(request));
        }
      });
      await using var client = await RoISClient.ConnectAsync(server.Url);
      var faults = new Faults();
      var seen = new ConcurrentQueue<string>();
      client.On<Exception>("error", faults.Add);
      client.Transport.On(
          "notification", (JsonRpcNotification message) => seen.Enqueue(message.Method));

      await client.SearchAsync();

      Assert.That(seen, Is.EqualTo(new[] { "vendor.news" }));
      Assert.That(faults.Seen, Is.Empty);
    }

    [Test]
    public async Task ATransportFaultReachesTheClientErrorListener()
    {
      await using var client = await RoISClient.ConnectAsync(Transports.Scripted("/malformed"));
      var faults = new Faults();
      client.On<Exception>("error", faults.Add);

      Assert.That(await client.SearchAsync("before"), Is.EqualTo(new[] { "before" }));

      Assert.That(faults.Seen, Has.Count.EqualTo(2));
    }

    [Test]
    public async Task WithNoListenerAFaultOfTheClientIsLoggedOnce()
    {
      var log = new ConcurrentQueue<string>();
      RoISLog.Sink = log.Enqueue;
      try
      {
        await using var client = await RoISClient.ConnectAsync(Transports.Scripted("/malformed"));

        await client.SearchAsync("before");

        Assert.That(log, Has.Count.EqualTo(2));
      }
      finally
      {
        RoISLog.Sink = null;
      }
    }

    [Test]
    public async Task OnRefusesAnEventOrAShapeThatDoesNotExist()
    {
      await using var client = await RoISClient.ConnectAsync(Transports.Scripted("/malformed"));

      Assert.Throws<ArgumentException>(() => client.On("no.such.event", (string _) => { }));
      Assert.Throws<ArgumentException>(
          () => client.On(RoISNotifications.Completed, (string _) => { }));
      Assert.Throws<ArgumentException>(() => client.On("open", (int _, string _) => { }));
    }

    [Test]
    public async Task ALostConnectionFailsCallsLocallyAfterwards()
    {
      var client = await RoISClient.ConnectAsync(Transports.Scripted("/drop"));
      var closed = CloseOf(client);

      await Expect.Throws<RoISConnectionException>(client.SearchAsync("one"));

      Assert.That((await closed.Soon()).Code, Is.EqualTo(1006));
      await Expect.Throws<TransportException>(client.SearchAsync("two"), "not connected");
      await client.DisconnectAsync();
    }

    [Test]
    public async Task DisconnectIsSafeTwiceAndACallAfterItFailsLocally()
    {
      await using var engine = new TestEngine();
      var client = await RoISClient.ConnectAsync(engine.Url);
      var closes = new ConcurrentQueue<int>();
      client.On("close", (int code, string _) => closes.Enqueue(code));

      await client.DisconnectAsync();
      await client.DisconnectAsync();

      Assert.That(closes, Is.EqualTo(new[] { 1000 }));
      await Expect.Throws<TransportException>(client.SearchAsync(), "not connected");
      Assert.That(engine.Methods.Count(method => method == Disconnect), Is.EqualTo(1));
    }

    [Test]
    public async Task OverlappingDisconnectsSendOneRequest()
    {
      await using var engine = new TestEngine();
      var client = await RoISClient.ConnectAsync(engine.Url);

      await Task.WhenAll(
          client.DisconnectAsync(), client.DisconnectAsync(), client.DisposeAsync().AsTask());

      Assert.That(engine.Methods.Count(method => method == Disconnect), Is.EqualTo(1));
    }

    [Test]
    public async Task OverlappingDisconnectsShareAnErrorFromTheEngine()
    {
      await using var engine = new TestEngine(
          Answer(Disconnect, request => Wire.Failure(request, -32603, "boom", null)));
      var client = await RoISClient.ConnectAsync(engine.Url);

      var first = client.DisconnectAsync();
      var second = client.DisconnectAsync();

      await Expect.Throws<RpcException>(first);
      await Expect.Throws<RpcException>(second);
      await client.DisconnectAsync();
      Assert.That(client.Transport.State, Is.EqualTo(TransportState.Disconnected));
    }

    [Test]
    public async Task OneCancelledDisconnectLeavesAnotherCallerItsOutcome()
    {
      var answering = new TaskCompletionSource<bool>(
          TaskCreationOptions.RunContinuationsAsynchronously);
      await using var server = TestServer.Serving(async peer =>
      {
        await foreach (var request in peer.Requests())
        {
          if (request.Method() == Disconnect)
          {
            await answering.Task;
          }
          await peer.SendAsync(Wire.Reply(request));
        }
      });
      var client = await RoISClient.ConnectAsync(server.Url);
      using var cancel = new CancellationTokenSource();
      var first = client.DisconnectAsync(cancel.Token);
      var second = client.DisconnectAsync();

      cancel.Cancel();

      await Expect.Throws<OperationCanceledException>(first);
      answering.SetResult(true);
      await second.Soon();
      Assert.That(client.Transport.State, Is.EqualTo(TransportState.Disconnected));
    }

    [Test]
    public async Task DisconnectAfterAnAbortEndsAtOnce()
    {
      await using var engine = new TestEngine();
      var client = await RoISClient.ConnectAsync(engine.Url);
      var closed = CloseOf(client);

      client.Abort();
      await closed.Soon();

      await client.DisconnectAsync().Soon();
      await Expect.Throws<TransportException>(client.SearchAsync(), "not connected");
    }

    [Test]
    public async Task TheConnectionClosesWhenTheEngineRefusesDisconnect()
    {
      await using var engine = new TestEngine(
          Answer(Disconnect, request => Wire.Reply(request, ("return_code", "ERROR"))));
      var client = await RoISClient.ConnectAsync(engine.Url);

      await Expect.Throws<RoISException>(client.DisconnectAsync());

      Assert.That(client.Transport.State, Is.EqualTo(TransportState.Disconnected));
    }
  }

  /// <summary>
  /// What a Unity player depends on: listeners on the main thread, and a client
  /// that does not need that thread to end.
  /// </summary>
  public sealed class MainThreadTests
  {
    [Test]
    public async Task ListenersAndCallersStayOnTheCapturedContextInOrder()
    {
      const int Count = 500;
      await using var server = TestServer.Serving(async peer =>
      {
        await foreach (var request in peer.Requests())
        {
          if (request.Method() == "vendor.flood")
          {
            for (var index = 0; index < Count; index++)
            {
              await peer.SendAsync(Wire.Notification(
                  RoISNotifications.Completed, new { command_id = $"c{index}", status = "OK" }));
            }
          }
          await peer.SendAsync(Wire.Reply(request));
        }
      });
      using var main = new MainThread();
      var wrongThread = new ConcurrentQueue<string>();

      void Check(string where)
      {
        if (Environment.CurrentManagedThreadId != main.ThreadId)
        {
          wrongThread.Enqueue(where);
        }
      }

      var ids = new List<string>();
      var closes = 0;
      await main.Run(async () =>
      {
        var client = await RoISClient.ConnectAsync(server.Url);
        Check("connect");
        client.On(RoISNotifications.Completed, (CompletedParams completed) =>
        {
          Check("listener");
          ids.Add(completed.CommandId);
        });
        client.On("close", (int _, string _) =>
        {
          Check("close");
          closes++;
        });

        await client.Transport.SendAsync("vendor.flood");
        Check("reply");

        // The last completion was posted ahead of the reply, so it has run by now.
        Assert.That(ids, Is.EqualTo(Enumerable.Range(0, Count).Select(index => $"c{index}")));
        await client.DisconnectAsync();
        Check("disconnect");
        Assert.That(closes, Is.EqualTo(1));
      }).WaitAsync(TimeSpan.FromSeconds(30));

      Assert.That(wrongThread, Is.Empty);
    }

    [Test]
    public async Task ABlockedContextStallsNeitherTheReaderNorTheClose()
    {
      await using var engine = new TestEngine();
      using var main = new MainThread();
      RoISClient? client = null;
      await main.Run(async () => client = await RoISClient.ConnectAsync(engine.Url)).Soon();
      var blocked = new TaskCompletionSource<bool>(
          TaskCreationOptions.RunContinuationsAsynchronously);
      var release = new TaskCompletionSource<bool>(
          TaskCreationOptions.RunContinuationsAsynchronously);
      main.Post(_ =>
      {
        blocked.TrySetResult(true);
        release.Task.Wait();
      }, null);
      await blocked.Task.Soon();

      try
      {
        await client!.DisconnectAsync().Soon();
      }
      finally
      {
        release.TrySetResult(true);
      }
    }

    [Test]
    public async Task AMainThreadThatBlocksOnConnectGetsItsClient()
    {
      await using var engine = new TestEngine();
      using var main = new MainThread();

      await main.Blocking(() =>
      {
        var client = RoISClient.ConnectAsync(engine.Url).GetAwaiter().GetResult();
        Assert.That(client.Transport.State, Is.EqualTo(TransportState.Connected));
      });
    }

    [Test]
    public async Task AMainThreadThatBlocksOnACallGetsItsResult()
    {
      await using var engine = new TestEngine(new Dictionary<string, Func<JsonElement, string>>
      {
        [Transports.Search] = request => Wire.Reply(
            request, ("component_ref_list", new[] { "mock/a" })),
      });
      using var main = new MainThread();
      RoISClient? client = null;
      await main.Run(async () => client = await RoISClient.ConnectAsync(engine.Url)).Soon();

      await main.Blocking(() =>
      {
        var found = client!.SearchAsync().GetAwaiter().GetResult();
        Assert.That(found, Is.EqualTo(new[] { "mock/a" }));
      });
    }

    [Test]
    public async Task AMainThreadThatBlocksOnDisconnectGetsTheSessionEnded()
    {
      await using var engine = new TestEngine();
      using var main = new MainThread();
      RoISClient? client = null;
      await main.Run(async () => client = await RoISClient.ConnectAsync(engine.Url)).Soon();

      await main.Blocking(() => client!.DisconnectAsync().GetAwaiter().GetResult());

      Assert.That(engine.Methods.Last(), Is.EqualTo("rois.system.disconnect"));
      Assert.That(client!.Transport.State, Is.EqualTo(TransportState.Disconnected));
    }

    [Test]
    public async Task AMainThreadThatBlocksOnCloseGetsTheConnectionClosed()
    {
      var answer = new TaskCompletionSource<bool>(
          TaskCreationOptions.RunContinuationsAsynchronously);
      await using var server = HoldingItsCloseAnswer(answer);
      using var main = new MainThread();
      WebSocketTransport? transport = null;
      await main.Run(async () =>
      {
        transport = await Transports.ConnectedAsync(server.Url);
        await transport.SendAsync("vendor.ping");
      }).Soon();

      await main.Blocking(() =>
      {
        var closing = transport!.CloseAsync();
        answer.SetResult(true);
        closing.GetAwaiter().GetResult();
      });

      Assert.That(transport!.State, Is.EqualTo(TransportState.Disconnected));
    }

    [Test]
    public async Task AMainThreadThatBlocksOnDisconnectDuringACloseGetsItsOutcome()
    {
      var answer = new TaskCompletionSource<bool>(
          TaskCreationOptions.RunContinuationsAsynchronously);
      await using var server = HoldingItsCloseAnswer(answer);
      using var main = new MainThread();
      RoISClient? client = null;
      await main.Run(async () => client = await RoISClient.ConnectAsync(server.Url)).Soon();

      // The request fails at once, so the wait for the close starts on this blocked thread,
      // where no earlier await has left it.
      await main.Blocking(() =>
      {
        client!.Transport.StartClose();
        var ending = client.DisconnectAsync();
        answer.SetResult(true);
        Assert.That(
            () => ending.GetAwaiter().GetResult(),
            Throws.InstanceOf<TransportException>());
      });

      Assert.That(client!.Transport.State, Is.EqualTo(TransportState.Disconnected));
    }

    /// <summary>
    /// A server that answers one request, and reads nothing more until told to.
    /// </summary>
    private static TestServer HoldingItsCloseAnswer(TaskCompletionSource<bool> answer)
    {
      return TestServer.Serving(async peer =>
      {
        await peer.SendAsync(Wire.Reply((await peer.ReceiveAsync())!.Value));
        await answer.Task;
        await peer.LeftAsync();
      });
    }

    [Test]
    public async Task AContextThatThrowsDoesNotStopTheReader()
    {
      var log = new ConcurrentQueue<string>();
      RoISLog.Sink = log.Enqueue;
      try
      {
        await using var engine = new TestEngine();
        var transport = new WebSocketTransport();
        var previous = SynchronizationContext.Current;
        SynchronizationContext.SetSynchronizationContext(new RefusingContext());
        Task connecting;
        try
        {
          connecting = transport.ConnectAsync(engine.Url);
        }
        finally
        {
          SynchronizationContext.SetSynchronizationContext(previous);
        }
        await connecting;

        Assert.That((await transport.SendAsync("vendor.ping")).ReturnCode(), Is.EqualTo("OK"));
        await transport.CloseAsync();
        Assert.That(log, Is.Not.Empty);
      }
      finally
      {
        RoISLog.Sink = null;
      }
    }

    private sealed class RefusingContext : SynchronizationContext
    {
      public override void Post(SendOrPostCallback callback, object? state)
      {
        throw new InvalidOperationException("This context takes nothing");
      }
    }
  }

  /// <summary>
  /// What the Editor calls when Play Mode ends. Its assembly stays with Unity,
  /// and this is the part of it that a Unity license does not gate.
  /// </summary>
  public sealed class LiveClientTests
  {
    private static HashSet<RoISClient> Clients()
    {
      var field = typeof(LiveClients).GetField(
          "s_clients", BindingFlags.NonPublic | BindingFlags.Static)!;
      return (HashSet<RoISClient>)field.GetValue(null)!;
    }

    private static bool Listed(RoISClient client)
    {
      var clients = Clients();
      lock (clients)
      {
        return clients.Contains(client);
      }
    }

    private static int ListedCount()
    {
      var clients = Clients();
      lock (clients)
      {
        return clients.Count;
      }
    }

    private static async Task UntilAsync(Func<bool> condition)
    {
      var clock = Stopwatch.StartNew();
      while (!condition() && clock.Elapsed < Expect.Promptly)
      {
        await Task.Delay(5);
      }
    }

    [Test]
    public async Task EndAllEndsASessionAnAttemptAndADeafPeerWithinItsPatience()
    {
      await using var engine = new TestEngine();
      await using var deaf = DeafAfterConnect();
      await using var mute = TestServer.Mute();
      var unseen = await Unseen.During(async () =>
      {
        using var main = new MainThread();
        RoISClient? answering = null;
        RoISClient? silent = null;
        Task? attempt = null;
        await main.Run(async () =>
        {
          answering = await RoISClient.ConnectAsync(engine.Url);
          silent = await RoISClient.ConnectAsync(deaf.Url);
          attempt = RoISClient.ConnectAsync(mute.Url);
        }).Soon();
        var answeringClosed = Transports.CloseOf(answering!.Transport);
        var silentClosed = Transports.CloseOf(silent!.Transport);
        await Task.Delay(20);

        // The Editor blocks its main thread here, with every client tied to its context.
        await main.Blocking(() => LiveClients.EndAll(TimeSpan.FromSeconds(1)));

        // The closing handshake with the deaf peer would take 10 seconds, past that limit.
        Assert.That((await answeringClosed.Soon()).Code, Is.EqualTo(1000));
        Assert.That((await silentClosed.Soon()).Code, Is.EqualTo(1006));
        await Expect.Throws<RoISConnectionException>(attempt!, "closed by client");
        Assert.That(Listed(answering!), Is.False);
        Assert.That(Listed(silent!), Is.False);
        Assert.That(engine.Methods.Last(), Is.EqualTo("rois.system.disconnect"));
      });

      Assert.That(unseen, Is.Empty);
    }

    private static TestServer DeafAfterConnect()
    {
      return TestServer.Serving(async peer =>
      {
        var request = await peer.ReceiveAsync();
        await peer.SendAsync(Wire.Reply(request!.Value));
        await Task.Delay(Timeout.Infinite, peer.Stopped);
      });
    }

    [Test]
    public async Task NoClientConnectsWhileRefused()
    {
      await using var engine = new TestEngine();
      LiveClients.Refuse();
      try
      {
        await Expect.Throws<RoISConnectionException>(
            RoISClient.ConnectAsync(engine.Url), "Play Mode is ending");
      }
      finally
      {
        LiveClients.Admit();
      }
      Assert.That(engine.Methods, Is.Empty);

      await using var client = await RoISClient.ConnectAsync(engine.Url);
      Assert.That(engine.Methods, Is.EqualTo(new[] { "rois.system.connect" }));
    }

    [Test]
    public async Task AListenerThatConnectsAgainDuringTheEndOpensNothing()
    {
      await using var engine = new TestEngine();
      using var main = new MainThread();
      var again = new TaskCompletionSource<Task>(TaskCreationOptions.RunContinuationsAsynchronously);
      await main.Run(async () =>
      {
        var client = await RoISClient.ConnectAsync(engine.Url);
        client.On("close", (int code, string reason) =>
            again.TrySetResult(RoISClient.ConnectAsync(engine.Url)));
      }).Soon();

      // In this order, as the Editor goes. The listener runs once the main thread is free.
      LiveClients.Refuse();
      try
      {
        await main.Blocking(() => LiveClients.EndAll(TimeSpan.FromSeconds(1)));
        await Expect.Throws<RoISConnectionException>(await again.Task.Soon(), "Play Mode is ending");
      }
      finally
      {
        LiveClients.Admit();
      }
      Assert.That(
          engine.Methods.Count(method => method == "rois.system.connect"), Is.EqualTo(1));
    }

    [Test]
    public async Task AFailedConnectLeavesNoClientListed()
    {
      var before = ListedCount();

      await Expect.Throws<RoISConnectionException>(
          RoISClient.ConnectAsync($"ws://127.0.0.1:{Transports.FreePort()}"));

      Assert.That(ListedCount(), Is.LessThanOrEqualTo(before));
    }

    [Test]
    public async Task ARefusedConnectStaysListedWhileItsPeerHoldsItOpen()
    {
      await using var deaf = TestServer.Serving(async peer =>
      {
        var request = await peer.ReceiveAsync();
        await peer.SendAsync(Wire.Reply(request!.Value, ("return_code", "OUT_OF_RESOURCES")));
        await Task.Delay(Timeout.Infinite, peer.Stopped);
      });
      var before = ListedCount();

      await Expect.Throws<RoISException>(RoISClient.ConnectAsync(deaf.Url));

      // The caller has no client to end, so only the list can still reach this connection.
      Assert.That(ListedCount(), Is.EqualTo(before + 1));
      LiveClients.EndAll(TimeSpan.FromMilliseconds(100));
      await UntilAsync(() => ListedCount() == before);
      Assert.That(ListedCount(), Is.EqualTo(before));
    }

    [Test]
    public async Task AConnectionThatEndsWithItsReplyNeverLooksConnected()
    {
      await using var engine = new TestEngine();
      var client = await RoISClient.ConnectAsync(engine.Url);
      await client.Transport.CloseAsync();

      // A close can overtake the caller of the reply, which runs this afterwards. Timing does
      // not decide that order in a test, so the test runs the late step by itself.
      client.Started();

      await Expect.Throws<TransportException>(client.SearchAsync(), "client is not connected");
    }

    [Test]
    public async Task AStoppedWaitForDisconnectLeavesNoUnseenFailure()
    {
      await using var deaf = DeafAfterConnect();
      var unseen = await Unseen.During(async () =>
      {
        var client = await RoISClient.ConnectAsync(deaf.Url);
        var closed = Transports.CloseOf(client.Transport);
        using var cancel = new CancellationTokenSource();
        var waiting = client.DisconnectAsync(cancel.Token);
        cancel.Cancel();
        await Expect.Throws<OperationCanceledException>(waiting);

        client.Abort();

        await closed.Soon();
      });

      Assert.That(unseen, Is.Empty);
    }

    [Test]
    public async Task AClientThatLostItsConnectionLeavesTheList()
    {
      var client = await RoISClient.ConnectAsync(Transports.Scripted("/drop"));
      var closed = Transports.CloseOf(client.Transport);
      Assert.That(Listed(client), Is.True);

      await Expect.Throws<RoISConnectionException>(client.SearchAsync("one"));
      await closed.Soon();

      Assert.That(Listed(client), Is.False);
    }
  }

}  // namespace OpenRoIS.Sdk.Core.Tests
