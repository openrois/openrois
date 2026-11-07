#nullable enable
using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Text.RegularExpressions;
using System.Threading;
using System.Threading.Tasks;
using NUnit.Framework;
using OpenRoIS.Interfaces;
using OpenRoIS.Interfaces.Catalog;
using OpenRoIS.Interfaces.Hri;
using OpenRoIS.Interfaces.Profiles;
using OpenRoIS.Interfaces.Service;

namespace OpenRoIS.Sdk.Core.Tests
{

  /// <summary>
  /// The conformance list of testing/conformance/README.md, one test per scenario.
  /// </summary>
  /// <remarks>
  /// <para>
  /// Each test has the id of its scenario in its name. The tests at the end
  /// need no stack: they fail when an id of the list has no test here, when a
  /// test has no id in the list, and when a method of the catalog has no
  /// client member.
  /// </para>
  /// <para>
  /// The scenarios use only the public surface and take only URLs. Every fault
  /// comes from a RoIS call on <c>mock/fault</c> or from a path of the scripted
  /// server. W01 to W03 stay with testing/conformance/wire_check.py, because a
  /// client SDK cannot reach them.
  /// </para>
  /// <para>
  /// C01 to C17 run when OPENROIS_GATEWAY_URL names a gateway with the mock
  /// adapter behind it, and are skipped otherwise. C18 to C21 need only the
  /// scripted server, so they always run. OPENROIS_MOCK_ENGINE_ID names the
  /// engine of the mock adapter, <c>mock</c> by default.
  /// </para>
  /// </remarks>
  public sealed class ConformanceTests
  {
    private static readonly string s_engineId =
        Environment.GetEnvironmentVariable("OPENROIS_MOCK_ENGINE_ID") ?? "mock";

    private static readonly string s_detection = $"{s_engineId}/person_detection";
    private static readonly string s_navigation = $"{s_engineId}/navigation";
    private static readonly string s_information = $"{s_engineId}/system_information";
    private static readonly string s_fault = $"{s_engineId}/fault";

    // The longest wait for one notification, enough for a detection at full time scale.
    private static readonly TimeSpan s_wait = TimeSpan.FromSeconds(20);

    // The longest wait for the stack to come up.
    private static readonly TimeSpan s_stackWait = TimeSpan.FromSeconds(60);

    // How many commands the scenario on lost completions runs.
    private const int CompletionRounds = 100;

    // How many parameter changes it runs, which take longer than a command.
    private const int ParameterRounds = 5;

    // Checked once, because the stack does not change between scenarios.
    private static readonly Lazy<Task<string>> s_gateway =
        new Lazy<Task<string>>(WaitForStackAsync);

    /// <summary>
    /// A client and every notification it received since it connected.
    /// </summary>
    /// <remarks>
    /// This is the recipe of the SDK README: the listener is there before the
    /// call whose ids it records.
    /// </remarks>
    private sealed class Session : IAsyncDisposable
    {
      // Listeners run on the reader of the socket, and the test reads from
      // wherever its last await left it.
      private readonly object _gate = new object();
      private TaskCompletionSource<bool> _arrived = NewArrival();

      private Session(RoISClient client)
      {
        Client = client;
        client.On(RoISNotifications.Completed, (CompletedParams p) => Record(Completed, p));
        client.On(RoISNotifications.NotifyEvent, (NotifyEventParams p) => Record(Events, p));
        client.On(RoISNotifications.NotifyError, (NotifyErrorParams p) => Record(Errors, p));
        client.On(
            RoISNotifications.ProfileChanged,
            (ProfileChangedParams p) => Record(ProfileChanges, p));
      }

      internal RoISClient Client { get; }

      internal List<CompletedParams> Completed { get; } = new List<CompletedParams>();

      internal List<NotifyEventParams> Events { get; } = new List<NotifyEventParams>();

      internal List<NotifyErrorParams> Errors { get; } = new List<NotifyErrorParams>();

      internal List<ProfileChangedParams> ProfileChanges { get; } =
          new List<ProfileChangedParams>();

      internal static async Task<Session> OpenAsync(string url)
      {
        return new Session(await RoISClient.ConnectAsync(url));
      }

      public ValueTask DisposeAsync()
      {
        return Client.DisposeAsync();
      }

      /// <summary>A copy of a list, safe to read while notifications arrive.</summary>
      internal List<T> Now<T>(List<T> received)
      {
        lock (_gate)
        {
          return new List<T>(received);
        }
      }

      /// <summary>The first notification of a list that matches, waiting for it if needed.</summary>
      internal Task<T> SeenAsync<T>(List<T> received, Func<T, bool>? match = null)
          where T : class
      {
        return UntilAsync(() => received.FirstOrDefault(match ?? (_ => true)), received);
      }

      /// <summary>Wait until a list holds more than <paramref name="count"/> notifications.</summary>
      internal Task BeyondAsync<T>(List<T> received, int count)
      {
        return UntilAsync(() => received.Count > count ? "yes" : null, received);
      }

      /// <summary>Wait until a command completes, and return its status.</summary>
      internal async Task<CompletedStatus> CompletionAsync(string commandId)
      {
        var completed = await SeenAsync(Completed, p => p.CommandId == commandId);
        return completed.Status;
      }

      private static TaskCompletionSource<bool> NewArrival()
      {
        return new TaskCompletionSource<bool>(TaskCreationOptions.RunContinuationsAsynchronously);
      }

      private void Record<T>(List<T> received, T notification)
      {
        TaskCompletionSource<bool> arrived;
        lock (_gate)
        {
          received.Add(notification);
          arrived = _arrived;
          _arrived = NewArrival();
        }
        arrived.TrySetResult(true);
      }

      /// <summary>
      /// Wait until <paramref name="find"/> returns something, looking again
      /// at each notification.
      /// </summary>
      private async Task<T> UntilAsync<T, U>(Func<T?> find, List<U> received)
          where T : class
      {
        using var deadline = new CancellationTokenSource(s_wait);
        while (true)
        {
          T? found;
          Task arrived;
          lock (_gate)
          {
            found = find();
            arrived = _arrived.Task;
          }
          if (found != null)
          {
            return found;
          }
          try
          {
            await arrived.WaitAsync(deadline.Token);
          }
          catch (OperationCanceledException)
          {
            Assert.Fail($"Nothing new within {s_wait}, after {Now(received).Count} notifications");
          }
        }
      }
    }

    private static async Task RefusedAsync(Task call, ReturnCode returnCode)
    {
      var error = await Expect.Throws<RoISException>(call);
      Assert.That(error.ReturnCode, Is.EqualTo(returnCode));
    }

    /// <summary>What a client reports when its connection closes.</summary>
    private static Task<(int Code, string Reason)> CloseOf(RoISClient client)
    {
      var closed = new TaskCompletionSource<(int, string)>(
          TaskCreationOptions.RunContinuationsAsynchronously);
      client.On("close", (int code, string reason) => closed.TrySetResult((code, reason)));
      return closed.Task;
    }

    /// <summary>The target_positions parameter of the navigation.</summary>
    private static IReadOnlyList<Parameter> Targets(string value)
    {
      return new[] { new Parameter("target_positions", "string[]", value) };
    }

    /// <summary>A command that gives its text back as a result, which tells it from any other.</summary>
    private static CommandUnit Echo(string text)
    {
      return new CommandUnit(
          s_fault, "echo", arguments: new[] { new Argument("text", "string", text) });
    }

    /// <summary>A command that ends with a chosen status.</summary>
    private static CommandUnit EndWith(string status)
    {
      return new CommandUnit(
          s_fault, "end_with", arguments: new[] { new Argument("status", "string", status) });
    }

    private static ICommandUnitSequenceItem[] Items(params ICommandUnitSequenceItem[] items)
    {
      return items;
    }

    private static string Value(IEnumerable<Result> results, string name)
    {
      return results.First(result => result.Name == name).Value;
    }

    private static async Task<bool> StackIsUpAsync(string url)
    {
      try
      {
        await using var client = await RoISClient.ConnectAsync(url);
        return (await client.SearchAsync()).Contains(s_fault);
      }
      catch (Exception error) when (error is RoISException || error is TransportException)
      {
        return false;
      }
    }

    private static async Task<string> WaitForStackAsync()
    {
      var url = Environment.GetEnvironmentVariable("OPENROIS_GATEWAY_URL")!;
      using var deadline = new CancellationTokenSource(s_stackWait);
      while (!await StackIsUpAsync(url))
      {
        if (deadline.IsCancellationRequested)
        {
          Assert.Fail($"{s_fault} did not appear at {url}");
        }
        await Task.Delay(500);
      }
      return url;
    }

    /// <summary>
    /// The gateway with the mock adapter behind it, once that adapter has
    /// joined. A scenario that takes it is skipped when no stack was named.
    /// </summary>
    private static Task<string> GatewayAsync()
    {
      if (string.IsNullOrEmpty(Environment.GetEnvironmentVariable("OPENROIS_GATEWAY_URL")))
      {
        Assert.Ignore("OPENROIS_GATEWAY_URL names no gateway");
      }
      return s_gateway.Value;
    }

    [Test]
    public async Task C01_DisconnectIsSafeTwiceAndALaterCallFailsLocally()
    {
      var gateway = await GatewayAsync();
      var client = await RoISClient.ConnectAsync(gateway);
      var closed = new List<int>();
      client.On("close", (int code, string _) => closed.Add(code));

      await client.DisconnectAsync();
      await client.DisconnectAsync();

      Assert.That(closed, Is.EqualTo(new[] { 1000 }));
      await Expect.Throws<TransportException>(client.SearchAsync(), "not connected");

      // The block ends while both calls are in flight, so its own disconnect overlaps them.
      var overlapped = await RoISClient.ConnectAsync(gateway);
      Task calls;
      await using (overlapped)
      {
        calls = Task.WhenAll(overlapped.DisconnectAsync(), overlapped.DisconnectAsync());
      }
      await calls;
      await Expect.Throws<TransportException>(overlapped.SearchAsync(), "not connected");
    }

    [Test]
    public async Task C02_GetProfileListsTheSubProfileAndEachComponentProfile()
    {
      await using var live = await Session.OpenAsync(await GatewayAsync());

      var engine = await live.Client.GetProfileAsync();

      Assert.That(engine.Profile.SubProfiles!.Select(sub => sub.Identifier.Code), Does.Contain(s_engineId));
      Assert.That(
          engine.ComponentProfiles.Keys,
          Is.SupersetOf(new[] { s_detection, s_navigation, s_information, s_fault }));
      var navigation = engine.ComponentProfiles[s_navigation];
      Assert.That(navigation.Function, Is.EqualTo(ComponentFunction.actuation));
      Assert.That(
          navigation.CommandProfiles!.Select(command => command.Name),
          Is.EqualTo(new[] { "start", "stop", "suspend", "resume" }));
    }

    [Test]
    public async Task C03_SearchSelectsByRefByTypeWithLikeAndWithAnd()
    {
      var byType = Condition.ComponentType(new RoISIdentifierType("Navigation", "OMG"));
      var prefix = Condition.Like(Condition.ComponentRefProperty, $"{s_engineId}/%");
      await using var live = await Session.OpenAsync(await GatewayAsync());
      var client = live.Client;

      Assert.That(await client.SearchAsync(Condition.ComponentRef(s_navigation)), Is.EqualTo(new[] { s_navigation }));
      Assert.That(await client.SearchAsync(byType), Is.EqualTo(new[] { s_navigation }));
      Assert.That(await client.SearchAsync(Condition.AllOf(prefix, byType)), Is.EqualTo(new[] { s_navigation }));

      // Each term matches alone, so an empty answer shows that both were applied.
      Assert.That(await client.SearchAsync(Condition.ComponentRef(s_detection)), Is.EqualTo(new[] { s_detection }));
      Assert.That(await client.SearchAsync(Condition.AllOf(Condition.ComponentRef(s_detection), byType)), Is.Empty);

      Assert.That(
          await client.SearchAsync(prefix),
          Is.SupersetOf(new[] { s_detection, s_navigation, s_information, s_fault }));
      await RefusedAsync(client.SearchAsync("nonsense !! 1"), ReturnCode.BAD_PARAMETER);
    }

    [Test]
    public async Task C04_AQuoteInAConditionValueSurvivesTheBuilders()
    {
      await using var live = await Session.OpenAsync(await GatewayAsync());

      Assert.That(Condition.Quote("it's"), Is.EqualTo("'it''s'"));

      // A quote that reached the engine unescaped would end the literal early, and the
      // engine would answer BAD_PARAMETER where these find nothing.
      Assert.That(await live.Client.SearchAsync(Condition.ComponentRef("it's/odd")), Is.Empty);
      Assert.That(
          await live.Client.SearchAsync(Condition.Like(Condition.ComponentRefProperty, "it's%")),
          Is.Empty);
    }

    [Test]
    public async Task C05_QueryFollowsItsCondition()
    {
      await using var live = await Session.OpenAsync(await GatewayAsync());
      var client = live.Client;

      var position = await client.QueryAsync("robot_position", Condition.ComponentRef(s_information));

      Assert.That(
          position.Select(result => result.Name),
          Is.EqualTo(new[] { "position_data", "robot_ref", "timestamp" }));
      await RefusedAsync(client.QueryAsync("no_such_query"), ReturnCode.UNSUPPORTED);
      await RefusedAsync(client.QueryAsync("component_status"), ReturnCode.BAD_PARAMETER);

      // Several components declare this query, so only the condition can make it answer.
      var status = await client.QueryAsync("component_status", Condition.ComponentRef(s_navigation));
      Assert.That(status.Select(result => result.Name), Does.Contain("status"));
    }

    [Test]
    public async Task C06_AnActuatorRefusesASecondClientAndASensorIsShared()
    {
      var gateway = await GatewayAsync();
      await using var one = await Session.OpenAsync(gateway);
      await using var two = await Session.OpenAsync(gateway);
      var first = one.Client;
      var second = two.Client;

      await first.BindAsync(s_navigation);
      await RefusedAsync(second.BindAsync(s_navigation), ReturnCode.OUT_OF_RESOURCES);
      await RefusedAsync(
          second.BindAnyAsync(Condition.ComponentRef(s_navigation)), ReturnCode.OUT_OF_RESOURCES);

      await first.BindAsync(s_detection);
      await second.BindAsync(s_detection);

      await first.ReleaseAsync(s_navigation);
      Assert.That(
          await second.BindAnyAsync(Condition.ComponentRef(s_navigation)),
          Is.EqualTo(s_navigation));
    }

    [Test]
    public async Task C07_ABindEndsWithItsSession()
    {
      var gateway = await GatewayAsync();
      await using (var live = await Session.OpenAsync(gateway))
      {
        await live.Client.BindAsync(s_navigation);
      }
      await using (var live = await Session.OpenAsync(gateway))
      {
        await live.Client.BindAsync(s_navigation);
      }
    }

    [Test]
    public async Task C08_SetParameterAppliesAndABadValueChangesNothing()
    {
      await using var live = await Session.OpenAsync(await GatewayAsync());
      var client = live.Client;
      await client.BindAsync(s_navigation);

      var applied = await client.SetParameterAsync(s_navigation, Targets("[\"kitchen\"]"));
      Assert.That(await live.CompletionAsync(applied), Is.EqualTo(CompletedStatus.OK));

      await RefusedAsync(
          client.SetParameterAsync(s_navigation, Targets("not json")), ReturnCode.BAD_PARAMETER);

      var parameters = await client.GetParameterAsync(s_navigation);
      Assert.That(
          parameters.First(parameter => parameter.Name == "target_positions").Value,
          Does.Contain("kitchen"));
      await live.CompletionAsync(await client.SetParameterAsync(s_navigation, Targets("[\"home\"]")));
    }

    [Test]
    public async Task C09_ExecuteRunsFromBindToReachedTarget()
    {
      await using var live = await Session.OpenAsync(await GatewayAsync());
      var client = live.Client;
      await client.BindAsync(s_navigation);
      await live.CompletionAsync(await client.SetParameterAsync(s_navigation, Targets("[\"kitchen\"]")));
      var subscribeId = await client.SubscribeAsync("reached_target", Condition.ComponentRef(s_navigation));

      var ids = await client.ExecuteAsync(Items(new CommandUnit(s_navigation, RoISCommandTypes.Start)));

      Assert.That(ids, Has.Count.EqualTo(1));
      Assert.That(await live.CompletionAsync(ids[0]), Is.EqualTo(CompletedStatus.OK));
      var reached = await live.SeenAsync(live.Events, e => e.SubscribeId == subscribeId);
      Assert.That(reached.EventType, Is.EqualTo("reached_target"));
      Assert.That(Value(reached.Results!, "target"), Is.EqualTo("kitchen"));
      Assert.That(await client.GetCommandResultAsync(ids[0]), Is.Empty);
      await live.CompletionAsync(await client.SetParameterAsync(s_navigation, Targets("[\"home\"]")));
    }

    [Test]
    public async Task C10_ASequenceWithBranchesReturnsIdsInOrder()
    {
      await using var live = await Session.OpenAsync(await GatewayAsync());
      var client = live.Client;
      await client.BindAsync(s_fault);

      var ids = await client.ExecuteAsync(Items(
          Echo("first"),
          new ConcurrentCommands(new[]
          {
            new Branch(new[] { Echo("left one"), Echo("left two") }),
            new Branch(new[] { Echo("right") }),
          }),
          Echo("last")));

      var statuses = new List<CompletedStatus>();
      foreach (var id in ids)
      {
        statuses.Add(await live.CompletionAsync(id));
      }
      Assert.That(statuses, Is.EqualTo(Enumerable.Repeat(CompletedStatus.OK, 5)));

      // Each command gives back its own text, so the ids must name them in this order.
      var texts = new List<string>();
      foreach (var id in ids)
      {
        texts.Add((await client.GetCommandResultAsync(id)).Single().Value);
      }
      Assert.That(texts, Is.EqualTo(new[] { "first", "left one", "left two", "right", "last" }));
    }

    [Test]
    public async Task C11_AListenerAddedFirstSeesEveryCompletion()
    {
      await using var live = await Session.OpenAsync(await GatewayAsync());
      var client = live.Client;
      await client.BindAsync(s_navigation);
      var ids = new List<string>();

      for (var round = 0; round < CompletionRounds; round++)
      {
        var commandId = (await client.ExecuteAsync(
            Items(new CommandUnit(s_navigation, RoISCommandTypes.Stop)))).Single();
        ids.Add(commandId);
        Assert.That(await live.CompletionAsync(commandId), Is.EqualTo(CompletedStatus.OK));
      }
      for (var round = 0; round < ParameterRounds; round++)
      {
        var commandId = await client.SetParameterAsync(s_navigation, Targets("[\"home\"]"));
        ids.Add(commandId);
        Assert.That(await live.CompletionAsync(commandId), Is.EqualTo(CompletedStatus.OK));
      }

      Assert.That(live.Now(live.Completed).Select(p => p.CommandId), Is.EqualTo(ids));
    }

    [Test]
    public async Task C12_ACommandEndingBadlyAbortsTheLaterItems()
    {
      await using var live = await Session.OpenAsync(await GatewayAsync());
      var client = live.Client;
      await client.BindAsync(s_fault);

      var ids = await client.ExecuteAsync(
          Items(EndWith("ERROR"), Echo("never runs"), Echo("never runs either")));

      Assert.That(await live.CompletionAsync(ids[0]), Is.EqualTo(CompletedStatus.ERROR));
      Assert.That(await live.CompletionAsync(ids[1]), Is.EqualTo(CompletedStatus.ABORT));
      Assert.That(await live.CompletionAsync(ids[2]), Is.EqualTo(CompletedStatus.ABORT));

      await client.BindAsync(s_navigation);
      var running = (await client.ExecuteAsync(
          Items(new CommandUnit(s_navigation, RoISCommandTypes.Start)))).Single();
      await client.ReleaseAsync(s_navigation);
      Assert.That(await live.CompletionAsync(running), Is.EqualTo(CompletedStatus.ABORT));
    }

    [Test]
    public async Task C13_EventsReachOnlyTheirSubscriberAndTwoClientsStayApart()
    {
      var gateway = await GatewayAsync();
      var condition = Condition.ComponentRef(s_detection);
      await using var first = await Session.OpenAsync(gateway);
      await using var second = await Session.OpenAsync(gateway);

      var one = await first.Client.SubscribeAsync("person_detected", condition);
      Assert.That(await first.Client.SubscribeAsync("person_detected", condition), Is.EqualTo(one));
      var other = await second.Client.SubscribeAsync("person_detected", condition);
      Assert.That(other, Is.Not.EqualTo(one));
      await first.Client.UnsubscribeAsync($"{s_engineId}/sub-0");

      // This condition selects a component without the event, which only a condition that
      // reaches the engine can refuse. No event of the mock adapter is declared twice, so
      // the refusal is what shows it here.
      await RefusedAsync(
          first.Client.SubscribeAsync("person_detected", Condition.ComponentRef(s_navigation)),
          ReturnCode.UNSUPPORTED);

      await first.SeenAsync(first.Events, e => e.SubscribeId == one);
      await second.SeenAsync(second.Events, e => e.SubscribeId == other);
      Assert.That(first.Now(first.Events).Select(e => e.SubscribeId), Is.All.EqualTo(one));
      Assert.That(second.Now(second.Events).Select(e => e.SubscribeId), Is.All.EqualTo(other));

      // One client leaves by unsubscribing. Two more events prove the other still receives
      // them while the one that left does not, because a reply and the events around it
      // arrive in order on one socket.
      await first.Client.UnsubscribeAsync(one);
      var left = first.Now(first.Events).Count;
      await second.BeyondAsync(second.Events, second.Now(second.Events).Count + 1);
      Assert.That(first.Now(first.Events), Has.Count.EqualTo(left));

      // Then it leaves by ending its session.
      await first.Client.SubscribeAsync("person_detected", condition);
      await first.Client.DisconnectAsync();
      await second.BeyondAsync(second.Events, second.Now(second.Events).Count);
    }

    [Test]
    public async Task C14_NotifyEventResultsEqualGetEventDetail()
    {
      await using var live = await Session.OpenAsync(await GatewayAsync());
      await live.Client.SubscribeAsync("person_detected", Condition.ComponentRef(s_detection));

      var notified = await live.SeenAsync(live.Events);

      Assert.That(notified.Results!.Select(r => r.Name), Is.EqualTo(new[] { "number", "timestamp" }));
      Assert.That(await live.Client.GetEventDetailAsync(notified.EventId), Is.EqualTo(notified.Results));
    }

    [Test]
    public async Task C15_NotifyErrorReachesEachHolderAndGetErrorDetailReadsIt()
    {
      var gateway = await GatewayAsync();
      await using var first = await Session.OpenAsync(gateway);
      await using var second = await Session.OpenAsync(gateway);
      await first.Client.BindAsync(s_fault);
      await second.Client.BindAsync(s_fault);

      await first.Client.ExecuteAsync(Items(new CommandUnit(s_fault, "raise_error")));

      var errorId = (await first.SeenAsync(first.Errors)).ErrorId;
      await second.SeenAsync(second.Errors, e => e.ErrorId == errorId);
      var detail = await first.Client.GetErrorDetailAsync(errorId);
      Assert.That(Value(detail, "component_ref"), Is.EqualTo(s_fault));

      // The error clears by itself, and the scenarios after this one need the component.
      using var deadline = new CancellationTokenSource(s_wait);
      while (true)
      {
        try
        {
          await first.Client.GetErrorDetailAsync(errorId);
          await Task.Delay(100, deadline.Token);
        }
        catch (RoISException error)
        {
          Assert.That(error.ReturnCode, Is.EqualTo(ReturnCode.BAD_PARAMETER));
          return;
        }
      }
    }

    [Test]
    public async Task C16_ProfileChangedArrivesWhenAnEngineJoinsAndLeaves()
    {
      await using var live = await Session.OpenAsync(await GatewayAsync());
      var client = live.Client;

      async Task<bool> HasPeerAsync()
      {
        var engine = await client.GetProfileAsync();
        return engine.Profile.SubProfiles!.Any(sub => sub.Identifier.Code == "mock_peer");
      }

      await client.BindAsync(s_fault);
      Assert.That(await HasPeerAsync(), Is.False);

      await client.ExecuteAsync(Items(new CommandUnit(s_fault, "peer_join")));

      await live.BeyondAsync(live.ProfileChanges, 0);
      Assert.That(await HasPeerAsync(), Is.True);
      await live.BeyondAsync(live.ProfileChanges, 1);
      Assert.That(await HasPeerAsync(), Is.False);
    }

    [Test]
    public async Task C17_MethodNotFoundThroughTheRawSendIsAnRpcException()
    {
      await using var live = await Session.OpenAsync(await GatewayAsync());

      var error = await Expect.Throws<RpcException>(live.Client.Transport.SendAsync("rois.bogus"));

      Assert.That(error.Code, Is.EqualTo(-32601));
      Assert.That(
          await live.Client.SearchAsync(Condition.ComponentRef(s_navigation)),
          Is.EqualTo(new[] { s_navigation }));
    }

    [Test]
    public async Task C18_RepliesInReverseOrderReachTheRightCallers()
    {
      await using var client = await RoISClient.ConnectAsync($"{ScriptedServer.Url}/reverse");

      // Which caller resumes first is up to the thread pool, unlike the other two clients, so
      // this checks who got which reply. The server answers the last request first, and a
      // client that matched replies by order would hand each caller the wrong one.
      var replies = await Task.WhenAll(
          client.SearchAsync("one"), client.SearchAsync("two"), client.SearchAsync("three"));

      Assert.That(replies[0], Is.EqualTo(new[] { "one" }));
      Assert.That(replies[1], Is.EqualTo(new[] { "two" }));
      Assert.That(replies[2], Is.EqualTo(new[] { "three" }));
    }

    [Test]
    public async Task C19_AMalformedMessageReachesTheErrorListener()
    {
      await using var client = await RoISClient.ConnectAsync($"{ScriptedServer.Url}/malformed");
      var errors = new Faults();
      client.On<Exception>("error", errors.Add);

      Assert.That(await client.SearchAsync("before"), Is.EqualTo(new[] { "before" }));

      Assert.That(errors.Seen, Has.Count.EqualTo(2));
      Assert.That(errors.Seen, Is.All.InstanceOf<TransportException>());
      Assert.That(await client.SearchAsync("after"), Is.EqualTo(new[] { "after" }));
    }

    [Test]
    public async Task C20_ADroppedConnectionFailsPendingRequestsAndFiresClose()
    {
      await using var client = await RoISClient.ConnectAsync($"{ScriptedServer.Url}/drop");
      var closed = CloseOf(client);

      var calls = new[]
      {
        client.SearchAsync("one"),
        client.SearchAsync("two"),
        client.SearchAsync("three"),
      };

      foreach (var call in calls)
      {
        await Expect.Throws<RoISConnectionException>(call);
      }
      Assert.That((await closed.WaitAsync(s_wait)).Code, Is.EqualTo(1006));
      await Expect.Throws<TransportException>(client.SearchAsync());
    }

    [Test]
    public async Task C21_AServerCloseReachesCloseWithItsCodeAndReason()
    {
      await using var client = await RoISClient.ConnectAsync($"{ScriptedServer.Url}/close-1001");
      var closed = CloseOf(client);

      Assert.That(await client.SearchAsync("only"), Is.EqualTo(new[] { "only" }));

      Assert.That(await closed.WaitAsync(s_wait), Is.EqualTo((1001, "scripted close")));
    }

    private static string Suite(string file)
    {
      return File.ReadAllText(Path.Combine(AppContext.BaseDirectory, "suite", file));
    }

    /// <summary>The ids in the table under "## The List" that a client SDK has to run.</summary>
    private static IReadOnlyList<string> ListedIds()
    {
      var section = Suite("README.md").Split("\n## The List\n")[1].Split("\n## ")[0];
      return Regex.Matches(section, @"^\| (C\d+) \|", RegexOptions.Multiline)
          .Select(match => match.Groups[1].Value)
          .ToArray();
    }

    /// <summary>The id at the start of each test name in this file.</summary>
    private static IReadOnlyList<string> IdsWithATest()
    {
      return Regex.Matches(Suite("ConformanceTests.cs"), @"^\s*public async Task (C\d+)_", RegexOptions.Multiline)
          .Select(match => match.Groups[1].Value)
          .ToArray();
    }

    /// <summary>What a catalog method is called on the client.</summary>
    private static string Member(string method)
    {
      var words = method.Substring(method.LastIndexOf('.') + 1).Split('_');
      return string.Concat(words.Select(word => char.ToUpperInvariant(word[0]) + word.Substring(1)))
          + "Async";
    }

    private static IEnumerable<string> CatalogMethods()
    {
      return RoISMethodTypes.ByMethod.Keys.OrderBy(method => method, StringComparer.Ordinal);
    }

    [Test]
    public void TheListCanBeRead()
    {
      Assert.That(ListedIds(), Does.Contain("C01"));
    }

    [Test]
    public void EachIdOfTheListHasOneTest()
    {
      Assert.That(IdsWithATest(), Is.EqualTo(ListedIds()));
    }

    [Test]
    public void TheScenariosUseOnlyThePublicSurface()
    {
      var source = Suite("ConformanceTests.cs");
      var namespaces = Regex.Matches(source, @"^using (OpenRoIS[\w.]*);", RegexOptions.Multiline)
          .Select(match => match.Groups[1].Value);
      Assert.That(namespaces, Is.All.Matches<string>(name => !name.StartsWith("OpenRoIS.Sdk", StringComparison.Ordinal)));

      // The test assembly sees the internals of the client, so a look at the usings cannot tell.
      var hidden = typeof(RoISClient).Assembly.GetTypes()
          .Where(type => !type.IsVisible && !type.IsNested && !type.Name.StartsWith("<", StringComparison.Ordinal))
          .Select(type => type.Name);
      var internalMembers = typeof(RoISClient).Assembly.GetExportedTypes()
          .SelectMany(type => type.GetMethods(BindingFlags.Instance | BindingFlags.Static | BindingFlags.NonPublic))
          .Where(method => method.IsAssembly)
          .Select(method => method.Name.Replace("get_", "").Replace("set_", ""));
      var used = Regex.Matches(source, @"\b[A-Z]\w+\b").Select(match => match.Value)
          .Where(name => hidden.Contains(name));
      var reached = Regex.Matches(source, @"\.(\w+)\b").Select(match => match.Groups[1].Value)
          .Where(name => internalMembers.Contains(name));
      Assert.That(used.Concat(reached), Is.Empty);
    }

    [TestCaseSource(nameof(CatalogMethods))]
    public void TheClientHasAMemberFor(string method)
    {
      // ConnectAsync is static, because it is the one operation that makes a client.
      Assert.That(typeof(RoISClient).GetMethod(Member(method)), Is.Not.Null);
    }

    [TestCaseSource(nameof(CatalogMethods))]
    public void EachMemberTakesACancellationTokenLast(string method)
    {
      var parameters = typeof(RoISClient).GetMethod(Member(method))!.GetParameters();

      Assert.That(parameters.Last().ParameterType, Is.EqualTo(typeof(CancellationToken)));
      Assert.That(parameters.Last().IsOptional, Is.True);
    }
  }

}  // namespace OpenRoIS.Sdk.Core.Tests
