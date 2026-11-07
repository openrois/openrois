#nullable enable
using System;
using System.IO;
using UnityEditor;
using UnityEditor.Build;
using UnityEditor.Build.Reporting;
using UnityEditor.SceneManagement;
using UnityEngine;

namespace OpenRoIS.Harness.Editor
{
  /// <summary>
  /// Batch mode entry point. The project holds no scene, settings or fixtures of its own:
  /// each build makes them, so the same files open on every Editor version without an
  /// upgrade of the project.
  /// </summary>
  public static class HarnessBuild
  {
    private const string ScenePath = "Assets/Main.unity";
    private const string StreamingAssets = "Assets/StreamingAssets";
    private const string ConfigFile = "harness.json";
    private const string ApplicationId = "org.openrois.harness";
    private const string FixturesFromProject = "../../interfaces/fixtures";
    private const string ConformanceListFromProject = "../conformance/README.md";
    private const string ConformanceListFile = "conformance-list.md";

    [Serializable]
    private sealed class HarnessConfig
    {
      public string gateway_url = "";
      public string scripted_url = "";
    }

    /// <summary>Builds the target named by the environment and exits the Editor.</summary>
    public static void Run()
    {
      var exitCode = 1;
      try
      {
        exitCode = Build() ? 0 : 1;
      }
      catch (Exception e)
      {
        Debug.LogException(e);
      }
      EditorApplication.Exit(exitCode);
    }

    private static bool Build()
    {
      var target = Required("OPENROIS_HARNESS_TARGET");
      var output = Required("OPENROIS_HARNESS_OUTPUT");

      CopyFixtures();
      var options = new BuildPlayerOptions { locationPathName = output, options = BuildOptions.None };
      switch (target)
      {
        case "linux-il2cpp":
          ConfigureLinux(ScriptingImplementation.IL2CPP, ref options);
          break;
        case "linux-mono":
          ConfigureLinux(ScriptingImplementation.Mono2x, ref options);
          break;
        case "android":
          ConfigureAndroid(ref options);
          break;
        default:
          throw new ArgumentException($"Unknown target: {target}");
      }
      AssetDatabase.Refresh();

      var scene = EditorSceneManager.NewScene(NewSceneSetup.EmptyScene);
      EditorSceneManager.SaveScene(scene, ScenePath);
      options.scenes = new[] { ScenePath };

      var summary = BuildPipeline.BuildPlayer(options).summary;
      Debug.Log($"HARNESS BUILD {target} {summary.result} errors={summary.totalErrors} seconds={summary.totalTime.TotalSeconds:F0}");
      return summary.result == BuildResult.Succeeded;
    }

    private static string Required(string variable)
    {
      var value = Environment.GetEnvironmentVariable(variable);
      if (string.IsNullOrEmpty(value))
        throw new InvalidOperationException(variable + " is not set.");
      return value;
    }

    private static void CopyFixtures()
    {
      Directory.CreateDirectory(StreamingAssets);
      foreach (var fixture in Directory.GetFiles(FixturesFromProject, "*.json"))
        File.Copy(fixture, Path.Combine(StreamingAssets, Path.GetFileName(fixture)), overwrite: true);

      // The player compares its scenarios to this list, so a new id fails on a device as well.
      File.Copy(ConformanceListFromProject, Path.Combine(StreamingAssets, ConformanceListFile), overwrite: true);
    }

    private static void ConfigureLinux(ScriptingImplementation backend, ref BuildPlayerOptions options)
    {
      Configure(NamedBuildTarget.Standalone, backend);
      options.target = BuildTarget.StandaloneLinux64;
    }

    private static void ConfigureAndroid(ref BuildPlayerOptions options)
    {
      Configure(NamedBuildTarget.Android, ScriptingImplementation.IL2CPP);
      PlayerSettings.Android.targetArchitectures = AndroidArchitecture.ARM64;

      // Unity adds this permission when it sees its own networking classes, and
      // ClientWebSocket is not one of them.
      PlayerSettings.Android.forceInternetPermission = true;
      EditorUserBuildSettings.buildAppBundle = false;
      options.target = BuildTarget.Android;

      var config = new HarnessConfig
      {
        gateway_url = Required("OPENROIS_GATEWAY_URL"),
        scripted_url = Required("OPENROIS_SCRIPTED_URL"),
      };
      File.WriteAllText(Path.Combine(StreamingAssets, ConfigFile), JsonUtility.ToJson(config));
    }

    // IL2CPP runs at High, the level that removes the most. Mono stays at the default Unity
    // gives it, because at High every System.Text.Json read fails on Mono with a
    // FieldAccessException, which Medium and below do not.
    private static ManagedStrippingLevel Stripping(ScriptingImplementation backend)
    {
      var level = Environment.GetEnvironmentVariable("OPENROIS_HARNESS_STRIPPING");
      if (!string.IsNullOrEmpty(level))
        return (ManagedStrippingLevel)Enum.Parse(typeof(ManagedStrippingLevel), level);
      return backend == ScriptingImplementation.IL2CPP ? ManagedStrippingLevel.High : ManagedStrippingLevel.Disabled;
    }

    private static void Configure(NamedBuildTarget target, ScriptingImplementation backend)
    {
      PlayerSettings.productName = "OpenRoIS Harness";
      PlayerSettings.SetApplicationIdentifier(target, ApplicationId);
      PlayerSettings.SetScriptingBackend(target, backend);
      PlayerSettings.SetManagedStrippingLevel(target, Stripping(backend));
    }
  }
}  // namespace OpenRoIS.Harness.Editor
