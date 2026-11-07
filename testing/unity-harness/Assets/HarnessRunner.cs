#nullable enable
using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Net.WebSockets;
using System.Numerics;
using System.Reflection;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Text.Json.Serialization;
using System.Text.RegularExpressions;
using System.Threading;
using System.Threading.Tasks;
using OpenRoIS.Interfaces;
using OpenRoIS.Interfaces.Catalog;
using OpenRoIS.Interfaces.Common;
using OpenRoIS.Interfaces.Hri;
using OpenRoIS.Interfaces.Profiles;
using OpenRoIS.Interfaces.Service;
using UnityEngine;
using UnityEngine.Networking;

namespace OpenRoIS.Harness
{
  /// <summary>
  /// Runs the shared fixtures, a live session and the conformance list inside a real player.
  /// </summary>
  /// <remarks>
  /// Every line this class prints starts with <c>HARNESS</c>, so a runner can pick them
  /// out of the player log, and the last one is <c>HARNESS RESULT</c>. The process exit
  /// code is 0 only when every check passed.
  ///
  /// The harness reads its own data through <see cref="JsonNode"/> and declares no class
  /// for <see cref="JsonSerializer"/>. High stripping removes the members of such a class,
  /// because reflection is invisible to the linker, and a link.xml here to keep them
  /// could also hide a gap in the link.xml of the SDK, which is what a player has to prove.
  /// </remarks>
  public sealed partial class HarnessRunner : MonoBehaviour
  {
    private const string Prefix = "HARNESS ";
    private const string ConfigFile = "harness.json";
    private const string GatewayUrlVariable = "OPENROIS_GATEWAY_URL";
    private const string GatewayUrlField = "gateway_url";
    private const string ScriptedUrlVariable = "OPENROIS_SCRIPTED_URL";
    private const string ScriptedUrlField = "scripted_url";
    private const string Language = "csharp";
    private const string Navigation = "mock/navigation";
    private const int RunLimitSeconds = 300;
    private const int SessionLimitSeconds = 60;
    private const int AdapterJoinAttempts = 50;
    private const int AdapterJoinDelayMilliseconds = 200;

    private readonly Dictionary<string, CompletedParams> _completed = new Dictionary<string, CompletedParams>();

    private int _mainThread;
    private int _passed;
    private int _failed;
    private int _nextId;
    private float _deadline;
    private volatile bool _done;
    private bool _quitting;
    private ClientWebSocket? _socket;
    private CancellationToken _cancel;

    /// <summary>Starts the harness with no scene object, so the scene can stay empty.</summary>
    /// <remarks>
    /// The Editor run has its own driver, and this would end its Play Mode with a quit.
    /// </remarks>
    [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.AfterSceneLoad)]
    private static void Boot()
    {
      if (Application.isEditor)
        return;
      new GameObject("harness").AddComponent<HarnessRunner>();
    }

    private async void Start()
    {
      Application.SetStackTraceLogType(LogType.Log, StackTraceLogType.None);
      _deadline = Time.realtimeSinceStartup + RunLimitSeconds;
      _mainThread = Thread.CurrentThread.ManagedThreadId;
      try
      {
        await Run();
      }
      catch (Exception e)
      {
        Fail("run", Describe(e));
      }
      _done = true;
    }

    /// <summary>
    /// Ends the run from the player loop and not from <see cref="Start"/>. An await that
    /// never returns, or one that lands on a worker thread, must still end the process.
    /// </summary>
    private void Update()
    {
      if (_quitting)
        return;
      if (!_done && Time.realtimeSinceStartup < _deadline)
        return;
      if (!_done)
        Fail("watchdog", $"not finished after {RunLimitSeconds} seconds");
      _quitting = true;
      var ok = _failed == 0;
      Say($"RESULT {(ok ? "OK" : "FAILED")} passed={_passed} failed={_failed}");
      Application.Quit(ok ? 0 : 1);
    }

    private async Task Run()
    {
      ReportEnvironment();
      await CheckMainThreadControls();
      try
      {
        await RunFixtures();
      }
      catch (Exception e)
      {
        Fail("fixtures", Describe(e));
      }
      try
      {
        await RunSession(await OnMain(ReadUrl(GatewayUrlVariable, GatewayUrlField), "read gateway url"));
      }
      catch (Exception e)
      {
        Fail("session", Describe(e));
      }
      try
      {
        await RunConformance(
            await OnMain(ReadUrl(GatewayUrlVariable, GatewayUrlField), "read gateway url"),
            await OnMain(ReadUrl(ScriptedUrlVariable, ScriptedUrlField), "read scripted url"));
      }
      catch (Exception e)
      {
        Fail("conformance", Describe(e));
      }
    }

    private void ReportEnvironment()
    {
#if ENABLE_IL2CPP
      const string backend = "il2cpp";
#else
      const string backend = "mono";
#endif
      var json = typeof(JsonSerializer).Assembly;
      var version = json.GetCustomAttribute<AssemblyInformationalVersionAttribute>()?.InformationalVersion;
      Say($"INFO platform={Application.platform} unity={Application.unityVersion} backend={backend}"
          + $" system_text_json={json.GetName().Version} ({version})");
    }

    /// <summary>
    /// Proves the main thread check can fail. A comparison that is always true would
    /// otherwise look the same as every await resuming where it should.
    /// </summary>
    private async Task CheckMainThreadControls()
    {
      Check("main-thread context", () =>
      {
        var name = SynchronizationContext.Current?.GetType().Name;
        Require(name == "UnitySynchronizationContext", $"context is {name ?? "null"}");
        return name!;
      });
      var worker = await OnMain(Task.Run(() => Thread.CurrentThread.ManagedThreadId), "Task.Run");
      Check("main-thread control", () =>
      {
        Require(worker != _mainThread, "a worker thread reports the id of the main thread");
        return $"main {_mainThread}, worker {worker}";
      });
    }

    // Fixtures

    private async Task RunFixtures()
    {
      var wire = (await OnMain(ReadStreamingAsset("wire.json"), "read wire.json")).AsArray();
      var conditions = (await OnMain(ReadStreamingAsset("conditions.json"), "read conditions.json")).AsArray();
      var values = (await OnMain(ReadStreamingAsset("values.json"), "read values.json")).AsArray();
      var edges = (await OnMain(ReadStreamingAsset("value-edges.json"), "read value-edges.json")).AsObject();

      Check("wire coverage", () => CheckWireCoverage(wire));
      foreach (var entry in wire)
      {
        var kind = (string)entry!["kind"]!;
        var method = (string)entry["method"]!;
        var body = entry["body"]!.AsObject();
        var name = $"{kind} {method}";
        Check("wire " + name, () => CheckRoundTrip(body, ModelType(kind, method)));
        Check("refuse-missing " + name, () => CheckRefusesMissing(body, ModelType(kind, method)));
        Check("refuse-unknown " + name, () => CheckRefusesUnknown(body, ModelType(kind, method)));
      }

      foreach (var vector in conditions)
      {
        var builder = (string)vector!["builder"]!;
        var expected = (string)vector["expected"]!;
        Check($"condition {builder} {expected}", () =>
        {
          var built = BuildCondition(builder, vector["args"]!.AsArray());
          Require(built == expected, $"built {built}");
          return "";
        });
      }

      foreach (var vector in values)
      {
        var dataType = (string)vector!["data_type"]!;
        var text = (string)vector["text"]!;
        Check($"value {dataType} {text}", () =>
        {
          var encoded = RoISValues.Encode(dataType, ToValue(dataType, vector["value"]));
          Require(encoded == text, $"encoded {encoded}");
          CheckDecoded(dataType, vector["value"], RoISValues.Decode(dataType, text));
          return "";
        });
      }

      RunValueEdges(edges);
    }

    /// <summary>
    /// Runs value-edges.json. The bits and not the text hold a number in its list of doubles,
    /// so a runtime that reads text inexactly cannot hide or fake a fault in how it writes.
    /// Those doubles are exact powers of two, the largest doubles, and random doubles for
    /// which the runtime's own text and parsing gave a different result from Python on Mono
    /// and IL2CPP. A case that the file records as a difference of C# is left out.
    /// </summary>
    private void RunValueEdges(JsonObject edges)
    {
      var skipped = new HashSet<string>(edges["exceptions"]!.AsArray()
          .Where(exception => (string)exception!["language"]! == Language)
          .SelectMany(exception => exception!["cases"]!.AsArray())
          .Select(reference => EdgeKey((string)reference!["list"]!, reference)));
      List<JsonNode> Cases(string list)
      {
        return edges[list]!.AsArray().Select(entry => entry!).Where(entry => !skipped.Contains(EdgeKey(list, entry))).ToList();
      }

      foreach (var entry in Cases("refused"))
      {
        var dataType = (string)entry["data_type"]!;
        Check("edge " + EdgeKey("refused", entry), () =>
        {
          try
          {
            RoISValues.Decode(dataType, (string)entry["text"]!);
          }
          catch (FormatException)
          {
            return "";
          }
          throw new InvalidOperationException("accepted");
        });
      }

      foreach (var entry in Cases("decoded"))
      {
        var dataType = (string)entry["data_type"]!;
        Check("edge " + EdgeKey("decoded", entry), () =>
        {
          CheckDecoded(dataType, entry["value"], RoISValues.Decode(dataType, (string)entry["text"]!));
          return "";
        });
      }

      foreach (var entry in Cases("encoded"))
      {
        var dataType = (string)entry["data_type"]!;
        var text = (string)entry["text"]!;
        Check("edge " + EdgeKey("encoded", entry), () =>
        {
          var encoded = RoISValues.Encode(dataType, ReadValueText((string)entry["value_text"]!));
          Require(encoded == text, $"encoded {encoded}");
          return "";
        });
      }

      foreach (var entry in Cases("models"))
      {
        var body = entry["body"]!.AsObject();
        var type = ModelType((string)entry["kind"]!, (string)entry["method"]!);
        Check($"edge model {(string)entry["name"]!}", () =>
        {
          if ((bool)entry["refused"]!)
            RequireRefused(body, type);
          else
            Parse(body, type);
          return "";
        });
      }

      foreach (var entry in edges["doubles"]!.AsArray())
      {
        var text = (string)entry!["text"]!;
        var bits = Convert.ToInt64((string)entry["bits"]!, 16);
        Check("double encode " + text, () =>
        {
          var encoded = RoISValues.Encode("double", BitConverter.Int64BitsToDouble(bits));
          Require(encoded == text, $"encoded {encoded}");
          return "";
        });
        Check("double decode " + text, () =>
        {
          var decoded = BitConverter.DoubleToInt64Bits((double)RoISValues.Decode("double", text));
          Require(decoded == bits, $"decoded bits {decoded}, expected {bits}");
          return "";
        });
      }
    }

    /// <summary>
    /// A case in one line of text. Its JSON form keeps a control character of a text out of
    /// the log, where a line break would end the HARNESS line.
    /// </summary>
    private static string EdgeKey(string list, JsonNode entry)
    {
      var fields = new[] { "data_type", "text", "value_text", "name" };
      return list + " " + string.Join(" ", fields.Where(field => entry[field] is not null).Select(field => entry[field]!.ToJsonString()));
    }

    private static Type ModelType(string kind, string method)
    {
      switch (kind)
      {
        case "params":
          return RoISMethodTypes.ByMethod[method].Params;
        case "result":
          return RoISMethodTypes.ByMethod[method].Result;
        case "notification":
          return RoISNotificationTypes.ByMethod[method];
        default:
          throw new ArgumentException($"Unknown kind: {kind}");
      }
    }

    private static string CheckWireCoverage(JsonArray wire)
    {
      var seen = new HashSet<string>(wire.Select(entry => (string)entry!["kind"]! + " " + (string)entry["method"]!));
      var expected = new List<string>();
      foreach (var method in RoISMethodTypes.ByMethod.Keys)
      {
        expected.Add("params " + method);
        expected.Add("result " + method);
      }
      foreach (var notification in RoISNotificationTypes.ByMethod.Keys)
        expected.Add("notification " + notification);
      var missing = expected.Where(name => !seen.Contains(name)).ToArray();
      Require(missing.Length == 0, "no entry for " + string.Join(", ", missing));
      return $"{wire.Count} entries, {expected.Count} catalog messages";
    }

    private static string CheckRoundTrip(JsonObject body, Type type)
    {
      var model = Parse(body, type);
      Require(model.GetType() == type, $"parsed a {model.GetType().Name}");
      var written = JsonSerializer.Serialize(model, type, RoISJson.Options);
      Require(JsonNode.DeepEquals(WithoutNulls(body), JsonNode.Parse(written)), "wrote " + written);
      var again = JsonSerializer.Deserialize(written, type, RoISJson.Options)!;
      var rewritten = JsonSerializer.Serialize(again, type, RoISJson.Options);
      Require(rewritten == written, "rewrote " + rewritten);
      return "";
    }

    private static object Parse(JsonNode body, Type type)
    {
      return JsonSerializer.Deserialize(body.ToJsonString(), type, RoISJson.Options)!;
    }

    /// <summary>The body as it reads once RoISJson.Options has dropped its nulls.</summary>
    private static JsonNode? WithoutNulls(JsonNode? node)
    {
      switch (node)
      {
        case JsonObject map:
          var kept = new JsonObject();
          foreach (var pair in map)
          {
            if (pair.Value is not null)
              kept[pair.Key] = WithoutNulls(pair.Value);
          }
          return kept;
        case JsonArray list:
          return new JsonArray(list.Select(WithoutNulls).ToArray());
        default:
          return node?.DeepClone();
      }
    }

    private static string CheckRefusesMissing(JsonObject body, Type type)
    {
      var cases = 0;
      var models = FindModels(body, type);
      for (var position = 0; position < models.Count; position++)
      {
        var required = Properties(models[position].Model)
            .Where(property => property.GetCustomAttribute<JsonRequiredAttribute>() is not null);
        foreach (var property in required)
        {
          var copy = body.DeepClone().AsObject();
          FindModels(copy, type)[position].Json.Remove(WireName(property));
          RequireRefused(copy, type);
          cases++;
        }
      }
      return $"{cases} cases";
    }

    private static string CheckRefusesUnknown(JsonObject body, Type type)
    {
      var models = FindModels(body, type);
      for (var position = 0; position < models.Count; position++)
      {
        var copy = body.DeepClone().AsObject();
        FindModels(copy, type)[position].Json["surprise"] = 1;
        RequireRefused(copy, type);
      }
      return $"{models.Count} cases";
    }

    /// <summary>
    /// Takes only <see cref="JsonException"/> as a refusal. Stripping fails with other
    /// exceptions, such as a missing constructor, and those must not count as a pass.
    /// </summary>
    private static void RequireRefused(JsonObject body, Type type)
    {
      try
      {
        Parse(body, type);
      }
      catch (JsonException)
      {
        return;
      }
      throw new InvalidOperationException("accepted " + body.ToJsonString());
    }

    /// <summary>Every object of a body with the model it parses into, outermost first.</summary>
    private static List<(JsonObject Json, Type Model)> FindModels(JsonNode body, Type type)
    {
      var found = new List<(JsonObject Json, Type Model)>();
      CollectModels(body, type, found);
      return found;
    }

    private static void CollectModels(JsonNode? node, Type type, List<(JsonObject Json, Type Model)> found)
    {
      if (node is null)
        return;
      type = Nullable.GetUnderlyingType(type) ?? type;

      if (node is JsonArray list)
      {
        var itemType = type.GetGenericArguments()[0];
        foreach (var item in list)
          CollectModels(item, itemType, found);
        return;
      }
      if (node is not JsonObject json)
        return;

      if (type.IsGenericType && type.GetGenericTypeDefinition() == typeof(IReadOnlyDictionary<,>))
      {
        var valueType = type.GetGenericArguments()[1];
        foreach (var pair in json)
          CollectModels(pair.Value, valueType, found);
        return;
      }

      if (type == typeof(ICommandUnitSequenceItem))
        type = json.ContainsKey("branch_list") ? typeof(ConcurrentCommands) : typeof(CommandUnit);
      found.Add((json, type));
      foreach (var property in Properties(type))
      {
        if (json.TryGetPropertyValue(WireName(property), out var value))
          CollectModels(value, property.PropertyType, found);
      }
    }

    private static IEnumerable<PropertyInfo> Properties(Type model)
    {
      return model.GetProperties(BindingFlags.Public | BindingFlags.Instance)
          .Where(property => property.GetCustomAttribute<JsonPropertyNameAttribute>() is not null);
    }

    private static string WireName(PropertyInfo property)
    {
      return property.GetCustomAttribute<JsonPropertyNameAttribute>()!.Name;
    }

    private static RoISIdentifierType Identifier(JsonNode node)
    {
      return new RoISIdentifierType(authority: (string)node["authority"]!, code: (string)node["code"]!);
    }

    // The vectors name the Python builders, because the Python package is where types start.
    private static string BuildCondition(string builder, JsonArray args)
    {
      var text = args.Select(arg => arg is JsonValue ? (string)arg! : "").ToArray();
      switch (builder)
      {
        case "quote":
          return Condition.Quote(text[0]);
        case "eq":
          return Condition.Eq(text[0], text[1]);
        case "like":
          return Condition.Like(text[0], text[1]);
        case "all_of":
          return Condition.AllOf(text);
        case "component_ref":
          return Condition.ComponentRef(text[0]);
        case "component_type":
          return Condition.ComponentType(Identifier(args[0]!));
        case "component_type_urn":
          return Condition.ComponentTypeUrn(Identifier(args[0]!));
        default:
          throw new ArgumentException($"Unknown builder: {builder}");
      }
    }

    private static string ItemType(string dataType)
    {
      return dataType.Substring(0, dataType.Length - 2);
    }

    private static string BaseType(string dataType)
    {
      return dataType.ToLowerInvariant().Replace("[]", "");
    }

    private static bool IsInteger(string dataType)
    {
      return BaseType(dataType) is "int" or "integer" or "long" or "short";
    }

    private static bool IsFloat(string dataType)
    {
      return BaseType(dataType) is "float" or "double";
    }

    private static bool IsBoolean(string dataType)
    {
      return BaseType(dataType) is "bool" or "boolean";
    }

    /// <summary>
    /// The value a C# caller would pass. JSON keeps 2 and 2.0 apart in its text only, so
    /// the type comes from the data type, as it does for every other language.
    /// </summary>
    private static object? ToValue(string dataType, JsonNode? node)
    {
      if (node is JsonArray items)
        return items.Select(item => ToValue(ItemType(dataType), item)).ToArray();
      if (IsInteger(dataType))
        return BigInteger.Parse(node!.ToJsonString(), CultureInfo.InvariantCulture);
      if (IsFloat(dataType))
        return node!.GetValue<double>();
      if (IsBoolean(dataType))
        return node!.GetValue<bool>();
      return node!.GetValue<string>();
    }

    /// <summary>Checks the decoded type as well as the value, so 2.0 for 2 and true for 1 fail.</summary>
    private static void CheckDecoded(string dataType, JsonNode? expected, object actual)
    {
      if (expected is JsonArray items)
      {
        var decoded = (object[])actual;
        Require(items.Count == decoded.Length, $"decoded {decoded.Length} items");
        for (var index = 0; index < decoded.Length; index++)
          CheckDecoded(ItemType(dataType), items[index], decoded[index]);
        return;
      }
      var same = false;
      if (IsInteger(dataType))
        same = (actual is long || actual is BigInteger) && expected!.ToJsonString() == actual.ToString();
      else if (IsFloat(dataType))
        same = actual is double number && SameDouble(number, ToDouble(expected!));
      else if (IsBoolean(dataType))
        same = actual is bool flag && flag == expected!.GetValue<bool>();
      else if (BaseType(dataType) == "component_status")
        same = actual is ComponentStatus status && status.ToString() == expected!.GetValue<string>();
      else
        same = actual is string text && text == expected!.GetValue<string>();
      Require(same, $"decoded {actual.GetType().Name} {actual}");
    }

    /// <summary>The bits decide, because == takes -0.0 and 0.0 as the same number.</summary>
    private static bool SameDouble(double left, double right)
    {
      if (double.IsNaN(left) || double.IsNaN(right))
        return double.IsNaN(left) && double.IsNaN(right);
      return BitConverter.DoubleToInt64Bits(left) == BitConverter.DoubleToInt64Bits(right);
    }

    /// <summary>A number of a vector, where a float JSON cannot carry stands as its text.</summary>
    private static double ToDouble(JsonNode node)
    {
      if (node.GetValueKind() != JsonValueKind.String)
        return node.GetValue<double>();
      switch (node.GetValue<string>())
      {
        case "NaN":
          return double.NaN;
        case "Infinity":
          return double.PositiveInfinity;
        case "-Infinity":
          return double.NegativeInfinity;
        case "-0.0":
          return BitConverter.Int64BitsToDouble(long.MinValue);
        default:
          throw new ArgumentException($"Not a float text: {node}");
      }
    }

    /// <summary>The value of a <c>value_text</c> column, as a C# caller would pass it.</summary>
    private static object ToEdgeValue(JsonNode node)
    {
      if (node is JsonArray items)
        return items.Select(item => ToEdgeValue(item!)).ToArray();
      if (node.GetValueKind() == JsonValueKind.String)
        return ToDouble(node);
      var text = node.ToJsonString();
      if (text.All(character => character == '-' || (character >= '0' && character <= '9')))
        return BigInteger.Parse(text, CultureInfo.InvariantCulture);
      return RoISValues.Decode("double", text);
    }

    /// <summary>Reads the column as JSON, with the names that JSON does not have quoted.</summary>
    private static object ReadValueText(string text)
    {
      return ToEdgeValue(JsonNode.Parse(Regex.Replace(text, "-?Infinity|NaN", "\"$0\""))!);
    }

    // Session

    private async Task RunSession(string url)
    {
      using var cancel = new CancellationTokenSource(TimeSpan.FromSeconds(SessionLimitSeconds));
      using var socket = new ClientWebSocket();
      _socket = socket;
      _cancel = cancel.Token;

      await OnMain(socket.ConnectAsync(new Uri(url), _cancel), "ConnectAsync");
      Pass("session open " + url);

      var connect = await OnMain(Call<ConnectResult>(RoISMethods.Connect, new ConnectParams()), "connect");
      RequireOk("session connect", connect.ReturnCode);
      await OnMain(WaitForAdapter(), "adapter joined");

      var profile = await OnMain(Call<GetProfileResult>(RoISMethods.GetProfile, new GetProfileParams("")), "get_profile");
      RequireOk("session get_profile", profile.ReturnCode);
      Check("session profile lists navigation", () =>
      {
        Require(profile.ComponentProfiles?.ContainsKey(Navigation) == true, "not in component_profiles");
        return $"{profile.ComponentProfiles!.Count} components";
      });

      var bind = await OnMain(Call<BindResult>(RoISMethods.Bind, new BindParams(Navigation)), "bind");
      RequireOk("session bind", bind.ReturnCode);

      var sequence = new ICommandUnitSequenceItem[] { new CommandUnit(Navigation, RoISCommandTypes.Start) };
      var execute = await OnMain(Call<ExecuteResult>(RoISMethods.Execute, new ExecuteParams(sequence)), "execute");
      RequireOk("session execute", execute.ReturnCode);

      var commandId = ((CommandUnit)execute.CommandUnitList![0]).CommandId;
      await OnMain(WaitForCompleted(commandId), "completed");
      Check("session completed " + commandId, () =>
      {
        Require(_completed[commandId].Status == CompletedStatus.OK, _completed[commandId].Status.ToString());
        return "";
      });

      var disconnect = await OnMain(Call<DisconnectResult>(RoISMethods.Disconnect, new DisconnectParams()), "disconnect");
      RequireOk("session disconnect", disconnect.ReturnCode);
      await OnMain(socket.CloseAsync(WebSocketCloseStatus.NormalClosure, "", _cancel), "CloseAsync");
      Pass("session closed");
    }

    /// <summary>Waits for the adapter, which joins the gateway a moment after it opens.</summary>
    private async Task WaitForAdapter()
    {
      var condition = Condition.ComponentRef(Navigation);
      for (var attempt = 1; attempt <= AdapterJoinAttempts; attempt++)
      {
        var search = await OnMain(Call<SearchResult>(RoISMethods.Search, new SearchParams(condition)), "search");
        if (search.ComponentRefList?.Contains(Navigation) == true)
        {
          Pass($"session search found {Navigation} on attempt {attempt}");
          return;
        }
        await OnMain(Task.Delay(AdapterJoinDelayMilliseconds, _cancel), "Task.Delay");
      }
      throw new TimeoutException("The mock adapter did not join.");
    }

    private async Task<TResult> Call<TResult>(string method, object body)
    {
      var (paramsType, resultType) = RoISMethodTypes.ByMethod[method];
      Require(paramsType == body.GetType() && resultType == typeof(TResult), "Catalog mismatch for " + method);
      var id = (++_nextId).ToString(CultureInfo.InvariantCulture);
      var request = new JsonObject
      {
        ["jsonrpc"] = "2.0",
        ["id"] = id,
        ["method"] = method,
        ["params"] = JsonSerializer.SerializeToNode(body, paramsType, RoISJson.Options),
      };
      var bytes = Encoding.UTF8.GetBytes(request.ToJsonString());
      await OnMain(
          _socket!.SendAsync(new ArraySegment<byte>(bytes), WebSocketMessageType.Text, true, _cancel),
          "SendAsync");
      while (true)
      {
        var message = await OnMain(Receive(), "Receive");
        if (!message.ContainsKey("id"))
        {
          OnNotification(message);
          continue;
        }
        Require(message["id"]?.ToString() == id, "Unexpected reply: " + message.ToJsonString());
        Require(!message.ContainsKey("error"), method + " failed: " + message["error"]?.ToJsonString());
        return JsonSerializer.Deserialize<TResult>(message["result"]!.ToJsonString(), RoISJson.Options)!;
      }
    }

    private async Task WaitForCompleted(string commandId)
    {
      while (!_completed.ContainsKey(commandId))
      {
        var message = await OnMain(Receive(), "Receive");
        Require(!message.ContainsKey("id"), "Unexpected reply: " + message.ToJsonString());
        OnNotification(message);
      }
    }

    /// <summary>Reassembles one message, which a socket can deliver in several frames.</summary>
    private async Task<JsonObject> Receive()
    {
      var buffer = new byte[1 << 16];
      using var message = new MemoryStream();
      WebSocketReceiveResult part;
      do
      {
        part = await OnMain(
            _socket!.ReceiveAsync(new ArraySegment<byte>(buffer), _cancel),
            "ReceiveAsync");
        message.Write(buffer, 0, part.Count);
      } while (!part.EndOfMessage);
      return JsonNode.Parse(message.ToArray())!.AsObject();
    }

    private void OnNotification(JsonObject message)
    {
      var method = (string)message["method"]!;
      var type = RoISNotificationTypes.ByMethod[method];
      var body = JsonSerializer.Deserialize(message["params"]!.ToJsonString(), type, RoISJson.Options);
      if (body is CompletedParams done)
        _completed[done.CommandId] = done;
    }

    // Input

    /// <summary>
    /// On Android a device reaches its servers over the LAN and a launched app has no
    /// environment of its own, so the addresses come from the build.
    /// </summary>
    private async Task<string> ReadUrl(string variable, string field)
    {
      if (Application.platform == RuntimePlatform.Android)
      {
        var config = await OnMain(ReadStreamingAsset(ConfigFile), "read " + ConfigFile);
        return (string)config[field]!;
      }
      var url = Environment.GetEnvironmentVariable(variable);
      if (string.IsNullOrEmpty(url))
        throw new InvalidOperationException(variable + " is not set.");
      return url;
    }

    /// <summary>
    /// Reads through UnityWebRequest on every platform, because on Android StreamingAssets
    /// sits inside the APK, where file APIs cannot reach it.
    /// </summary>
    private static async Task<JsonNode> ReadStreamingAsset(string name)
    {
      return JsonNode.Parse(await ReadStreamingBytes(name))!;
    }

    /// <inheritdoc cref="ReadStreamingAsset(string)"/>
    private static async Task<byte[]> ReadStreamingBytes(string name)
    {
      var path = Path.Combine(Application.streamingAssetsPath, name);
      using var request = UnityWebRequest.Get(path.Contains("://") ? path : new Uri(path).AbsoluteUri);
      var finished = new TaskCompletionSource<bool>();
      request.SendWebRequest().completed += _ => finished.SetResult(true);
      await finished.Task;
      if (request.result != UnityWebRequest.Result.Success)
        throw new IOException($"Cannot read {name}: {request.error}");
      return request.downloadHandler.data;
    }

    // Reporting

    /// <summary>Awaits a task and checks where the code resumed, as every await here does.</summary>
    private async Task OnMain(Task task, string what)
    {
      await task;
      CheckResumed(what);
    }

    /// <inheritdoc cref="OnMain(Task, string)"/>
    private async Task<T> OnMain<T>(Task<T> task, string what)
    {
      var result = await task;
      CheckResumed(what);
      return result;
    }

    private void CheckResumed(string what)
    {
      var thread = Thread.CurrentThread.ManagedThreadId;
      if (thread == _mainThread)
        Pass("main-thread after " + what);
      else
        Fail("main-thread after " + what, $"on thread {thread}, main is {_mainThread}");
    }

    private void Check(string name, Func<string> body)
    {
      try
      {
        var detail = body();
        Pass(detail.Length == 0 ? name : $"{name} ({detail})");
      }
      catch (Exception e)
      {
        Fail(name, Describe(e));
      }
    }

    private void RequireOk(string name, ReturnCode code)
    {
      if (code == ReturnCode.OK)
        Pass(name);
      else
        Fail(name, code.ToString());
    }

    private static void Require(bool condition, string message)
    {
      if (!condition)
        throw new InvalidOperationException(message);
    }

    private void Pass(string check)
    {
      Interlocked.Increment(ref _passed);
      Say("PASS " + check);
    }

    private void Fail(string check, string why)
    {
      Interlocked.Increment(ref _failed);
      Say($"FAIL {check}: {why}");
    }

    private static string Describe(Exception e)
    {
      return $"{e.GetType().Name}: {e.Message}";
    }

    private static void Say(string line)
    {
      Debug.Log(Prefix + line);
    }
  }
}  // namespace OpenRoIS.Harness
