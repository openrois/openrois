using System;
using System.Collections.Generic;
using System.Threading.Tasks;
using OpenRoIS.Interfaces;
using OpenRoIS.Interfaces.Catalog;
using OpenRoIS.Interfaces.Hri;
using OpenRoIS.Interfaces.Service;
using UnityEngine;

namespace OpenRoIS.Sdk.Samples
{
  /// <summary>
  /// Runs one session against the mock adapter: connect, bind, execute, and
  /// the completed notification of the command. Attach it to a GameObject and
  /// enter Play Mode, with a gateway on the URL below and the mock adapter
  /// behind it. The Console shows each step.
  /// </summary>
  public sealed class NavigationSession : MonoBehaviour
  {
    [SerializeField] private string _gatewayUrl = "ws://127.0.0.1:8765";
    [SerializeField] private string _navigation = "mock/navigation";

    // Listeners run on the main thread, like this script, so the record needs no lock.
    private readonly Dictionary<string, CompletedStatus> _statuses =
        new Dictionary<string, CompletedStatus>();
    private bool _closed;

    private async void Start()
    {
      // An async void method has no caller, so a failure has to end here.
      try
      {
        await RunAsync();
      }
      catch (OperationCanceledException)
      {
        // The object was destroyed, and the await using below ended the session.
      }
      catch (Exception failure)
      {
        Debug.LogError($"The session failed: {failure.Message}");
      }
    }

    private async Task RunAsync()
    {
      var stop = destroyCancellationToken;

      // One client is one session, so the binding below ends with this block at the latest.
      await using var client = await RoISClient.ConnectAsync(
          _gatewayUrl, cancellationToken: stop);
      Debug.Log($"Connected to {_gatewayUrl}");

      client.On("close", (int code, string reason) =>
      {
        _closed = true;
        Debug.Log($"Connection closed: {code} {reason}");
      });

      // A command can end before the reply of ExecuteAsync is read, so the
      // listener has to be there before the call.
      client.On(RoISNotifications.Completed, (CompletedParams completed) =>
          _statuses[completed.CommandId] = completed.Status);

      var found = await client.SearchAsync(Condition.ComponentRef(_navigation), stop);
      if (found.Count == 0)
      {
        Debug.LogWarning($"{_navigation} is not there. Is the mock adapter running?");
        return;
      }

      await client.BindAsync(_navigation, stop);
      Debug.Log($"Bound {_navigation}");

      var ids = await client.ExecuteAsync(
          new[] { new CommandUnit(_navigation, RoISCommandTypes.Start) }, stop);
      Debug.Log($"Command {ids[0]} accepted");

      // ExecuteAsync returned when the engine accepted the command, and it
      // ends later, so read the record by the id in the reply.
      CompletedStatus status;
      while (!_statuses.TryGetValue(ids[0], out status))
      {
        if (_closed)
        {
          throw new InvalidOperationException("The connection closed before the command ended.");
        }
        await Awaitable.NextFrameAsync(stop);
      }
      Debug.Log($"Command {ids[0]} ended with {status}");

      await client.ReleaseAsync(_navigation, stop);
      Debug.Log($"Released {_navigation}");
    }
  }
}  // namespace OpenRoIS.Sdk.Samples
