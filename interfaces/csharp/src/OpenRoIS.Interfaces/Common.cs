// GENERATED FROM interfaces/schema — DO NOT EDIT
// Source: ComponentStatus.schema.json, StreamStatus.schema.json
// Generator: scripts/Generator/Program.cs

using System;
using System.Collections.Generic;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace OpenRoIS.Interfaces.Common
{
    /// <summary>
    /// Status of a RoIS component.
    /// 
    /// Maps to RoIS_Common::Component_Status in the IDL.
    /// 
    /// UNINITIALIZED: Component has not been initialized.
    /// READY: Component is ready to operate.
    /// BUSY: Component is currently processing.
    /// WARNING: Component is operational but has a warning condition.
    /// ERROR: Component has encountered an error.
    /// </summary>
    public enum ComponentStatus
    {
        UNINITIALIZED,
        READY,
        BUSY,
        WARNING,
        ERROR
    }

    /// <summary>
    /// Status of a streaming connection.
    /// 
    /// Maps to RoIS_Common::Stream_Status in the IDL.
    /// 
    /// NOT_CONNECTED: No peer connection established.
    /// NOT_RUNNING: Connection exists but stream is not active.
    /// RUNNING: Stream is actively delivering data.
    /// SUSPENDED: Stream has been suspended (track disabled).
    /// RESUMED: Stream has been resumed after suspension.
    /// </summary>
    public enum StreamStatus
    {
        STREAMING_NOT_CONNECTED,
        STREAMING_NOT_RUNNING,
        STREAMING_RUNNING,
        STREAMING_SUSPENDED,
        STREAMING_RESUMED
    }

}
