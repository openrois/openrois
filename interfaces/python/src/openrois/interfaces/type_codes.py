"""The data_type_ref codes of the RoIS XML profiles and their Python types.

Annex A of the specification writes a data type as a URN such as
``urn:x-rois:def:DataType:ATR::Integer``. The 18 normative XML profiles use short codes
instead, twelve of them, with inconsistent case (``string`` and ``String``). The codec
keeps every code verbatim in ``data_type_ref.code`` and this table gives the Python type
of each known code. An unknown code, for example the ``Boolean`` or ``Set<String>`` of a
user-defined component, keeps its string and maps to ``Any``.

Source: OMG RoIS Framework 2.0, the XML profiles and Annex A (docs/rois-reference.md,
section 16).
"""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType
from typing import Any

from openrois.interfaces.common import ComponentStatus, StreamStatus
from openrois.interfaces.hri import DateTime, RoISIdentifier

_ARRAY_SUFFIX = "[]"

_SCALARS: Mapping[str, object] = MappingProxyType(
    {
        "string": str,
        "String": str,
        "int": int,
        "bool": bool,
        "RoISIdentifier": RoISIdentifier,
        "DateTime": DateTime,
        "Component_Status": ComponentStatus,
        "Stream_Status": StreamStatus,
    }
)

TYPE_CODES: Mapping[str, object] = MappingProxyType(
    {
        **_SCALARS,
        "string[]": list[str],
        "String[]": list[str],
        "int[]": list[int],
        "RoISIdentifier[]": list[RoISIdentifier],
    }
)
"""The twelve codes the normative profiles use, each with its Python type.

``RoISIdentifier`` maps to the identifier type, ``DateTime`` to the ISO 8601 string
type, and ``Component_Status`` and ``Stream_Status`` to their enumerations.
"""


def python_type(code: str) -> object:
    """The Python type of a ``data_type_ref`` code.

    ``string`` matches without regard to case. A trailing ``[]`` maps to a ``list`` of
    the item type. A code the table does not know maps to ``Any``.

    Args:
        code: The ``data_type_ref`` code, for example ``int`` or ``String[]``.

    Returns:
        The Python type, or ``typing.Any`` for an unknown code.
    """
    if code.endswith(_ARRAY_SUFFIX):
        return list[_scalar(code[: -len(_ARRAY_SUFFIX)])]  # type: ignore[misc]
    return _scalar(code)


def _scalar(code: str) -> Any:
    if code.lower() == "string":
        return str
    return _SCALARS.get(code, Any)


__all__ = ["TYPE_CODES", "python_type"]
