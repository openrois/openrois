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
from openrois.interfaces.hri import CommandUnit, Parameter
from openrois.interfaces.profiles import HRIComponentProfile, HRIEngineProfileType
from openrois.interfaces.service import CompletedStatus, NotifyEventParams

#: Delivers one event of a subscription to the session that holds it.
type Deliver = Callable[[NotifyEventParams], None]

#: Reports how a set_parameter command ended: its command id and its status.
type OnCompleted = Callable[[str, CompletedStatus], None]


class ComponentContract(Protocol):
    """A source of components for an engine.

    Every component ref belongs to exactly one source. The ids a source assigns, for
    subscriptions, events, errors and set_parameter commands, start with the id of the
    engine that owns the component, so the engine can route them back.
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

    async def run(self, unit: CommandUnit) -> CompletedStatus:
        """Run one command until it ends, and return how it ended."""
        ...

    async def set_parameter(
        self,
        ref: str,
        parameters: Sequence[Parameter],
        on_completed: OnCompleted,
    ) -> SetParameterResult:
        """Start a set_parameter command. ``on_completed`` reports its end once."""
        ...

    async def get_parameter(self, ref: str) -> GetParameterResult:
        """The current parameter values of a component."""
        ...

    async def command_result(self, command_id: str) -> GetCommandResultResult:
        """The results of a command this source ran."""
        ...

    async def query(self, ref: str, query_type: str) -> QueryResult:
        """Answer a query of one component."""
        ...

    async def subscribe(self, ref: str, event_type: str, deliver: Deliver) -> SubscribeResult:
        """Subscribe to an event of one component. ``deliver`` receives each event."""
        ...

    async def unsubscribe(self, subscribe_id: str) -> None:
        """End a subscription. An unknown id is ignored."""
        ...

    async def event_detail(self, event_id: str) -> GetEventDetailResult:
        """The results of an event until it expires."""
        ...

    async def error_detail(self, error_id: str) -> GetErrorDetailResult:
        """The detail of an engine error."""
        ...
