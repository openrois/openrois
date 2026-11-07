#nullable enable
using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.Diagnostics;
using System.Linq;
using System.Net;
using System.Net.Sockets;
using System.Net.WebSockets;
using System.Reflection;
using System.Text;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using NUnit.Framework;
using OpenRoIS.Interfaces.Hri;
using OpenRoIS.Sdk.JsonRpc;
using OpenRoIS.Sdk.Transport;

namespace OpenRoIS.Sdk.Core.Tests
{

  /// <summary>What the transport tests have in common.</summary>
  /// <remarks>
  /// Most connect to testing/conformance/scripted_server.py, and
  /// <c>/reverse</c> holds a lone request forever, which is what a timeout
  /// needs. The rest run a <see cref="TestServer"/>.
  /// </remarks>
  internal static class Transports
  {
    internal const string Search = "rois.command.search";

    internal static string Scripted(string path)
    {
      return ScriptedServer.Url + path;
    }

    internal static async Task<WebSocketTransport> ConnectedAsync(
        string url, TimeSpan? requestTimeout = null, TimeSpan? closeTimeout = null)
    {
      var transport = new WebSocketTransport(requestTimeout);
      if (closeTimeout != null)
      {
        transport.CloseTimeout = closeTimeout.Value;
      }
      await transport.ConnectAsync(url);
      return transport;
    }

    /// <summary>What a transport reports when its connection closes.</summary>
    internal static Task<(int Code, string Reason)> CloseOf(WebSocketTransport transport)
    {
      var closed = new TaskCompletionSource<(int, string)>(
          TaskCreationOptions.RunContinuationsAsynchronously);
      transport.On("close", (int code, string reason) => closed.TrySetResult((code, reason)));
      return closed.Task;
    }

    /// <summary>A port with nothing listening on it.</summary>
    internal static int FreePort()
    {
      var probe = new TcpListener(IPAddress.Loopback, 0);
      probe.Start();
      var port = ((IPEndPoint)probe.LocalEndpoint).Port;
      probe.Stop();
      return port;
    }

    /// <summary>Send a request and read one string of its result.</summary>
    internal static async Task<string?> SearchAsync(WebSocketTransport transport, string condition)
    {
      var result = await transport.SendAsync(Search, new { condition });
      return result.GetProperty("component_ref_list")[0].GetString();
    }

    internal static string ReturnCode(this JsonElement result)
    {
      return result.GetProperty("return_code").GetString()!;
    }
  }

  public sealed class ErrorTests
  {
    [Test]
    public void TheTransportErrorsShareABase()
    {
      Assert.That(new RoISConnectionException("lost"), Is.InstanceOf<TransportException>());
      Assert.That(
          new RequestTimeoutException("m", "req-1", TimeSpan.FromSeconds(1)),
          Is.InstanceOf<TransportException>());
      Assert.That(new RpcException(-32601, "no"), Is.InstanceOf<TransportException>());
    }

    [Test]
    public void AConnectionErrorKeepsItsUrl()
    {
      var error = new RoISConnectionException("lost", "ws://here");

      Assert.That(error.Message, Is.EqualTo("lost"));
      Assert.That(error.Url, Is.EqualTo("ws://here"));
    }

    [Test]
    public void ATimeoutNamesTheRequest()
    {
      var error = new RequestTimeoutException("m", "req-1", TimeSpan.FromSeconds(1.5));

      Assert.That(error.Method, Is.EqualTo("m"));
      Assert.That(error.RequestId, Is.EqualTo("req-1"));
      Assert.That(error.Message, Does.Contain("1.5s"));
    }

    [Test]
    public void AnRpcErrorCarriesItsCodeAndData()
    {
      using var data = JsonDocument.Parse("{\"field\":\"x\"}");

      var error = new RpcException(-32602, "bad", data.RootElement);

      Assert.That(error.Code, Is.EqualTo(-32602));
      Assert.That(error.Data!.Value.GetProperty("field").GetString(), Is.EqualTo("x"));
      Assert.That(error.Message, Is.EqualTo("RPC error -32602: bad"));
    }

    [Test]
    public void ARoISErrorCarriesTheReturnCodeAndTheMethod()
    {
      var error = new RoISException(ReturnCode.OUT_OF_RESOURCES, "rois.command.bind");

      Assert.That(error.ReturnCode, Is.EqualTo(ReturnCode.OUT_OF_RESOURCES));
      Assert.That(error.Method, Is.EqualTo("rois.command.bind"));
    }
  }

  public sealed class CorrelationTests
  {
    [Test]
    public async Task RepliesInReverseOrderReachTheirCallers()
    {
      var transport = await Transports.ConnectedAsync(Transports.Scripted("/reverse"));

      var replies = await Task.WhenAll(
          Transports.SearchAsync(transport, "one"),
          Transports.SearchAsync(transport, "two"),
          Transports.SearchAsync(transport, "three"));

      Assert.That(replies, Is.EqualTo(new[] { "one", "two", "three" }));
      await transport.CloseAsync();
    }

    [Test]
    public async Task AMethodWithNoParamsSendsNone()
    {
      await using var engine = new TestEngine();
      var transport = await Transports.ConnectedAsync(engine.Url);

      await transport.SendAsync("vendor.ping");

      await transport.CloseAsync();
      Assert.That(engine.Received[0].TryGetProperty("params", out _), Is.False);
    }

    [Test]
    public async Task AReplyNobodyWaitsForIsAFault()
    {
      await using var server = TestServer.Serving(async peer =>
      {
        await foreach (var request in peer.Requests())
        {
          await peer.SendAsync(Wire.Reply(request));
          await peer.SendAsync(Wire.Reply(request));
        }
      });
      var transport = await Transports.ConnectedAsync(server.Url);
      var faults = new Faults();
      transport.On<Exception>("error", faults.Add);

      await transport.SendAsync("vendor.ping");

      Assert.That((await faults.First()).Message, Does.Contain("unknown id"));
      await transport.CloseAsync();
    }

    [Test]
    public async Task AJsonRpcErrorReachesItsCallerAsAnRpcException()
    {
      var answers = new Dictionary<string, Func<JsonElement, string>>
      {
        ["vendor.ping"] = request => Wire.Failure(request, -32601, "No such method", new[] { "x" }),
      };
      await using var engine = new TestEngine(answers);
      var transport = await Transports.ConnectedAsync(engine.Url);

      var error = await Expect.Throws<RpcException>(transport.SendAsync("vendor.ping"));

      Assert.That(error.Code, Is.EqualTo(-32601));
      Assert.That(error.Data!.Value[0].GetString(), Is.EqualTo("x"));
      await transport.CloseAsync();
    }

    [Test]
    public async Task AReplyRightAfterItsCancellationLeavesTheReaderWorking()
    {
      await using var server = TestServer.Serving(async peer =>
      {
        await foreach (var request in peer.Requests())
        {
          if (request.Method() == "vendor.cancelled")
          {
            await peer.SendAsync(Wire.Notification("vendor.one", new { }));
          }
          await peer.SendAsync(Wire.Reply(request));
        }
      });
      var transport = await Transports.ConnectedAsync(server.Url);
      var faults = new Faults();
      using var cancel = new CancellationTokenSource();
      transport.On<Exception>("error", faults.Add);

      // The reader runs this and then reaches the reply, with no chance for the caller to run
      // in between and take its request away.
      transport.On("notification", (JsonRpcNotification _) => cancel.Cancel());

      await Expect.Throws<OperationCanceledException>(
          transport.SendAsync("vendor.cancelled", null, cancel.Token));

      Assert.That((await transport.SendAsync("vendor.ping")).ReturnCode(), Is.EqualTo("OK"));
      Assert.That(faults.Seen, Is.Empty);
      await transport.CloseAsync();
    }

    [Test]
    public async Task AReplyToACancelledRequestIsNoFault()
    {
      var answering = new TaskCompletionSource<bool>(
          TaskCreationOptions.RunContinuationsAsynchronously);
      var held = new TaskCompletionSource<bool>(
          TaskCreationOptions.RunContinuationsAsynchronously);
      await using var server = TestServer.Serving(async peer =>
      {
        await foreach (var request in peer.Requests())
        {
          if (request.Method() == "vendor.held")
          {
            held.TrySetResult(true);
            await answering.Task;
          }
          await peer.SendAsync(Wire.Reply(request));
        }
      });
      var transport = await Transports.ConnectedAsync(server.Url);
      var faults = new Faults();
      transport.On<Exception>("error", faults.Add);
      using var cancel = new CancellationTokenSource();

      var call = transport.SendAsync("vendor.held", null, cancel.Token);
      await held.Task.Soon();
      cancel.Cancel();
      await Expect.Throws<OperationCanceledException>(call);
      answering.SetResult(true);

      // The server answers in order, so this reply comes after the one nobody awaits.
      Assert.That((await transport.SendAsync("vendor.ping")).ReturnCode(), Is.EqualTo("OK"));
      Assert.That(faults.Seen, Is.Empty);
      await transport.CloseAsync();
    }

    [Test]
    public async Task TheMemoryOfCancelledRequestsIsBounded()
    {
      const int Remembered = 1024;
      var requests = new ConcurrentQueue<JsonElement>();
      var arrivals = new SemaphoreSlim(0);
      await using var server = TestServer.Serving(async peer =>
      {
        await foreach (var request in peer.Requests())
        {
          if (request.Method() == "vendor.flush")
          {
            while (requests.TryDequeue(out var waiting))
            {
              await peer.SendAsync(Wire.Reply(waiting));
            }
            await peer.SendAsync(Wire.Reply(request));
          }
          else
          {
            requests.Enqueue(request);
            arrivals.Release();
          }
        }
      });
      var transport = await Transports.ConnectedAsync(server.Url);
      var faults = new Faults();
      transport.On<Exception>("error", faults.Add);

      for (var count = 0; count <= Remembered; count++)
      {
        using var cancel = new CancellationTokenSource();
        var call = transport.SendAsync("vendor.ping", null, cancel.Token);

        // A request still in the queue is not sent, and this needs the server to hold each one.
        await arrivals.WaitAsync().Soon();
        cancel.Cancel();
        await Expect.Throws<OperationCanceledException>(call);
      }

      await transport.SendAsync("vendor.flush");

      Assert.That(
          faults.Seen.Select(fault => fault.Message),
          Is.EqualTo(new[] { "Received reply for unknown id: req-1" }));
      await transport.CloseAsync();
    }

    [Test]
    public async Task AFragmentedReplyArrivesWhole()
    {
      const int Size = 200_000;
      await using var server = TestServer.Serving(async peer =>
      {
        await foreach (var request in peer.Requests())
        {
          var id = request.GetProperty("id").GetString();
          await peer.SendFragmentsAsync(
              $"{{\"jsonrpc\":\"2.0\",\"id\":\"{id}\",",
              "\"result\":{\"return_code\":\"OK\",",
              $"\"blob\":\"{new string('y', Size)}\"",
              "}}");
        }
      });
      var transport = await Transports.ConnectedAsync(server.Url);

      var result = await transport.SendAsync("vendor.ping");

      Assert.That(result.GetProperty("blob").GetString(), Has.Length.EqualTo(Size));
      await transport.CloseAsync();
    }

    [Test]
    public async Task AMessageJustUnderTheLimitArrives()
    {
      var size = WebSocketTransport.MaxMessageBytes - (1 << 20);
      var answers = new Dictionary<string, Func<JsonElement, string>>
      {
        ["vendor.big"] = request => Wire.Reply(request, ("blob", new string('x', size))),
      };
      await using var engine = new TestEngine(answers);
      var transport = await Transports.ConnectedAsync(engine.Url);

      var result = await transport.SendAsync("vendor.big");

      Assert.That(result.GetProperty("blob").GetString(), Has.Length.EqualTo(size));
      await transport.CloseAsync();
    }

    [Test]
    public async Task ABurstFromManyThreadsIsAnsweredInFull()
    {
      await using var engine = new TestEngine();
      var transport = await Transports.ConnectedAsync(engine.Url);

      var calls = Enumerable.Range(0, 2000)
          .Select(_ => Task.Run(() => transport.SendAsync("vendor.ping")));

      await Task.WhenAll(calls).WaitAsync(TimeSpan.FromSeconds(30));
      Assert.That(engine.Received, Has.Count.EqualTo(2000));
      await transport.CloseAsync();
    }
  }

  public sealed class TimeoutTests
  {
    private static readonly TimeSpan s_short = TimeSpan.FromMilliseconds(50);

    [Test]
    public void TheDefaultsAreThoseOfEverySdk()
    {
      Assert.That(WebSocketTransport.DefaultRequestTimeout, Is.EqualTo(TimeSpan.FromSeconds(30)));
      Assert.That(WebSocketTransport.DefaultConnectTimeout, Is.EqualTo(TimeSpan.FromSeconds(10)));
    }

    [Test]
    public void ATimeoutThatDoesNotFitATimerIsRefused()
    {
      Assert.Throws<ArgumentOutOfRangeException>(
          () => new WebSocketTransport(TimeSpan.FromSeconds(-1)));
      Assert.Throws<ArgumentOutOfRangeException>(
          () => new WebSocketTransport(connectTimeout: TimeSpan.FromDays(365)));
    }

    [Test]
    public async Task ARequestWithNoReplyTimesOut()
    {
      var transport = await Transports.ConnectedAsync(Transports.Scripted("/reverse"), s_short);

      var error = await Expect.Throws<RequestTimeoutException>(
          transport.SendAsync(Transports.Search, new { condition = "alone" }));

      Assert.That(error.Method, Is.EqualTo(Transports.Search));
      Assert.That(error.RequestId, Is.EqualTo("req-1"));
      Assert.That(transport.State, Is.EqualTo(TransportState.Connected));
      await transport.CloseAsync();
    }

    [Test]
    public async Task AReplyAfterTheTimeoutIsAFault()
    {
      await using var server = TestServer.Serving(async peer =>
      {
        await foreach (var request in peer.Requests())
        {
          await Task.Delay(300);
          await peer.SendAsync(Wire.Reply(request));
        }
      });
      var transport = await Transports.ConnectedAsync(server.Url, s_short);
      var faults = new Faults();
      transport.On<Exception>("error", faults.Add);

      await Expect.Throws<RequestTimeoutException>(transport.SendAsync("vendor.ping"));

      Assert.That((await faults.First()).Message, Does.Contain("unknown id"));
      await transport.CloseAsync();
    }

    [Test]
    public async Task AServerThatNeverAnswersTheHandshakeTimesOut()
    {
      await using var server = TestServer.Mute();
      var transport = new WebSocketTransport(connectTimeout: s_short);

      var error = await Expect.Throws<RoISConnectionException>(
          transport.ConnectAsync(server.Url), "timed out");

      Assert.That(error.Url, Is.EqualTo(server.Url));
      Assert.That(transport.State, Is.EqualTo(TransportState.Disconnected));
    }

    [Test]
    public async Task ASessionOutlivesTheConnectTimeout()
    {
      var transport = new WebSocketTransport(connectTimeout: s_short);
      await transport.ConnectAsync(Transports.Scripted("/malformed"));

      // The timer of the attempt must end with the attempt, or it would cut this session.
      await Task.Delay(s_short * 3);

      Assert.That(transport.State, Is.EqualTo(TransportState.Connected));
      Assert.That(await Transports.SearchAsync(transport, "after"), Is.EqualTo("after"));
      await transport.CloseAsync();
    }

    [Test]
    public async Task ACancelledRequestLeavesTheTransportWorking()
    {
      var transport = await Transports.ConnectedAsync(Transports.Scripted("/malformed"));
      using var cancel = new CancellationTokenSource();
      cancel.Cancel();

      await Expect.Throws<OperationCanceledException>(
          transport.SendAsync(Transports.Search, new { condition = "never" }, cancel.Token));

      Assert.That(transport.State, Is.EqualTo(TransportState.Connected));
      Assert.That(await Transports.SearchAsync(transport, "after"), Is.EqualTo("after"));
      await transport.CloseAsync();
    }
  }

  public sealed class ConnectingTests
  {
    [Test]
    public async Task NothingListeningFailsWithAConnectionError()
    {
      var url = $"ws://127.0.0.1:{Transports.FreePort()}";
      var transport = new WebSocketTransport();

      var error = await Expect.Throws<RoISConnectionException>(transport.ConnectAsync(url));

      Assert.That(error.Url, Is.EqualTo(url));
      Assert.That(transport.State, Is.EqualTo(TransportState.Disconnected));
    }

    [Test]
    public async Task ARefusedHandshakeFailsWithAConnectionError()
    {
      await Expect.Throws<RoISConnectionException>(
          new WebSocketTransport().ConnectAsync(Transports.Scripted("/no-such-script")), "404");
    }

    [TestCase("http://127.0.0.1:1")]
    [TestCase("not a url")]
    [TestCase("ws://127.0.0.1:99999")]
    public async Task ABadUrlFailsWithAConnectionError(string url)
    {
      await Expect.Throws<RoISConnectionException>(new WebSocketTransport().ConnectAsync(url));
    }

    [Test]
    public async Task ConnectingTwiceFailsAndKeepsTheConnection()
    {
      var url = Transports.Scripted("/malformed");
      var transport = await Transports.ConnectedAsync(url);

      await Expect.Throws<RoISConnectionException>(transport.ConnectAsync(url), "Connected");

      Assert.That(transport.State, Is.EqualTo(TransportState.Connected));
      await transport.CloseAsync();
    }

    [Test]
    public async Task CloseDuringConnectEndsTheAttemptWithNoCloseEvent()
    {
      await using var server = TestServer.Mute();
      var transport = new WebSocketTransport();
      var closed = new List<int>();
      transport.On("close", (int code, string _) => closed.Add(code));
      var attempt = transport.ConnectAsync(server.Url);
      await Task.Delay(20);
      Assert.That(transport.State, Is.EqualTo(TransportState.Connecting));

      await transport.CloseAsync().Soon();

      await Expect.Throws<RoISConnectionException>(attempt, "closed by client");
      Assert.That(transport.State, Is.EqualTo(TransportState.Disconnected));
      Assert.That(closed, Is.Empty);
    }

    [Test]
    public async Task CloseDuringConnectReturnsWithTheAttemptOver()
    {
      await using var server = TestServer.Mute();
      var transport = new WebSocketTransport();
      var attempt = transport.ConnectAsync(server.Url);
      await Task.Delay(20);

      await transport.CloseAsync().Soon();

      Assert.That(transport.State, Is.EqualTo(TransportState.Disconnected));
      await transport.ConnectAsync(Transports.Scripted("/malformed"));
      await transport.CloseAsync();
      await Expect.Throws<RoISConnectionException>(attempt, "closed by client");
    }

    [Test]
    public async Task OverlappingClosesDuringConnectAllReturn()
    {
      await using var server = TestServer.Mute();
      var transport = new WebSocketTransport();
      var attempt = transport.ConnectAsync(server.Url);
      await Task.Delay(20);

      await Task.WhenAll(transport.CloseAsync(), transport.CloseAsync()).Soon();

      await Expect.Throws<RoISConnectionException>(attempt, "closed by client");
    }

    [Test]
    public async Task CloseAtAnyPointOfConnectLeavesNoConnectionBehind()
    {
      const int Rounds = 100;
      var arrived = 0;
      var left = 0;
      await using var server = TestServer.Serving(async peer =>
      {
        Interlocked.Increment(ref arrived);
        try
        {
          await peer.LeftAsync();
        }
        finally
        {
          Interlocked.Increment(ref left);
        }
      });

      // This walks the close across the attempt. Timing alone does not reach the moment
      // between the handshake and the state that follows, which has a test of its own.
      for (var round = 0; round < Rounds; round++)
      {
        var transport = new WebSocketTransport();
        var attempt = transport.ConnectAsync(server.Url);
        await Task.Delay(TimeSpan.FromTicks(round * 500));

        await transport.CloseAsync().Soon();

        try
        {
          await attempt.Soon();
        }
        catch (RoISConnectionException error)
        {
          Assert.That(error.Message, Does.Contain("closed by client"));
        }
        await transport.CloseAsync().Soon();
        Assert.That(transport.State, Is.EqualTo(TransportState.Disconnected));
      }

      var clock = Stopwatch.StartNew();
      while (Volatile.Read(ref left) < Volatile.Read(ref arrived) && clock.Elapsed < Expect.Promptly)
      {
        await Task.Delay(10);
      }
      Assert.That(left, Is.EqualTo(arrived));
    }

    [Test]
    public async Task CloseRightAfterTheHandshakeLeavesNoConnectionBehind()
    {
      var left = new TaskCompletionSource<bool>(TaskCreationOptions.RunContinuationsAsynchronously);
      await using var server = TestServer.Serving(async peer =>
      {
        try
        {
          await peer.LeftAsync();
        }
        finally
        {
          left.TrySetResult(true);
        }
      });
      var transport = new WebSocketTransport();
      var events = new ConcurrentQueue<string>();
      transport.On("open", () => events.Enqueue("open"));
      transport.On("close", (int _, string _) => events.Enqueue("close"));
      Task? closing = null;
      transport.AfterHandshake = () => closing = transport.CloseAsync();

      await Expect.Throws<RoISConnectionException>(
          transport.ConnectAsync(server.Url), "closed by client");

      await closing!.Soon();
      Assert.That(transport.State, Is.EqualTo(TransportState.Disconnected));
      Assert.That(events, Is.Empty);
      await left.Task.Soon();
    }

    [Test]
    public async Task ACallerThatBlocksAfterACloseDuringConnectLeavesTheConnectFree()
    {
      await using var server = TestServer.Mute();
      var transport = new WebSocketTransport();
      var attempt = transport.ConnectAsync(server.Url);

      // The end of the attempt releases this close, and a continuation that ran inline there
      // would hold up the attempt it is waiting for.
      var closed = transport.CloseAsync().ContinueWith(
          _ => Task.WhenAny(attempt).Wait(),
          TaskContinuationOptions.ExecuteSynchronously);

      await Expect.Throws<RoISConnectionException>(attempt, "closed by client");
      await closed.Soon();
    }

    [Test]
    public async Task ACancelledConnectLeavesNoUnseenFailure()
    {
      var unseen = await Unseen.During(async () =>
      {
        await using var server = TestServer.Mute();
        var transport = new WebSocketTransport();
        using var cancel = new CancellationTokenSource();
        var attempt = transport.ConnectAsync(server.Url, cancel.Token);
        await Task.Delay(20);

        cancel.Cancel();

        await Expect.Throws<OperationCanceledException>(attempt);
      });

      Assert.That(unseen, Is.Empty);
    }

    [Test]
    public async Task ACancelledConnectLeavesTheTransportDisconnected()
    {
      await using var server = TestServer.Mute();
      var transport = new WebSocketTransport();
      using var cancel = new CancellationTokenSource();
      var attempt = transport.ConnectAsync(server.Url, cancel.Token);
      await Task.Delay(20);

      cancel.Cancel();

      await Expect.Throws<OperationCanceledException>(attempt);
      Assert.That(transport.State, Is.EqualTo(TransportState.Disconnected));
    }

    [Test]
    public async Task OpenFiresWhenTheConnectionOpens()
    {
      var transport = new WebSocketTransport();
      var opened = 0;
      transport.On("open", () => opened++);

      await transport.ConnectAsync(Transports.Scripted("/malformed"));

      Assert.That(opened, Is.EqualTo(1));
      await transport.CloseAsync();
    }

    [Test]
    public async Task NoMessageReachesAListenerAheadOfOpen()
    {
      await using var server = TestServer.Serving(async peer =>
      {
        await peer.SendAsync(Wire.Notification("vendor.first", new { }));
        await peer.LeftAsync();
      });
      var transport = new WebSocketTransport();
      var events = new ConcurrentQueue<string>();
      var heard = new TaskCompletionSource<bool>(TaskCreationOptions.RunContinuationsAsynchronously);
      transport.On("open", () =>
      {
        // A message that could overtake this listener has the time to do so here.
        Thread.Sleep(20);
        events.Enqueue("open");
      });
      transport.On<JsonRpcNotification>("notification", _ =>
      {
        events.Enqueue("notification");
        heard.TrySetResult(true);
      });

      await transport.ConnectAsync(server.Url);
      await heard.Task.Soon();

      Assert.That(events, Is.EqualTo(new[] { "open", "notification" }));
      await transport.CloseAsync();
    }
  }

  public sealed class FaultTests
  {
    private const string Reply = "\"id\": \"req-1\"";

    private static readonly object[] s_unusableText =
    {
      "[1, 2]",
      "\"text\"",
      "null",
      new string('[', 200_000),
      "{\"jsonrpc\": \"1.0\", " + Reply + ", \"result\": {}}",
      "{" + Reply + ", \"result\": {}}",
      "{\"jsonrpc\": \"2.0\", \"id\": true, \"result\": {}}",
      "{\"jsonrpc\": \"2.0\", \"id\": [\"req-1\"], \"result\": {}}",
      "{\"jsonrpc\": \"2.0\", " + Reply + ", \"result\": {}, \"extra\": 1}",
      "{\"jsonrpc\": \"2.0\", " + Reply + ", \"error\": \"text\"}",
      "{\"jsonrpc\": \"2.0\", " + Reply + ", \"error\": {\"code\": \"x\", \"message\": \"m\"}}",
      "{\"jsonrpc\": \"2.0\", " + Reply + ", \"error\": {\"code\": 1}}",
      "{\"jsonrpc\": \"2.0\", " + Reply + ", \"method\": \"server.request\"}",
      "{\"jsonrpc\": \"2.0\", \"method\": 7}",
      "{\"jsonrpc\": \"2.0\", \"method\": \"m.m\", \"params\": 7}",
      "{\"jsonrpc\": \"2.0\", \"method\": \"ab\"}",
      "{\"jsonrpc\": \"2.0\", \"method\": \"\"}",
      "{\"jsonrpc\": \"2.0\", \"method\": \"m.m\", \"params\": {\"x\": NaN}}",
      "{\"jsonrpc\": \"2.0\", \"method\": \"m.m\", \"params\": {\"x\": -Infinity}}",
      "{\"jsonrpc\": \"2.0\", \"method\": \"\\ud800abc\"}",
      "{\"jsonrpc\": \"\\ud800\", \"method\": \"m.m\"}",
    };

    private static async Task ExpectOneFaultAsync(Func<Peer, Task> send)
    {
      await using var server = TestServer.Serving(async peer =>
      {
        await foreach (var request in peer.Requests())
        {
          await send(peer);
          await peer.SendAsync(Wire.Reply(request));
        }
      });
      var transport = await Transports.ConnectedAsync(server.Url);
      var faults = new Faults();
      var seen = new ConcurrentQueue<JsonRpcNotification>();
      transport.On<Exception>("error", faults.Add);
      transport.On<JsonRpcNotification>("notification", seen.Enqueue);

      var result = await transport.SendAsync("vendor.ping");

      Assert.That(result.ReturnCode(), Is.EqualTo("OK"));
      Assert.That(faults.Seen, Has.Count.EqualTo(1));
      Assert.That(faults.Seen, Is.All.InstanceOf<TransportException>());
      Assert.That(seen, Is.Empty);
      await transport.CloseAsync();
    }

    [Test]
    public async Task AMalformedMessageReachesTheErrorListener()
    {
      var transport = await Transports.ConnectedAsync(Transports.Scripted("/malformed"));
      var faults = new Faults();
      transport.On<Exception>("error", faults.Add);

      Assert.That(await Transports.SearchAsync(transport, "before"), Is.EqualTo("before"));

      Assert.That(faults.Seen, Has.Count.EqualTo(2));
      Assert.That(faults.Seen, Is.All.InstanceOf<TransportException>());
      Assert.That(await Transports.SearchAsync(transport, "after"), Is.EqualTo("after"));
      await transport.CloseAsync();
    }

    [Test]
    public async Task WithNoErrorListenerAFaultIsLogged()
    {
      var log = new ConcurrentQueue<string>();
      RoISLog.Sink = log.Enqueue;
      try
      {
        var transport = await Transports.ConnectedAsync(Transports.Scripted("/malformed"));

        await Transports.SearchAsync(transport, "before");

        Assert.That(log, Has.Count.EqualTo(2));
        Assert.That(log, Is.All.StartsWith("OpenRoIS: "));
        await transport.CloseAsync();
      }
      finally
      {
        RoISLog.Sink = null;
      }
    }

    [TestCaseSource(nameof(s_unusableText))]
    public async Task AnUnusableMessageIsAFaultAndTheTransportKeepsWorking(string message)
    {
      await ExpectOneFaultAsync(peer => peer.SendAsync(message));
    }

    [TestCase("{\"jsonrpc\": \"2.0\", \"method\": \"m.m\", \"params\": {}}")]
    [TestCase("not text at all")]
    public async Task ABinaryMessageIsAFaultAndTheTransportKeepsWorking(string message)
    {
      await ExpectOneFaultAsync(peer => peer.SendBinaryAsync(Encoding.UTF8.GetBytes(message)));
    }

    [Test]
    public async Task AMessageOverTheLimitSaysSoAndIsNotADroppedConnection()
    {
      var answers = new Dictionary<string, Func<JsonElement, string>>
      {
        ["vendor.big"] = request =>
            Wire.Reply(request, ("blob", new string('x', WebSocketTransport.MaxMessageBytes))),
      };
      await using var engine = new TestEngine(answers);
      var transport = await Transports.ConnectedAsync(engine.Url);
      var closed = Transports.CloseOf(transport);

      await Expect.Throws<RoISConnectionException>(transport.SendAsync("vendor.big"), "code 1009");

      var (code, reason) = await closed.Soon();
      Assert.That(code, Is.EqualTo(1009));
      Assert.That(reason, Does.Contain(WebSocketTransport.MaxMessageBytes.ToString()));
    }

    [Test]
    public async Task AMessageThatCannotBeDecodedCostsOneMessage()
    {
      await using var engine = new TestEngine();
      var transport = await Transports.ConnectedAsync(engine.Url);
      var faults = new Faults();
      transport.On<Exception>("error", faults.Add);

      // A socket refuses this text by itself where it validates, and only this catch stands
      // behind a runtime that does not, so the test hands the bytes over directly.
      transport.Receive(WebSocketMessageType.Text, new byte[] { 0xC3, 0x28 }, 2);

      Assert.That((await faults.First()).Message, Does.Contain("Cannot read a message"));
      await transport.SendAsync("vendor.ping").Soon();
      await transport.CloseAsync();
    }

    [Test]
    public async Task TextThatIsNotUtf8SaysSoAndIsNotADroppedConnection()
    {
      await using var server = TestServer.Serving(async peer =>
      {
        await peer.ReceiveAsync();
        await peer.SendInvalidTextAsync();
        await peer.LeftAsync();
      });
      var transport = await Transports.ConnectedAsync(server.Url);
      var faults = new Faults();
      transport.On<Exception>("error", faults.Add);
      var closed = Transports.CloseOf(transport);

      await Expect.Throws<RoISConnectionException>(
          transport.SendAsync("vendor.ping"), "code 1006, reason: refused frame");

      Assert.That(await closed.Soon(), Is.EqualTo((1006, "refused frame")));
      Assert.That(await faults.First(), Is.InstanceOf<TransportException>());
    }

    [Test]
    public async Task ASendStuckWhenTheConnectionEndsFailsAndLeavesNoUnseenFailure()
    {
      var unseen = new ConcurrentQueue<Exception>();
      void Record(object? sender, UnobservedTaskExceptionEventArgs failure)
      {
        unseen.Enqueue(failure.Exception!);
      }

      TaskScheduler.UnobservedTaskException += Record;
      try
      {
        var arrived = new TaskCompletionSource<Peer>(
            TaskCreationOptions.RunContinuationsAsynchronously);
        await using var server = TestServer.Deaf(peer => arrived.TrySetResult(peer));
        var transport = await Transports.ConnectedAsync(server.Url);
        var closed = Transports.CloseOf(transport);
        var peer = await arrived.Task.Soon();

        // The kernel would otherwise take all of this, and no send would have to wait.
        var blob = new string('x', 1 << 23);
        var sends = Enumerable.Range(0, 4)
            .Select(_ => transport.SendAsync("vendor.ping", new { blob }))
            .ToArray();
        await Task.Delay(50);

        peer.Drop();

        foreach (var send in sends)
        {
          await Expect.Throws<RoISConnectionException>(send);
        }
        await closed.Soon();
      }
      finally
      {
        GC.Collect();
        GC.WaitForPendingFinalizers();
        TaskScheduler.UnobservedTaskException -= Record;
      }
      Assert.That(unseen, Is.Empty);
    }

    /// <summary>Fill the socket of a peer that reads nothing, so that the next send waits.</summary>
    private static Task[] StickSends(WebSocketTransport transport)
    {
      // The kernel would otherwise take all of this, and no send would have to wait.
      var blob = new string('x', 1 << 23);
      return Enumerable.Range(0, 2)
          .Select(_ => transport.SendAsync("vendor.stuck", new { blob }))
          .ToArray();
    }

    [Test]
    public async Task ARequestCancelledInTheQueueIsNotSent()
    {
      var read = new TaskCompletionSource<bool>(TaskCreationOptions.RunContinuationsAsynchronously);
      var seen = new ConcurrentQueue<string>();
      await using var server = TestServer.Serving(async peer =>
      {
        await read.Task;
        await foreach (var request in peer.Requests())
        {
          seen.Enqueue(request.Method());
          await peer.SendAsync(Wire.Reply(request));
        }
      });
      var transport = await Transports.ConnectedAsync(server.Url);
      var stuck = StickSends(transport);
      using var cancel = new CancellationTokenSource();
      var queued = transport.SendAsync("vendor.gone", null, cancel.Token);
      await Task.Delay(50);

      cancel.Cancel();
      await Expect.Throws<OperationCanceledException>(queued);
      read.SetResult(true);

      await transport.SendAsync("vendor.after").Soon();
      await Task.WhenAll(stuck).Soon();
      Assert.That(seen, Does.Not.Contain("vendor.gone"));
      Assert.That(seen, Does.Contain("vendor.after"));
      await transport.CloseAsync();
    }

    [Test]
    public async Task AConnectionThatEndedStuckLeavesNothingForTheNext()
    {
      var connections = 0;
      await using var server = TestServer.Serving(async peer =>
      {
        if (Interlocked.Increment(ref connections) == 1)
        {
          await Task.Delay(Timeout.Infinite, peer.Stopped);
        }
        await foreach (var request in peer.Requests())
        {
          await peer.SendAsync(Wire.Reply(request));
        }
      });
      var transport = await Transports.ConnectedAsync(
          server.Url, closeTimeout: TimeSpan.FromMilliseconds(100));
      var faults = new Faults();
      transport.On<Exception>("error", faults.Add);
      var stuck = StickSends(transport);
      await Task.Delay(50);

      // Its close frame waits behind the sends, until the close timeout drops the connection.
      await transport.CloseAsync().Soon();
      foreach (var send in stuck)
      {
        await Expect.Throws<RoISConnectionException>(send);
      }
      await transport.ConnectAsync(server.Url).Soon();

      var result = await transport.SendAsync("vendor.ping").Soon();
      Assert.That(result.ReturnCode(), Is.EqualTo("OK"));
      await Task.Delay(50);
      Assert.That(transport.State, Is.EqualTo(TransportState.Connected));
      await transport.CloseAsync();
    }

    [Test]
    public async Task AnAnswerToACloseCannotOutlastTheCloseTimeout()
    {
      var close = new TaskCompletionSource<bool>(TaskCreationOptions.RunContinuationsAsynchronously);
      await using var server = TestServer.Serving(async peer =>
      {
        await close.Task;
        await peer.CloseAsync(1001, "server");
        await Task.Delay(Timeout.Infinite, peer.Stopped);
      });
      var transport = await Transports.ConnectedAsync(
          server.Url, closeTimeout: TimeSpan.FromMilliseconds(100));
      var faults = new Faults();
      transport.On<Exception>("error", faults.Add);
      var closed = Transports.CloseOf(transport);
      var stuck = StickSends(transport);
      await Task.Delay(50);

      close.SetResult(true);

      Assert.That((await closed.Soon()).Code, Is.EqualTo(1001));
      Assert.That((await faults.First()).Message, Does.Contain("Cannot answer the close frame"));
      foreach (var send in stuck)
      {
        await Expect.Throws<RoISConnectionException>(send);
      }
    }

    [Test]
    public async Task ADroppedConnectionFailsPendingRequestsAndFiresClose()
    {
      var transport = await Transports.ConnectedAsync(Transports.Scripted("/drop"));
      var closed = Transports.CloseOf(transport);

      var calls = new[] { "one", "two", "three" }
          .Select(condition => transport.SendAsync(Transports.Search, new { condition }))
          .ToArray();

      foreach (var call in calls)
      {
        await Expect.Throws<RoISConnectionException>(call);
      }
      Assert.That((await closed.Soon()).Code, Is.EqualTo(1006));
      Assert.That(transport.State, Is.EqualTo(TransportState.Disconnected));
      await Expect.Throws<TransportException>(
          transport.SendAsync(Transports.Search, new { condition = "after" }), "Disconnected");
    }

    [Test]
    public async Task AServerCloseReachesCloseWithItsCodeAndReason()
    {
      var transport = await Transports.ConnectedAsync(Transports.Scripted("/close-1001"));
      var closed = Transports.CloseOf(transport);

      await Transports.SearchAsync(transport, "only");

      Assert.That(await closed.Soon(), Is.EqualTo((1001, "scripted close")));
    }

    [Test]
    public async Task AServerCloseWithNoCodeReportsWhatTheSocketSays()
    {
      await using var server = TestServer.Serving(async peer =>
      {
        await peer.ReceiveAsync();
        await peer.SendEmptyCloseAsync();
        await peer.LeftAsync();
      });
      var transport = await Transports.ConnectedAsync(server.Url);
      var closed = Transports.CloseOf(transport);
      var call = transport.SendAsync("vendor.ping");

      Assert.That(await closed.Soon(), Is.EqualTo((1000, "")));
      await Expect.Throws<RoISConnectionException>(call);
    }

    [Test]
    public async Task RequestsFailWhenAServerCloses()
    {
      var transport = await Transports.ConnectedAsync(Transports.Scripted("/close-1001"));
      var closed = Transports.CloseOf(transport);
      await Transports.SearchAsync(transport, "first");
      await closed.Soon();

      await Expect.Throws<TransportException>(Transports.SearchAsync(transport, "second"));
    }
  }

  public sealed class ClosingTests
  {
    private static readonly TimeSpan s_quickly = TimeSpan.FromMilliseconds(100);

    [Test]
    public async Task SendingBeforeConnectingFailsLocally()
    {
      await Expect.Throws<TransportException>(
          new WebSocketTransport().SendAsync("vendor.ping"), "Disconnected");
    }

    [Test]
    public async Task ClosingBeforeConnectingDoesNothing()
    {
      await new WebSocketTransport().CloseAsync();
    }

    [Test]
    public async Task CloseReportsTheCodeAndReasonItWasGiven()
    {
      var transport = await Transports.ConnectedAsync(Transports.Scripted("/malformed"));
      var closed = Transports.CloseOf(transport);

      await transport.CloseAsync(4001, "done here");

      Assert.That(closed.IsCompleted, Is.True);
      Assert.That(closed.Result, Is.EqualTo((4001, "done here")));
      Assert.That(transport.State, Is.EqualTo(TransportState.Disconnected));
    }

    [Test]
    public async Task APeerThatIgnoresTheCloseFrameStillGetsTheCodeReported()
    {
      await using var server = TestServer.Deaf();
      var transport = await Transports.ConnectedAsync(server.Url, closeTimeout: s_quickly);
      var closed = Transports.CloseOf(transport);

      await transport.CloseAsync(4001, "done here").Soon();

      Assert.That(await closed.Soon(), Is.EqualTo((4001, "done here")));
      Assert.That(transport.State, Is.EqualTo(TransportState.Disconnected));
    }

    [Test]
    public async Task CloseReportsWhatTheCallerAskedWhateverThePeerAnswers()
    {
      var closing = new TaskCompletionSource<bool>(
          TaskCreationOptions.RunContinuationsAsynchronously);
      await using var server = TestServer.Serving(async peer =>
      {
        // Not reading keeps the close frame of the client from being echoed, as usual.
        await closing.Task;
        await peer.CloseAsync(1001, "going away");
        await peer.LeftAsync();
      });
      var transport = await Transports.ConnectedAsync(server.Url);
      var closed = Transports.CloseOf(transport);
      var closes = transport.CloseAsync(4001, "done here");

      closing.SetResult(true);

      await closes.Soon();
      Assert.That(await closed.Soon(), Is.EqualTo((4001, "done here")));
    }

    [Test]
    public async Task ACancelledCloseFinishesWithoutItsCaller()
    {
      await using var server = TestServer.Deaf();
      var transport = await Transports.ConnectedAsync(server.Url, closeTimeout: s_quickly);
      var closed = Transports.CloseOf(transport);
      using var cancel = new CancellationTokenSource();
      var closing = transport.CloseAsync(4001, "done here", cancel.Token);

      cancel.Cancel();

      await Expect.Throws<OperationCanceledException>(closing);

      Assert.That(await closed.Soon(), Is.EqualTo((4001, "done here")));
      Assert.That(transport.State, Is.EqualTo(TransportState.Disconnected));
    }

    [Test]
    public async Task OneCancelledCloseLeavesAnotherCallerWaiting()
    {
      await using var server = TestServer.Deaf();
      var transport = await Transports.ConnectedAsync(server.Url, closeTimeout: s_quickly);
      var closed = Transports.CloseOf(transport);
      using var cancel = new CancellationTokenSource();
      var first = transport.CloseAsync(cancellationToken: cancel.Token);
      var second = transport.CloseAsync();

      cancel.Cancel();

      await Expect.Throws<OperationCanceledException>(first);
      await second.Soon();
      Assert.That(closed.IsCompleted, Is.True);
    }

    [Test]
    public async Task NothingReachesAListenerAfterClose()
    {
      var closing = new TaskCompletionSource<bool>(
          TaskCreationOptions.RunContinuationsAsynchronously);
      await using var server = TestServer.Serving(async peer =>
      {
        // Not reading keeps the close frame from stopping the second message.
        await peer.SendAsync(Wire.Notification("vendor.one", new { }));
        await closing.Task;
        await peer.SendAsync(Wire.Notification("vendor.two", new { }));
        await peer.SendAsync("not json");
        await peer.LeftAsync();
      });
      var transport = new WebSocketTransport();
      var arrived = new TaskCompletionSource<bool>(
          TaskCreationOptions.RunContinuationsAsynchronously);
      var seen = new ConcurrentQueue<string>();
      var faults = new Faults();
      transport.On<Exception>("error", faults.Add);
      transport.On("notification", (JsonRpcNotification message) =>
      {
        seen.Enqueue(message.Method);
        arrived.TrySetResult(true);
      });
      await transport.ConnectAsync(server.Url);
      await arrived.Task.Soon();

      var closes = transport.CloseAsync();
      closing.SetResult(true);
      await closes.Soon();

      Assert.That(seen, Is.EqualTo(new[] { "vendor.one" }));
      Assert.That(faults.Seen, Is.Empty);
    }

    [Test]
    public async Task AnAbortEndsTheConnectionAndTellsEveryone()
    {
      var ended = new TaskCompletionSource<bool>(
          TaskCreationOptions.RunContinuationsAsynchronously);
      await using var server = TestServer.Serving(async peer =>
      {
        try
        {
          await peer.LeftAsync();
        }
        finally
        {
          ended.TrySetResult(true);
        }
      });
      var transport = await Transports.ConnectedAsync(server.Url);
      var closes = new ConcurrentQueue<(int, string)>();
      transport.On("close", (int code, string reason) => closes.Enqueue((code, reason)));
      var closed = Transports.CloseOf(transport);
      var call = transport.SendAsync("vendor.ping");
      await Task.Delay(20);

      transport.Abort();

      await Expect.Throws<RoISConnectionException>(call, "code 1006");
      await closed.Soon();
      await ended.Task.Soon();
      Assert.That(closes, Is.EqualTo(new[] { (1006, "") }));
      Assert.That(transport.State, Is.EqualTo(TransportState.Disconnected));
      await transport.CloseAsync();
      await transport.ConnectAsync(server.Url);
      await transport.CloseAsync();
      Assert.That(closes, Has.Count.EqualTo(2));
    }

    [Test]
    public async Task AnAbortDuringCloseIsNoFailureOfTheCaller()
    {
      await using var server = TestServer.Deaf();
      var transport = await Transports.ConnectedAsync(server.Url);
      var closed = Transports.CloseOf(transport);
      var closing = transport.CloseAsync(4001, "done here");

      transport.Abort();

      await closing.Soon();
      Assert.That(await closed.Soon(), Is.EqualTo((4001, "done here")));
    }

    [Test]
    public async Task ACloseFrameThatCannotBeSentReachesTheErrorListenersAndEndsTheConnection()
    {
      await using var engine = new TestEngine();
      var transport = await Transports.ConnectedAsync(engine.Url);
      var faults = new Faults();
      transport.On<Exception>("error", faults.Add);
      var closed = Transports.CloseOf(transport);

      // A live socket gives no way to fail at exactly this send, so this calls what such a
      // failure calls, on an item of the shape the close frame has.
      const BindingFlags Hidden = BindingFlags.NonPublic | BindingFlags.Instance;
      var type = typeof(WebSocketTransport);
      var closeFrame = Activator.CreateInstance(
          type.GetNestedType("Outgoing", BindingFlags.NonPublic)!,
          Hidden,
          null,
          new object?[] { null, Array.Empty<byte>() },
          null);
      type.GetMethod("SendFailed", Hidden)!.Invoke(transport, new[]
      {
        type.GetField("_socket", Hidden)!.GetValue(transport),
        closeFrame,
        new InvalidOperationException("no frame"),
      });

      Assert.That((await faults.First()).Message, Does.Contain("no frame"));
      Assert.That((await closed.Soon()).Code, Is.EqualTo(1006));
      Assert.That(transport.State, Is.EqualTo(TransportState.Disconnected));
    }

    /// <summary>A peer that closes as soon as a client connects, then waits for the answer.</summary>
    private static TestServer ClosingPeer(Action<int?>? answered = null)
    {
      return TestServer.Serving(async peer =>
      {
        await peer.CloseAsync(1001, "server");
        await peer.LeftAsync();
        answered?.Invoke(peer.CloseCode);

        // A client socket waits for the server to end the TCP connection.
        peer.Drop();
      });
    }

    [Test]
    public async Task APeerThatClosesIsAnsweredWithItsOwnCode()
    {
      var answered = new TaskCompletionSource<int?>(TaskCreationOptions.RunContinuationsAsynchronously);
      await using var server = ClosingPeer(code => answered.TrySetResult(code));

      await Transports.ConnectedAsync(server.Url);

      Assert.That(await answered.Task.Soon(), Is.EqualTo(1001));
    }

    [Test]
    public async Task ACloseThatCrossesThePeersCloseIsNoFault()
    {
      await using var server = ClosingPeer();
      var transport = new WebSocketTransport();
      var faults = new Faults();
      transport.On<Exception>("error", faults.Add);
      var closed = Transports.CloseOf(transport);

      // The close frame of this side wins the race, so the answer finds the socket closed.
      transport.BeforeCloseAnswer = async socket =>
      {
        transport.StartClose();
        await socket.CloseOutputAsync(WebSocketCloseStatus.NormalClosure, "client closed", default);
      };
      await transport.ConnectAsync(server.Url);

      Assert.That(await closed.Soon(), Is.EqualTo((1000, "client closed")));
      Assert.That(faults.Seen, Is.Empty);
    }

    [Test]
    public async Task AnAnswerThatCannotBeSentIsAFaultWhenNobodyAskedToClose()
    {
      await using var server = ClosingPeer();
      var transport = new WebSocketTransport();
      var faults = new Faults();
      transport.On<Exception>("error", faults.Add);
      var closed = Transports.CloseOf(transport);
      transport.BeforeCloseAnswer = socket => socket.CloseOutputAsync(
          WebSocketCloseStatus.NormalClosure, "not the answer", default);

      await transport.ConnectAsync(server.Url);

      Assert.That((await closed.Soon()).Code, Is.EqualTo(1001));
      Assert.That((await faults.First()).Message, Does.Contain("Cannot answer the close frame"));
    }

    [Test]
    public async Task NoCloseFrameGoesOutOnASocketThatIsNotOpen()
    {
      await using var server = ClosingPeer();
      var transport = new WebSocketTransport();
      var faults = new Faults();
      transport.On<Exception>("error", faults.Add);
      var closed = Transports.CloseOf(transport);
      transport.BeforeCloseAnswer = async socket =>
      {
        socket.Abort();
        transport.StartClose();
        await Task.Delay(50);
      };

      await transport.ConnectAsync(server.Url);

      await closed.Soon();
      Assert.That(faults.Seen, Is.Empty);
    }

    [Test]
    public async Task AFinishedConnectionLetsGoOfItsSocket()
    {
      await using var server = ClosingPeer();
      var transport = new WebSocketTransport();
      ClientWebSocket? held = null;
      transport.BeforeCloseAnswer = socket =>
      {
        held = socket;
        return Task.CompletedTask;
      };

      await transport.ConnectAsync(server.Url);

      var clock = Stopwatch.StartNew();
      while (!IsDisposed(held) && clock.Elapsed < Expect.Promptly)
      {
        await Task.Delay(10);
      }
      Assert.That(IsDisposed(held), Is.True);
    }

    private static bool IsDisposed(ClientWebSocket? socket)
    {
      if (socket == null)
      {
        return false;
      }
      try
      {
        socket.SendAsync(
            new ArraySegment<byte>(Array.Empty<byte>()),
            WebSocketMessageType.Text,
            true,
            CancellationToken.None).GetAwaiter().GetResult();
      }
      catch (ObjectDisposedException)
      {
        return true;
      }
      catch (WebSocketException)
      {
        return false;
      }
      return false;
    }

    [Test]
    public async Task CloseIsSafeTwiceAndOverlapping()
    {
      var transport = await Transports.ConnectedAsync(Transports.Scripted("/malformed"));
      var closes = new ConcurrentQueue<int>();
      transport.On("close", (int code, string _) => closes.Enqueue(code));

      await Task.WhenAll(transport.CloseAsync(), transport.CloseAsync());
      await transport.CloseAsync();

      Assert.That(closes, Is.EqualTo(new[] { 1000 }));
    }

    [Test]
    public async Task CloseFailsPendingRequests()
    {
      var transport = await Transports.ConnectedAsync(Transports.Scripted("/reverse"));
      var call = transport.SendAsync(Transports.Search, new { condition = "alone" });

      await transport.CloseAsync();

      await Expect.Throws<RoISConnectionException>(call, "closed by client");
    }

    [TestCase(999)]
    [TestCase(1001)]
    [TestCase(1006)]
    [TestCase(2999)]
    [TestCase(5000)]
    public async Task ACodeAClientCannotSendIsRefused(int code)
    {
      var transport = await Transports.ConnectedAsync(Transports.Scripted("/malformed"));

      await Expect.Throws<TransportException>(transport.CloseAsync(code), "Cannot close");

      Assert.That(transport.State, Is.EqualTo(TransportState.Connected));
      await transport.CloseAsync();
    }

    [Test]
    public async Task AReasonTooLongForTheFrameIsRefused()
    {
      var transport = await Transports.ConnectedAsync(Transports.Scripted("/malformed"));

      await Expect.Throws<TransportException>(
          transport.CloseAsync(1000, new string('é', 62)), "123 bytes");

      Assert.That(transport.State, Is.EqualTo(TransportState.Connected));
      await transport.CloseAsync(1000, new string('é', 61));
      Assert.That(transport.State, Is.EqualTo(TransportState.Disconnected));
    }

    [Test]
    public async Task ATransportCanConnectAgainAfterItClosed()
    {
      var transport = await Transports.ConnectedAsync(Transports.Scripted("/malformed"));
      await transport.CloseAsync();

      await transport.ConnectAsync(Transports.Scripted("/close-1001"));

      Assert.That(transport.State, Is.EqualTo(TransportState.Connected));
      await transport.CloseAsync();
    }
  }

  public sealed class ListenerTests
  {
    private static string Note(string method)
    {
      return Wire.Notification(method, new { });
    }

    private static async Task<WebSocketTransport> PushedToAsync(
        TestEngine engine, Action<WebSocketTransport> listen)
    {
      var transport = new WebSocketTransport();
      listen(transport);
      await transport.ConnectAsync(engine.Url);
      await transport.SendAsync("rois.system.connect");
      return transport;
    }

    [Test]
    public async Task ACallerThatBlocksAfterItsReplyLeavesTheReaderFree()
    {
      await using var engine = new TestEngine();
      var transport = await Transports.ConnectedAsync(engine.Url);
      var release = new TaskCompletionSource<bool>();

      // With no context a continuation runs wherever the reply completed it, which must not
      // be the reader, or application code would hold up every later message.
      var caller = Task.Run(async () =>
      {
        await transport.SendAsync("vendor.first");
        release.Task.Wait();
      });
      await Task.Delay(50);

      try
      {
        await transport.SendAsync("vendor.second").Soon();
      }
      finally
      {
        release.SetResult(true);
      }
      await caller.Soon();
      await transport.CloseAsync();
    }

    [Test]
    public async Task AListenerRemovedWhileItsEventIsPostedHearsNothing()
    {
      var push = new TaskCompletionSource<bool>(TaskCreationOptions.RunContinuationsAsynchronously);
      await using var server = TestServer.Serving(async peer =>
      {
        await push.Task;
        await peer.SendAsync(Note("vendor.one"));
        await peer.LeftAsync();
      });
      using var main = new MainThread();
      var transport = new WebSocketTransport();
      await main.Run(() => transport.ConnectAsync(server.Url)).Soon();
      var heard = 0;
      Action<JsonRpcNotification> listener = _ => Interlocked.Increment(ref heard);
      transport.On("notification", listener);
      var posted = new TaskCompletionSource<bool>(TaskCreationOptions.RunContinuationsAsynchronously);
      transport.Observe("notification", _ => posted.TrySetResult(true));
      var release = new TaskCompletionSource<bool>();

      // The main thread is busy when the event is posted, and removes the listener first.
      main.Post(_ =>
      {
        release.Task.Wait();
        transport.Off("notification", listener);
      }, null);
      push.SetResult(true);
      await posted.Task.Soon();
      await Task.Delay(20);
      release.SetResult(true);
      await main.Run(() => Task.CompletedTask).Soon();

      Assert.That(heard, Is.EqualTo(0));
      await transport.CloseAsync();
    }

    [Test]
    public async Task AListenerThatThrowsStopsNeitherTheReaderNorTheOthers()
    {
      await using var engine = new TestEngine(null, Note("vendor.one"), Note("vendor.two"));
      var seen = new ConcurrentQueue<string>();
      var faults = new Faults();

      var transport = await PushedToAsync(engine, listening =>
      {
        listening.On<Exception>("error", faults.Add);
        listening.On(
            "notification",
            (JsonRpcNotification message) => throw new InvalidOperationException(message.Method));
        listening.On("notification", (JsonRpcNotification message) => seen.Enqueue(message.Method));
      });

      await transport.SendAsync("vendor.ping");

      Assert.That(seen, Is.EqualTo(new[] { "vendor.one", "vendor.two" }));
      Assert.That(
          faults.Seen.Select(fault => fault.Message),
          Is.EqualTo(new[] { "vendor.one", "vendor.two" }));
      await transport.CloseAsync();
    }

    [Test]
    public async Task AnErrorListenerThatThrowsIsLogged()
    {
      var log = new ConcurrentQueue<string>();
      RoISLog.Sink = log.Enqueue;
      try
      {
        var transport = await Transports.ConnectedAsync(Transports.Scripted("/malformed"));
        transport.On("error", (Exception _) => throw new InvalidOperationException("listener fault"));

        await Transports.SearchAsync(transport, "before");

        Assert.That(string.Join("\n", log), Does.Contain("listener fault"));
        await transport.CloseAsync();
      }
      finally
      {
        RoISLog.Sink = null;
      }
    }

    [Test]
    public async Task AListenerRunsBeforeTheNextMessageIsRead()
    {
      var pushes = Enumerable.Range(0, 20).Select(n => Note($"vendor.{n}")).ToArray();
      await using var engine = new TestEngine(null, pushes);
      var order = new ConcurrentQueue<string>();

      var transport = await PushedToAsync(engine, listening =>
          listening.On("notification", (JsonRpcNotification message) => order.Enqueue(message.Method)));

      await transport.SendAsync("vendor.ping");

      Assert.That(order, Is.EqualTo(Enumerable.Range(0, 20).Select(n => $"vendor.{n}")));
      await transport.CloseAsync();
    }

    [Test]
    public async Task ANotificationListenerGetsTheWholeMessage()
    {
      await using var engine = new TestEngine(
          null,
          Wire.Notification("vendor.one", new { n = 1 }),
          "{\"jsonrpc\": \"2.0\", \"method\": \"vendor.two\"}");
      var seen = new ConcurrentQueue<JsonRpcNotification>();

      var transport = await PushedToAsync(
          engine, listening => listening.On<JsonRpcNotification>("notification", seen.Enqueue));

      await transport.SendAsync("vendor.ping");

      var messages = seen.ToArray();
      Assert.That(messages.Select(message => message.Method), Is.EqualTo(new[] { "vendor.one", "vendor.two" }));
      Assert.That(messages[0].Params!.Value.GetProperty("n").GetInt32(), Is.EqualTo(1));
      Assert.That(messages[1].Params, Is.Null);
      await transport.CloseAsync();
    }

    [Test]
    public async Task ANotificationNeverGoesOutUnderItsOwnName()
    {
      await using var engine = new TestEngine(null, Note("close"));
      var closed = new ConcurrentQueue<int>();
      var seen = new ConcurrentQueue<string>();

      var transport = await PushedToAsync(engine, listening =>
      {
        listening.On("close", (int code, string _) => closed.Enqueue(code));
        listening.On("notification", (JsonRpcNotification message) => seen.Enqueue(message.Method));
      });

      await transport.SendAsync("vendor.ping");

      Assert.That(closed, Is.Empty);
      Assert.That(seen, Is.EqualTo(new[] { "close" }));
      await transport.CloseAsync();
    }

    [Test]
    public async Task OffRemovesAListenerAndAMethodGroupMatchesItself()
    {
      var transport = await Transports.ConnectedAsync(Transports.Scripted("/malformed"));
      var faults = new Faults();
      var spare = new Faults();
      transport.On<Exception>("error", spare.Add);
      transport.On<Exception>("error", faults.Add);
      transport.Off<Exception>("error", faults.Add);

      await Transports.SearchAsync(transport, "before");

      Assert.That(faults.Seen, Is.Empty);
      Assert.That(spare.Seen, Has.Count.EqualTo(2));
      await transport.CloseAsync();
    }

    [Test]
    public async Task AListenerCanRemoveItselfWithoutSkippingTheNext()
    {
      var transport = await Transports.ConnectedAsync(Transports.Scripted("/malformed"));
      var once = new Faults();
      var always = new Faults();
      void FirstOnly(Exception error)
      {
        once.Add(error);
        transport.Off<Exception>("error", FirstOnly);
      }

      transport.On<Exception>("error", FirstOnly);
      transport.On<Exception>("error", always.Add);

      await Transports.SearchAsync(transport, "before");

      Assert.That(once.Seen, Has.Count.EqualTo(1));
      Assert.That(always.Seen, Has.Count.EqualTo(2));
      await transport.CloseAsync();
    }

    [Test]
    public void AListenerOfTheWrongShapeIsRefused()
    {
      var transport = new WebSocketTransport();

      Assert.Throws<ArgumentException>(() => transport.On("no.such.event", (string _) => { }));
      Assert.Throws<ArgumentException>(() => transport.On("close", (string _) => { }));
      Assert.Throws<ArgumentException>(() => transport.On("open", (int _, string _) => { }));
    }
  }

}  // namespace OpenRoIS.Sdk.Core.Tests
