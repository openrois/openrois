// RoISClient: the OpenRoIS client for Unity and any .NET runtime.
//
// Wraps a ClientWebSocket and the JSON-RPC 2.0 protocol into the five RoIS
// interfaces, mirroring the TypeScript SDK:
//
//   System   ConnectAsync, DisconnectAsync, GetProfileAsync, GetErrorDetailAsync
//   Command  SearchAsync, BindAsync, BindAnyAsync, ReleaseAsync, GetParameterAsync,
//            SetParameterAsync, ExecuteAsync, GetCommandResultAsync
//   Query    QueryAsync
//   Event    SubscribeAsync, UnsubscribeAsync, GetEventDetailAsync
//   Streaming  ConnectStreamAsync, DisconnectStreamAsync, SuspendStreamAsync,
//              ResumeStreamAsync, QueryStreamStatusAsync (control plane; media out of band)
//
// Callbacks are marshaled to the SynchronizationContext captured at connect time,
// which on Unity's main thread means they run on the main thread and may touch
// scene objects. Pass CallbackContext = null to receive them on the socket thread.

#nullable enable

using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.IO;
using System.Net.WebSockets;
using System.Text;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using OpenRoIS.Sdk.JsonRpc;

namespace OpenRoIS.Sdk
{
    public sealed class RoISClient : IDisposable
    {
        private readonly ClientWebSocket _socket;
        private readonly ClientOptions _options;
        private readonly ConcurrentDictionary<string, TaskCompletionSource<JsonElement>> _pending
            = new ConcurrentDictionary<string, TaskCompletionSource<JsonElement>>();
        private readonly CancellationTokenSource _closing = new CancellationTokenSource();
        private readonly SemaphoreSlim _sendLock = new SemaphoreSlim(1, 1);
        private Task? _receiveLoop;
        private int _nextId;
        private bool _disposed;

        /// <summary>A component event for one of this client's subscriptions.</summary>
        public event Action<EventNotification>? EventReceived;

        /// <summary>A command this client issued has completed.</summary>
        public event Action<CommandCompletion>? CommandCompleted;

        /// <summary>The engine reported an error to this client.</summary>
        public event Action<ErrorNotification>? ErrorNotified;

        /// <summary>The engine profile changed: an adapter connected or left.</summary>
        public event Action? ProfileChanged;

        /// <summary>The status of a stream this client connected changed.</summary>
        public event Action<StreamStatusNotification>? StreamStatusChanged;

        /// <summary>The connection closed, with the close status when known.</summary>
        public event Action<WebSocketCloseStatus?, string?>? Closed;

        /// <summary>Whether the RoIS connect handshake succeeded and the socket is open.</summary>
        public bool IsConnected => _socket.State == WebSocketState.Open;

        private RoISClient(ClientWebSocket socket, ClientOptions options)
        {
            _socket = socket;
            _options = options;
        }

        // ─── System ──────────────────────────────────────────────────────────

        /// <summary>Open the WebSocket and perform rois.system.connect.</summary>
        public static async Task<RoISClient> ConnectAsync(
            string url,
            ClientOptions? options = null,
            CancellationToken cancellationToken = default)
        {
            options ??= new ClientOptions();
            var socket = new ClientWebSocket();
            if (!string.IsNullOrEmpty(options.Token))
            {
                socket.Options.SetRequestHeader("Authorization", "Bearer " + options.Token);
            }
            await socket.ConnectAsync(new Uri(url), cancellationToken).ConfigureAwait(false);

            var client = new RoISClient(socket, options);
            client._receiveLoop = Task.Run(client.ReceiveLoopAsync);
            var result = await client.SendAsync("rois.system.connect", new { }).ConfigureAwait(false);
            client.Check(result, "rois.system.connect");
            return client;
        }

        /// <summary>Send rois.system.disconnect and close the socket.</summary>
        public async Task DisconnectAsync()
        {
            if (_socket.State == WebSocketState.Open)
            {
                try
                {
                    await SendAsync("rois.system.disconnect", new { }).ConfigureAwait(false);
                }
                catch (Exception)
                {
                    // The gateway may already be gone; closing is what matters.
                }
                await _socket.CloseAsync(WebSocketCloseStatus.NormalClosure, "disconnect", CancellationToken.None)
                    .ConfigureAwait(false);
            }
        }

        /// <summary>The engine profile as JSON: identifier, component_ids, component_profiles.</summary>
        public async Task<JsonElement> GetProfileAsync()
        {
            var result = await SendAsync("rois.system.get_profile", new { }).ConfigureAwait(false);
            Check(result, "rois.system.get_profile");
            return result.TryGetProperty("profile", out var profile) ? profile.Clone() : default;
        }

        public async Task<JsonElement> GetErrorDetailAsync(string errorId)
        {
            var result = await SendAsync("rois.system.get_error_detail", new { error_id = errorId })
                .ConfigureAwait(false);
            Check(result, "rois.system.get_error_detail");
            return result.Clone();
        }

        // ─── Command ─────────────────────────────────────────────────────────

        /// <summary>All component refs the engine offers, optionally filtered by a condition.</summary>
        public async Task<List<string>> SearchAsync(string condition = "")
        {
            var result = await SendAsync("rois.command.search", new { condition }).ConfigureAwait(false);
            Check(result, "rois.command.search");
            return Json.Strings(result, "component_ref_list");
        }

        public async Task BindAsync(string componentRef)
        {
            Check(await SendAsync("rois.command.bind", new { component_ref = componentRef })
                .ConfigureAwait(false), "rois.command.bind");
        }

        /// <summary>Bind the first free component matching the condition; returns its ref.</summary>
        public async Task<string> BindAnyAsync(string condition)
        {
            var result = await SendAsync("rois.command.bind_any", new { condition }).ConfigureAwait(false);
            Check(result, "rois.command.bind_any");
            return Json.String(result, "component_ref");
        }

        public async Task ReleaseAsync(string componentRef)
        {
            Check(await SendAsync("rois.command.release", new { component_ref = componentRef })
                .ConfigureAwait(false), "rois.command.release");
        }

        public async Task<List<RoISValue>> GetParameterAsync(string componentRef, IEnumerable<string>? names = null)
        {
            object parameters = names == null
                ? new { component_ref = componentRef }
                : new { component_ref = componentRef, names = new List<string>(names) };
            var result = await SendAsync("rois.command.get_parameter", parameters).ConfigureAwait(false);
            Check(result, "rois.command.get_parameter");
            return Json.Values(result, "results");
        }

        public async Task SetParameterAsync(string componentRef, IEnumerable<RoISValue> parameters)
        {
            var wire = new List<Dictionary<string, string>>();
            foreach (var p in parameters)
            {
                wire.Add(p.ToWire());
            }
            var result = await SendAsync(
                "rois.command.set_parameter",
                new { component_ref = componentRef, parameters = wire }).ConfigureAwait(false);
            Check(result, "rois.command.set_parameter");
        }

        /// <summary>Execute a command (default "execute") with optional parameters.</summary>
        public async Task<ExecuteResult> ExecuteAsync(
            string componentRef,
            string commandType = "execute",
            IEnumerable<RoISValue>? parameters = null)
        {
            var wire = new List<Dictionary<string, string>>();
            if (parameters != null)
            {
                foreach (var p in parameters)
                {
                    wire.Add(p.ToWire());
                }
            }
            var result = await SendAsync(
                "rois.command.execute",
                new { component_ref = componentRef, command_type = commandType, parameters = wire })
                .ConfigureAwait(false);
            Check(result, "rois.command.execute");
            return new ExecuteResult
            {
                ReturnCode = Json.String(result, "return_code"),
                CommandId = Json.String(result, "command_id"),
                Results = Json.Values(result, "results"),
            };
        }

        public async Task<List<RoISValue>> GetCommandResultAsync(string commandId)
        {
            var result = await SendAsync("rois.command.get_command_result", new { command_id = commandId })
                .ConfigureAwait(false);
            Check(result, "rois.command.get_command_result");
            return Json.Values(result, "results");
        }

        // ─── Query ───────────────────────────────────────────────────────────

        public async Task<List<RoISValue>> QueryAsync(string componentRef, string queryType, string condition = "")
        {
            var result = await SendAsync(
                "rois.query.query",
                new { component_ref = componentRef, query_type = queryType, condition }).ConfigureAwait(false);
            Check(result, "rois.query.query");
            return Json.Values(result, "results");
        }

        // ─── Event ───────────────────────────────────────────────────────────

        /// <summary>Subscribe to an event; returns the subscribe_id to unsubscribe with.</summary>
        public async Task<string> SubscribeAsync(string componentRef, string eventType, string condition = "")
        {
            var result = await SendAsync(
                "rois.event.subscribe",
                new { component_ref = componentRef, event_type = eventType, condition }).ConfigureAwait(false);
            Check(result, "rois.event.subscribe");
            return Json.String(result, "subscribe_id");
        }

        public async Task UnsubscribeAsync(string subscribeId)
        {
            Check(await SendAsync("rois.event.unsubscribe", new { subscribe_id = subscribeId })
                .ConfigureAwait(false), "rois.event.unsubscribe");
        }

        public async Task<JsonElement> GetEventDetailAsync(string eventId)
        {
            var result = await SendAsync("rois.event.get_event_detail", new { event_id = eventId })
                .ConfigureAwait(false);
            Check(result, "rois.event.get_event_detail");
            return result.Clone();
        }

        // ─── Streaming ───────────────────────────────────────────────────────

        /// <summary>Open a stream on a streaming component; the results carry the transport descriptor.</summary>
        public async Task<StreamHandle> ConnectStreamAsync(string componentRef, IEnumerable<RoISValue>? parameters = null)
        {
            var wire = new List<Dictionary<string, string>>();
            if (parameters != null)
            {
                foreach (var p in parameters)
                {
                    wire.Add(p.ToWire());
                }
            }
            var result = await SendAsync(
                "rois.stream.connect_stream",
                new { component_ref = componentRef, parameters = wire }).ConfigureAwait(false);
            Check(result, "rois.stream.connect_stream");
            return new StreamHandle
            {
                StreamId = Json.String(result, "stream_id"),
                Results = Json.Values(result, "results"),
            };
        }

        public Task DisconnectStreamAsync(string streamId) => StreamOperationAsync("rois.stream.disconnect_stream", streamId);

        public Task SuspendStreamAsync(string streamId) => StreamOperationAsync("rois.stream.suspend_stream", streamId);

        public Task ResumeStreamAsync(string streamId) => StreamOperationAsync("rois.stream.resume_stream", streamId);

        /// <summary>The current RoIS stream status, for example STREAMING_RUNNING.</summary>
        public async Task<string> QueryStreamStatusAsync(string streamId)
        {
            var result = await SendAsync("rois.stream.query_stream_status", new { stream_id = streamId })
                .ConfigureAwait(false);
            Check(result, "rois.stream.query_stream_status");
            return Json.String(result, "status");
        }

        private async Task StreamOperationAsync(string method, string streamId)
        {
            Check(await SendAsync(method, new { stream_id = streamId }).ConfigureAwait(false), method);
        }

        // ─── Plumbing ────────────────────────────────────────────────────────

        private void Check(JsonElement result, string method)
        {
            var code = Json.String(result, "return_code");
            if (code != ReturnCodes.OK)
            {
                throw new RoISException(string.IsNullOrEmpty(code) ? ReturnCodes.ERROR : code, method);
            }
        }

        private async Task<JsonElement> SendAsync(string method, object parameters)
        {
            if (_socket.State != WebSocketState.Open)
            {
                throw new InvalidOperationException("The client is not connected");
            }
            var id = Interlocked.Increment(ref _nextId).ToString();
            var tcs = new TaskCompletionSource<JsonElement>(TaskCreationOptions.RunContinuationsAsynchronously);
            _pending[id] = tcs;
            var json = JsonRpcBuilder.CreateRequest(id, method, parameters);
            var bytes = Encoding.UTF8.GetBytes(json);

            await _sendLock.WaitAsync().ConfigureAwait(false);
            try
            {
                await _socket.SendAsync(new ArraySegment<byte>(bytes), WebSocketMessageType.Text, true, _closing.Token)
                    .ConfigureAwait(false);
            }
            finally
            {
                _sendLock.Release();
            }

            using var timeout = new CancellationTokenSource(_options.RequestTimeout);
            using (timeout.Token.Register(() => tcs.TrySetException(new TimeoutException($"{method} timed out"))))
            {
                try
                {
                    return await tcs.Task.ConfigureAwait(false);
                }
                finally
                {
                    _pending.TryRemove(id, out _);
                }
            }
        }

        private async Task ReceiveLoopAsync()
        {
            var buffer = new byte[16 * 1024];
            WebSocketCloseStatus? closeStatus = null;
            string? closeDescription = null;
            try
            {
                while (!_closing.IsCancellationRequested && _socket.State == WebSocketState.Open)
                {
                    using var message = new MemoryStream();
                    WebSocketReceiveResult received;
                    do
                    {
                        received = await _socket.ReceiveAsync(new ArraySegment<byte>(buffer), _closing.Token)
                            .ConfigureAwait(false);
                        if (received.MessageType == WebSocketMessageType.Close)
                        {
                            closeStatus = received.CloseStatus;
                            closeDescription = received.CloseStatusDescription;
                            break;
                        }
                        message.Write(buffer, 0, received.Count);
                    } while (!received.EndOfMessage);

                    if (received.MessageType == WebSocketMessageType.Close)
                    {
                        break;
                    }
                    Route(Encoding.UTF8.GetString(message.ToArray()));
                }
            }
            catch (OperationCanceledException)
            {
                // Disposed while receiving.
            }
            catch (WebSocketException exception)
            {
                closeDescription = exception.Message;
            }
            finally
            {
                FailPending(new InvalidOperationException("The connection closed"));
                Marshal(() => Closed?.Invoke(closeStatus, closeDescription));
            }
        }

        private void Route(string json)
        {
            JsonRpcMessage message;
            try
            {
                message = JsonRpcParser.Parse(json);
            }
            catch (Exception)
            {
                return;
            }
            switch (message.Type)
            {
                case JsonRpcMessageType.Response:
                    if (message.Response != null && _pending.TryRemove(message.Response.Id, out var ok))
                    {
                        ok.TrySetResult(message.Response.Result.Clone());
                    }
                    break;
                case JsonRpcMessageType.Error:
                    if (message.Error?.Id != null && _pending.TryRemove(message.Error.Id, out var failed))
                    {
                        failed.TrySetException(new RpcException(message.Error.Error.Code, message.Error.Error.Message));
                    }
                    break;
                case JsonRpcMessageType.Notification:
                    if (message.Notification != null)
                    {
                        Notify(message.Notification);
                    }
                    break;
            }
        }

        private void Notify(JsonRpcNotification notification)
        {
            var p = notification.Params ?? default;
            switch (notification.Method)
            {
                case "rois.event.notify":
                    var evt = new EventNotification
                    {
                        EventId = Json.String(p, "event_id"),
                        SubscribeId = Json.String(p, "subscribe_id"),
                        ComponentRef = Json.String(p, "component_ref"),
                        EventType = Json.String(p, "event_type"),
                        Results = Json.Values(p, "results"),
                    };
                    Marshal(() => EventReceived?.Invoke(evt));
                    break;
                case "rois.command.completed":
                    var done = new CommandCompletion
                    {
                        CommandId = Json.String(p, "command_id"),
                        Status = Json.String(p, "status"),
                        Results = Json.Values(p, "results"),
                    };
                    Marshal(() => CommandCompleted?.Invoke(done));
                    break;
                case "rois.system.notify_error":
                    var error = new ErrorNotification
                    {
                        ErrorId = Json.String(p, "error_id"),
                        ErrorType = Json.String(p, "error_type"),
                        CommandId = Json.String(p, "command_id"),
                        Message = Json.String(p, "message"),
                    };
                    Marshal(() => ErrorNotified?.Invoke(error));
                    break;
                case "rois.system.profile_changed":
                    Marshal(() => ProfileChanged?.Invoke());
                    break;
                case "rois.stream.notify_status":
                    var stream = new StreamStatusNotification
                    {
                        StreamId = Json.String(p, "stream_id"),
                        Status = Json.String(p, "status"),
                        ComponentRef = Json.String(p, "component_ref"),
                        Timestamp = Json.String(p, "timestamp"),
                    };
                    Marshal(() => StreamStatusChanged?.Invoke(stream));
                    break;
            }
        }

        private void Marshal(Action callback)
        {
            var context = _options.CallbackContext;
            if (context == null)
            {
                callback();
            }
            else
            {
                context.Post(_ => callback(), null);
            }
        }

        private void FailPending(Exception exception)
        {
            foreach (var entry in _pending)
            {
                if (_pending.TryRemove(entry.Key, out var tcs))
                {
                    tcs.TrySetException(exception);
                }
            }
        }

        public void Dispose()
        {
            if (_disposed)
            {
                return;
            }
            _disposed = true;
            _closing.Cancel();
            _socket.Dispose();
            _closing.Dispose();
            _sendLock.Dispose();
        }
    }
}
