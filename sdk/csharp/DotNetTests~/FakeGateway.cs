// A minimal in-process gateway for the client tests: one WebSocket endpoint that
// answers the RoIS methods with canned results and pushes notifications on demand.

#nullable enable

using System;
using System.Collections.Generic;
using System.Net;
using System.Net.WebSockets;
using System.Text;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;

namespace OpenRoIS.Sdk.Tests
{
    public sealed class FakeGateway : IDisposable
    {
        private readonly HttpListener _listener = new HttpListener();
        private readonly CancellationTokenSource _stop = new CancellationTokenSource();
        private WebSocket? _socket;
        private readonly TaskCompletionSource<bool> _connected = new TaskCompletionSource<bool>();

        public int Port { get; }
        public string Url => $"ws://127.0.0.1:{Port}/";
        public List<string> Methods { get; } = new List<string>();
        public string? LastAuthorization { get; private set; }

        public FakeGateway()
        {
            Port = FreePort();
            _listener.Prefixes.Add($"http://127.0.0.1:{Port}/");
            _listener.Start();
            _ = Task.Run(AcceptAsync);
        }

        private static int FreePort()
        {
            var socket = new System.Net.Sockets.TcpListener(IPAddress.Loopback, 0);
            socket.Start();
            var port = ((IPEndPoint)socket.LocalEndpoint).Port;
            socket.Stop();
            return port;
        }

        private async Task AcceptAsync()
        {
            try
            {
                var context = await _listener.GetContextAsync();
                LastAuthorization = context.Request.Headers["Authorization"];
                if (!context.Request.IsWebSocketRequest)
                {
                    context.Response.StatusCode = 400;
                    context.Response.Close();
                    return;
                }
                var ws = await context.AcceptWebSocketAsync(null);
                _socket = ws.WebSocket;
                _connected.TrySetResult(true);
                await ServeAsync(_socket);
            }
            catch (Exception)
            {
                // Listener stopped.
            }
        }

        private async Task ServeAsync(WebSocket socket)
        {
            var buffer = new byte[64 * 1024];
            while (socket.State == WebSocketState.Open && !_stop.IsCancellationRequested)
            {
                var received = await socket.ReceiveAsync(new ArraySegment<byte>(buffer), _stop.Token);
                if (received.MessageType == WebSocketMessageType.Close)
                {
                    await socket.CloseAsync(WebSocketCloseStatus.NormalClosure, "bye", CancellationToken.None);
                    return;
                }
                var request = JsonDocument.Parse(Encoding.UTF8.GetString(buffer, 0, received.Count)).RootElement;
                var method = request.GetProperty("method").GetString() ?? "";
                var id = request.GetProperty("id");
                Methods.Add(method);
                var result = Answer(method, request.TryGetProperty("params", out var p) ? p : default);
                await SendAsync(socket, new { jsonrpc = "2.0", id, result });
            }
        }

        private static object Answer(string method, JsonElement p)
        {
            switch (method)
            {
                case "rois.system.get_profile":
                    return new
                    {
                        return_code = "OK",
                        profile = new
                        {
                            identifier = new { authority = "OpenRoIS", code = "fake", codebook_ref = "", version = "" },
                            component_ids = new[] { "robot_1/Navigation" },
                            component_profiles = new[] { new { identifier = new { authority = "", code = "Navigation", codebook_ref = "", version = "" }, name = "Navigation" } },
                        },
                    };
                case "rois.command.search":
                    return new { return_code = "OK", component_ref_list = new[] { "robot_1/Navigation", "robot_1/SystemInformation" } };
                case "rois.command.bind_any":
                    return new { return_code = "OK", component_ref = "robot_1/Navigation" };
                case "rois.command.execute":
                    return new
                    {
                        return_code = p.GetProperty("component_ref").GetString() == "robot_1/Navigation" ? "OK" : "UNSUPPORTED",
                        command_id = "cmd-1",
                        results = Array.Empty<object>(),
                    };
                case "rois.command.get_parameter":
                case "rois.command.get_command_result":
                case "rois.query.query":
                    return new
                    {
                        return_code = "OK",
                        results = new[] { new { name = "x", data_type_ref = "float", value = "1.5" }, new { name = "y", data_type_ref = "float", value = "2.0" } },
                    };
                case "rois.event.subscribe":
                    return new { return_code = "OK", subscribe_id = "sub-1" };
                case "rois.stream.connect_stream":
                    return new { return_code = "OK", stream_id = "v1", results = new[] { new { name = "media_url", data_type_ref = "string", value = "http://cam/whep/v1" } } };
                case "rois.stream.query_stream_status":
                    return new { return_code = "OK", status = "STREAMING_RUNNING" };
                case "rois.command.bind":
                    return new { return_code = p.GetProperty("component_ref").GetString() == "robot_1/Navigation" ? "OK" : "OUT_OF_RESOURCES" };
                default:
                    return new { return_code = "OK" };
            }
        }

        public async Task PushAsync(object notification)
        {
            await _connected.Task;
            await SendAsync(_socket!, notification);
        }

        private static async Task SendAsync(WebSocket socket, object payload)
        {
            var bytes = JsonSerializer.SerializeToUtf8Bytes(payload);
            await socket.SendAsync(new ArraySegment<byte>(bytes), WebSocketMessageType.Text, true, CancellationToken.None);
        }

        public void Dispose()
        {
            _stop.Cancel();
            try { _listener.Stop(); } catch (Exception) { }
            _listener.Close();
        }
    }
}
