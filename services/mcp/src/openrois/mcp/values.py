"""Plain JSON values from an agent to RoIS strings, and back.

An agent writes ``{"target_positions": ["kitchen"]}``. RoIS carries every value as a
string with its type in ``data_type_ref``, and the type comes from the component profile,
so the agent never writes either.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from enum import Enum
from typing import Any

from openrois.interfaces import Parameter, Result
from openrois.interfaces.profiles import ParameterProfile
from openrois.interfaces.values import decode_value, encode_value


class ValueRefusedError(ValueError):
    """A value the profile does not accept, named so the agent can fix it.

    Attributes:
        name: The parameter or argument.
        reason: Why it was refused.
    """

    def __init__(self, name: str, reason: str) -> None:
        super().__init__(f"{name}: {reason}")
        self.name = name
        self.reason = reason


def encode(
    values: Mapping[str, object],
    profiles: Sequence[ParameterProfile],
    *,
    refuse_read_only: bool = False,
) -> list[dict[str, str]]:
    """Write named values as RoIS name, data_type_ref and value strings.

    Args:
        values: The values by name, as JSON values or their RoIS string forms.
        profiles: The parameter or argument profiles that type them.
        refuse_read_only: Refuse a parameter the profile marks read-only.

    Raises:
        ValueRefusedError: A name the profile does not declare, a read-only parameter, or a
            value that does not fit its type.
    """
    by_name = {profile.name: profile for profile in profiles}
    items: list[dict[str, str]] = []
    for name, value in values.items():
        profile = by_name.get(name)
        if profile is None:
            known = ", ".join(sorted(by_name)) or "none"
            raise ValueRefusedError(name, f"not declared by the profile (declared: {known})")
        if refuse_read_only and profile.read_only:
            raise ValueRefusedError(name, "read-only")
        data_type = profile.data_type_ref.code
        try:
            text = encode_value(data_type, value)
        except ValueError as exc:
            raise ValueRefusedError(name, f"not a {data_type} value ({exc})") from exc
        items.append({"name": name, "data_type_ref": data_type, "value": text})
    return items


def decode(items: Sequence[Result | Parameter]) -> list[dict[str, Any]]:
    """Read results or parameters as name, type and a JSON value.

    A value that does not fit its declared type stays the string it arrived as, so a
    faulty component still shows what it sent.
    """
    decoded: list[dict[str, Any]] = []
    for item in items:
        value: Any
        try:
            value = decode_value(item.data_type_ref, item.value)
        except ValueError:
            value = item.value
        if isinstance(value, list):
            value = [_plain(entry) for entry in value]
        decoded.append({"name": item.name, "type": item.data_type_ref, "value": _plain(value)})
    return decoded


def _plain(value: object) -> object:
    """An enum member as its value, so it serializes as JSON."""
    return value.value if isinstance(value, Enum) else value
