#nullable enable
using System;
using System.Collections.Generic;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using OpenRoIS.Interfaces.Catalog;
using OpenRoIS.Interfaces.Hri;
using OpenRoIS.Interfaces.Profiles;
using OpenRoIS.Sdk.JsonRpc;
using OpenRoIS.Sdk.Transport;

namespace OpenRoIS.Sdk
{

  /// <summary>
  /// The <c>rois.system.get_profile</c> result of an engine that answered OK.
  /// </summary>
  public sealed class EngineProfile
  {
    /// <summary>
    /// The engine profile, as HRIEngineProfileType in XML-Profiles.xsd defines it.
    /// </summary>
    public HRIEngineProfileType Profile { get; }

    /// <summary>
    /// The profile of every component in the engine profile, keyed by fully
    /// qualified ref. An OpenRoIS extension (docs/rois-reference.md section 17.3).
    /// </summary>
    public IReadOnlyDictionary<string, HRIComponentProfile> ComponentProfiles { get; }

    internal EngineProfile(
        HRIEngineProfileType profile,
        IReadOnlyDictionary<string, HRIComponentProfile> componentProfiles)
    {
      Profile = profile;
      ComponentProfiles = componentProfiles;
    }
  }

  /// <summary>
  /// A connection to an OpenRoIS engine, with one method per RoIS operation.
  /// </summary>
  /// <remarks>
  /// <para>
  /// Create it with <see cref="ConnectAsync"/>. One client is one session:
  /// bindings and subscriptions end with it, and nothing reconnects by itself.
  /// </para>
  /// <para>
  /// Each method is named after the IDL operation, takes its <c>in</c>
  /// parameters in IDL order, and takes an optional
  /// <see cref="CancellationToken"/> last, which stops waiting for the reply.
  /// Every call reads its result through the generated models with
  /// <see cref="RoISJson.Options"/>, and turns a return code other than OK
  /// into a <see cref="RoISException"/>. A streaming component is driven with
  /// these same methods. Carrying its media is planned.
  /// </para>
  /// <para>
  /// Params are not validated here, because the generated classes do not
  /// describe their constraints: an invalid value comes back from the engine
  /// as an <see cref="RpcException"/>. It never reaches a component.
  /// </para>
  /// <para>Listen with <c>On</c> and <c>Off</c>:</para>
  /// <list type="table">
  /// <item><term>rois.event.notify_event</term><description><c>NotifyEventParams</c>, for every event of a subscription.</description></item>
  /// <item><term>rois.command.completed</term><description><c>CompletedParams</c>, when a command ends.</description></item>
  /// <item><term>rois.system.notify_error</term><description><c>NotifyErrorParams</c>, when the engine reports an error.</description></item>
  /// <item><term>rois.system.profile_changed</term><description><c>ProfileChangedParams</c>, when components join or leave.</description></item>
  /// <item><term>close</term><description>(int code, string reason), when the connection closes.</description></item>
  /// <item><term>error</term><description><see cref="Exception"/>, for a message that cannot be used or a listener that throws. With no listener it is logged.</description></item>
  /// </list>
  /// <para>
  /// Listeners run in the <see cref="SynchronizationContext"/> that was
  /// current at <see cref="ConnectAsync"/>, which on the main thread of Unity
  /// is the main thread, so they can call Unity APIs. With no context they
  /// run on the reader of the socket, so they must not block.
  /// </para>
  /// <code>
  /// await using var client = await RoISClient.ConnectAsync("ws://127.0.0.1:8765");
  /// const string nav = "robot_1/navigation";
  /// var status = await client.QueryAsync("component_status", Condition.ComponentRef(nav));
  ///
  /// // Listen before the call, because a command can end before the reply is read.
  /// var ended = new Dictionary&lt;string, CompletedStatus&gt;();
  /// client.On(RoISNotifications.Completed, (CompletedParams p) =&gt; ended[p.CommandId] = p.Status);
  ///
  /// await client.BindAsync(nav);
  /// var ids = await client.ExecuteAsync(new[] { new CommandUnit(nav, RoISCommandTypes.Start) });
  /// // Later: ended[ids[0]] is OK once the navigation has ended.
  /// await client.ReleaseAsync(nav);
  /// </code>
  /// <para>Wire binding: docs/rois-reference.md section 17.</para>
  /// </remarks>
  public sealed class RoISClient : IAsyncDisposable
  {
    private static readonly IReadOnlyDictionary<string, Type> s_payloads = Payloads();
    private static readonly JsonElement s_noParams = NoParams();

    private readonly Emitter _emitter = new Emitter(s_payloads);
    private readonly WebSocketTransport _wire;
    private readonly object _gate = new object();
    private volatile bool _connected;
    private Task? _ending;

    private RoISClient(WebSocketTransport wire, SynchronizationContext? context)
    {
      _wire = wire;
      _emitter.Context = context;
      wire.Observe(EventNames.Notification, OnNotification);
      wire.Observe(EventNames.Close, OnClose);
      wire.Observe(EventNames.Error, OnError);
    }

    /// <summary>
    /// The transport under the client, for JSON-RPC methods outside the
    /// catalog. The client does not validate what is sent through it.
    /// </summary>
    public WebSocketTransport Transport => _wire;

    /// <summary>
    /// Add a listener of a catalog notification, which takes its params, or
    /// of <c>error</c>, which takes an <see cref="Exception"/>. It stays
    /// until <c>Off</c> removes it.
    /// </summary>
    /// <exception cref="ArgumentException">No event has this name and this
    /// payload type.</exception>
    public RoISClient On<T>(string name, Action<T> listener)
    {
      _emitter.Add(name, listener);
      return this;
    }

    /// <summary>Add a listener of <c>close</c>. It stays until <c>Off</c> removes it.</summary>
    public RoISClient On(string name, Action<int, string> listener)
    {
      _emitter.Add(name, listener);
      return this;
    }

    /// <summary>Remove a listener added with <c>On</c>.</summary>
    public RoISClient Off<T>(string name, Action<T> listener)
    {
      _emitter.Remove(name, listener);
      return this;
    }

    /// <summary>Remove a listener of <c>close</c>.</summary>
    public RoISClient Off(string name, Action<int, string> listener)
    {
      _emitter.Remove(name, listener);
      return this;
    }

    // -----------------------------------------------------------------------
    // SystemIF
    // -----------------------------------------------------------------------

    /// <summary>
    /// Open a connection to an engine and run <c>rois.system.connect</c>.
    /// </summary>
    /// <remarks>
    /// Captures <see cref="SynchronizationContext.Current"/>, where listeners
    /// run from then on. In the Editor the client ends with Play Mode, and
    /// this fails while Play Mode is ending.
    /// </remarks>
    /// <param name="url">The engine's WebSocket URL, for example
    /// <c>ws://127.0.0.1:8765</c>.</param>
    /// <param name="requestTimeout">How long a request waits for its reply,
    /// by default 30 seconds.</param>
    /// <param name="connectTimeout">How long the WebSocket has to open, by
    /// default 10 seconds.</param>
    /// <param name="cancellationToken">Ends the attempt.</param>
    /// <exception cref="RoISConnectionException">The WebSocket cannot be
    /// opened, or Play Mode is ending.</exception>
    /// <exception cref="RoISException">The engine answers with a code other than OK.</exception>
    public static async Task<RoISClient> ConnectAsync(
        string url,
        TimeSpan? requestTimeout = null,
        TimeSpan? connectTimeout = null,
        CancellationToken cancellationToken = default)
    {
      var wire = new WebSocketTransport(requestTimeout, connectTimeout);
      var client = new RoISClient(wire, SynchronizationContext.Current);
      if (!LiveClients.TryAdd(client))
      {
        throw new RoISConnectionException("Cannot connect: Play Mode is ending", url);
      }
      try
      {
        await wire.ConnectAsync(url, cancellationToken).ConfigureAwait(false);
        await client.RequestAsync(
            RoISMethods.Connect,
            new ConnectParams(),
            (ConnectResult result) => result.ReturnCode,
            cancellationToken).ConfigureAwait(false);
      }
      catch (Exception)
      {
        // Started and not awaited, because a peer that stopped answering
        // would hold the caller for the whole closing handshake.
        wire.StartClose();

        // A closing connection stays listed until its close event, so that
        // Play Mode cannot end while a silent peer holds it open.
        if (wire.State == TransportState.Disconnected)
        {
          LiveClients.Remove(client);
        }
        throw;
      }
      client.Started();
      return client;
    }

    /// <summary>
    /// Run <c>rois.system.disconnect</c> and close the connection.
    /// </summary>
    /// <remarks>
    /// The connection closes even when the engine answers with an error. Safe
    /// to call more than once. Calls that overlap send one
    /// <c>rois.system.disconnect</c> and share its outcome.
    /// </remarks>
    /// <param name="cancellationToken">Stops waiting, and the session ends
    /// without this caller.</param>
    public Task DisconnectAsync(CancellationToken cancellationToken = default)
    {
      Task ending;
      lock (_gate)
      {
        if (_ending == null || _ending.IsCompleted)
        {
          _ending = EndSessionAsync();

          // Every caller can give up, and the outcome has nowhere to go then.
          _ending.Forget();
        }
        ending = _ending;
      }
      return ending.WaitOrCancel(cancellationToken);
    }

    /// <summary>Run <see cref="DisconnectAsync"/> when an <c>await using</c> block ends.</summary>
    public async ValueTask DisposeAsync()
    {
      await DisconnectAsync().ConfigureAwait(false);
    }

    /// <summary>Read the engine profile and the profiles of its components.</summary>
    /// <param name="condition">Selects the components the profile lists.
    /// Empty lists all.</param>
    /// <param name="cancellationToken">Stops waiting for the reply.</param>
    public async Task<EngineProfile> GetProfileAsync(
        string condition = "", CancellationToken cancellationToken = default)
    {
      var result = await CallAsync(
          RoISMethods.GetProfile,
          new GetProfileParams(condition),
          (GetProfileResult reply) => reply.ReturnCode,
          cancellationToken).ConfigureAwait(false);
      if (result.Profile is null)
      {
        throw new TransportException("rois.system.get_profile returned OK without a profile");
      }
      return new EngineProfile(
          result.Profile,
          result.ComponentProfiles ?? new Dictionary<string, HRIComponentProfile>());
    }

    /// <summary>
    /// Read the details of an error from a <c>rois.system.notify_error</c> notification.
    /// </summary>
    /// <param name="errorId">The <c>error_id</c> of the notification.</param>
    /// <param name="condition">Filter on the results. Must be empty for now.</param>
    /// <param name="cancellationToken">Stops waiting for the reply.</param>
    public async Task<IReadOnlyList<Result>> GetErrorDetailAsync(
        string errorId, string condition = "", CancellationToken cancellationToken = default)
    {
      var result = await CallAsync(
          RoISMethods.GetErrorDetail,
          new GetErrorDetailParams(errorId, condition),
          (GetErrorDetailResult reply) => reply.ReturnCode,
          cancellationToken).ConfigureAwait(false);
      return result.Results ?? Array.Empty<Result>();
    }

    // -----------------------------------------------------------------------
    // CommandIF
    // -----------------------------------------------------------------------

    /// <summary>Find components.</summary>
    /// <param name="condition">Selects the components. Empty matches every
    /// component.</param>
    /// <param name="cancellationToken">Stops waiting for the reply.</param>
    /// <returns>Their fully qualified refs.</returns>
    public async Task<IReadOnlyList<string>> SearchAsync(
        string condition = "", CancellationToken cancellationToken = default)
    {
      var result = await CallAsync(
          RoISMethods.Search,
          new SearchParams(condition),
          (SearchResult reply) => reply.ReturnCode,
          cancellationToken).ConfigureAwait(false);
      return result.ComponentRefList ?? Array.Empty<string>();
    }

    /// <summary>Reserve a component for this client.</summary>
    public Task BindAsync(string componentRef, CancellationToken cancellationToken = default)
    {
      return CallAsync(
          RoISMethods.Bind,
          new BindParams(componentRef),
          (BindResult reply) => reply.ReturnCode,
          cancellationToken);
    }

    /// <summary>
    /// Reserve one of the components a condition selects, chosen by the engine.
    /// </summary>
    /// <returns>The ref of the reserved component.</returns>
    public async Task<string> BindAnyAsync(
        string condition = "", CancellationToken cancellationToken = default)
    {
      var result = await CallAsync(
          RoISMethods.BindAny,
          new BindAnyParams(condition),
          (BindAnyResult reply) => reply.ReturnCode,
          cancellationToken).ConfigureAwait(false);
      return result.ComponentRef;
    }

    /// <summary>
    /// Release a component reserved with <see cref="BindAsync"/> or <see cref="BindAnyAsync"/>.
    /// </summary>
    public Task ReleaseAsync(string componentRef, CancellationToken cancellationToken = default)
    {
      return CallAsync(
          RoISMethods.Release,
          new ReleaseParams(componentRef),
          (ReleaseResult reply) => reply.ReturnCode,
          cancellationToken);
    }

    /// <summary>Read the current value of every parameter of a component.</summary>
    public async Task<IReadOnlyList<Parameter>> GetParameterAsync(
        string componentRef, CancellationToken cancellationToken = default)
    {
      var result = await CallAsync(
          RoISMethods.GetParameter,
          new GetParameterParams(componentRef),
          (GetParameterResult reply) => reply.ReturnCode,
          cancellationToken).ConfigureAwait(false);
      return result.Parameters ?? Array.Empty<Parameter>();
    }

    /// <summary>Set parameters of a component.</summary>
    /// <returns>The command id the engine assigned to the change. Its
    /// <c>rois.command.completed</c> notification reports when the change
    /// took effect.</returns>
    public async Task<string> SetParameterAsync(
        string componentRef,
        IReadOnlyList<Parameter> parameters,
        CancellationToken cancellationToken = default)
    {
      var result = await CallAsync(
          RoISMethods.SetParameter,
          new SetParameterParams(componentRef, parameters),
          (SetParameterResult reply) => reply.ReturnCode,
          cancellationToken).ConfigureAwait(false);
      return result.CommandId;
    }

    /// <summary>Run commands in order.</summary>
    /// <remarks>
    /// A <see cref="ConcurrentCommands"/> item runs its branches at the same
    /// time, and each branch runs its commands in order. The engine answers
    /// as soon as it accepts the commands, with the command id it assigned to
    /// each one. Each command then ends with a <c>rois.command.completed</c>
    /// notification carrying that id, and <see cref="GetCommandResultAsync"/>
    /// reads its results.
    /// </remarks>
    /// <param name="commandUnitList">The commands, without command ids.</param>
    /// <param name="cancellationToken">Stops waiting for the reply.</param>
    /// <returns>The command id the engine assigned to every command, in the
    /// order the list gives them, with the commands of a
    /// <see cref="ConcurrentCommands"/> item branch by branch.</returns>
    public async Task<IReadOnlyList<string>> ExecuteAsync(
        IReadOnlyList<ICommandUnitSequenceItem> commandUnitList,
        CancellationToken cancellationToken = default)
    {
      var result = await CallAsync(
          RoISMethods.Execute,
          new ExecuteParams(commandUnitList),
          (ExecuteResult reply) => reply.ReturnCode,
          cancellationToken).ConfigureAwait(false);

      var ids = new List<string>();
      foreach (var item in result.CommandUnitList ?? Array.Empty<ICommandUnitSequenceItem>())
      {
        if (item is ConcurrentCommands concurrent)
        {
          foreach (var branch in concurrent.BranchList)
          {
            foreach (var unit in branch.CommandList)
            {
              ids.Add(unit.CommandId);
            }
          }
        }
        else if (item is CommandUnit unit)
        {
          ids.Add(unit.CommandId);
        }
      }
      return ids;
    }

    /// <summary>Read the results of a command.</summary>
    /// <param name="commandId">The command, by the id <see cref="ExecuteAsync"/>
    /// returned.</param>
    /// <param name="condition">Filter on the results. Must be empty for now.</param>
    /// <param name="cancellationToken">Stops waiting for the reply.</param>
    public async Task<IReadOnlyList<Result>> GetCommandResultAsync(
        string commandId, string condition = "", CancellationToken cancellationToken = default)
    {
      var result = await CallAsync(
          RoISMethods.GetCommandResult,
          new GetCommandResultParams(commandId, condition),
          (GetCommandResultResult reply) => reply.ReturnCode,
          cancellationToken).ConfigureAwait(false);
      return result.Results ?? Array.Empty<Result>();
    }

    // -----------------------------------------------------------------------
    // QueryIF
    // -----------------------------------------------------------------------

    /// <summary>Run a query and wait for its results.</summary>
    /// <remarks>
    /// The engine sends the query to the one component that declares
    /// <paramref name="queryType"/> and matches the condition. It returns
    /// UNSUPPORTED when none does, and BAD_PARAMETER when several do.
    /// </remarks>
    /// <param name="queryType">The query name from a component profile, for
    /// example <c>component_status</c>.</param>
    /// <param name="condition">Selects the component, for example the
    /// result of <c>Condition.ComponentRef("reachy_real/head")</c>.</param>
    /// <param name="cancellationToken">Stops waiting for the reply.</param>
    public async Task<IReadOnlyList<Result>> QueryAsync(
        string queryType, string condition = "", CancellationToken cancellationToken = default)
    {
      var result = await CallAsync(
          RoISMethods.Query,
          new QueryParams(queryType, condition),
          (QueryResult reply) => reply.ReturnCode,
          cancellationToken).ConfigureAwait(false);
      return result.Results ?? Array.Empty<Result>();
    }

    // -----------------------------------------------------------------------
    // EventIF
    // -----------------------------------------------------------------------

    /// <summary>Subscribe to an event.</summary>
    /// <remarks>
    /// Its occurrences arrive as <c>rois.event.notify_event</c> notifications,
    /// which carry the id this returns. The engine subscribes to the one
    /// component that declares <paramref name="eventType"/> and matches the
    /// condition, with the same rules as <see cref="QueryAsync"/>.
    /// </remarks>
    /// <returns>The subscribe id, for <see cref="UnsubscribeAsync"/>.</returns>
    public async Task<string> SubscribeAsync(
        string eventType, string condition = "", CancellationToken cancellationToken = default)
    {
      var result = await CallAsync(
          RoISMethods.Subscribe,
          new SubscribeParams(eventType, condition),
          (SubscribeResult reply) => reply.ReturnCode,
          cancellationToken).ConfigureAwait(false);
      return result.SubscribeId;
    }

    /// <summary>
    /// Cancel a subscription. The engine ignores an id it does not know, as RoIS requires.
    /// </summary>
    public Task UnsubscribeAsync(string subscribeId, CancellationToken cancellationToken = default)
    {
      return CallAsync(
          RoISMethods.Unsubscribe,
          new UnsubscribeParams(subscribeId),
          (UnsubscribeResult reply) => reply.ReturnCode,
          cancellationToken);
    }

    /// <summary>Read the payload of an event until it expires.</summary>
    /// <param name="eventId">The <c>event_id</c> of the notification.</param>
    /// <param name="condition">Filter on the results. Must be empty for now.</param>
    /// <param name="cancellationToken">Stops waiting for the reply.</param>
    public async Task<IReadOnlyList<Result>> GetEventDetailAsync(
        string eventId, string condition = "", CancellationToken cancellationToken = default)
    {
      var result = await CallAsync(
          RoISMethods.GetEventDetail,
          new GetEventDetailParams(eventId, condition),
          (GetEventDetailResult reply) => reply.ReturnCode,
          cancellationToken).ConfigureAwait(false);
      return result.Results ?? Array.Empty<Result>();
    }

    // -----------------------------------------------------------------------
    // Internal
    // -----------------------------------------------------------------------

    /// <summary>End the session now, whatever state it is in.</summary>
    internal void Abort()
    {
      _wire.Abort();
    }

    // -----------------------------------------------------------------------
    // Private: calls
    // -----------------------------------------------------------------------

    private static JsonElement NoParams()
    {
      using var document = JsonDocument.Parse("{}");
      return document.RootElement.Clone();
    }

    private static IReadOnlyDictionary<string, Type> Payloads()
    {
      var payloads = new Dictionary<string, Type>
      {
        [EventNames.Close] = typeof(CloseReport),
        [EventNames.Error] = typeof(Exception),
      };
      foreach (var notification in RoISNotificationTypes.ByMethod)
      {
        payloads[notification.Key] = notification.Value;
      }
      return payloads;
    }

    /// <summary>
    /// Mark the session as running, unless its connection has ended since
    /// the reply arrived, in which case the client must not look connected.
    /// </summary>
    internal void Started()
    {
      lock (_gate)
      {
        _connected = _wire.State == TransportState.Connected;
      }
    }

    /// <summary>The work of <see cref="DisconnectAsync"/>, once for all the calls that overlap.</summary>
    private async Task EndSessionAsync()
    {
      if (!_connected)
      {
        return;
      }
      try
      {
        await CallAsync(
            RoISMethods.Disconnect,
            new DisconnectParams(),
            (DisconnectResult reply) => reply.ReturnCode,
            CancellationToken.None).ConfigureAwait(false);
      }
      finally
      {
        _connected = false;

        // The default code and reason cannot be refused, so this cannot hide
        // the outcome of the call above. A close frame that cannot be sent
        // reaches the error listeners.
        await _wire.CloseAsync().ConfigureAwait(false);
      }
    }

    /// <summary>Run a catalog method on a connected client.</summary>
    private async Task<TResult> CallAsync<TResult>(
        string method,
        object parameters,
        Func<TResult, ReturnCode> returnCode,
        CancellationToken cancellationToken)
        where TResult : class
    {
      if (!_connected)
      {
        throw new TransportException($"Cannot call {method}: client is not connected");
      }
      return await RequestAsync(method, parameters, returnCode, cancellationToken)
          .ConfigureAwait(false);
    }

    /// <summary>
    /// Send a request, read its result through the generated model, and
    /// check its return code.
    /// </summary>
    /// <remarks>
    /// The model is read off the main thread, because a large profile would
    /// otherwise cost a frame.
    /// </remarks>
    private async Task<TResult> RequestAsync<TResult>(
        string method,
        object parameters,
        Func<TResult, ReturnCode> returnCode,
        CancellationToken cancellationToken)
        where TResult : class
    {
      var raw = await _wire.SendAsync(method, parameters, cancellationToken).ConfigureAwait(false);
      TResult? result;
      try
      {
        result = raw.Deserialize<TResult>(RoISJson.Options);
      }
      catch (JsonException error)
      {
        throw new TransportException($"Invalid result of {method}: {error.Message}", error);
      }
      if (result == null)
      {
        throw new TransportException($"Invalid result of {method}: null");
      }

      var code = returnCode(result);
      if (code != ReturnCode.OK)
      {
        throw new RoISException(code, method);
      }
      return result;
    }

    // -----------------------------------------------------------------------
    // Private: what the transport receives
    // -----------------------------------------------------------------------

    /// <summary>
    /// Read a catalog notification and emit its params. Methods outside the
    /// catalog stay on the notification event of the transport.
    /// </summary>
    private void OnNotification(object? payload)
    {
      var notification = (JsonRpcNotification)payload!;
      var method = notification.Method;
      if (!RoISNotificationTypes.ByMethod.TryGetValue(method, out var type))
      {
        return;
      }

      object? parsed;
      try
      {
        parsed = (notification.Params ?? s_noParams).Deserialize(type, RoISJson.Options);
      }
      catch (JsonException error)
      {
        _emitter.Emit(EventNames.Error, new TransportException(
            $"Invalid params in {method} notification: {error.Message}", error));
        return;
      }
      _emitter.Emit(method, parsed);
    }

    private void OnClose(object? payload)
    {
      lock (_gate)
      {
        _connected = false;
      }
      LiveClients.Remove(this);
      _emitter.Emit(EventNames.Close, payload);
    }

    private void OnError(object? payload)
    {
      _emitter.Emit(EventNames.Error, payload);
    }
  }

}  // namespace OpenRoIS.Sdk
