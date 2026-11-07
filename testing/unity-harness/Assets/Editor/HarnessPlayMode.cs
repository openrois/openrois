#nullable enable
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using OpenRoIS.Interfaces;
using OpenRoIS.Sdk;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using Debug = UnityEngine.Debug;

namespace OpenRoIS.Harness.Editor
{
  /// <summary>
  /// Batch mode proof that a client does not outlive Play Mode with domain reload off.
  /// </summary>
  /// <remarks>
  /// <para>
  /// With domain reload off the managed domain survives leaving Play Mode, and with it any
  /// socket a scene forgot. Each cycle here opens the four kinds of client that can be left
  /// behind, and never ends them: the Editor has to. The peers then report what they saw,
  /// because a client that only believes it ended would pass a check made in this process.
  /// </para>
  /// <para>
  /// The steps are an iterator pumped by <see cref="EditorApplication.update"/>, and await
  /// nothing. Whether a context captured in Play Mode still runs after Play Mode is part of
  /// what is under test, so the driver must not depend on it.
  /// </para>
  /// </remarks>
  [InitializeOnLoad]
  public static class HarnessPlayMode
  {
    private const string Prefix = "HARNESS ";
    private const string Navigation = "mock/navigation";
    private const string DisconnectLine = "method rois.system.disconnect";
    private const int Cycles = 2;
    private const int NormalClose = 1000;
    private const int LimitSeconds = 180;
    private const int PeerWaitSeconds = 5;
    private const int CallbackWaitSeconds = 5;

    // The Editor waits 1 second for a deaf peer, and this leaves room for a loaded machine.
    private const double LeaveLimitSeconds = 5;

    // These survive the assembly reload, which every static here does not.
    private const string ReloadTagKey = "OpenRoIS.Harness.ReloadTag";
    private const string PassedKey = "OpenRoIS.Harness.Passed";
    private const string FailedKey = "OpenRoIS.Harness.Failed";

    private static IEnumerator<Func<bool>>? s_steps;
    private static Func<bool> s_waiting = () => true;
    private static double s_deadline;
    private static int s_mainThread;
    private static PlayModeStateChange s_mode = PlayModeStateChange.EnteredEditMode;
    private static int s_passed;
    private static int s_failed;
    private static int s_refused;

    /// <summary>Picks the run up again after the assembly reload that ends it.</summary>
    static HarnessPlayMode()
    {
      if (SessionState.GetString(ReloadTagKey, "").Length > 0)
        Start(AfterReload());
    }

    /// <summary>Runs the proof and exits the Editor with its result.</summary>
    public static void Run()
    {
      EditorSettings.enterPlayModeOptionsEnabled = true;
      EditorSettings.enterPlayModeOptions = EnterPlayModeOptions.DisableDomainReload | EnterPlayModeOptions.DisableSceneReload;
      EditorSceneManager.NewScene(NewSceneSetup.EmptyScene);
      Start(Proof());
    }

    private static void Start(IEnumerator<Func<bool>> steps)
    {
      Application.SetStackTraceLogType(LogType.Log, StackTraceLogType.None);
      s_mainThread = Thread.CurrentThread.ManagedThreadId;
      s_deadline = EditorApplication.timeSinceStartup + LimitSeconds;
      s_steps = steps;
      EditorApplication.playModeStateChanged += change => s_mode = change;
      EditorApplication.update += Pump;
    }

    private static void Pump()
    {
      try
      {
        if (EditorApplication.timeSinceStartup > s_deadline)
        {
          Fail("watchdog", $"not finished after {LimitSeconds} seconds");
          Finish();
          return;
        }
        while (s_steps != null && s_waiting())
        {
          if (!s_steps.MoveNext())
          {
            s_steps = null;
            return;
          }
          s_waiting = s_steps.Current;
        }
      }
      catch (Exception e)
      {
        Fail("step", $"{e.GetType().Name}: {e.Message}");
        Finish();
      }
    }

    private static IEnumerator<Func<bool>> Proof()
    {
      var gateway = Required("OPENROIS_GATEWAY_URL");
      var peer = Required("OPENROIS_LIFECYCLE_URL");
      Say($"INFO unity={Application.unityVersion} options={EditorSettings.enterPlayModeOptions}");
      Check(
          "playmode domain reload off",
          EditorSettings.enterPlayModeOptions.HasFlag(EnterPlayModeOptions.DisableDomainReload),
          EditorSettings.enterPlayModeOptions.ToString());

      for (var cycle = 1; cycle <= Cycles; cycle++)
      {
        var steps = Cycle(cycle, gateway, peer);
        while (steps.MoveNext())
          yield return steps.Current;
      }

      // Without this the check of the recipe proves nothing, if no close came before OnDestroy.
      Check("recipe tried to connect during the exit", s_refused > 0, "no connect was refused");

      // An assembly reload is the other way a domain ends, and it needs no Play Mode.
      const string tag = "reload";
      var client = RoISClient.ConnectAsync($"{peer}/record/{tag}");
      yield return Done(client);
      Check("reload opened", client.Status == TaskStatus.RanToCompletion, $"{client.Status}");
      SessionState.SetString(ReloadTagKey, tag);
      SessionState.SetInt(PassedKey, s_passed);
      SessionState.SetInt(FailedKey, s_failed);
      EditorUtility.RequestScriptReload();

      // The domain goes away during this wait, and this iterator with it.
      yield return () => false;
    }

    private static IEnumerator<Func<bool>> AfterReload()
    {
      s_passed = SessionState.GetInt(PassedKey, 0);
      s_failed = SessionState.GetInt(FailedKey, 0);
      var tag = SessionState.GetString(ReloadTagKey, "");
      SessionState.EraseString(ReloadTagKey);

      yield return Within(PeerWaitSeconds, () => Recorded(tag, "close " + NormalClose) > 0);
      Check("reload disconnect", Recorded(tag, DisconnectLine) == 1, Lines(tag));
      Check("reload close", Recorded(tag, "close " + NormalClose) == 1, Lines(tag));
      Finish();
    }

    private static IEnumerator<Func<bool>> Cycle(int cycle, string gateway, string peer)
    {
      var name = $"cycle{cycle}";
      EditorApplication.EnterPlaymode();
      yield return () => s_mode == PlayModeStateChange.EnteredPlayMode;
      Application.runInBackground = true;

      var bound = new Watched(gateway);
      var recorded = new Watched($"{peer}/record/{name}-record");
      var deaf = new Watched($"{peer}/deaf/{name}-deaf");
      yield return Done(bound.Connecting, recorded.Connecting, deaf.Connecting);
      var binding = bound.Client.BindAsync(Navigation);
      yield return Done(binding);
      Check($"{name} bound", binding.Status == TaskStatus.RanToCompletion, $"{binding.Exception}");

      var reopening = new GameObject("reopening").AddComponent<Reopening>();
      reopening.Url = $"{peer}/record/{name}-reopen";
      var opening = reopening.OpenSessionAsync();
      yield return Done(opening);
      Check($"{name} recipe connected", opening.Status == TaskStatus.RanToCompletion, $"{opening.Exception}");

      // Started last and never answered, so it is still in flight when Play Mode ends.
      var attempt = RoISClient.ConnectAsync($"{peer}/silent/{name}-attempt");
      yield return Within(PeerWaitSeconds, () => Recorded($"{name}-attempt", "method rois.system.connect") == 1);
      Check($"{name} attempt in flight", !attempt.IsCompleted, $"{attempt.Status}");

      var clock = Stopwatch.StartNew();
      EditorApplication.ExitPlaymode();
      yield return () => s_mode == PlayModeStateChange.EnteredEditMode;
      clock.Stop();
      Check($"{name} left within {LeaveLimitSeconds} seconds", clock.Elapsed.TotalSeconds < LeaveLimitSeconds, $"{clock.Elapsed.TotalSeconds:F2}");
      Say($"INFO {name} leaving took {clock.Elapsed.TotalSeconds:F2} seconds");

      // Each close is posted to a context from Play Mode, which has to run outside it as well.
      yield return Within(CallbackWaitSeconds, () => bound.Closes.Count > 0 && recorded.Closes.Count > 0 && deaf.Closes.Count > 0);
      yield return Within(PeerWaitSeconds, () => Recorded($"{name}-record", "close " + NormalClose) > 0);
      yield return Within(PeerWaitSeconds, () => Lines($"{name}-deaf").Contains("close") && Lines($"{name}-attempt").Contains("close"));

      // Only a close that comes before OnDestroy connects again, and either order is fine.
      yield return Within(CallbackWaitSeconds, () => reopening.Heard > 0);
      yield return Done(reopening.Trying);
      Say($"INFO {name} recipe heard {reopening.Heard} close, refused so far {s_refused}");
      Check(
          $"{name} recipe left no client",
          Recorded($"{name}-reopen", "open") == 1 && Recorded($"{name}-reopen", "close " + NormalClose) == 1,
          Lines($"{name}-reopen"));

      Check($"{name} session closed", bound.Closes.SequenceEqual(new[] { NormalClose }), string.Join(",", bound.Closes));
      Check($"{name} record closed", recorded.Closes.SequenceEqual(new[] { NormalClose }), string.Join(",", recorded.Closes));
      Check($"{name} deaf peer dropped", deaf.Closes.Count == 1, string.Join(",", deaf.Closes));
      Check($"{name} attempt failed", attempt.IsFaulted, $"{attempt.Status}");
      Check($"{name} callbacks on the main thread", bound.WrongThread + recorded.WrongThread + deaf.WrongThread == 0, "a close ran on a worker");

      Check($"{name} peer saw one disconnect", Recorded($"{name}-record", DisconnectLine) == 1, Lines($"{name}-record"));
      Check($"{name} peer saw a normal close", Recorded($"{name}-record", "close " + NormalClose) == 1, Lines($"{name}-record"));
      Check($"{name} deaf peer was asked once", Recorded($"{name}-deaf", DisconnectLine) == 1, Lines($"{name}-deaf"));
      Check($"{name} deaf peer lost the socket", Lines($"{name}-deaf").Contains("close"), Lines($"{name}-deaf"));
      Check($"{name} attempt lost the socket", Lines($"{name}-attempt").Contains("close"), Lines($"{name}-attempt"));

      var late = bound.Client.SearchAsync();
      yield return Done(late);
      Check($"{name} a later call fails", late.Exception?.GetBaseException() is TransportException, $"{late.Status}");

      // The engine had one holder of this actuator, so it answers OK only if that one left.
      var next = RoISClient.ConnectAsync(gateway);
      yield return Done(next);
      var rebound = next.Result.BindAsync(Navigation);
      yield return Done(rebound);
      Check($"{name} the engine released the bind", rebound.Status == TaskStatus.RanToCompletion, $"{rebound.Exception}");
      var ended = next.Result.DisconnectAsync();
      yield return Done(ended);
    }

    /// <summary>
    /// The reconnect recipe of the README of the package, as an application writes it.
    /// </summary>
    /// <remarks>
    /// Leaving Play Mode closes this client, and the close can reach the script while
    /// nothing has told it yet that it is leaving.
    /// </remarks>
    private sealed class Reopening : MonoBehaviour
    {
      private bool _leaving;

      internal string Url { get; set; } = "";

      internal int Heard { get; private set; }

      internal Task Trying { get; private set; } = Task.CompletedTask;

      internal async Task OpenSessionAsync()
      {
        var client = await RoISClient.ConnectAsync(Url);
        client.On("close", OnClosed);
        await client.BindAsync(Navigation);
      }

      private void OnDestroy()
      {
        _leaving = true;
      }

      private void OnClosed(int code, string reason)
      {
        Heard++;
        if (!_leaving)
          Trying = ReopenAsync();
      }

      private async Task ReopenAsync()
      {
        try
        {
          await OpenSessionAsync();
        }
        catch (RoISConnectionException)
        {
          s_refused++;
        }
      }
    }

    /// <summary>A client with its close events, added as an application would add them.</summary>
    private sealed class Watched
    {
      private readonly Task<RoISClient> _connecting;

      internal Watched(string url)
      {
        _connecting = RoISClient.ConnectAsync(url);
        Connecting = Listen();
      }

      internal List<int> Closes { get; } = new List<int>();

      internal int WrongThread { get; private set; }

      internal Task Connecting { get; }

      internal RoISClient Client => _connecting.Result;

      private async Task Listen()
      {
        var client = await _connecting;
        client.On("close", (int code, string reason) =>
        {
          if (Thread.CurrentThread.ManagedThreadId != s_mainThread)
            WrongThread++;
          Closes.Add(code);
        });
      }
    }

    private static Func<bool> Done(params Task[] tasks)
    {
      return () => tasks.All(task => task.IsCompleted);
    }

    /// <summary>A wait that gives up, so the check after it reports what was seen.</summary>
    private static Func<bool> Within(int seconds, Func<bool> condition)
    {
      var deadline = EditorApplication.timeSinceStartup + seconds;
      return () => condition() || EditorApplication.timeSinceStartup > deadline;
    }

    private static string[] Record()
    {
      var path = Required("OPENROIS_LIFECYCLE_RECORD");
      return File.Exists(path) ? File.ReadAllLines(path) : Array.Empty<string>();
    }

    private static int Recorded(string tag, string line)
    {
      return Record().Count(entry => entry == $"{tag} {line}");
    }

    private static string Lines(string tag)
    {
      return string.Join("; ", Record().Where(entry => entry.StartsWith(tag + " ", StringComparison.Ordinal)));
    }

    private static string Required(string variable)
    {
      var value = Environment.GetEnvironmentVariable(variable);
      if (string.IsNullOrEmpty(value))
        throw new InvalidOperationException(variable + " is not set.");
      return value;
    }

    private static void Check(string name, bool passed, string detail)
    {
      if (passed)
      {
        s_passed++;
        Say("PASS " + name);
      }
      else
      {
        Fail(name, detail);
      }
    }

    private static void Fail(string name, string why)
    {
      s_failed++;
      Say($"FAIL {name}: {why}");
    }

    private static void Finish()
    {
      EditorApplication.update -= Pump;
      s_steps = null;
      var ok = s_failed == 0;
      Say($"RESULT {(ok ? "OK" : "FAILED")} passed={s_passed} failed={s_failed}");
      EditorApplication.Exit(ok ? 0 : 1);
    }

    private static void Say(string line)
    {
      Debug.Log(Prefix + line);
    }
  }
}  // namespace OpenRoIS.Harness.Editor
