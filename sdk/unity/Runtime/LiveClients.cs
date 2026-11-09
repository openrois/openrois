#nullable enable
using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading.Tasks;
using OpenRoIS.Sdk.Transport;

namespace OpenRoIS.Sdk
{

  /// <summary>
  /// Every client with a connection or an attempt to open one.
  /// </summary>
  /// <remarks>
  /// The Editor keeps the managed domain when Play Mode ends with domain
  /// reload off, and nothing else would end a client the scene forgot. So the
  /// Editor assembly calls <see cref="EndAll"/>. This has to stay in the
  /// runtime assembly, which alone sees what a client holds.
  /// </remarks>
  internal static class LiveClients
  {
    private static readonly HashSet<RoISClient> s_clients = new HashSet<RoISClient>();
    private static bool s_refusing;

    /// <summary>List a client, unless the Editor is ending every client.</summary>
    /// <returns>Whether the client may connect.</returns>
    internal static bool TryAdd(RoISClient client)
    {
      lock (s_clients)
      {
        return !s_refusing && s_clients.Add(client);
      }
    }

    internal static void Remove(RoISClient client)
    {
      lock (s_clients)
      {
        s_clients.Remove(client);
      }
    }

    /// <summary>
    /// Refuse new clients until <see cref="Admit"/>.
    /// </summary>
    /// <remarks>
    /// The Editor runs scripts for a while after Play Mode starts to end, so
    /// a close listener that connects again would open a client that
    /// <see cref="EndAll"/> has already passed, and nothing would end it.
    /// </remarks>
    internal static void Refuse()
    {
      lock (s_clients)
      {
        s_refusing = true;
      }
    }

    /// <summary>Accept new clients again.</summary>
    internal static void Admit()
    {
      lock (s_clients)
      {
        s_refusing = false;
      }
    }

    /// <summary>
    /// End every session, and drop what has not ended when the time is up.
    /// </summary>
    /// <remarks>
    /// This blocks the caller, because the Editor leaves Play Mode as soon as
    /// the caller returns. No step here needs the main thread, since listeners
    /// are only posted to it.
    /// </remarks>
    internal static void EndAll(TimeSpan patience)
    {
      RoISClient[] clients;
      lock (s_clients)
      {
        clients = s_clients.ToArray();
      }

      var endings = clients.Select(client => client.DisconnectAsync()).ToArray();

      // A peer that does not answer in time leaves its task to fail later,
      // when nothing here is waiting for it any more.
      foreach (var ending in endings)
      {
        ending.Forget();
      }
      try
      {
        Task.WaitAll(endings, patience);
      }
      catch (AggregateException failures)
      {
        RoISLog.Fault(failures);
      }
      foreach (var client in clients)
      {
        client.Abort();
      }
    }
  }

}  // namespace OpenRoIS.Sdk
