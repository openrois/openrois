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

    /// <summary>Async callback that receives event envelopes from a Component Contract implementation.</summary>
    public delegate Task EventSink(EventEnvelope envelope);

    // ─── Exceptions ──────────────────────────────────────────────────────

    /// <summary>Base error raised by Component Contract implementations.</summary>
    public class ComponentContractError : Exception
    {
        /// <summary>The RoIS return code associated with this error.</summary>
        public ReturnCode ReturnCode { get; }

        public ComponentContractError(string message, ReturnCode returnCode = ReturnCode.ERROR)
            : base(message)
        {
            ReturnCode = returnCode;
        }
    }

    /// <summary>Raised when a component_ref cannot be resolved by the adapter.</summary>
    /// <remarks>
    /// Derives from the deprecated <see cref="BusAdapterError"/> during the compatibility
    /// window so that existing <c>catch (BusAdapterError)</c> blocks keep catching it.
    /// </remarks>
#pragma warning disable CS0618
    public class ComponentNotFoundError : BusAdapterError
#pragma warning restore CS0618
    {
        /// <summary>The component reference that was not found.</summary>
        public string ComponentRef { get; }

        public ComponentNotFoundError(string componentRef)
            : base($"Component not found: {componentRef}", ReturnCode.UNSUPPORTED)
        {
            ComponentRef = componentRef;
        }
    }

    // ─── Component Contract interface ────────────────────────────────────

    /// <summary>
    /// Transport-neutral contract between the RoIS engine and a concrete bus.
    /// Implementations include a remote child engine reached over WebSocket and JSON-RPC,
    /// and an in-process component registry.
    /// </summary>
    public interface IComponentContract
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

    // ─── Deprecated names, kept for one alpha release ────────────────────

    /// <summary>Deprecated. Use <see cref="IComponentContract"/>.</summary>
    [System.Obsolete("Use IComponentContract.")]
    public interface IBusAdapter : IComponentContract
    {
    }

    /// <summary>Deprecated. Use <see cref="ComponentContractError"/>.</summary>
    [System.Obsolete("Use ComponentContractError.")]
    public class BusAdapterError : ComponentContractError
    {
        public BusAdapterError(string message, ReturnCode returnCode = ReturnCode.ERROR)
            : base(message, returnCode)
        {
        }
    }
}