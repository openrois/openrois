using System;
using OpenRoIS.Interfaces.Hri;
using OpenRoIS.Interfaces.Common;
using OpenRoIS.Interfaces.Service;
using OpenRoIS.Interfaces.Profiles;
using OpenRoIS.Interfaces.Components.PersonDetection;
using OpenRoIS.Interfaces.Components.Navigation;
using Xunit;
using ComponentStatus = OpenRoIS.Interfaces.Common.ComponentStatus;
using CompletedStatus = OpenRoIS.Interfaces.Service.CompletedStatus;
using ErrorType = OpenRoIS.Interfaces.Service.ErrorType;

namespace OpenRoIS.Interfaces.Tests
{
    public class ExportTests
    {
    [Fact]
    public void Hri_TypesExist()
    {
        Assert.NotNull(typeof(Result));
        Assert.NotNull(typeof(Parameter));
        Assert.NotNull(typeof(Argument));
        Assert.NotNull(typeof(CommandUnit));
        Assert.NotNull(typeof(CommandUnitSequence));
        Assert.NotNull(typeof(ConcurrentCommands));
        Assert.NotNull(typeof(ReturnCode));
    }

    [Fact]
    public void Common_TypesExist()
    {
        Assert.NotNull(typeof(ComponentStatus));
        Assert.NotNull(typeof(StreamStatus));
    }

    [Fact]
    public void Service_TypesExist()
    {
        Assert.NotNull(typeof(CompletedStatus));
        Assert.NotNull(typeof(ErrorType));
        Assert.NotNull(typeof(CompletedParams));
        Assert.NotNull(typeof(NotifyErrorParams));
        Assert.NotNull(typeof(NotifyEventParams));
        Assert.NotNull(typeof(ProfileChangedParams));
    }

    [Fact]
    public void Profiles_TypesExist()
    {
        Assert.NotNull(typeof(HRIComponentProfile));
        Assert.NotNull(typeof(ComponentFunction));
        Assert.NotNull(typeof(HRIEngineProfileType));
        Assert.NotNull(typeof(ParameterProfile));
        Assert.NotNull(typeof(RoISIdentifierType));
    }

    [Fact]
    public void Component_TypesExist()
    {
        Assert.NotNull(typeof(PersonDetectedEvent));
        Assert.NotNull(typeof(PersonDetectionStatusResult));
        Assert.NotNull(typeof(NavigationSetParameter));
        Assert.NotNull(typeof(NavigationSetParameterResult));
        Assert.NotNull(typeof(NavigationGetParameterResult));
        Assert.NotNull(typeof(NavigationStatusResult));
        Assert.NotNull(typeof(NavigationReachedTargetEvent));
    }
    }
}