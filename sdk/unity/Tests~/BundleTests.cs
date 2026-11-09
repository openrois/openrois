#nullable enable
using System;
using System.IO;
using System.Reflection;
using System.Runtime.Versioning;
using NUnit.Framework;

namespace OpenRoIS.Sdk.Core.Tests
{

  /// <summary>
  /// Whether this run tests what ships. Nothing else here can tell, because
  /// the rest of the suite also passes on the copies inside .NET.
  /// </summary>
  public sealed class BundleTests
  {
    [TestCase("OpenRoIS.Interfaces")]
    [TestCase("System.Text.Json")]
    [TestCase("System.Text.Encodings.Web")]
    [TestCase("System.Runtime.CompilerServices.Unsafe")]
    [TestCase("Microsoft.Bcl.AsyncInterfaces")]
    public void TheBundledAssemblyIsTheOneThatLoads(string name)
    {
      var loaded = Assembly.Load(name);

      Assert.That(
          Path.GetDirectoryName(loaded.Location) + Path.DirectorySeparatorChar,
          Is.EqualTo(AppContext.BaseDirectory));
    }

    [Test]
    public void TheJsonLibraryIsTheVersionUnityGets()
    {
      var version = typeof(System.Text.Json.JsonSerializer).Assembly.GetName().Version!;

      Assert.That(version.Major, Is.EqualTo(8));
    }

    [Test]
    public void TheClientIsTheBuildForNetStandard()
    {
      var built = typeof(RoISClient).Assembly.GetCustomAttribute<TargetFrameworkAttribute>()!;

      Assert.That(built.FrameworkName, Is.EqualTo(".NETStandard,Version=v2.1"));
    }
  }

}  // namespace OpenRoIS.Sdk.Core.Tests
