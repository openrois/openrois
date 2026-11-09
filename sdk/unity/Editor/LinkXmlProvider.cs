using System.IO;
using UnityEditor.Build;
using UnityEditor.Build.Reporting;
using UnityEditor.PackageManager;
using UnityEditor.UnityLinker;

namespace OpenRoIS.Sdk.Editor
{
  /// <summary>
  /// Hands <c>Runtime/link.xml</c> to the managed code linker.
  /// </summary>
  /// <remarks>
  /// The linker only finds link.xml files under <c>Assets</c>, so one in a
  /// package has no effect by itself. Without it, stripping removes the
  /// constructors that System.Text.Json calls through reflection.
  /// </remarks>
  internal sealed class LinkXmlProvider : IUnityLinkerProcessor
  {
    public int callbackOrder => 0;

    public string GenerateAdditionalLinkXmlFile(
        BuildReport report,
        UnityLinkerBuildPipelineData data)
    {
      PackageInfo package = PackageInfo.FindForAssembly(typeof(LinkXmlProvider).Assembly);
      return Path.Combine(package.resolvedPath, "Runtime", "link.xml");
    }
  }
}  // namespace OpenRoIS.Sdk.Editor
