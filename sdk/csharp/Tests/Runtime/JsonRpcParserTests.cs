using System.Text.Json;
using NUnit.Framework;
using OpenRoIS.Sdk.JsonRpc;

namespace OpenRoIS.Sdk.Tests
{

  [TestFixture]
  public class JsonRpcParserTests
  {

    [Test]
    public void Parse_Response_ClassifiesAsResponse()
    {
      var json = @"{""jsonrpc"":""2.0"",""id"":""1"",""result"":{""return_code"":""OK"",""component_ref_list"":[""Nav_0"",""PD_0""]}}";

      var msg = JsonRpcParser.Parse(json);

      Assert.That(msg.Type, Is.EqualTo(JsonRpcMessageType.Response));
      Assert.That(msg.Response, Is.Not.Null);
      Assert.That(msg.Response!.Id, Is.EqualTo("1"));
      Assert.That(msg.Response.Result.GetProperty("return_code").GetString(),
          Is.EqualTo("OK"));

      var list = msg.Response.Result.GetProperty("component_ref_list");
      Assert.That(list.GetArrayLength(), Is.EqualTo(2));
      Assert.That(list[0].GetString(), Is.EqualTo("Nav_0"));
    }

    [Test]
    public void Parse_Response_WithNumericId_ClassifiesAsResponse()
    {
      var json = @"{""jsonrpc"":""2.0"",""id"":42,""result"":{""return_code"":""OK""}}";

      var msg = JsonRpcParser.Parse(json);

      Assert.That(msg.Type, Is.EqualTo(JsonRpcMessageType.Response));
      Assert.That(msg.Response, Is.Not.Null);
      // Numeric id is deserialized to string by System.Text.Json.
      Assert.That(msg.Response!.Id, Is.EqualTo("42"));
    }

    [Test]
    public void Parse_Error_ClassifiesAsError()
    {
      var json = @"{""jsonrpc"":""2.0"",""id"":""5"",""error"":{""code"":-32601,""message"":""Method not found""}}";

      var msg = JsonRpcParser.Parse(json);

      Assert.That(msg.Type, Is.EqualTo(JsonRpcMessageType.Error));
      Assert.That(msg.Error, Is.Not.Null);
      Assert.That(msg.Error!.Id, Is.EqualTo("5"));
      Assert.That(msg.Error.Error.Code, Is.EqualTo(-32601));
      Assert.That(msg.Error.Error.Message, Is.EqualTo("Method not found"));
    }

    [Test]
    public void Parse_Error_WithDataField_ParsesData()
    {
      var json = @"{""jsonrpc"":""2.0"",""id"":""6"",""error"":{""code"":-32602,""message"":""Invalid params"",""data"":{""return_code"":""BAD_PARAMETER""}}}";

      var msg = JsonRpcParser.Parse(json);

      Assert.That(msg.Type, Is.EqualTo(JsonRpcMessageType.Error));
      Assert.That(msg.Error!.Error.Data, Is.Not.Null);
      Assert.That(msg.Error.Error.Data!.Value.GetProperty("return_code")
          .GetString(), Is.EqualTo("BAD_PARAMETER"));
    }

    [Test]
    public void Parse_Notification_ClassifiesAsNotification()
    {
      var json = @"{""jsonrpc"":""2.0"",""method"":""rois.event.notify"",""params"":{""event_id"":""evt-001"",""event_type"":""person_detected"",""subscribe_id"":""sub-1""}}";

      var msg = JsonRpcParser.Parse(json);

      Assert.That(msg.Type, Is.EqualTo(JsonRpcMessageType.Notification));
      Assert.That(msg.Notification, Is.Not.Null);
      Assert.That(msg.Notification!.Method, Is.EqualTo("rois.event.notify"));
      Assert.That(msg.Notification.Params, Is.Not.Null);
      Assert.That(msg.Notification.Params!.Value.GetProperty("event_id")
          .GetString(), Is.EqualTo("evt-001"));
    }

    [Test]
    public void Parse_Notification_WithoutParams_ClassifiesAsNotification()
    {
      var json = @"{""jsonrpc"":""2.0"",""method"":""rois.command.completed""}";

      var msg = JsonRpcParser.Parse(json);

      Assert.That(msg.Type, Is.EqualTo(JsonRpcMessageType.Notification));
      Assert.That(msg.Notification, Is.Not.Null);
      Assert.That(msg.Notification!.Method,
          Is.EqualTo("rois.command.completed"));
      Assert.That(msg.Notification.Params, Is.Null);
    }

    [Test]
    public void Parse_Request_ClassifiesAsRequest()
    {
      var json = @"{""jsonrpc"":""2.0"",""id"":""10"",""method"":""rois.command.search"",""params"":{""condition"":""""}}";

      var msg = JsonRpcParser.Parse(json);

      Assert.That(msg.Type, Is.EqualTo(JsonRpcMessageType.Request));
      Assert.That(msg.Request, Is.Not.Null);
      Assert.That(msg.Request!.Id, Is.EqualTo("10"));
      Assert.That(msg.Request.Method, Is.EqualTo("rois.command.search"));
    }

    [Test]
    public void Parse_InvalidJson_ClassifiesAsUnknown()
    {
      var msg = JsonRpcParser.Parse("not json at all");

      Assert.That(msg.Type, Is.EqualTo(JsonRpcMessageType.Unknown));
      Assert.That(msg.RawJson, Is.EqualTo("not json at all"));
    }

    [Test]
    public void Parse_EmptyJson_ClassifiesAsUnknown()
    {
      var msg = JsonRpcParser.Parse("{}");

      // No id, no result, no error, no method -> Unknown.
      Assert.That(msg.Type, Is.EqualTo(JsonRpcMessageType.Unknown));
    }

    [Test]
    public void Parse_RawJson_PreservedInMessage()
    {
      var json = @"{""jsonrpc"":""2.0"",""id"":""1"",""result"":{""return_code"":""OK""}}";

      var msg = JsonRpcParser.Parse(json);

      Assert.That(msg.RawJson, Is.EqualTo(json));
    }

    [Test]
    public void Parse_Response_ResultIsAccessibleAsJsonElement()
    {
      var json = @"{""jsonrpc"":""2.0"",""id"":""1"",""result"":{""return_code"":""OK"",""subscribe_id"":""sub-abc""}}";

      var msg = JsonRpcParser.Parse(json);

      Assert.That(msg.Type, Is.EqualTo(JsonRpcMessageType.Response));
      // The caller can deserialize Result to a specific type.
      var subscribeId = msg.Response!.Result.GetProperty("subscribe_id")
          .GetString();
      Assert.That(subscribeId, Is.EqualTo("sub-abc"));
    }
  }

}  // namespace OpenRoIS.Sdk.Tests