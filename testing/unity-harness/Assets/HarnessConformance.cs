#nullable enable
using System;
using System.Collections.Generic;
using System.Linq;
using System.Text;
using System.Text.RegularExpressions;
using System.Threading;
using System.Threading.Tasks;
using OpenRoIS.Interfaces;
using OpenRoIS.Interfaces.Catalog;
using OpenRoIS.Interfaces.Common;
using OpenRoIS.Interfaces.Hri;
using OpenRoIS.Interfaces.Profiles;
using OpenRoIS.Interfaces.Service;
using OpenRoIS.Sdk;

namespace OpenRoIS.Harness
{
  /// <summary>
  /// The conformance list of testing/conformance/README.md, run through
  /// <see cref="RoISClient"/> on the main thread of a player.
  /// </summary>
  /// <remarks>
  /// <para>
  /// A player has no test framework, so each scenario is a method that throws, and the
  /// scenarios follow the ones in sdk/unity/Tests~/ConformanceTests.cs. They differ in where
  /// the code runs: there a listener runs on the reader of the socket, and here it is posted
  /// to the main thread, which is what this file exists to prove. A check of the thread comes
  /// first in every callback and after every await.
  /// </para>
  /// <para>
  /// A fault that a scenario does not expect fails the run, even when the scenario then
  /// passes, because <c>error</c> is the only way a client reports what went wrong inside it.
  /// </para>
  /// </remarks>
  public sealed partial class HarnessRunner
  {
    private const string ListFile = "conformance-list.md";
    private const string ListHeading = "\n## The List\n";
    private const string Engine = "mock";
    private const string Detection = "mock/person_detection";
    private const string Information = "mock/system_information";
    private const string FaultComponent = "mock/fault";
    private const string Reverse = "/reverse";
    private const string Malformed = "/malformed";
    private const string Drop = "/drop";
    private const string Close1001 = "/close-1001";
    private const string CloseEvent = "close";
    private const string ErrorEvent = "error";
    private const int ScenarioLimitSeconds = 60;
    private const int NotificationWaitSeconds = 20;
    private const int StackWaitSeconds = 60;
    private const int StackPollMilliseconds = 500;
    private const int ErrorPollMilliseconds = 100;
    private const int CompletionRounds = 100;
    private const int ParameterRounds = 5;
    private const int MethodNotFound = -32601;

    private string _scenario = "";

    /// <summary>
    /// A client, and every event it received since it connected. All listeners are added
    /// here, so that no callback of a scenario escapes the check of its thread.
    /// </summary>
    /// <remarks>
    /// Listeners and scenarios share these lists with no lock, because both run on the main
    /// thread. A listener that does not is a failure already.
    /// </remarks>
    private sealed class Session : IAsyncDisposable
    {
      private readonly HarnessRunner _harness;
      private TaskCompletionSource<bool> _arrived = NewArrival();

      internal Session(HarnessRunner harness, RoISClient client)
      {
        _harness = harness;
        Client = client;
        client.On(RoISNotifications.Completed, (CompletedParams p) => Record(RoISNotifications.Completed, Completed, p));
        client.On(RoISNotifications.NotifyEvent, (NotifyEventParams p) => Record(RoISNotifications.NotifyEvent, Events, p));
        client.On(RoISNotifications.NotifyError, (NotifyErrorParams p) => Record(RoISNotifications.NotifyError, Errors, p));
        client.On(RoISNotifications.ProfileChanged, (ProfileChangedParams p) => Record(RoISNotifications.ProfileChanged, ProfileChanges, p));
        client.On(CloseEvent, (int code, string reason) => Record(CloseEvent, Closes, (code, reason)));
        client.On<Exception>(ErrorEvent, OnFault);
      }

      internal RoISClient Client { get; }

      internal List<CompletedParams> Completed { get; } = new List<CompletedParams>();

      internal List<NotifyEventParams> Events { get; } = new List<NotifyEventParams>();

      internal List<NotifyErrorParams> Errors { get; } = new List<NotifyErrorParams>();

      internal List<ProfileChangedParams> ProfileChanges { get; } = new List<ProfileChangedParams>();

      internal List<(int Code, string Reason)> Closes { get; } = new List<(int, string)>();

      internal List<Exception> Faults { get; } = new List<Exception>();

      /// <summary>How many faults this scenario provokes on purpose.</summary>
      internal int ExpectedFaults { get; set; }

      public async ValueTask DisposeAsync()
      {
        await Client.DisposeAsync();
        _harness.CheckResumed(_harness._scenario + " dispose");
      }

      /// <summary>Waits until a list holds more than <paramref name="count"/> events.</summary>
      internal Task Beyond<T>(List<T> received, int count)
      {
        return Until(() => received.Count > count, $"more than {count} events");
      }

      /// <summary>The first event of a list that matches, waiting for it if needed.</summary>
      internal async Task<T> Seen<T>(List<T> received, Func<T, bool>? match = null)
          where T : class
      {
        await Until(() => received.Any(match ?? (_ => true)), "a matching event");
        return received.First(match ?? (_ => true));
      }

      /// <summary>Waits until a command completes, and returns its status.</summary>
      internal async Task<CompletedStatus> Completion(string commandId)
      {
        return (await Seen(Completed, p => p.CommandId == commandId)).Status;
      }

      private static TaskCompletionSource<bool> NewArrival()
      {
        return new TaskCompletionSource<bool>(TaskCreationOptions.RunContinuationsAsynchronously);
      }

      private void OnFault(Exception fault)
      {
        Record(ErrorEvent, Faults, fault);
        if (Faults.Count > ExpectedFaults)
          _harness.Fail($"unexpected fault in {_harness._scenario}", Describe(fault));
      }

      private void Record<T>(string name, List<T> received, T item)
      {
        _harness.CheckCallback(name);
        received.Add(item);
        var arrived = _arrived;
        _arrived = NewArrival();
        arrived.TrySetResult(true);
      }

      /// <summary>Looks again at each event, until the condition holds or the time is up.</summary>
      private async Task Until(Func<bool> condition, string what)
      {
        var deadline = Task.Delay(TimeSpan.FromSeconds(NotificationWaitSeconds));
        while (!condition())
        {
          var first = await _harness.Step(Task.WhenAny(_arrived.Task, deadline));
          if (first == deadline)
            throw new TimeoutException($"No {what} within {NotificationWaitSeconds} seconds.");
        }
      }
    }

    private async Task RunConformance(string gateway, string scripted)
    {
      var scenarios = new (string Id, Func<Task> Run)[]
      {
        ("C01", () => C01(gateway)),
        ("C02", () => C02(gateway)),
        ("C03", () => C03(gateway)),
        ("C04", () => C04(gateway)),
        ("C05", () => C05(gateway)),
        ("C06", () => C06(gateway)),
        ("C07", () => C07(gateway)),
        ("C08", () => C08(gateway)),
        ("C09", () => C09(gateway)),
        ("C10", () => C10(gateway)),
        ("C11", () => C11(gateway)),
        ("C12", () => C12(gateway)),
        ("C13", () => C13(gateway)),
        ("C14", () => C14(gateway)),
        ("C15", () => C15(gateway)),
        ("C16", () => C16(gateway)),
        ("C17", () => C17(gateway)),
        ("C18", () => C18(scripted)),
        ("C19", () => C19(scripted)),
        ("C20", () => C20(scripted)),
        ("C21", () => C21(scripted)),
      };

      var list = await OnMain(ReadStreamingBytes(ListFile), "read " + ListFile);
      Check("conformance coverage", () => CheckCoverage(Encoding.UTF8.GetString(list), scenarios.Select(scenario => scenario.Id)));

      await RunScenario("callback control", () => CheckCallbackControl(scripted));
      await RunScenario("stack", () => WaitForStack(gateway));
      foreach (var (id, run) in scenarios)
        await RunScenario(id, () => run());
    }

    /// <summary>A scenario that hangs fails alone, and the next one still runs.</summary>
    private async Task RunScenario(string name, Func<Task> scenario)
    {
      _scenario = name;
      var run = scenario();
      var first = await OnMain(Task.WhenAny(run, Task.Delay(TimeSpan.FromSeconds(ScenarioLimitSeconds))), name);
      if (first != run)
      {
        Fail("conformance " + name, $"not finished after {ScenarioLimitSeconds} seconds");
        return;
      }
      try
      {
        await run;
        Pass("conformance " + name);
      }
      catch (Exception e)
      {
        Fail("conformance " + name, Describe(e));
      }
    }

    /// <summary>The list ships in the player, so a new id fails on a device as well.</summary>
    private static string CheckCoverage(string readme, IEnumerable<string> ids)
    {
      var section = Regex.Split(readme, ListHeading)[1];
      section = section.Substring(0, section.IndexOf("\n## ", StringComparison.Ordinal));
      var listed = Regex.Matches(section, @"^\| (C\d+) \|", RegexOptions.Multiline)
          .Cast<Match>().Select(match => match.Groups[1].Value);
      Same(ids, listed.ToArray());
      return $"{listed.Count()} scenarios";
    }

    /// <summary>
    /// Proves the check of a callback can fail. A client connected away from the main thread
    /// captures no context, so its listener runs on the reader. Without this control, every
    /// callback landing on the main thread would look the same as a check that never fails.
    /// </summary>
    private async Task CheckCallbackControl(string scripted)
    {
      var client = await Step(Task.Run(() => RoISClient.ConnectAsync(scripted + Close1001)));
      var closed = new TaskCompletionSource<int>(TaskCreationOptions.RunContinuationsAsynchronously);
      client.On(CloseEvent, (int code, string reason) => closed.TrySetResult(Thread.CurrentThread.ManagedThreadId));
      await Step(client.SearchAsync("only"));
      var thread = await Step(closed.Task);
      Require(thread != _mainThread, "a listener with no context ran on the main thread");
      await Step(client.DisconnectAsync());
    }

    /// <summary>Waits for the adapter, as the session may have failed before it joined.</summary>
    private async Task WaitForStack(string gateway)
    {
      var deadline = Task.Delay(TimeSpan.FromSeconds(StackWaitSeconds));
      while (!deadline.IsCompleted)
      {
        await using (var live = await Open(gateway))
        {
          if ((await Step(live.Client.SearchAsync())).Contains(FaultComponent))
            return;
        }
        await Step(Task.Delay(StackPollMilliseconds));
      }
      throw new TimeoutException(FaultComponent + " did not appear.");
    }

    private async Task<Session> Open(string url)
    {
      return new Session(this, await Step(RoISClient.ConnectAsync(url)));
    }

    private void CheckCallback(string name)
    {
      var thread = Thread.CurrentThread.ManagedThreadId;
      if (thread == _mainThread)
        Pass($"main-thread callback {_scenario} {name}");
      else
        Fail($"main-thread callback {_scenario} {name}", $"on thread {thread}, main is {_mainThread}");
    }

    private Task Step(Task task)
    {
      return OnMain(task, _scenario);
    }

    private Task<T> Step<T>(Task<T> task)
    {
      return OnMain(task, _scenario);
    }

    /// <summary>
    /// Expects a task to fail with this exception or a subclass. Any other exception goes on
    /// to the scenario, which then reports what really happened.
    /// </summary>
    private async Task<E> Throws<E>(Task call, string contains = "")
        where E : Exception
    {
      try
      {
        await call;
      }
      catch (E error)
      {
        CheckResumed(_scenario);
        Require(error.Message.Contains(contains), $"the message is {error.Message}");
        return error;
      }
      throw new InvalidOperationException($"Nothing was thrown, where {typeof(E).Name} should be.");
    }

    private async Task Refused(Task call, ReturnCode code)
    {
      var error = await Throws<RoISException>(call);
      Require(error.ReturnCode == code, $"answered {error.ReturnCode}, expected {code}");
    }

    private static void Same<T>(IEnumerable<T> actual, params T[] expected)
    {
      var seen = actual.ToArray();
      Require(seen.SequenceEqual(expected), $"got [{string.Join(", ", seen)}], expected [{string.Join(", ", expected)}]");
    }

    private static void Includes<T>(IEnumerable<T> actual, params T[] expected)
    {
      var seen = actual.ToArray();
      Require(expected.All(seen.Contains), $"got [{string.Join(", ", seen)}], expected at least [{string.Join(", ", expected)}]");
    }

    private static IReadOnlyList<Parameter> Targets(string value)
    {
      return new[] { new Parameter("target_positions", "string[]", value) };
    }

    /// <summary>A command that gives its text back as a result, which tells it from any other.</summary>
    private static CommandUnit Echo(string text)
    {
      return new CommandUnit(FaultComponent, "echo", arguments: new[] { new Argument("text", "string", text) });
    }

    /// <summary>A command that ends with a chosen status.</summary>
    private static CommandUnit EndWith(string status)
    {
      return new CommandUnit(FaultComponent, "end_with", arguments: new[] { new Argument("status", "string", status) });
    }

    private static ICommandUnitSequenceItem[] Items(params ICommandUnitSequenceItem[] items)
    {
      return items;
    }

    private static string Value(IEnumerable<Result> results, string name)
    {
      return results.First(result => result.Name == name).Value;
    }

    private async Task C01(string gateway)
    {
      var live = await Open(gateway);

      await Step(live.Client.DisconnectAsync());
      await Step(live.Client.DisconnectAsync());

      Same(live.Closes.Select(close => close.Code), 1000);
      await Throws<TransportException>(live.Client.SearchAsync(), "not connected");

      // The block ends while both calls are in flight, so its own disconnect overlaps them.
      var overlapped = await Open(gateway);
      Task calls;
      await using (overlapped)
        calls = Task.WhenAll(overlapped.Client.DisconnectAsync(), overlapped.Client.DisconnectAsync());
      await Step(calls);
      await Throws<TransportException>(overlapped.Client.SearchAsync(), "not connected");
    }

    private async Task C02(string gateway)
    {
      await using var live = await Open(gateway);

      var engine = await Step(live.Client.GetProfileAsync());

      Includes(engine.Profile.SubProfiles!.Select(sub => sub.Identifier.Code), Engine);
      Includes(engine.ComponentProfiles.Keys, Detection, Navigation, Information, FaultComponent);
      var navigation = engine.ComponentProfiles[Navigation];
      Require(navigation.Function == ComponentFunction.actuation, navigation.Function.ToString()!);
      Same(navigation.CommandProfiles!.Select(command => command.Name), "start", "stop", "suspend", "resume");
    }

    private async Task C03(string gateway)
    {
      var byType = Condition.ComponentType(new RoISIdentifierType("Navigation", "OMG"));
      var prefix = Condition.Like(Condition.ComponentRefProperty, Engine + "/%");
      await using var live = await Open(gateway);
      var client = live.Client;

      Same(await Step(client.SearchAsync(Condition.ComponentRef(Navigation))), Navigation);
      Same(await Step(client.SearchAsync(byType)), Navigation);
      Same(await Step(client.SearchAsync(Condition.AllOf(prefix, byType))), Navigation);

      // Each term matches alone, so an empty answer shows that both were applied.
      Same(await Step(client.SearchAsync(Condition.ComponentRef(Detection))), Detection);
      Same(await Step(client.SearchAsync(Condition.AllOf(Condition.ComponentRef(Detection), byType))));

      Includes(await Step(client.SearchAsync(prefix)), Detection, Navigation, Information, FaultComponent);
      await Refused(client.SearchAsync("nonsense !! 1"), ReturnCode.BAD_PARAMETER);
    }

    private async Task C04(string gateway)
    {
      await using var live = await Open(gateway);

      Require(Condition.Quote("it's") == "'it''s'", Condition.Quote("it's"));

      // A quote that reached the engine unescaped would end the literal early, and the
      // engine would answer BAD_PARAMETER where these find nothing.
      Same(await Step(live.Client.SearchAsync(Condition.ComponentRef("it's/odd"))));
      Same(await Step(live.Client.SearchAsync(Condition.Like(Condition.ComponentRefProperty, "it's%"))));
    }

    private async Task C05(string gateway)
    {
      await using var live = await Open(gateway);
      var client = live.Client;

      var position = await Step(client.QueryAsync("robot_position", Condition.ComponentRef(Information)));

      Same(position.Select(result => result.Name), "position_data", "robot_ref", "timestamp");
      await Refused(client.QueryAsync("no_such_query"), ReturnCode.UNSUPPORTED);
      await Refused(client.QueryAsync("component_status"), ReturnCode.BAD_PARAMETER);

      // Several components declare this query, so only the condition can make it answer.
      var status = await Step(client.QueryAsync("component_status", Condition.ComponentRef(Navigation)));
      Includes(status.Select(result => result.Name), "status");
    }

    private async Task C06(string gateway)
    {
      await using var one = await Open(gateway);
      await using var two = await Open(gateway);
      var first = one.Client;
      var second = two.Client;

      await Step(first.BindAsync(Navigation));
      await Refused(second.BindAsync(Navigation), ReturnCode.OUT_OF_RESOURCES);
      await Refused(second.BindAnyAsync(Condition.ComponentRef(Navigation)), ReturnCode.OUT_OF_RESOURCES);

      await Step(first.BindAsync(Detection));
      await Step(second.BindAsync(Detection));

      await Step(first.ReleaseAsync(Navigation));
      var bound = await Step(second.BindAnyAsync(Condition.ComponentRef(Navigation)));
      Require(bound == Navigation, bound);
    }

    private async Task C07(string gateway)
    {
      await using (var live = await Open(gateway))
        await Step(live.Client.BindAsync(Navigation));
      await using (var live = await Open(gateway))
        await Step(live.Client.BindAsync(Navigation));
    }

    private async Task C08(string gateway)
    {
      await using var live = await Open(gateway);
      var client = live.Client;
      await Step(client.BindAsync(Navigation));

      var applied = await Step(client.SetParameterAsync(Navigation, Targets("[\"kitchen\"]")));
      Same(new[] { await live.Completion(applied) }, CompletedStatus.OK);

      await Refused(client.SetParameterAsync(Navigation, Targets("not json")), ReturnCode.BAD_PARAMETER);

      var parameters = await Step(client.GetParameterAsync(Navigation));
      var targets = parameters.First(parameter => parameter.Name == "target_positions").Value;
      Require(targets.Contains("kitchen"), targets);
      await live.Completion(await Step(client.SetParameterAsync(Navigation, Targets("[\"home\"]"))));
    }

    private async Task C09(string gateway)
    {
      await using var live = await Open(gateway);
      var client = live.Client;
      await Step(client.BindAsync(Navigation));
      await live.Completion(await Step(client.SetParameterAsync(Navigation, Targets("[\"kitchen\"]"))));
      var subscribeId = await Step(client.SubscribeAsync("reached_target", Condition.ComponentRef(Navigation)));

      var ids = await Step(client.ExecuteAsync(Items(new CommandUnit(Navigation, RoISCommandTypes.Start))));

      Require(ids.Count == 1, $"{ids.Count} ids");
      Same(new[] { await live.Completion(ids[0]) }, CompletedStatus.OK);
      var reached = await live.Seen(live.Events, e => e.SubscribeId == subscribeId);
      Require(reached.EventType == "reached_target", reached.EventType);
      Require(Value(reached.Results!, "target") == "kitchen", Value(reached.Results!, "target"));
      Same(await Step(client.GetCommandResultAsync(ids[0])));
      await live.Completion(await Step(client.SetParameterAsync(Navigation, Targets("[\"home\"]"))));
    }

    private async Task C10(string gateway)
    {
      await using var live = await Open(gateway);
      var client = live.Client;
      await Step(client.BindAsync(FaultComponent));

      var ids = await Step(client.ExecuteAsync(Items(
          Echo("first"),
          new ConcurrentCommands(new[]
          {
            new Branch(new[] { Echo("left one"), Echo("left two") }),
            new Branch(new[] { Echo("right") }),
          }),
          Echo("last"))));

      var statuses = new List<CompletedStatus>();
      foreach (var id in ids)
        statuses.Add(await live.Completion(id));
      Same(statuses, Enumerable.Repeat(CompletedStatus.OK, 5).ToArray());

      // Each command gives back its own text, so the ids must name them in this order.
      var texts = new List<string>();
      foreach (var id in ids)
        texts.Add((await Step(client.GetCommandResultAsync(id))).Single().Value);
      Same(texts, "first", "left one", "left two", "right", "last");
    }

    private async Task C11(string gateway)
    {
      await using var live = await Open(gateway);
      var client = live.Client;
      await Step(client.BindAsync(Navigation));
      var ids = new List<string>();

      for (var round = 0; round < CompletionRounds; round++)
      {
        var commandId = (await Step(client.ExecuteAsync(Items(new CommandUnit(Navigation, RoISCommandTypes.Stop))))).Single();
        ids.Add(commandId);
        Same(new[] { await live.Completion(commandId) }, CompletedStatus.OK);
      }
      for (var round = 0; round < ParameterRounds; round++)
      {
        var commandId = await Step(client.SetParameterAsync(Navigation, Targets("[\"home\"]")));
        ids.Add(commandId);
        Same(new[] { await live.Completion(commandId) }, CompletedStatus.OK);
      }

      Same(live.Completed.Select(p => p.CommandId), ids.ToArray());
    }

    private async Task C12(string gateway)
    {
      await using var live = await Open(gateway);
      var client = live.Client;
      await Step(client.BindAsync(FaultComponent));

      var ids = await Step(client.ExecuteAsync(Items(EndWith("ERROR"), Echo("never runs"), Echo("never runs either"))));

      Same(new[] { await live.Completion(ids[0]) }, CompletedStatus.ERROR);
      Same(new[] { await live.Completion(ids[1]) }, CompletedStatus.ABORT);
      Same(new[] { await live.Completion(ids[2]) }, CompletedStatus.ABORT);

      await Step(client.BindAsync(Navigation));
      var running = (await Step(client.ExecuteAsync(Items(new CommandUnit(Navigation, RoISCommandTypes.Start))))).Single();
      await Step(client.ReleaseAsync(Navigation));
      Same(new[] { await live.Completion(running) }, CompletedStatus.ABORT);
    }

    private async Task C13(string gateway)
    {
      var condition = Condition.ComponentRef(Detection);
      await using var first = await Open(gateway);
      await using var second = await Open(gateway);

      var one = await Step(first.Client.SubscribeAsync("person_detected", condition));
      Same(new[] { await Step(first.Client.SubscribeAsync("person_detected", condition)) }, one);
      var other = await Step(second.Client.SubscribeAsync("person_detected", condition));
      Require(other != one, other);
      await Step(first.Client.UnsubscribeAsync(Engine + "/sub-0"));

      // This condition selects a component without the event, which only a condition that
      // reaches the engine can refuse. No event of the mock adapter is declared twice, so
      // the refusal is what shows it here.
      await Refused(first.Client.SubscribeAsync("person_detected", Condition.ComponentRef(Navigation)), ReturnCode.UNSUPPORTED);

      await first.Seen(first.Events, e => e.SubscribeId == one);
      await second.Seen(second.Events, e => e.SubscribeId == other);
      Require(first.Events.All(e => e.SubscribeId == one), "the first client got an event of the second");
      Require(second.Events.All(e => e.SubscribeId == other), "the second client got an event of the first");

      // One client leaves by unsubscribing. Two more events prove the other still receives
      // them while the one that left does not, because a reply and the events around it
      // arrive in order on one socket.
      await Step(first.Client.UnsubscribeAsync(one));
      var left = first.Events.Count;
      await second.Beyond(second.Events, second.Events.Count + 1);
      Require(first.Events.Count == left, $"{first.Events.Count - left} events after leaving");

      // Then it leaves by ending its session.
      await Step(first.Client.SubscribeAsync("person_detected", condition));
      await Step(first.Client.DisconnectAsync());
      await second.Beyond(second.Events, second.Events.Count);
    }

    private async Task C14(string gateway)
    {
      await using var live = await Open(gateway);
      await Step(live.Client.SubscribeAsync("person_detected", Condition.ComponentRef(Detection)));

      var notified = await live.Seen(live.Events);

      Same(notified.Results!.Select(result => result.Name), "number", "timestamp");
      Same(await Step(live.Client.GetEventDetailAsync(notified.EventId)), notified.Results!.ToArray());
    }

    private async Task C15(string gateway)
    {
      await using var first = await Open(gateway);
      await using var second = await Open(gateway);
      await Step(first.Client.BindAsync(FaultComponent));
      await Step(second.Client.BindAsync(FaultComponent));

      await Step(first.Client.ExecuteAsync(Items(new CommandUnit(FaultComponent, "raise_error"))));

      var errorId = (await first.Seen(first.Errors)).ErrorId;
      await second.Seen(second.Errors, e => e.ErrorId == errorId);
      var detail = await Step(first.Client.GetErrorDetailAsync(errorId));
      Require(Value(detail, "component_ref") == FaultComponent, Value(detail, "component_ref"));

      // The error clears by itself, and the scenarios after this one need the component.
      while (true)
      {
        try
        {
          await Step(first.Client.GetErrorDetailAsync(errorId));
          await Step(Task.Delay(ErrorPollMilliseconds));
        }
        catch (RoISException error)
        {
          Require(error.ReturnCode == ReturnCode.BAD_PARAMETER, error.ReturnCode.ToString());
          return;
        }
      }
    }

    private async Task C16(string gateway)
    {
      await using var live = await Open(gateway);
      var client = live.Client;

      async Task<bool> HasPeer()
      {
        var engine = await Step(client.GetProfileAsync());
        return engine.Profile.SubProfiles!.Any(sub => sub.Identifier.Code == "mock_peer");
      }

      await Step(client.BindAsync(FaultComponent));
      Require(!await HasPeer(), "the peer is there before it joined");

      await Step(client.ExecuteAsync(Items(new CommandUnit(FaultComponent, "peer_join"))));

      await live.Beyond(live.ProfileChanges, 0);
      Require(await HasPeer(), "the peer did not join");
      await live.Beyond(live.ProfileChanges, 1);
      Require(!await HasPeer(), "the peer did not leave");
    }

    private async Task C17(string gateway)
    {
      await using var live = await Open(gateway);

      var error = await Throws<RpcException>(live.Client.Transport.SendAsync("rois.bogus"));

      Require(error.Code == MethodNotFound, error.Code.ToString());
      Same(await Step(live.Client.SearchAsync(Condition.ComponentRef(Navigation))), Navigation);
    }

    private async Task C18(string scripted)
    {
      await using var live = await Open(scripted + Reverse);
      var client = live.Client;

      // The server answers the last request first, and a client that matched replies by
      // order would hand each caller the wrong one. This checks who got which reply and not
      // the order they resumed in, because that order is up to the thread pool.
      var replies = await Step(Task.WhenAll(client.SearchAsync("one"), client.SearchAsync("two"), client.SearchAsync("three")));

      Same(replies[0], "one");
      Same(replies[1], "two");
      Same(replies[2], "three");
    }

    private async Task C19(string scripted)
    {
      await using var live = await Open(scripted + Malformed);
      live.ExpectedFaults = 2;

      Same(await Step(live.Client.SearchAsync("before")), "before");

      Require(live.Faults.Count == 2, $"{live.Faults.Count} faults");
      Require(live.Faults.All(fault => fault is TransportException), Describe(live.Faults[0]));
      Same(await Step(live.Client.SearchAsync("after")), "after");
    }

    private async Task C20(string scripted)
    {
      await using var live = await Open(scripted + Drop);
      var client = live.Client;

      var calls = new[] { client.SearchAsync("one"), client.SearchAsync("two"), client.SearchAsync("three") };

      foreach (var call in calls)
        await Throws<RoISConnectionException>(call);
      await live.Beyond(live.Closes, 0);
      Same(live.Closes.Select(close => close.Code), 1006);
      await Throws<TransportException>(client.SearchAsync());
    }

    private async Task C21(string scripted)
    {
      await using var live = await Open(scripted + Close1001);

      Same(await Step(live.Client.SearchAsync("only")), "only");

      await live.Beyond(live.Closes, 0);
      Same(live.Closes, (1001, "scripted close"));
    }
  }
}  // namespace OpenRoIS.Harness
