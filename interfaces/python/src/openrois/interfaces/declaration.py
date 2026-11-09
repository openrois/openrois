"""Declare a user-defined component in Python and get its RoIS profile.

Annex C of the specification shows components that a vendor or an integrator defines
for itself: a wheelchair, a speech recognizer configured by a grammar, an arm that
approaches a pose. A ``ComponentDeclaration`` names such a component in Python. From it
``profile()`` builds the ``HRIComponentProfile`` that the engine serves and a
component class declares, and ``to_xml()`` writes the XML profile.

    WHEELCHAIR = ComponentDeclaration(
        identifier="urn:x-rois:def:component:ACME::Wheelchair",
        name="wheelchair",
        function="actuation",
        commands=[Command("brake", arguments=[Param("status", "Boolean")])],
        queries=[Query("wc_status_change", results=[Param("brake_status", "Boolean")])],
        events=[Event("wc_status_change", results=[Param("brake_status", "Boolean")])],
        parameters=[Param("preferred_max_speed", "Double")],
    )

The RoSO function (``sensing``, ``actuation`` or ``function``) sets the default bind
cardinality the engine applies. A declaration includes the RoIS_Common profile (start,
stop, suspend, resume and component_status) unless it names other sub-profiles or none.
Message names are unique per kind only, so a query and an event may share a name, and
any ``data_type_ref`` code is accepted: ``openrois.interfaces.type_codes`` maps an
unknown one to ``Any``.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from openrois.interfaces.components.standard_profiles import ROIS_COMMON_URN, standard_registry
from openrois.interfaces.profiles import (
    CommandMessageProfile,
    ComponentFunction,
    EventMessageProfile,
    HRIComponentProfile,
    MessageProfile,
    ParameterProfile,
    QueryMessageProfile,
    RoISIdentifierType,
)
from openrois.interfaces.values import encode_value
from openrois.interfaces.xmlcodec import (
    ProfileRegistry,
    UnresolvedProfileError,
    parse_urn,
    resolve_profile,
    write_component_profile,
)


class DeclarationError(ValueError):
    """The declaration breaks a rule of the RoIS profile model."""


@dataclass(frozen=True, slots=True)
class Param:
    """A parameter, an argument or a result.

    Attributes:
        name: The name.
        type: The ``data_type_ref`` code, for example ``int``, ``string[]`` or a code of
            the component's own such as ``NbestType``.
        description: A human-readable description.
        default: The default value of a component parameter, or None for no default. A
            value that is not a string is written in its string form by its type
            (``openrois.interfaces.values``).
        read_only: True for a component parameter that get_parameter returns and
            set_parameter refuses.
    """

    name: str
    type: str
    description: str = ""
    default: object = None
    read_only: bool = False

    def profile(self) -> ParameterProfile:
        """The ParameterProfile of this parameter."""
        default = self.default
        if default is not None and not isinstance(default, str):
            try:
                default = encode_value(self.type, default)
            except ValueError as error:
                raise DeclarationError(f"Default of {self.name!r}: {error}") from error
        return ParameterProfile(
            name=self.name,
            data_type_ref=RoISIdentifierType(code=self.type),
            default_value=default,
            description=self.description,
            read_only=self.read_only,
        )


def _unique(kind: str, names: Sequence[str]) -> None:
    seen: set[str] = set()
    for name in names:
        if name in seen:
            raise DeclarationError(f"Two {kind} named {name!r}")
        seen.add(name)


@dataclass(frozen=True, slots=True)
class _Message:
    name: str
    arguments: Sequence[Param] = ()
    results: Sequence[Param] = ()

    def __post_init__(self) -> None:
        _unique(f"arguments of {self.name!r}", [a.name for a in self.arguments])
        _unique(f"results of {self.name!r}", [r.name for r in self.results])

    def _arguments(self) -> list[ParameterProfile]:
        return [a.profile() for a in self.arguments]

    def _results(self) -> list[ParameterProfile]:
        return [r.profile() for r in self.results]


@dataclass(frozen=True, slots=True)
class Command(_Message):
    """A command message: its arguments, results and timeout in milliseconds."""

    timeout: int | None = None

    def profile(self) -> CommandMessageProfile:
        """The CommandMessageProfile of this command."""
        return CommandMessageProfile(
            name=self.name,
            arguments=self._arguments(),
            results=self._results(),
            timeout=self.timeout,
        )


@dataclass(frozen=True, slots=True)
class Query(_Message):
    """A query message: its results, and the arguments that select them."""

    def profile(self) -> QueryMessageProfile:
        """The QueryMessageProfile of this query."""
        return QueryMessageProfile(
            name=self.name, arguments=self._arguments(), results=self._results()
        )


@dataclass(frozen=True, slots=True)
class Event(_Message):
    """An event message: its results, and the arguments a subscription selects."""

    def profile(self) -> EventMessageProfile:
        """The EventMessageProfile of this event."""
        return EventMessageProfile(
            name=self.name, arguments=self._arguments(), results=self._results()
        )


@dataclass(frozen=True, slots=True)
class ComponentDeclaration:
    """A user-defined component, declared in Python.

    Attributes:
        identifier: The URN of the component type, for example
            ``urn:x-rois:def:component:ACME::Wheelchair``.
        name: The gml:name of the profile, for example ``wheelchair``.
        function: The RoSO function class: ``sensing``, ``actuation`` or ``function``.
        commands: The component's own command messages.
        queries: The component's own query messages.
        events: The component's own event messages.
        parameters: The parameters get_parameter and set_parameter exchange.
        sub_profiles: URNs of the profiles the component includes. RoIS_Common unless
            given, and none when empty.
    """

    identifier: str
    name: str
    function: ComponentFunction | str
    commands: Sequence[Command] = ()
    queries: Sequence[Query] = ()
    events: Sequence[Event] = ()
    parameters: Sequence[Param] = ()
    sub_profiles: Sequence[str] = field(default=(ROIS_COMMON_URN,))

    def __post_init__(self) -> None:
        try:
            ComponentFunction(self.function)
        except ValueError:
            kinds = ", ".join(f.value for f in ComponentFunction)
            raise DeclarationError(
                f"function {self.function!r} is not one of {kinds}"
            ) from None
        _unique("commands", [c.name for c in self.commands])
        _unique("queries", [q.name for q in self.queries])
        _unique("events", [e.name for e in self.events])
        _unique("parameters", [p.name for p in self.parameters])

    def own_profile(self) -> HRIComponentProfile:
        """The profile with the component's own messages only, as its XML file lists them."""
        return HRIComponentProfile(
            identifier=parse_urn(self.identifier),
            name=self.name,
            function=ComponentFunction(self.function),
            sub_component_profiles=list(self.sub_profiles),
            command_profiles=[c.profile() for c in self.commands],
            query_profiles=[q.profile() for q in self.queries],
            event_profiles=[e.profile() for e in self.events],
            parameter_profiles=[p.profile() for p in self.parameters],
        )

    def profile(self, registry: ProfileRegistry | None = None) -> HRIComponentProfile:
        """The full profile: the messages of the sub-profiles first, then the own ones.

        Args:
            registry: Where the sub-profiles are looked up. The 18 standard profiles
                when not given.

        Raises:
            DeclarationError: A sub-profile is unknown, or an own message repeats the
                name of a message a sub-profile already defines.
        """
        own = self.own_profile()
        registry = registry if registry is not None else standard_registry()
        try:
            inherited = resolve_profile(
                own.model_copy(
                    update={"command_profiles": [], "query_profiles": [], "event_profiles": []}
                ),
                registry,
            )
        except UnresolvedProfileError as error:
            raise DeclarationError(str(error)) from error
        _not_redeclared("command", inherited.command_profiles, own.command_profiles)
        _not_redeclared("query", inherited.query_profiles, own.query_profiles)
        _not_redeclared("event", inherited.event_profiles, own.event_profiles)
        return resolve_profile(own, registry)

    def to_xml(self, registry: ProfileRegistry | None = None) -> bytes:
        """The XML profile of the component, listing its own messages only."""
        registry = registry if registry is not None else standard_registry()
        return write_component_profile(self.profile(registry), registry=registry)


def _not_redeclared(
    kind: str, inherited: Sequence[MessageProfile], own: Sequence[MessageProfile]
) -> None:
    names = {m.name for m in inherited}
    for message in own:
        if message.name in names:
            raise DeclarationError(
                f"The {kind} {message.name!r} is already defined by a sub-profile"
            )


__all__ = [
    "Command",
    "ComponentDeclaration",
    "DeclarationError",
    "Event",
    "Param",
    "Query",
]
