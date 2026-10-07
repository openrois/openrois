"""The Component base class and what it needs from the engine that hosts it.

A component is a subclass of Component declared with ``@component(profile)``. Its author
writes handlers for the messages it supports and reads two things the engine binds at
registration: ``self.parameters``, the current parameter values, and ``self.emit``,
which sends an event to the clients that subscribed.

The methods whose names start with ``rois_`` are the side the engine calls. An engine
that hosts components written with this SDK calls them to read the served profile, bind
itself, run commands and queries, start subscriptions and apply new parameter values.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from types import MappingProxyType
from typing import Any, ClassVar, Protocol

from openrois.interfaces.hri import Argument, Parameter, Result
from openrois.interfaces.profiles import (
    CommandMessageProfile,
    HRIComponentProfile,
    MessageProfile,
)
from openrois.interfaces.service import CompletedStatus
from openrois.interfaces.values import decode_value, encode_value

from openrois.components.core._spec import ComponentSpec


class CommandFailed(Exception):  # noqa: N818, the name says what happened to the command.
    """Raised by a command handler to end its command with a status other than OK.

    Any other exception ends the command with ERROR.

    Attributes:
        status: How the command ended: ERROR, ABORT, OUT_OF_RESOURCES or TIMEOUT.
    """

    def __init__(self, status: CompletedStatus = CompletedStatus.ERROR, message: str = "") -> None:
        if status is CompletedStatus.OK:
            raise ValueError("A failed command cannot end with OK")
        super().__init__(message or status.value)
        self.status = status


class EngineBinding(Protocol):
    """What a component needs from the engine that hosts it.

    The engine passes an object of this shape to ``Component.rois_bind`` when it
    registers the component.
    """

    @property
    def ref(self) -> str:
        """The fully qualified ref of the component, ``engine_id/name``."""
        ...

    def parameters(self) -> Sequence[Parameter]:
        """The current value of every parameter of the component."""
        ...

    def emit(self, event_type: str, results: Sequence[Result]) -> None:
        """Send an event to its subscriptions. Safe to call from any thread."""
        ...


class Component:
    """Base class of a RoIS HRI Component.

    Subclass it, declare the profile with ``@component``, and write handlers::

        @component(NAVIGATION_PROFILE)
        class Navigation(Component):
            @invoke("start")
            async def start(self) -> dict[str, object]:
                target = self.parameters["target_positions"][0]
                await self._robot.go_to(target)
                self.emit("reached_target", target=target, is_final_target=True)
                return {}

            @subscribe("reached_target")
            async def reached_target(self) -> None:
                pass  # start emits the event when the robot arrives.

    A command handler runs for as long as the command lasts. It takes the arguments of
    its command by name, converted from their profile types, and returns the values of
    the command's results by name, or None. Raising CommandFailed ends the command with
    the status it names, and any other exception ends it with ERROR. A query handler
    returns the values of the query's results the same way.

    The engine calls ``connect()`` before the component takes requests and
    ``disconnect()`` when it stops. Override them to open and close the connection to
    the backend.
    """

    # Set by @component on the class it declares.
    __rois_spec__: ClassVar[ComponentSpec | None] = None

    # Set by rois_bind when the engine registers the component.
    _rois_binding: EngineBinding | None = None

    # -- For component authors ---------------------------------------------------------

    @property
    def ref(self) -> str:
        """The fully qualified ref the engine registered the component under."""
        return self._binding().ref

    @property
    def parameters(self) -> Mapping[str, Any]:
        """The current parameter values, converted from their profile types.

        A ``string[]`` parameter reads as a list of str and an ``int`` as an int. The
        engine stores the values and changes them on ``set_parameter``. A parameter with
        no value yet, because its profile gives no default and no client has set it, is
        missing from the mapping.
        """
        types = {p.name: p.data_type_ref.code for p in self._spec().declared.parameter_profiles}
        return MappingProxyType(
            {
                p.name: decode_value(types.get(p.name, p.data_type_ref), p.value)
                for p in self._binding().parameters()
                if p.value != ""
            }
        )

    def emit(self, event_type: str, **values: object) -> None:
        """Send an event to the clients that subscribed to it.

        The values are the event's results by name, converted to their profile types. A
        result left out is not sent. Safe to call from any thread, for example a ROS 2
        callback.

        Raises:
            ValueError: The component does not serve the event, or a value has no result
                of that name or does not fit its type.
            RuntimeError: No engine hosts the component yet.
        """
        spec = self._spec()
        if event_type not in spec.events:
            raise ValueError(
                f"{type(self).__qualname__} does not serve the event {event_type!r}. "
                "Mark it with @subscribe"
            )
        message = _message(spec.served.event_profiles, event_type)
        self._binding().emit(event_type, _results(message, values))

    async def connect(self) -> None:
        """Open the connection to the backend. The default does nothing."""

    async def disconnect(self) -> None:
        """Close the connection to the backend. The default does nothing."""

    # -- Called by the engine ----------------------------------------------------------

    @classmethod
    def rois_profile(cls) -> HRIComponentProfile:
        """The profile the engine serves for this class: what it implements."""
        return cls._spec().served

    def rois_bind(self, binding: EngineBinding) -> None:
        """Attach the engine that hosts this component."""
        self._rois_binding = binding

    async def rois_command(
        self,
        command_type: str,
        arguments: Sequence[Argument] = (),
    ) -> list[Result]:
        """Run one command until it completes, and return its results.

        ``stop`` without a handler returns at once: the engine aborts the running
        command itself.

        Raises:
            CommandFailed: The handler ended the command with another status.
            ValueError: The component does not serve the command, or an argument does
                not fit its profile.
        """
        spec = self._spec()
        message = _message(spec.served.command_profiles, command_type)
        method = spec.commands.get(command_type)
        if method is None:
            return []
        values = await getattr(self, method)(**_arguments(message, arguments))
        return _results(message, values)

    async def rois_query(self, query_type: str) -> list[Result]:
        """Answer one query with its results.

        Raises:
            ValueError: The component has no handler for the query.
        """
        spec = self._spec()
        method = spec.queries.get(query_type)
        if method is None:
            raise ValueError(f"{type(self).__qualname__} does not answer {query_type!r}")
        message = _message(spec.served.query_profiles, query_type)
        return _results(message, await getattr(self, method)())

    async def rois_subscribed(self, event_type: str) -> None:
        """Run the @subscribe method of an event for a new subscription.

        Raises:
            ValueError: The component does not serve the event.
        """
        method = self._spec().events.get(event_type)
        if method is None:
            raise ValueError(f"{type(self).__qualname__} does not serve {event_type!r}")
        await getattr(self, method)()

    async def rois_set_parameters(self, parameters: Sequence[Parameter]) -> None:
        """Run the @on_set_parameter hook with new values, before the engine stores them.

        Without a hook this returns at once. An exception from the hook refuses the
        values, and the engine keeps the old ones.

        Raises:
            ValueError: A parameter is not in the profile or its value does not fit.
        """
        spec = self._spec()
        if spec.set_parameter_hook is None:
            return
        types = {p.name: p.data_type_ref.code for p in spec.declared.parameter_profiles}
        values: dict[str, Any] = {}
        for parameter in parameters:
            if parameter.name not in types:
                raise ValueError(f"The profile defines no parameter {parameter.name!r}")
            values[parameter.name] = decode_value(types[parameter.name], parameter.value)
        await getattr(self, spec.set_parameter_hook)(MappingProxyType(values))

    # -- Internals ---------------------------------------------------------------------

    @classmethod
    def _spec(cls) -> ComponentSpec:
        spec = cls.__rois_spec__
        if spec is None:
            raise TypeError(f"{cls.__qualname__} is not declared with @component(profile)")
        return spec

    def _binding(self) -> EngineBinding:
        if self._rois_binding is None:
            raise RuntimeError(f"No engine hosts this {type(self).__qualname__} yet")
        return self._rois_binding


def _message[M: MessageProfile](messages: Sequence[M], name: str) -> M:
    """The message profile of one name, among the served ones."""
    for message in messages:
        if message.name == name:
            return message
    raise ValueError(f"The component does not serve {name!r}")


def _arguments(message: CommandMessageProfile, arguments: Sequence[Argument]) -> dict[str, Any]:
    """The arguments of a command by name, converted from their profile types."""
    types = {a.name: a.data_type_ref.code for a in message.arguments}
    values: dict[str, Any] = {}
    for argument in arguments:
        if argument.name not in types:
            raise ValueError(f"The command {message.name!r} has no argument {argument.name!r}")
        values[argument.name] = decode_value(types[argument.name], argument.value)
    return values


def _results(message: MessageProfile, values: object) -> list[Result]:
    """The results of a message from their values by name, in the order of the profile."""
    if values is None:
        return []
    if not isinstance(values, Mapping):
        raise TypeError(
            f"A handler of {message.name!r} returns its result values by name, or None, "
            f"not {type(values).__name__}"
        )
    declared = {r.name for r in message.results}
    unknown = sorted(set(values) - declared)
    if unknown:
        raise ValueError(f"{message.name!r} has no result named {', '.join(unknown)}")
    return [
        Result(
            name=r.name,
            data_type_ref=r.data_type_ref.code,
            value=encode_value(r.data_type_ref.code, values[r.name]),
        )
        for r in message.results
        if r.name in values
    ]
