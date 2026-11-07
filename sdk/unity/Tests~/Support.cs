#nullable enable
using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Threading.Tasks;
using NUnit.Framework;

namespace OpenRoIS.Sdk.Core.Tests
{

  /// <summary>What every test file needs.</summary>
  internal static class Expect
  {
    /// <summary>How long a test waits for something that should happen at once.</summary>
    internal static readonly TimeSpan Promptly = TimeSpan.FromSeconds(5);

    /// <summary>Fail a test rather than hang it when a task never ends.</summary>
    internal static Task Soon(this Task task) => task.WaitAsync(Promptly);

    /// <summary>Fail a test rather than hang it when a task never ends.</summary>
    internal static Task<T> Soon<T>(this Task<T> task) => task.WaitAsync(Promptly);

    /// <summary>
    /// Expect a task to fail with this exception or a subclass. Another
    /// exception goes on to the test, which then shows what really happened.
    /// </summary>
    internal static async Task<E> Throws<E>(Task call, string contains = "")
        where E : Exception
    {
      try
      {
        await call.Soon();
      }
      catch (E error)
      {
        Assert.That(error.Message, Does.Contain(contains));
        return error;
      }
      Assert.Fail($"Nothing was thrown, where {typeof(E).Name} should be");
      throw new InvalidOperationException();
    }
  }

  /// <summary>
  /// What the runtime reports about a failed task that nothing has looked at.
  /// </summary>
  internal static class Unseen
  {
    private const int Sweeps = 4;

    /// <summary>The reports of failures that work leaves behind.</summary>
    /// <remarks>
    /// The work runs in a method of its own, because a task stays reachable
    /// for as long as a local of a running method can reach it, and only a
    /// collected task is reported.
    /// </remarks>
    internal static async Task<IReadOnlyList<Exception>> During(Func<Task> work)
    {
      var seen = new ConcurrentQueue<Exception>();
      void Record(object? sender, UnobservedTaskExceptionEventArgs failure)
      {
        seen.Enqueue(failure.Exception!);
      }

      TaskScheduler.UnobservedTaskException += Record;
      try
      {
        await work();
        for (var sweep = 0; sweep < Sweeps; sweep++)
        {
          await Task.Delay(20);
          GC.Collect();
          GC.WaitForPendingFinalizers();
        }
      }
      finally
      {
        TaskScheduler.UnobservedTaskException -= Record;
      }
      return seen.ToArray();
    }
  }

  /// <summary>
  /// testing/conformance/scripted_server.py, which every SDK shares.
  /// </summary>
  /// <remarks>
  /// It starts with the first test that needs it, so the tests that use no
  /// socket need no Python. <c>python3</c> needs the websockets package.
  /// </remarks>
  internal static class ScriptedServer
  {
    private static readonly Lazy<(Process Process, string Url)> s_server =
        new Lazy<(Process, string)>(Start);

    /// <summary>The URL of the server. A path picks its script.</summary>
    internal static string Url => s_server.Value.Url;

    internal static void Stop()
    {
      if (s_server.IsValueCreated)
      {
        s_server.Value.Process.Kill(true);
        s_server.Value.Process.Dispose();
      }
    }

    private static (Process, string) Start()
    {
      var script = Path.Combine(AppContext.BaseDirectory, "suite", "scripted_server.py");
      var process = Process.Start(new ProcessStartInfo("python3", $"\"{script}\"")
      {
        RedirectStandardOutput = true,
        UseShellExecute = false,
      })!;
      var port = process.StandardOutput.ReadLine();
      if (port == null)
      {
        throw new InvalidOperationException(
            "The scripted server did not start. Does python3 have the websockets package?");
      }
      return (process, $"ws://127.0.0.1:{port}");
    }
  }

  /// <summary>Stops what outlives one test.</summary>
  [SetUpFixture]
  public sealed class SuiteEnd
  {
    /// <summary>Stop the scripted server when the run ends.</summary>
    [OneTimeTearDown]
    public void StopTheScriptedServer()
    {
      ScriptedServer.Stop();
    }
  }

}  // namespace OpenRoIS.Sdk.Core.Tests
