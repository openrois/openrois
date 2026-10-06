// Transport-neutral component contract for OpenRoIS.
//
// This file is hand-written, because JSON Schema cannot represent behavioral interfaces.
// The request/response models and EventEnvelope are generated in Generated/ContractModels.cs.
//
// Mirrors interfaces/python/src/openrois/interfaces/contract.py.

using System;
using System.Threading.Tasks;
using OpenRoIS.Interfaces.Contract.Models;
using ReturnCode = OpenRoIS.Interfaces.Hri.ReturnCode;

namespace OpenRoIS.Interfaces.Contract
{
    // ─── Event sink ──────────────────────────────────────────────────────

    /// <summary>Async callback that receives event envelopes from a ComponentContract.</summary>
    public delegate Task EventSink(EventEnvelope envelope);

    // ─── Exceptions ──────────────────────────────────────────────────────

    /// <summary>Base error raised by ComponentContract implementations.</summary>
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
    public class ComponentNotFoundError : ComponentContractError
    {
        /// <summary>The component reference that was not found.</summary>
        public string ComponentRef { get; }

        public ComponentNotFoundError(string componentRef)
            : base($"Component not found: {componentRef}", ReturnCode.UNSUPPORTED)
        {
            ComponentRef = componentRef;
        }
    }

    // ─── ComponentContract interface ─────────────────────────────────────

    /// <summary>
    /// Transport-neutral contract between an engine and the components it reaches.
    /// The Python engine implements it with ComponentRegistry (local components) and
    /// ChildEngineProxy (a remote child engine over WebSocket JSON-RPC).
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
}