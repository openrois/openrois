#nullable enable
using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Net;
using System.Net.Sockets;
using System.Net.WebSockets;
using System.Runtime.CompilerServices;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;

namespace OpenRoIS.Sdk.Core.Tests
{

  /// <summary>Writes what a server sends.</summary>
  internal static class Wire
  {
    /// <summary>
    /// A reply to a request, with OK unless the fields give another return code.
    /// </summary>
    internal static string Reply(JsonElement request, params (string Name, object? Value)[] fields)
    {
      var result = new Dictionary<string, object?> { ["return_code"] = "OK" };
      foreach (var (name, value) in fields)
      {
        result[name] = value;
      }
      return JsonSerializer.Serialize(new Dictionary<string, object?>
      {
        ["jsonrpc"] = "2.0",
        ["id"] = request.GetProperty("id"),
        ["result"] = result,
      });
    }

    internal static string Notification(string method, object parameters)
    {
      return JsonSerializer.Serialize(new Dictionary<string, object?>
      {
        ["jsonrpc"] = "2.0",
        ["method"] = method,
        ["params"] = parameters,
      });
    }

    internal static string Failure(JsonElement request, int code, string message, object? data)
    {
      return JsonSerializer.Serialize(new Dictionary<string, object?>
      {
        ["jsonrpc"] = "2.0",
        ["id"] = request.GetProperty("id"),
        ["error"] = new Dictionary<string, object?>
        {
          ["code"] = code,
          ["message"] = message,
          ["data"] = data,
        },
      });
    }

    internal static string Method(this JsonElement request)
    {
      return request.GetProperty("method").GetString()!;
    }
  }

  /// <summary>One client of a <see cref="TestServer"/>.</summary>
  internal sealed class Peer
  {
    private const int FinalText = 0x81;
    private const int FinalClose = 0x88;

    private readonly TcpClient _tcp;
    private readonly WebSocket _socket;

    internal Peer(TcpClient tcp, CancellationToken stopped)
    {
      _tcp = tcp;
      _socket = WebSocket.CreateFromStream(
          tcp.GetStream(), isServer: true, subProtocol: null, TimeSpan.Zero);
      Stopped = stopped;
    }

    /// <summary>Fires when the server stops.</summary>
    internal CancellationToken Stopped { get; }

    /// <summary>The close code the client sent, once one arrived.</summary>
    internal int? CloseCode { get; private set; }

    /// <summary>
    /// Read every request until the client closes, and answer its close frame.
    /// </summary>
    internal async IAsyncEnumerable<JsonElement> Requests()
    {
      while (true)
      {
        var message = await ReceiveAsync();
        if (message == null)
        {
          yield break;
        }
        yield return message.Value;
      }
    }

    /// <summary>The next request, or null when the client closed.</summary>
    internal async Task<JsonElement?> ReceiveAsync()
    {
      var buffer = new byte[64 * 1024];
      using var message = new MemoryStream();
      while (true)
      {
        var part = await _socket.ReceiveAsync(new ArraySegment<byte>(buffer), Stopped);
        if (part.MessageType == WebSocketMessageType.Close)
        {
          CloseCode = (int?)_socket.CloseStatus;
          if (_socket.State == WebSocketState.CloseReceived)
          {
            await _socket.CloseOutputAsync(
                _socket.CloseStatus ?? WebSocketCloseStatus.Empty,
                _socket.CloseStatusDescription,
                Stopped);
          }
          return null;
        }
        message.Write(buffer, 0, part.Count);
        if (part.EndOfMessage)
        {
          using var document = JsonDocument.Parse(message.ToArray());
          return document.RootElement.Clone();
        }
      }
    }

    /// <summary>Wait until the client has gone.</summary>
    internal async Task LeftAsync()
    {
      while (await ReceiveAsync() != null)
      {
      }
    }

    internal Task SendAsync(string text)
    {
      return _socket.SendAsync(
          new ArraySegment<byte>(Encoding.UTF8.GetBytes(text)),
          WebSocketMessageType.Text,
          true,
          Stopped);
    }

    internal Task SendBinaryAsync(byte[] message)
    {
      return _socket.SendAsync(
          new ArraySegment<byte>(message), WebSocketMessageType.Binary, true, Stopped);
    }

    /// <summary>Send one message in several frames.</summary>
    internal async Task SendFragmentsAsync(params string[] parts)
    {
      for (var index = 0; index < parts.Length; index++)
      {
        await _socket.SendAsync(
            new ArraySegment<byte>(Encoding.UTF8.GetBytes(parts[index])),
            WebSocketMessageType.Text,
            index == parts.Length - 1,
            Stopped);
      }
    }

    /// <summary>Send one text frame of a single byte that is not UTF-8.</summary>
    /// <remarks>
    /// It goes around the socket here, which would refuse to write this.
    /// </remarks>
    internal Task SendInvalidTextAsync()
    {
      return WriteRawAsync(FinalText, 1, 0xff);
    }

    /// <summary>Send a close frame that carries no code.</summary>
    internal Task SendEmptyCloseAsync()
    {
      return WriteRawAsync(FinalClose, 0);
    }

    /// <summary>Start a closing handshake, and leave the rest to the client.</summary>
    internal Task CloseAsync(int code, string reason)
    {
      return _socket.CloseOutputAsync((WebSocketCloseStatus)code, reason, Stopped);
    }

    /// <summary>Leave without a close frame, as a crash or a lost network does.</summary>
    internal void Drop()
    {
      _tcp.LingerState = new LingerOption(true, 0);
      _tcp.Close();
    }

    private async Task WriteRawAsync(params int[] bytes)
    {
      var frame = bytes.Select(value => (byte)value).ToArray();
      await _tcp.GetStream().WriteAsync(frame, Stopped);
    }
  }

  /// <summary>
  /// A server in this process, where a handler decides what each client gets.
  /// </summary>
  /// <remarks>
  /// The scripted server serves every SDK, so it stays small: it never sends a
  /// JSON-RPC error, a notification or a bad result. The tests of those run
  /// this, and it does its own handshake so that it can also refuse to.
  /// </remarks>
  internal sealed class TestServer : IAsyncDisposable
  {
    private readonly TcpListener _listener = new TcpListener(IPAddress.Loopback, 0);
    private readonly CancellationTokenSource _stopping = new CancellationTokenSource();
    private readonly ConcurrentBag<Task> _serving = new ConcurrentBag<Task>();
    private readonly ConcurrentBag<TcpClient> _accepted = new ConcurrentBag<TcpClient>();
    private readonly Func<Peer, Task>? _handler;
    private readonly Task _accepting;

    private TestServer(Func<Peer, Task>? handler)
    {
      _handler = handler;
      _listener.Start();
      Url = $"ws://127.0.0.1:{((IPEndPoint)_listener.LocalEndpoint).Port}";
      _accepting = AcceptAsync();
    }

    internal string Url { get; }

    /// <summary>Run a handler for each client that connects.</summary>
    internal static TestServer Serving(Func<Peer, Task> handler)
    {
      return new TestServer(handler);
    }

    /// <summary>
    /// A server that accepts a connection and never answers its handshake.
    /// </summary>
    internal static TestServer Mute()
    {
      return new TestServer(null);
    }

    /// <summary>
    /// A server that completes the handshake and then reads nothing, not even
    /// a close frame.
    /// </summary>
    internal static TestServer Deaf(Action<Peer>? arrived = null)
    {
      return Serving(async peer =>
      {
        arrived?.Invoke(peer);
        await Task.Delay(Timeout.Infinite, peer.Stopped);
      });
    }

    public async ValueTask DisposeAsync()
    {
      _stopping.Cancel();
      _listener.Stop();
      await _accepting;
      foreach (var tcp in _accepted)
      {
        tcp.Dispose();
      }
      await Task.WhenAll(_serving);
    }

    private async Task AcceptAsync()
    {
      while (!_stopping.IsCancellationRequested)
      {
        TcpClient tcp;
        try
        {
          tcp = await _listener.AcceptTcpClientAsync();
        }
        catch (Exception error) when (error is SocketException || error is ObjectDisposedException)
        {
          // Only stopping the listener ends this wait.
          return;
        }
        _accepted.Add(tcp);
        _serving.Add(ServeAsync(tcp));
      }
    }

    private async Task ServeAsync(TcpClient tcp)
    {
      try
      {
        var request = await ReadRequestAsync(tcp.GetStream());
        if (_handler == null)
        {
          await Task.Delay(Timeout.Infinite, _stopping.Token);
          return;
        }
        await AnswerAsync(tcp.GetStream(), request);
        await _handler(new Peer(tcp, _stopping.Token));
      }
      catch (Exception error) when (
          error is WebSocketException
          || error is IOException
          || error is OperationCanceledException
          || error is ObjectDisposedException)
      {
        // Tests end connections in every way there is, and each one lands here.
      }
    }

    /// <summary>Read the HTTP upgrade request up to its empty line.</summary>
    private async Task<string> ReadRequestAsync(Stream stream)
    {
      var read = new List<byte>();
      var buffer = new byte[1];
      while (!Encoding.ASCII.GetString(read.ToArray()).EndsWith("\r\n\r\n", StringComparison.Ordinal))
      {
        if (await stream.ReadAsync(buffer, _stopping.Token) == 0)
        {
          throw new IOException("The client left during the handshake");
        }
        read.Add(buffer[0]);
      }
      return Encoding.ASCII.GetString(read.ToArray());
    }

    private async Task AnswerAsync(Stream stream, string request)
    {
      const string Magic = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11";
      var key = request
          .Split("\r\n")
          .First(line => line.StartsWith("Sec-WebSocket-Key:", StringComparison.OrdinalIgnoreCase))
          .Split(':')[1]
          .Trim();
      var accept = Convert.ToBase64String(SHA1.HashData(Encoding.ASCII.GetBytes(key + Magic)));
      var answer = "HTTP/1.1 101 Switching Protocols\r\n"
          + "Upgrade: websocket\r\n"
          + "Connection: Upgrade\r\n"
          + $"Sec-WebSocket-Accept: {accept}\r\n\r\n";
      await stream.WriteAsync(Encoding.ASCII.GetBytes(answer), _stopping.Token);
    }
  }

  /// <summary>
  /// A server that answers a session as an engine does, and records every request.
  /// </summary>
  internal sealed class TestEngine : IAsyncDisposable
  {
    private readonly ConcurrentQueue<JsonElement> _received = new ConcurrentQueue<JsonElement>();
    private readonly TestServer _server;

    /// <summary>Start the server.</summary>
    /// <param name="answers">The reply of each method that needs more than OK.</param>
    /// <param name="pushes">Messages to send right after the reply to
    /// <c>rois.system.connect</c>.</param>
    internal TestEngine(
        IReadOnlyDictionary<string, Func<JsonElement, string>>? answers = null,
        params string[] pushes)
    {
      _server = TestServer.Serving(async peer =>
      {
        await foreach (var request in peer.Requests())
        {
          _received.Enqueue(request);
          var method = request.Method();
          await peer.SendAsync(
              answers != null && answers.TryGetValue(method, out var answer)
                  ? answer(request)
                  : Wire.Reply(request));
          if (method == "rois.system.connect")
          {
            foreach (var message in pushes)
            {
              await peer.SendAsync(message);
            }
          }
        }
      });
    }

    internal string Url => _server.Url;

    internal IReadOnlyList<JsonElement> Received => _received.ToArray();

    /// <summary>The methods that arrived, in order.</summary>
    internal IReadOnlyList<string> Methods => Received.Select(request => request.Method()).ToArray();

    public ValueTask DisposeAsync()
    {
      return _server.DisposeAsync();
    }
  }

  /// <summary>
  /// Records what reaches a listener of <c>error</c>, and lets a test wait for it.
  /// </summary>
  internal sealed class Faults
  {
    private readonly ConcurrentQueue<Exception> _seen = new ConcurrentQueue<Exception>();
    private readonly TaskCompletionSource<Exception> _first =
        new TaskCompletionSource<Exception>(TaskCreationOptions.RunContinuationsAsynchronously);

    /// <summary>What has arrived so far.</summary>
    internal IReadOnlyList<Exception> Seen => _seen.ToArray();

    internal void Add(Exception error)
    {
      _seen.Enqueue(error);
      _first.TrySetResult(error);
    }

    internal Task<Exception> First()
    {
      return _first.Task.Soon();
    }
  }

  /// <summary>
  /// A thread that runs what is posted to it in order, as the main thread of
  /// Unity does.
  /// </summary>
  internal sealed class MainThread : SynchronizationContext, IDisposable
  {
    private readonly BlockingCollection<Action> _queue = new BlockingCollection<Action>();
    private readonly Thread _thread;

    internal MainThread()
    {
      _thread = new Thread(() =>
      {
        SetSynchronizationContext(this);
        foreach (var work in _queue.GetConsumingEnumerable())
        {
          work();
        }
      })
      {
        IsBackground = true,
      };
      _thread.Start();
    }

    internal int ThreadId => _thread.ManagedThreadId;

    public override void Post(SendOrPostCallback callback, object? state)
    {
      if (!_queue.IsAddingCompleted)
      {
        _queue.Add(() => callback(state));
      }
    }

    /// <summary>Run work on this thread, as a script of a scene does.</summary>
    internal Task Run(Func<Task> body)
    {
      var done = new TaskCompletionSource<bool>(TaskCreationOptions.RunContinuationsAsynchronously);
      Post(async _ =>
      {
        try
        {
          await body();
          done.TrySetResult(true);
        }
        catch (Exception error)
        {
          done.TrySetException(error);
        }
      }, null);
      return done.Task;
    }

    /// <summary>
    /// Run work that blocks this thread until it returns, as code does that
    /// waits for a task on the main thread. A continuation posted here would
    /// wait for the work, and the work for the continuation.
    /// </summary>
    internal Task Blocking(Action body)
    {
      var done = new TaskCompletionSource<bool>(TaskCreationOptions.RunContinuationsAsynchronously);
      Post(_ =>
      {
        try
        {
          body();
          done.TrySetResult(true);
        }
        catch (Exception error)
        {
          done.TrySetException(error);
        }
      }, null);
      return done.Task.Soon();
    }

    public void Dispose()
    {
      _queue.CompleteAdding();
    }
  }

}  // namespace OpenRoIS.Sdk.Core.Tests
