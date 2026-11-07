#nullable enable
using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Net.WebSockets;
using System.Text;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using OpenRoIS.Sdk.JsonRpc;

namespace OpenRoIS.Sdk.Transport
{

  /// <summary>
  /// Connection lifecycle of a transport.
  /// </summary>
  /// <remarks>
  /// Disconnected, Connecting, Connected, Closing, then Disconnected again. A
  /// connection that ends on its own goes from Connected straight to
  /// Disconnected.
  /// </remarks>
  public enum TransportState
  {
    /// <summary>No connection. <c>ConnectAsync</c> opens one.</summary>
    Disconnected,

    /// <summary>The WebSocket is opening.</summary>
    Connecting,

    /// <summary>Messages travel both ways.</summary>
    Connected,

    /// <summary>The connection, or the attempt to open one, is ending.</summary>
    Closing,
  }

  /// <summary>
  /// A single WebSocket connection to an engine, speaking JSON-RPC 2.0.
  /// </summary>
  /// <remarks>
  /// <para>
  /// It opens and closes the connection, correlates replies with requests by
  /// id, and passes on what the engine pushes. It does not look inside params
  /// or results: <see cref="RoISClient"/> reads those through the generated
  /// models. <see cref="SendAsync"/> reaches methods outside the catalog.
  /// </para>
  /// <para>
  /// One transport manages one connection at a time. After it closes,
  /// <see cref="ConnectAsync"/> opens a new one.
  /// </para>
  /// <para>
  /// <see cref="ClientWebSocket"/> takes one send at a time, so a single task
  /// sends what a queue holds, and one reader task receives every message. No
  /// token reaches the socket, because cancelling a socket call aborts the
  /// connection, which is not what a caller who gives up on one request asks
  /// for.
  /// </para>
  /// <para>Events, for <c>On</c> and <c>Off</c>:</para>
  /// <list type="table">
  /// <item><term>open</term><description>No arguments. The connection opened.</description></item>
  /// <item><term>notification</term><description><see cref="JsonRpcNotification"/>, in or outside the catalog.</description></item>
  /// <item><term>close</term><description>(int code, string reason). The connection closed, from either side.</description></item>
  /// <item><term>error</term><description><see cref="Exception"/>. A message could not be used, or a listener threw. With no listener it is logged.</description></item>
  /// </list>
  /// </remarks>
  public sealed class WebSocketTransport
  {
    /// <summary>How long a request waits for its reply.</summary>
    public static readonly TimeSpan DefaultRequestTimeout = TimeSpan.FromSeconds(30);

    /// <summary>How long the WebSocket has to open.</summary>
    public static readonly TimeSpan DefaultConnectTimeout = TimeSpan.FromSeconds(10);

    /// <summary>The largest message accepted, in bytes, as in the Python client.</summary>
    public const int MaxMessageBytes = 16 * 1024 * 1024;

    private const int NormalClose = 1000;
    private const string ClientReason = "client closed";

    // The close code of a connection that ended with no close frame.
    private const int AbnormalClose = 1006;

    // The close code of a close frame that carried no code.
    private const int NoStatusClose = 1005;

    // The most bytes of UTF-8 that a close frame has room for as its reason.
    private const int MaxCloseReasonBytes = 123;

    private const int ReceiveBufferBytes = 64 * 1024;

    // How many cancelled requests a transport remembers. A peer might never
    // answer them, so the memory has to stop somewhere, and a reply past it
    // is only reported as a fault.
    private const int MaxAbandonedRequests = 1024;

    // How much of an unusable message an error quotes.
    private const int QuotedCharacters = 200;

    private const string ClosedByClient = "Connection closed by client";
    private const string RefusedFrame = "refused frame";

    private static readonly UTF8Encoding s_utf8 = new UTF8Encoding(false, true);

    private static readonly IReadOnlyDictionary<string, Type> s_payloads =
        new Dictionary<string, Type>
        {
          [EventNames.Open] = typeof(void),
          [EventNames.Notification] = typeof(JsonRpcNotification),
          [EventNames.Close] = typeof(CloseReport),
          [EventNames.Error] = typeof(Exception),
        };

    private sealed class Outgoing
    {
      // Null for the close frame, which ends the queue.
      internal string? Id { get; }

      internal byte[] Message { get; }

      internal Outgoing(string? id, byte[] message)
      {
        Id = id;
        Message = message;
      }
    }

    private readonly Emitter _emitter = new Emitter(s_payloads);
    private readonly TimeSpan _requestTimeout;
    private readonly TimeSpan _connectTimeout;

    // Guards every field below. Nothing runs application code while it holds
    // this lock, and a task's continuations run elsewhere.
    private readonly object _gate = new object();
    private readonly Dictionary<string, TaskCompletionSource<JsonElement>> _pending =
        new Dictionary<string, TaskCompletionSource<JsonElement>>();
    private readonly Queue<Outgoing> _outgoing = new Queue<Outgoing>();
    private readonly HashSet<string> _abandoned = new HashSet<string>();
    private readonly Queue<string> _abandonedOrder = new Queue<string>();
    private TransportState _state = TransportState.Disconnected;
    private string _url = string.Empty;
    private ClientWebSocket? _socket;
    private Task? _reader;
    private CancellationTokenSource? _attempt;
    private Task? _attemptEnded;
    private (int Code, string Reason)? _closeRequest;
    private CancellationTokenSource? _closeDeadline;
    private bool _sending;
    private long _nextId;

    /// <summary>Create a transport with no connection.</summary>
    /// <param name="requestTimeout">How long a request waits for its reply,
    /// by default <see cref="DefaultRequestTimeout"/>.</param>
    /// <param name="connectTimeout">How long the WebSocket has to open, by
    /// default <see cref="DefaultConnectTimeout"/>.</param>
    public WebSocketTransport(TimeSpan? requestTimeout = null, TimeSpan? connectTimeout = null)
    {
      _requestTimeout = Checked(requestTimeout ?? DefaultRequestTimeout, nameof(requestTimeout));
      _connectTimeout = Checked(connectTimeout ?? DefaultConnectTimeout, nameof(connectTimeout));
    }

    /// <summary>The current connection state.</summary>
    public TransportState State
    {
      get
      {
        lock (_gate)
        {
          return _state;
        }
      }
    }

    /// <summary>
    /// How long a peer has to answer a close frame before the connection is
    /// dropped, which is the close timeout of the Python client.
    /// </summary>
    internal TimeSpan CloseTimeout { get; set; } = TimeSpan.FromSeconds(10);

    /// <summary>
    /// Runs between the handshake and the state that follows it, for a test,
    /// because no peer and no caller can stop a connection at that point.
    /// </summary>
    internal Action? AfterHandshake { get; set; }

    /// <summary>
    /// Runs with a close frame of the peer read and not yet answered, for a
    /// test, because only a test can decide which side of that race wins.
    /// </summary>
    internal Func<ClientWebSocket, Task>? BeforeCloseAnswer { get; set; }

    /// <summary>Add a listener of <c>open</c>. It stays until <c>Off</c> removes it.</summary>
    public WebSocketTransport On(string name, Action listener)
    {
      _emitter.Add(name, listener);
      return this;
    }

    /// <summary>Add a listener of <c>close</c>. It stays until <c>Off</c> removes it.</summary>
    public WebSocketTransport On(string name, Action<int, string> listener)
    {
      _emitter.Add(name, listener);
      return this;
    }

    /// <summary>
    /// Add a listener of <c>notification</c>, which takes a
    /// <see cref="JsonRpcNotification"/>, or of <c>error</c>, which takes an
    /// <see cref="Exception"/>. It stays until <c>Off</c> removes it.
    /// </summary>
    public WebSocketTransport On<T>(string name, Action<T> listener)
    {
      _emitter.Add(name, listener);
      return this;
    }

    /// <summary>Remove a listener of <c>open</c>.</summary>
    public WebSocketTransport Off(string name, Action listener)
    {
      _emitter.Remove(name, listener);
      return this;
    }

    /// <summary>Remove a listener of <c>close</c>.</summary>
    public WebSocketTransport Off(string name, Action<int, string> listener)
    {
      _emitter.Remove(name, listener);
      return this;
    }

    /// <summary>Remove a listener of <c>notification</c> or <c>error</c>.</summary>
    public WebSocketTransport Off<T>(string name, Action<T> listener)
    {
      _emitter.Remove(name, listener);
      return this;
    }

    /// <summary>Open a WebSocket connection to an engine.</summary>
    /// <remarks>
    /// Captures <see cref="SynchronizationContext.Current"/>, where listeners
    /// run from then on.
    /// </remarks>
    /// <param name="url">The WebSocket URL, for example <c>ws://127.0.0.1:8765</c>.</param>
    /// <param name="cancellationToken">Ends the attempt.</param>
    /// <exception cref="RoISConnectionException">The connection failed or
    /// timed out, <see cref="CloseAsync"/> ran first, or this transport is
    /// not disconnected.</exception>
    /// <exception cref="OperationCanceledException">The token fired.</exception>
    public async Task ConnectAsync(string url, CancellationToken cancellationToken = default)
    {
      cancellationToken.ThrowIfCancellationRequested();
      var context = SynchronizationContext.Current;
      var ended = new TaskCompletionSource<bool>(
          TaskCreationOptions.RunContinuationsAsynchronously);
      using var attempt = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);
      lock (_gate)
      {
        if (_state != TransportState.Disconnected)
        {
          throw new RoISConnectionException(
              $"Cannot connect: transport is in state {_state}", url);
        }
        _state = TransportState.Connecting;
        _url = url;
        _attempt = attempt;
        _attemptEnded = ended.Task;
      }
      _emitter.Context = context;

      ClientWebSocket? socket = null;
      Task<Task>? reader = null;
      try
      {
        socket = new ClientWebSocket();
        attempt.CancelAfter(_connectTimeout);
        var opening = socket.ConnectAsync(new Uri(url), attempt.Token);

        // A token alone does not bound this on every runtime. Waiting here
        // does, and the socket is dropped below if the attempt is still going.
        opening.Forget();
        await opening.WaitOrCancel(attempt.Token).ConfigureAwait(false);
        AfterHandshake?.Invoke();

        var connected = socket;
        lock (_gate)
        {
          if (_state == TransportState.Connecting)
          {
            reader = new Task<Task>(() => ReadAsync(connected));
            _reader = reader.Unwrap();
            _socket = connected;
            _state = TransportState.Connected;
            _attempt = null;
            _attemptEnded = null;
          }
        }
        if (reader == null)
        {
          throw new RoISConnectionException(ClosedByClient, url);
        }
      }
      catch (Exception error) when (!(error is RoISConnectionException))
      {
        bool closedFirst;
        lock (_gate)
        {
          closedFirst = _state == TransportState.Closing;
        }
        if (closedFirst)
        {
          throw new RoISConnectionException(ClosedByClient, url, error);
        }
        cancellationToken.ThrowIfCancellationRequested();
        if (attempt.IsCancellationRequested)
        {
          throw new RoISConnectionException(
              $"Connection timed out after {Seconds(_connectTimeout)}s", url, error);
        }
        throw new RoISConnectionException(
            $"WebSocket connection failed: {error.Message}", url, error);
      }
      finally
      {
        if (reader == null)
        {
          lock (_gate)
          {
            _state = TransportState.Disconnected;
            _attempt = null;
            _attemptEnded = null;
          }
          socket?.Dispose();
        }
        ended.TrySetResult(true);
      }

      // The reader starts only now, so that no message can reach a listener
      // ahead of open.
      _emitter.Emit(EventNames.Open, null);
      reader!.Start(TaskScheduler.Default);
    }

    /// <summary>Send a JSON-RPC request and wait for its reply.</summary>
    /// <remarks>
    /// Nothing is validated here. <see cref="RoISClient"/> reads results
    /// through the generated models, and methods outside the catalog have
    /// nothing to check against.
    /// </remarks>
    /// <param name="method">The JSON-RPC method name, for example
    /// <c>rois.command.search</c>.</param>
    /// <param name="parameters">The named parameters of the method, or null.</param>
    /// <param name="cancellationToken">Stops waiting for the reply. A request
    /// still in the queue is not sent.</param>
    /// <returns>The <c>result</c> of the reply.</returns>
    /// <exception cref="RpcException">The engine answered with a JSON-RPC error.</exception>
    /// <exception cref="RequestTimeoutException">No reply arrived in time.</exception>
    /// <exception cref="RoISConnectionException">The connection closed while
    /// waiting.</exception>
    /// <exception cref="TransportException">The transport is not connected.</exception>
    /// <exception cref="OperationCanceledException">The token fired.</exception>
    public async Task<JsonElement> SendAsync(
        string method,
        object? parameters = null,
        CancellationToken cancellationToken = default)
    {
      cancellationToken.ThrowIfCancellationRequested();
      var id = $"req-{Interlocked.Increment(ref _nextId).ToString(CultureInfo.InvariantCulture)}";
      var message = s_utf8.GetBytes(JsonRpcBuilder.CreateRequest(id, method, parameters));
      var reply = new TaskCompletionSource<JsonElement>(
          TaskCreationOptions.RunContinuationsAsynchronously);
      lock (_gate)
      {
        if (_state != TransportState.Connected)
        {
          throw new TransportException($"Cannot send: transport is in state {_state}");
        }

        // Registered before it can be sent, because the reply can arrive
        // while the send is still in progress.
        _pending[id] = reply;
        Enqueue(new Outgoing(id, message));
      }

      using var deadline = new CancellationTokenSource(_requestTimeout);
      using (deadline.Token.Register(() => Expire(id, method)))
      using (cancellationToken.Register(() => Abandon(id, cancellationToken)))
      {
        return await reply.Task.ConfigureAwait(false);
      }
    }

    /// <summary>Close the connection, and wait until it has closed.</summary>
    /// <remarks>
    /// <para>
    /// Requests still waiting fail with <see cref="RoISConnectionException"/>.
    /// This is safe to call when already disconnected, and calls that overlap
    /// all wait for the same close. A caller who cancels stops waiting, and
    /// the close goes on without it.
    /// </para>
    /// <para>
    /// During <see cref="ConnectAsync"/> it ends the attempt instead and
    /// waits for it. <c>ConnectAsync</c> throws
    /// <see cref="RoISConnectionException"/>, and no close event fires,
    /// because no connection opened.
    /// </para>
    /// <para>
    /// A close frame that cannot be sent is reported to the error listeners,
    /// and the connection is dropped, so this still ends with the connection
    /// closed.
    /// </para>
    /// </remarks>
    /// <param name="code">The WebSocket close code: 1000, or 3000 to 4999,
    /// which is what the WebSocket API lets a client send.</param>
    /// <param name="reason">The close reason, at most 123 bytes of UTF-8.</param>
    /// <param name="cancellationToken">Stops waiting.</param>
    /// <exception cref="TransportException">The code or the reason is not
    /// one of those, in any state. A connection stays open.</exception>
    public async Task CloseAsync(
        int code = NormalClose,
        string reason = ClientReason,
        CancellationToken cancellationToken = default)
    {
      if (code != NormalClose && !(code >= 3000 && code <= 4999))
      {
        throw new TransportException($"Cannot close with code {code}: use 1000, or 3000 to 4999");
      }
      if (Encoding.UTF8.GetByteCount(reason) > MaxCloseReasonBytes)
      {
        throw new TransportException(
            $"Cannot close with this reason: it is over {MaxCloseReasonBytes} bytes of UTF-8");
      }

      CancellationTokenSource? attempt;
      Task? finished;
      lock (_gate)
      {
        attempt = _attempt;
        finished = _attemptEnded;
        if (finished != null)
        {
          _state = TransportState.Closing;
        }
        else
        {
          BeginClose(code, reason, ClosedByClient);
          finished = _reader;
        }
      }

      EndAttempt(attempt);
      if (finished != null)
      {
        await finished.WaitOrCancel(cancellationToken).ConfigureAwait(false);
      }
    }

    /// <summary>
    /// Begin to close a connection, and leave the rest to the transport.
    /// </summary>
    /// <remarks>
    /// For a caller who must not wait for a peer that stopped answering,
    /// because the closing handshake can take the whole close timeout.
    /// </remarks>
    internal void StartClose()
    {
      lock (_gate)
      {
        BeginClose(NormalClose, ClientReason, ClosedByClient);
      }
    }

    /// <summary>End the connection or the attempt now, with no closing handshake.</summary>
    internal void Abort()
    {
      CancellationTokenSource? attempt;
      ClientWebSocket? socket;
      lock (_gate)
      {
        attempt = _attempt;
        socket = _socket;
        if (attempt != null)
        {
          _state = TransportState.Closing;
        }
      }
      EndAttempt(attempt);
      socket?.Abort();
    }

    /// <summary>Set the one listener of an event that runs on the reader.</summary>
    internal void Observe(string name, Action<object?> observer)
    {
      _emitter.Observe(name, observer);
    }

    private static TimeSpan Checked(TimeSpan timeout, string name)
    {
      if (timeout != Timeout.InfiniteTimeSpan
          && (timeout < TimeSpan.Zero || timeout.TotalMilliseconds > int.MaxValue))
      {
        throw new ArgumentOutOfRangeException(name, timeout, "A timeout has to fit a timer.");
      }
      return timeout;
    }

    private static string Seconds(TimeSpan timeout)
    {
      return timeout.TotalSeconds.ToString(CultureInfo.InvariantCulture);
    }

    private static void EndAttempt(CancellationTokenSource? attempt)
    {
      // Outside the lock, because a token runs its callbacks inline and those
      // can reach code that belongs to the caller of ConnectAsync.
      try
      {
        attempt?.Cancel();
      }
      catch (ObjectDisposedException)
      {
        // The attempt ended on its own first, which is what this asked for.
      }
    }

    // -----------------------------------------------------------------------
    // Private: sending
    // -----------------------------------------------------------------------

    /// <summary>Add to the queue. The caller holds the lock.</summary>
    private void Enqueue(Outgoing item)
    {
      _outgoing.Enqueue(item);
      if (!_sending)
      {
        _sending = true;
        var socket = _socket!;
        Task.Run(() => SendQueueAsync(socket));
      }
    }

    /// <summary>
    /// Fail what waits and queue the close frame, unless a close has already
    /// begun. The caller holds the lock.
    /// </summary>
    private void BeginClose(int code, string reason, string failure)
    {
      var socket = _socket;
      if (_state != TransportState.Connected || socket == null)
      {
        return;
      }
      _state = TransportState.Closing;
      _closeRequest = (code, reason);
      FailPending(failure);
      Enqueue(new Outgoing(null, Array.Empty<byte>()));

      // Only the end of the handshake lets go of a peer that never answers
      // the close frame, and the reader cannot end before that.
      _closeDeadline = new CancellationTokenSource(CloseTimeout);
      _closeDeadline.Token.Register(socket.Abort);
    }

    /// <summary>Fail every request still waiting. The caller holds the lock.</summary>
    private void FailPending(string message)
    {
      foreach (var reply in _pending.Values)
      {
        reply.TrySetException(new RoISConnectionException(message, _url));
      }
      _pending.Clear();
    }

    private async Task SendQueueAsync(ClientWebSocket socket)
    {
      while (true)
      {
        Outgoing item;
        (int Code, string Reason)? close;
        lock (_gate)
        {
          // A later connection has a queue task of its own.
          if (_socket != socket)
          {
            return;
          }
          if (_outgoing.Count == 0)
          {
            _sending = false;
            return;
          }
          item = _outgoing.Dequeue();

          // Its caller gave up, or the connection is closing.
          if (item.Id != null && !_pending.ContainsKey(item.Id))
          {
            continue;
          }
          close = _closeRequest;
        }

        try
        {
          if (item.Id != null)
          {
            await socket.SendAsync(
                new ArraySegment<byte>(item.Message),
                WebSocketMessageType.Text,
                true,
                CancellationToken.None).ConfigureAwait(false);
          }
          else if (socket.State == WebSocketState.Open)
          {
            await socket.CloseOutputAsync(
                (WebSocketCloseStatus)close!.Value.Code,
                close.Value.Reason,
                CancellationToken.None).ConfigureAwait(false);
          }
        }
        catch (Exception error)
        {
          SendFailed(socket, item, error);
        }
      }
    }

    private void SendFailed(ClientWebSocket socket, Outgoing item, Exception error)
    {
      TaskCompletionSource<JsonElement>? reply = null;
      lock (_gate)
      {
        if (item.Id != null)
        {
          _pending.Remove(item.Id, out reply);
        }
      }
      if (reply != null)
      {
        reply.TrySetException(
            new RoISConnectionException($"Connection lost: {error.Message}", _url, error));
      }
      else if (item.Id == null)
      {
        _emitter.Emit(EventNames.Error, new TransportException(
            $"Cannot send the close frame: {error.Message}", error));
      }

      // Nothing else can go out on this socket, and the end of the reader is
      // what tells everyone else.
      socket.Abort();
    }

    private void Expire(string id, string method)
    {
      TaskCompletionSource<JsonElement>? reply;
      lock (_gate)
      {
        if (!_pending.Remove(id, out reply))
        {
          return;
        }
      }
      reply!.TrySetException(new RequestTimeoutException(method, id, _requestTimeout));
    }

    private void Abandon(string id, CancellationToken cancellationToken)
    {
      TaskCompletionSource<JsonElement>? reply;
      lock (_gate)
      {
        if (!_pending.Remove(id, out reply))
        {
          return;
        }

        // The peer does not know the caller left, so a reply can still arrive.
        if (_abandoned.Count == MaxAbandonedRequests)
        {
          _abandoned.Remove(_abandonedOrder.Dequeue());
        }
        _abandoned.Add(id);
        _abandonedOrder.Enqueue(id);
      }
      reply!.TrySetCanceled(cancellationToken);
    }

    // -----------------------------------------------------------------------
    // Private: the reader
    // -----------------------------------------------------------------------

    /// <summary>
    /// Receive every message of a connection, then report how it ended.
    /// </summary>
    /// <remarks>
    /// The report runs however this ends, because the requests would
    /// otherwise wait for a reply nothing can deliver. That includes a
    /// cancellation, which an aborted socket raises in place of the failure
    /// it raises for a lost connection. It never throws, so a caller of
    /// <see cref="CloseAsync"/> who waits for this task sees no failure that
    /// is not its own.
    /// </remarks>
    private async Task ReadAsync(ClientWebSocket socket)
    {
      var code = AbnormalClose;
      var reason = string.Empty;
      try
      {
        var buffer = new byte[ReceiveBufferBytes];
        using var message = new MemoryStream();
        var oversized = false;
        while (true)
        {
          var part = await socket.ReceiveAsync(
              new ArraySegment<byte>(buffer),
              CancellationToken.None).ConfigureAwait(false);
          if (part.MessageType == WebSocketMessageType.Close)
          {
            code = socket.CloseStatus == null ? NoStatusClose : (int)socket.CloseStatus.Value;
            reason = socket.CloseStatusDescription ?? string.Empty;
            await AnswerCloseAsync(socket).ConfigureAwait(false);
            return;
          }

          if (message.Length + part.Count > MaxMessageBytes)
          {
            oversized = true;
            message.SetLength(0);
            CloseOverLimit();
          }
          if (!oversized)
          {
            message.Write(buffer, 0, part.Count);
          }
          if (part.EndOfMessage)
          {
            if (!oversized)
            {
              Receive(part.MessageType, message.GetBuffer(), (int)message.Length);
            }
            message.SetLength(0);
            oversized = false;
          }
        }
      }
      catch (WebSocketException error) when (IsRefusedFrame(error))
      {
        // The socket refuses a bad frame, or text that is not UTF-8, by itself
        // and does not say which it was. No close frame arrived, so 1006 is
        // still the code, but the reason tells this from a lost network.
        reason = RefusedFrame;
        _emitter.Emit(EventNames.Error, new TransportException(
            $"The socket refused a frame: {error.Message}", error));
      }
      catch (Exception error)
      {
        // A lost connection is no fault, because the close event reports it.
        // Anything else is a defect to hear about.
        if (!(error is WebSocketException
            || error is OperationCanceledException
            || error is ObjectDisposedException
            || error is IOException))
        {
          _emitter.Emit(EventNames.Error, error);
        }
      }
      finally
      {
        Finish(code, reason);
        socket.Dispose();
      }
    }

    /// <summary>
    /// Whether the socket ended the connection over what the peer sent. The
    /// Unity class libraries report this as the inner exception of a lost
    /// connection, and .NET reports it directly.
    /// </summary>
    private static bool IsRefusedFrame(WebSocketException error)
    {
      return error.WebSocketErrorCode == WebSocketError.Faulted
          || (error.InnerException is WebSocketException inner
              && inner.WebSocketErrorCode == WebSocketError.Faulted);
    }

    /// <summary>Complete a closing handshake the peer started.</summary>
    private async Task AnswerCloseAsync(ClientWebSocket socket)
    {
      if (socket.State != WebSocketState.CloseReceived)
      {
        return;
      }
      using var deadline = new CancellationTokenSource(CloseTimeout);
      try
      {
        if (BeforeCloseAnswer != null)
        {
          await BeforeCloseAnswer(socket).ConfigureAwait(false);
        }
        var status = socket.CloseStatus ?? WebSocketCloseStatus.Empty;
        await socket.CloseOutputAsync(
            status,
            status == WebSocketCloseStatus.Empty ? null : socket.CloseStatusDescription,
            deadline.Token).ConfigureAwait(false);
      }
      catch (Exception error)
      {
        // The peer's close can cross the close frame of this side, which
        // leaves nothing to answer, so that failure says nothing went wrong.
        if (ClosingByRequest())
        {
          return;
        }

        // The connection is over either way, and the peer's own code is what
        // the close event reports, but the peer heard no answer.
        _emitter.Emit(EventNames.Error, new TransportException(
            $"Cannot answer the close frame: {error.Message}", error));
      }
    }

    private bool ClosingByRequest()
    {
      lock (_gate)
      {
        return _closeRequest != null;
      }
    }

    /// <summary>
    /// End a connection whose message is too large, and report the code this
    /// sends rather than a dropped connection.
    /// </summary>
    private void CloseOverLimit()
    {
      const int code = (int)WebSocketCloseStatus.MessageTooBig;
      var reason = $"message over {MaxMessageBytes} bytes";
      lock (_gate)
      {
        BeginClose(code, reason, $"WebSocket closed unexpectedly: code {code}, reason: {reason}");
      }
    }

    private void Finish(int code, string reason)
    {
      lock (_gate)
      {
        // Report what the caller of CloseAsync asked for, because a peer that
        // never answers the close frame leaves only 1006 behind.
        if (_closeRequest != null)
        {
          (code, reason) = _closeRequest.Value;
          _closeRequest = null;
        }
        var shown = reason.Length == 0 ? "none" : reason;
        FailPending($"WebSocket closed unexpectedly: code {code}, reason: {shown}");
        _outgoing.Clear();
        _abandoned.Clear();
        _abandonedOrder.Clear();
        _closeDeadline?.Dispose();
        _closeDeadline = null;
        _sending = false;
        _socket = null;
        _reader = null;
        _state = TransportState.Disconnected;
      }
      _emitter.Emit(EventNames.Close, new CloseReport(code, reason));
    }

    /// <summary>
    /// Classify one message and dispatch it, or report it as a fault. A
    /// failure here must not end the reader, so that one bad message costs
    /// one message.
    /// </summary>
    internal void Receive(WebSocketMessageType type, byte[] buffer, int length)
    {
      // After CloseAsync nothing reaches a listener, because the caller has
      // been told the connection is gone, but the socket still has to drain
      // to finish closing.
      if (State != TransportState.Connected)
      {
        return;
      }
      if (type == WebSocketMessageType.Binary)
      {
        // JSON-RPC here is text, and a browser could not parse this frame at all.
        _emitter.Emit(EventNames.Error, new TransportException(
            $"Received a binary message of {length} bytes"));
        return;
      }

      try
      {
        var text = s_utf8.GetString(buffer, 0, length);
        var message = JsonRpcParser.Parse(text);
        switch (message.Type)
        {
          case JsonRpcMessageType.Response:
            Settle(message.Response!.Id, message.Response.Result, null);
            break;
          case JsonRpcMessageType.Error:
            var error = message.Error!;
            Settle(error.Id, default, new RpcException(
                error.Error.Code, error.Error.Message, error.Error.Data));
            break;
          case JsonRpcMessageType.Notification:
            // Only ever under this one name, because a server could otherwise
            // fake the close event by naming a notification after it.
            _emitter.Emit(EventNames.Notification, message.Notification);
            break;
          default:
            _emitter.Emit(EventNames.Error, new TransportException(
                $"Received unrecognized message: {Quoted(text)}"));
            break;
        }
      }
      catch (Exception fault)
      {
        _emitter.Emit(EventNames.Error, new TransportException(
            $"Cannot read a message: {fault.Message}", fault));
      }
    }

    private static string Quoted(string text)
    {
      return text.Length > QuotedCharacters ? text.Substring(0, QuotedCharacters) : text;
    }

    /// <summary>Hand a reply to the request it answers.</summary>
    private void Settle(string? id, JsonElement result, RpcException? fault)
    {
      TaskCompletionSource<JsonElement>? reply = null;
      bool abandoned;
      lock (_gate)
      {
        if (id != null)
        {
          _pending.Remove(id, out reply);
        }
        abandoned = id != null && _abandoned.Contains(id);
      }

      if (reply == null)
      {
        // A caller who cancels stops caring about the answer, so that is no
        // fault. Anything else is a duplicate, or a reply that arrived after
        // its request timed out.
        if (!abandoned)
        {
          _emitter.Emit(EventNames.Error, new TransportException(
              $"Received reply for unknown id: {id ?? "null"}"));
        }
      }
      else if (fault != null)
      {
        reply.TrySetException(fault);
      }
      else
      {
        reply.TrySetResult(result);
      }
    }
  }

}  // namespace OpenRoIS.Sdk.Transport
