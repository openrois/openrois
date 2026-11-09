#nullable enable
using System;
using System.Collections.Generic;
using System.Threading;

namespace OpenRoIS.Sdk
{

  /// <summary>The event names the client and the transport have in common.</summary>
  internal static class EventNames
  {
    internal const string Open = "open";
    internal const string Notification = "notification";
    internal const string Close = "close";
    internal const string Error = "error";
  }

  /// <summary>The payload of a close event.</summary>
  internal sealed class CloseReport
  {
    internal int Code { get; }

    internal string Reason { get; }

    internal CloseReport(int code, string reason)
    {
      Code = code;
      Reason = reason;
    }
  }

  /// <summary>
  /// Where a fault goes when no error listener can take it.
  /// </summary>
  /// <remarks>
  /// This assembly has no engine references, so it cannot call
  /// <c>Debug.Log</c>. A Unity player sends <see cref="Console.Out"/> to its
  /// log file, which on Android is logcat, and the Editor assembly sets
  /// <see cref="Sink"/> so that a fault reaches the Console window.
  /// </remarks>
  internal static class RoISLog
  {
    internal static Action<string>? Sink;

    internal static void Fault(object fault)
    {
      var text = $"OpenRoIS: {fault}";
      var sink = Sink;
      if (sink != null)
      {
        sink(text);
      }
      else
      {
        Console.WriteLine(text);
      }
    }
  }

  /// <summary>
  /// The listeners of the client or of the transport.
  /// </summary>
  /// <remarks>
  /// <para>
  /// A fault is an event that nothing turns into a throw, because the caller
  /// of <see cref="Emit"/> is the reader of a socket and has to carry on with
  /// the next message. It goes to the error listeners, or to the log if there
  /// are none.
  /// </para>
  /// <para>
  /// Listeners run in the <see cref="SynchronizationContext"/> captured at
  /// connect, in the order of the events. With no context, which is the case
  /// outside Unity and on a worker thread, they run inline on the thread that
  /// emits, so the next message waits for them. An observer always runs
  /// inline: it is how the client takes an event from its transport, and
  /// parsing a message must not cost the main thread.
  /// </para>
  /// </remarks>
  internal sealed class Emitter
  {
    private sealed class Entry
    {
      internal Delegate Listener { get; }

      internal Action<object?> Invoke { get; }

      internal Entry(Delegate listener, Action<object?> invoke)
      {
        Listener = listener;
        Invoke = invoke;
      }
    }

    private readonly IReadOnlyDictionary<string, Type> _payloads;
    private readonly Dictionary<string, List<Entry>> _listeners =
        new Dictionary<string, List<Entry>>();
    private readonly Dictionary<string, Action<object?>> _observers =
        new Dictionary<string, Action<object?>>();

    /// <summary>Create the listeners of the events a payload table names.</summary>
    /// <param name="payloads">The payload type of each event. An event with
    /// no arguments has <see cref="Void"/>, and a close event
    /// <see cref="CloseReport"/>.</param>
    internal Emitter(IReadOnlyDictionary<string, Type> payloads)
    {
      _payloads = payloads;
    }

    /// <summary>Where listeners run, or null to run them inline.</summary>
    internal SynchronizationContext? Context { get; set; }

    internal void Add<T>(string name, Action<T> listener)
    {
      Require(name, typeof(T));
      Add(name, new Entry(listener, payload => listener((T)payload!)));
    }

    internal void Add(string name, Action listener)
    {
      Require(name, typeof(void));
      Add(name, new Entry(listener, payload => listener()));
    }

    internal void Add(string name, Action<int, string> listener)
    {
      Require(name, typeof(CloseReport));
      Add(name, new Entry(listener, payload =>
      {
        var report = (CloseReport)payload!;
        listener(report.Code, report.Reason);
      }));
    }

    /// <summary>Remove the listener added last that equals this one.</summary>
    internal void Remove(string name, Delegate listener)
    {
      lock (_listeners)
      {
        if (!_listeners.TryGetValue(name, out var added))
        {
          return;
        }
        for (var index = added.Count - 1; index >= 0; index--)
        {
          if (added[index].Listener.Equals(listener))
          {
            added.RemoveAt(index);
            return;
          }
        }
      }
    }

    /// <summary>Set the one listener of an event that runs inline.</summary>
    internal void Observe(string name, Action<object?> observer)
    {
      lock (_listeners)
      {
        _observers[name] = observer;
      }
    }

    /// <summary>Hand an event to its listeners. This never throws.</summary>
    internal void Emit(string name, object? payload)
    {
      Action<object?>? observer;
      lock (_listeners)
      {
        _observers.TryGetValue(name, out observer);
      }
      if (observer != null)
      {
        Run(name, observer, payload);
      }

      var observed = observer != null;
      var context = Context;
      if (context == null)
      {
        Deliver(name, payload, observed);
        return;
      }
      try
      {
        context.Post(_ => Deliver(name, payload, observed), null);
      }
      catch (Exception fault)
      {
        // A context is application code, and the thread here is a reader
        // that has to keep reading.
        RoISLog.Fault(fault);
      }
    }

    private void Require(string name, Type payload)
    {
      if (!_payloads.TryGetValue(name, out var expected))
      {
        throw new ArgumentException($"There is no event named {name}.", nameof(name));
      }
      if (expected != payload)
      {
        throw new ArgumentException(
            $"A listener of {name} takes {Describe(expected)}, not {Describe(payload)}.",
            nameof(name));
      }
    }

    private static string Describe(Type payload)
    {
      if (payload == typeof(void))
      {
        return "no arguments";
      }
      return payload == typeof(CloseReport) ? "(int code, string reason)" : payload.Name;
    }

    private void Add(string name, Entry entry)
    {
      lock (_listeners)
      {
        if (!_listeners.TryGetValue(name, out var added))
        {
          added = new List<Entry>();
          _listeners[name] = added;
        }
        added.Add(entry);
      }
    }

    private void Deliver(string name, object? payload, bool observed)
    {
      // Read here and not when the event was posted, so that a listener
      // removed on the main thread hears nothing more.
      Entry[] entries;
      lock (_listeners)
      {
        entries = _listeners.TryGetValue(name, out var added)
            ? added.ToArray()
            : Array.Empty<Entry>();
      }
      if (name == EventNames.Error && entries.Length == 0 && !observed)
      {
        RoISLog.Fault(payload!);
      }
      foreach (var entry in entries)
      {
        Run(name, entry.Invoke, payload);
      }
    }

    private void Run(string name, Action<object?> listener, object? payload)
    {
      try
      {
        listener(payload);
      }
      catch (Exception fault)
      {
        // An error listener that throws has nowhere else to report to.
        if (name == EventNames.Error)
        {
          RoISLog.Fault(fault);
        }
        else
        {
          Emit(EventNames.Error, fault);
        }
      }
    }
  }

}  // namespace OpenRoIS.Sdk
