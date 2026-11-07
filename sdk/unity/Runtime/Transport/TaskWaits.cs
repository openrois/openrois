#nullable enable
using System.Threading;
using System.Threading.Tasks;

namespace OpenRoIS.Sdk.Transport
{

  /// <summary>
  /// The one wait this assembly needs that netstandard2.1 does not have.
  /// </summary>
  internal static class TaskWaits
  {
    /// <summary>
    /// Wait for a task until a token fires, and leave the task running.
    /// </summary>
    /// <remarks>
    /// A caller who gives up stops waiting and nothing else, because the
    /// work is often shared, or has to finish whoever is watching.
    /// </remarks>
    internal static async Task WaitOrCancel(this Task task, CancellationToken cancellationToken)
    {
      if (cancellationToken.CanBeCanceled)
      {
        var cancelled = new TaskCompletionSource<bool>(
            TaskCreationOptions.RunContinuationsAsynchronously);
        using (cancellationToken.Register(() => cancelled.TrySetResult(true)))
        {
          var first = await Task.WhenAny(task, cancelled.Task).ConfigureAwait(false);
          if (first != task)
          {
            cancellationToken.ThrowIfCancellationRequested();
          }
        }
      }
      await task.ConfigureAwait(false);
    }

    /// <summary>
    /// Mark the outcome of a task nobody waits for as seen, because the
    /// runtime reports a failed task that nothing has looked at.
    /// </summary>
    internal static void Forget(this Task task)
    {
      task.ContinueWith(
          ended => _ = ended.Exception,
          CancellationToken.None,
          TaskContinuationOptions.OnlyOnFaulted | TaskContinuationOptions.ExecuteSynchronously,
          TaskScheduler.Default);
    }
  }

}  // namespace OpenRoIS.Sdk.Transport
