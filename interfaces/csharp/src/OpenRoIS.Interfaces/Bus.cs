// Transport-neutral bus adapter contract for OpenRoIS.
//
// This file is hand-written — JSON Schema cannot represent behavioral interfaces.
// The request/response models and EventEnvelope are generated in Generated/BusModels.cs.
//
// Source: roadmap.md M0 Task 0.2; mirrors interfaces/python/.../bus.py

using System;
using System.Threading.Tasks;
using OpenRoIS.Interfaces.Bus.Models;
using ReturnCode = OpenRoIS.Interfaces.Hri.ReturnCode;

namespace OpenRoIS.Interfaces.Bus
{
    // ─── Event sink ──────────────────────────────────────────────────────

    /// <summary>Async callback that receives event envelopes from a BusAdapter.</summary>
    public delegate Task EventSink(EventEnvelope envelope);

    // ─── Exceptions ──────────────────────────────────────────────────────

    /// <summary>Base error raised by BusAdapter implementations.</summary>
    public class BusAdapterError : Exception
    {
        /// <summary>The RoIS return code associated with this error.</summary>
        public ReturnCode ReturnCode { get; }

        public BusAdapterError(string message, ReturnCode returnCode = ReturnCode.ERROR)
            : base(message)
        {
            ReturnCode = returnCode;
        }
    }

    /// <summary>Raised when a component_ref cannot be resolved by the adapter.</summary>
    public class ComponentNotFoundError : BusAdapterError
    {
        /// <summary>The component reference that was not found.</summary>
        public string ComponentRef { get; }

        public ComponentNotFoundError(string componentRef)
            : base($"Component not found: {componentRef}", ReturnCode.UNSUPPORTED)
        {
            ComponentRef = componentRef;
        }
    }

    // ─── BusAdapter interface ────────────────────────────────────────────

    /// <summary>
    /// Transport-neutral contract between the RoIS engine and a concrete bus.
    /// Implementations include UniversalBusAdapter (M1, WS+JSON-RPC), ROS2BusAdapter (M3),
    /// RosBridgeBusAdapter (future).
    /// </summary>
    public interface IBusAdapter
    {
        /// <summary>Discover components matching the request condition. Maps to CommandIF.search().</summary>
        Task<DiscoverResponse> Discover(DiscoverRequest request);

        /// <summary>Invoke a command on a bound component. Maps to CommandIF operations.</summary>
        Task<InvokeResponse> Invoke(CommandRequest request);

        /// <summary>Execute a synchronous query on a component. Maps to QueryIF.query().</summary>
        Task<QueryResponse> Query(QueryRequest request);

        /// <summary>Subscribe to async events from a component. Maps to EventIF.subscribe().</summary>
        Task<SubscribeResponse> Subscribe(SubscribeRequest request, EventSink sink);

        /// <summary>Cancel an event subscription. Maps to EventIF.unsubscribe(). Duplicate requests are silently ignored.</summary>
        Task<ReturnCode> Unsubscribe(string subscribeId);
    }
}