using System.Text.Json;
using NUnit.Framework;
using OpenRoIS.Sdk.JsonRpc;

namespace OpenRoIS.Sdk.Tests
{

  [TestFixture]
  public class JsonRpcBuilderTests
  {

    [Test]
    public void CreateRequest_ProducesValidJsonRpcStructure()
    {
      var json = JsonRpcBuilder.CreateRequest("1", "rois.command.search",
          new { condition = "" });

      var doc = JsonDocument.Parse(json);
      var root = doc.RootElement;

      Assert.That(root.GetProperty("jsonrpc").GetString(), Is.EqualTo("2.0"));
      Assert.That(root.GetProperty("id").GetString(), Is.EqualTo("1"));
      Assert.That(root.GetProperty("method").GetString(),
          Is.EqualTo("rois.command.search"));
      Assert.That(root.GetProperty("params").GetProperty("condition")
          .GetString(), Is.EqualTo(""));
    }

    [Test]
    public void CreateRequest_WithNullParams_OmitsParamsField()
    {
      var json = JsonRpcBuilder.CreateRequest("2", "rois.system.connect");

      var doc = JsonDocument.Parse(json);
      var root = doc.RootElement;

      Assert.That(root.GetProperty("jsonrpc").GetString(), Is.EqualTo("2.0"));
      Assert.That(root.GetProperty("id").GetString(), Is.EqualTo("2"));
      Assert.That(root.GetProperty("method").GetString(),
          Is.EqualTo("rois.system.connect"));
      Assert.That(root.TryGetProperty("params", out _), Is.False);
    }

    [Test]
    public void CreateRequest_WithComplexParams_SerializesCorrectly()
    {
      var json = JsonRpcBuilder.CreateRequest("3", "rois.command.execute",
          new
          {
            component_ref = "Navigation_0",
            command_type = "execute",
            command_id = "cmd-001",
            parameters = new[]
            {
              new { name = "target_positions", data_type_ref = "string[]",
                  value = "[\"3.0,1.5,0.0\"]" },
            },
          });

      var doc = JsonDocument.Parse(json);
      var root = doc.RootElement;
      var parameters = root.GetProperty("params");

      Assert.That(parameters.GetProperty("component_ref").GetString(),
          Is.EqualTo("Navigation_0"));
      Assert.That(parameters.GetProperty("command_type").GetString(),
          Is.EqualTo("execute"));
      Assert.That(parameters.GetProperty("command_id").GetString(),
          Is.EqualTo("cmd-001"));

      var paramArray = parameters.GetProperty("parameters");
      Assert.That(paramArray.GetArrayLength(), Is.EqualTo(1));
      Assert.That(paramArray[0].GetProperty("name").GetString(),
          Is.EqualTo("target_positions"));
    }

    [Test]
    public void CreateNotification_ProducesValidJsonRpcStructure()
    {
      var json = JsonRpcBuilder.CreateNotification("rois.event.notify",
          new
          {
            event_id = "evt-001",
            event_type = "person_detected",
            subscribe_id = "sub-1",
          });

      var doc = JsonDocument.Parse(json);
      var root = doc.RootElement;

      Assert.That(root.GetProperty("jsonrpc").GetString(),
          Is.EqualTo("2.0"));
      Assert.That(root.GetProperty("method").GetString(),
          Is.EqualTo("rois.event.notify"));
      // Notifications must NOT have an id field.
      Assert.That(root.TryGetProperty("id", out _), Is.False);

      var parameters = root.GetProperty("params");
      Assert.That(parameters.GetProperty("event_id").GetString(),
          Is.EqualTo("evt-001"));
      Assert.That(parameters.GetProperty("event_type").GetString(),
          Is.EqualTo("person_detected"));
    }

    [Test]
    public void CreateNotification_WithNullParams_OmitsParamsField()
    {
      var json = JsonRpcBuilder.CreateNotification("rois.system.notify_error");

      var doc = JsonDocument.Parse(json);
      var root = doc.RootElement;

      Assert.That(root.GetProperty("jsonrpc").GetString(),
          Is.EqualTo("2.0"));
      Assert.That(root.GetProperty("method").GetString(),
          Is.EqualTo("rois.system.notify_error"));
      Assert.That(root.TryGetProperty("id", out _), Is.False);
      Assert.That(root.TryGetProperty("params", out _), Is.False);
    }

    [Test]
    public void CreateRequest_ProducesCompactJson()
    {
      var json = JsonRpcBuilder.CreateRequest("1", "rois.query.query",
          new { component_ref = "Nav_0", query_type = "component_status" });

      // Verify no indentation (compact wire format).
      Assert.That(json, Does.Not.Contain("\n"));
      Assert.That(json, Does.Not.Contain("  "));
    }
  }

}  // namespace OpenRoIS.Sdk.Tests