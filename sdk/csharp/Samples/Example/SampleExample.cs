// A Unity sample: connect to an OpenRoIS gateway, list the components, subscribe
// to one event, and drive one command. Attach it to a GameObject and set the
// gateway URL in the inspector. Callbacks arrive on the main thread, so they may
// touch scene objects directly.

#nullable enable

using System.Threading.Tasks;
using OpenRoIS.Sdk;
using UnityEngine;

namespace OpenRoIS.Sdk.Samples
{
    public sealed class RoISClientExample : MonoBehaviour
    {
        [Tooltip("WebSocket URL of the gateway, for example ws://localhost:8765")]
        public string gatewayUrl = "ws://localhost:8765";

        [Tooltip("Bearer token, only when the gateway authenticates")]
        public string token = "";

        private RoISClient? _client;

        private async void Start()
        {
            try
            {
                await RunAsync();
            }
            catch (RoISException exception)
            {
                Debug.LogError($"RoIS {exception.Method} answered {exception.ReturnCode}");
            }
            catch (System.Exception exception)
            {
                Debug.LogError(exception);
            }
        }

        private async Task RunAsync()
        {
            var options = new ClientOptions { Token = string.IsNullOrEmpty(token) ? null : token };
            _client = await RoISClient.ConnectAsync(gatewayUrl, options);

            var refs = await _client.SearchAsync();
            Debug.Log($"Components: {string.Join(", ", refs)}");

            var navigation = refs.Find(r => r.Contains("Navigation"));
            if (navigation == null)
            {
                Debug.Log("No Navigation component on this gateway");
                return;
            }

            _client.EventReceived += e =>
                Debug.Log($"Event {e.EventType} from {e.ComponentRef}: {e.Results.Count} results");
            _client.CommandCompleted += c => Debug.Log($"Command {c.CommandId} completed: {c.Status}");
            await _client.SubscribeAsync(navigation, "reached_target");

            await _client.BindAsync(navigation);
            await _client.SetParameterAsync(navigation, new[]
            {
                new RoISValue("target_positions", "string[]", "[\"kitchen\"]"),
            });
            var executed = await _client.ExecuteAsync(navigation);
            Debug.Log($"Started command {executed.CommandId}");
        }

        private async void OnDestroy()
        {
            if (_client != null)
            {
                await _client.DisconnectAsync();
                _client.Dispose();
            }
        }
    }
}
