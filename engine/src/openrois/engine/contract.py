"""The component contract: where the components of an engine live.

An engine reaches every component through this contract, whether the component runs
in the engine's own process or behind a child engine on another machine. The engine
itself answers the method catalog: it validates requests, selects components by
condition, holds the bindings, runs command sequences and routes ids. A source behind
the contract runs what the engine hands it, for the components it owns.

``LocalComponents`` implements the contract for the components of this process, and
``ChildEngine`` implements it for one child engine, as a client of the method catalog.
The contract names no transport and no robot paradigm, which keeps the engine
paradigm-neutral (docs/architecture.md, section 8).
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import Protocol

from openrois.interfaces.catalog import (
    GetCommandResultResult,
    GetErrorDetailResult,
    GetEventDetailResult,
    GetParameterResult,
    QueryResult,
    SetParameterResult,
    SubscribeResult,
)
from openrois.interfaces.hri import Argument, CommandUnit, Parameter
from openrois.interfaces.profiles import HRIComponentProfile, HRIEngineProfileType
from openrois.interfaces.service import CompletedStatus, ErrorType, NotifyEventParams

#: Delivers one event of a subscription to the session that holds it.
type Deliver = Callable[[NotifyEventParams], None]

#: Receives one error a source raised: the component ref, or "" for an error of the
#: engine itself, the error id, and the error type.
type OnError = Callable[[str, str, ErrorType], None]


class ComponentContract(Protocol):
    """A source of components for an engine.

    Every component ref belongs to exactly one source. The ids a source assigns, for
    subscriptions, events, errors and set_parameter commands, start with the id of the
    engine that owns the component, so the engine can route them back. Command ids come
    from the engine the client called, and a source reuses them.
    """

    @property
    def engine_ids(self) -> frozenset[str]:
        """The ids of the engines whose components this source holds."""
        ...

    def profiles(self) -> Mapping[str, HRIComponentProfile]:
        """The served profile of each component, by fully qualified ref."""
        ...

    def engine_profile(self) -> HRIEngineProfileType | None:
        """The engine profile of a child engine, or None for the local components."""
        ...

    def on_error(self, callback: OnError) -> None:
        """Hand the source the callback that receives every error it raises."""
        ...

    async def run(self, unit: CommandUnit) -> CompletedStatus:
        """Run one command until it ends, and return how it ended.

        Cancelling the call aborts the command: the source halts what it started.
        """
        ...

    def keep_running(self, command_id: str) -> None:
        """Let a running command run on when the engine next cancels its ``run``.

        The engine calls it before it aborts a command of a client on a component that
        other clients still hold, so the cancel only stops the wait for the command.
        """
        ...

    async def set_parameter(
        self, ref: str, parameters: Sequence[Parameter]
    ) -> tuple[SetParameterResult, CompletedStatus]:
        """Apply new parameter values, and return the result and how the change ended.

        The values are applied when the call returns, so a command sent after the reply
        sees them.
        """
        ...

    async def get_parameter(self, ref: str) -> GetParameterResult:
        """The current parameter values of a component."""
        ...

    async def command_result(self, command_id: str) -> GetCommandResultResult:
        """The results of a command this source ran."""
        ...

    async def query(self, ref: str, query_type: str, arguments: Sequence[Argument]) -> QueryResult:
        """Answer a query of one component, with the arguments its condition gave."""
        ...

    async def subscribe(
        self, ref: str, event_type: str, arguments: Sequence[Argument], deliver: Deliver
    ) -> SubscribeResult:
        """Subscribe to an event of one component. ``deliver`` receives each event.

        An event reaches the subscription when the argument values it concerns equal
        the arguments of the subscription, an argument the subscription did not give
        matching any value.
        """
        ...

    async def unsubscribe(self, subscribe_id: str) -> None:
        """End a subscription. An unknown id is ignored."""
        ...

    async def event_detail(self, event_id: str) -> GetEventDetailResult:
        """The results of an event until it expires."""
        ...

    async def error_detail(self, error_id: str) -> GetErrorDetailResult:
        """The detail of an error until it is cleared."""
        ...
