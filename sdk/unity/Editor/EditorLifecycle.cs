using System;
using UnityEditor;
using UnityEngine;

namespace OpenRoIS.Sdk.Editor
{
  /// <summary>
  /// Ends every client when Play Mode ends, and connects the log of the SDK
  /// to the Console window.
  /// </summary>
  /// <remarks>
  /// With domain reload off, which Fast Enter Play Mode gives, the managed
  /// domain survives leaving Play Mode, and with it a socket, a reader and
  /// listeners on objects that no longer exist. Before an assembly reload the
  /// same clients would die with no rois.system.disconnect, so the engine would
  /// hold their bindings until it noticed. A client opened from an Editor tool
  /// outside Play Mode ends here as well, because the runtime assembly cannot
  /// tell the two apart.
  /// </remarks>
  [InitializeOnLoad]
  internal static class EditorLifecycle
  {
    // A session normally ends in milliseconds. The Editor waits this long at
    // most for an engine that stopped answering, then drops the connection.
    private static readonly TimeSpan s_patience = TimeSpan.FromSeconds(1);

    static EditorLifecycle()
    {
      RoISLog.Sink = Debug.LogError;
      EditorApplication.playModeStateChanged += OnPlayModeChanged;
      AssemblyReloadEvents.beforeAssemblyReload += EndClients;
    }

    private static void OnPlayModeChanged(PlayModeStateChange change)
    {
      if (change == PlayModeStateChange.ExitingPlayMode)
      {
        // Listeners and scripts still run until Edit Mode, and a close is
        // often delivered before OnDestroy, when a script that connects again
        // does not know yet that it is leaving.
        LiveClients.Refuse();
        EndClients();
      }
      else if (change == PlayModeStateChange.EnteredEditMode)
      {
        // A connect on another thread can pass the refusal just before it
        // begins, and is not an attempt yet when the first sweep looks.
        EndClients();
        LiveClients.Admit();
      }
    }

    private static void EndClients()
    {
      LiveClients.EndAll(s_patience);
    }
  }
}  // namespace OpenRoIS.Sdk.Editor
