"""Record real gateway traffic into ``interfaces/fixtures/wire.json``.

Every interface package parses each recorded body into its generated model and writes it
back, so a model that cannot carry what a gateway really sends fails in its own tests. The
script drives one session through a gateway with the mock adapter behind it, and fails
unless the file ends up with the params and the result of every catalog method, every
notification, and everything in ``WANTED``.

The file is a list of ``{kind, method, body}``, where ``kind`` is ``params``, ``result`` or
``notification`` and ``body`` is the JSON the message carried there. Params are sent in the
full form of their model, with every field present and null where a field is unset, because
that is the form an engine writes results in. Every body then round trips with no field
added.

This needs the websockets package and openrois-interfaces.

Usage:
    python testing/conformance/capture.py [--url ws://127.0.0.1:8765] [--engine-id mock]
        [--timeout 60] [--event-timeout 20] [--output FILE]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections.abc import Iterator
from enum import Enum
from pathlib import Path
from typing import Any

from openrois.interfaces.catalog import (
    METHODS,
    METHODS_BY_NAME,
    NOTIFICATIONS,
    NOTIFICATIONS_BY_NAME,
)
from pydantic import BaseModel
from wire_check import (
    COMPLETED,
    NAVIGATION_URN,
    NOTIFY_ERROR,
    NOTIFY_EVENT,
    PROFILE_CHANGED,
    CheckFailed,
    Client,
    Message,
    Stack,
    check,
    command_ids,
    ref_is,
    wait_for_stack,
)

#: The file the interface packages read, from the root of the repository.
OUTPUT = Path(__file__).resolve().parents[2] / "interfaces" / "fixtures" / "wire.json"

#: What a plain session leaves out, each as ``Model.field`` for a field that must hold a value
#: and ``Enum.MEMBER`` for an enumerator. A model is only as proven as the bodies it reads, so
#: losing one of these from the recording has to stop the script.
WANTED = (
    "CommandUnit.arguments",
    "ConcurrentCommands.delay_time",
    "GetCommandResultResult.results",
    "CommandMessageProfile.arguments",
    "CommandMessageProfile.results",
    "CommandMessageProfile.timeout",
    "EventMessageProfile.arguments",
    "QueryMessageProfile.arguments",
    "CompletedStatus.ABORT",
    "CompletedStatus.ERROR",
    "CompletedStatus.OUT_OF_RESOURCES",
    "CompletedStatus.TIMEOUT",
    "ReturnCode.BAD_PARAMETER",
    "ReturnCode.ERROR",
    "ReturnCode.OUT_OF_RESOURCES",
    "ReturnCode.UNSUPPORTED",
)

#: The statuses that mock/fault ends a command with on request. ABORT is left to a release,
#: since that is how a running command really ends with it.
FAILURES = ("ERROR", "OUT_OF_RESOURCES", "TIMEOUT")


def filled(value: object) -> Iterator[str]:
    """``Model.field`` of each field with a value and ``Enum.MEMBER`` of each enumerator."""
    if isinstance(value, BaseModel):
        for name in type(value).model_fields:
            field = getattr(value, name)
            # A zero is a value, unlike an empty list.
            if field not in (None, "", [], {}):
                yield f"{type(value).__name__}.{name}"
            yield from filled(field)
    elif isinstance(value, Enum):
        yield f"{type(value).__name__}.{value.name}"
    elif isinstance(value, dict):
        for item in value.values():
            yield from filled(item)
    elif isinstance(value, list | tuple):
        for item in value:
            yield from filled(item)


def text_argument(name: str, value: str) -> Message:
    """An argument of a mock/fault command."""
    return {"name": name, "data_type_ref": "string", "value": value}


class Recorder:
    """Collects the bodies of one session in the order they travelled."""

    def __init__(self) -> None:
        self.entries: list[Message] = []
        self.filled: set[str] = set()

    def add(self, kind: str, method: str, body: Message, model: type[BaseModel]) -> None:
        """Keep a body, which must read back unchanged through its catalog model."""
        parsed = model.model_validate(body)
        written = parsed.model_dump(mode="json")
        check(written == body, f"{method} {kind} did not round trip: {body} became {written}")
        self.entries.append({"kind": kind, "method": method, "body": body})
        self.filled.update(filled(parsed))

    async def call(
        self, client: Client, method: str, *, expect: str = "OK", **params: Any
    ) -> Message:
        """Send a request in the full form of its model, and keep it with its result."""
        spec = METHODS_BY_NAME[method]
        sent = spec.params.model_validate(params).model_dump(mode="json")
        result = await client.call(method, **sent)
        check(result["return_code"] == expect, f"{method} answered {result}, not {expect}")
        self.add("params", method, sent, spec.params)
        self.add("result", method, result, spec.result)
        return result

    def notification(self, method: str, body: Message) -> None:
        """Keep the params of a notification."""
        self.add("notification", method, body, NOTIFICATIONS_BY_NAME[method].params)

    def missing(self) -> list[str]:
        """What the entries lack: ``kind method`` from the catalog, then from ``WANTED``."""
        seen = {(entry["kind"], entry["method"]) for entry in self.entries}
        wanted = [(kind, spec.method) for spec in METHODS for kind in ("params", "result")]
        wanted += [("notification", spec.method) for spec in NOTIFICATIONS]
        absent = [f"{kind} {method}" for kind, method in wanted if (kind, method) not in seen]
        return absent + [item for item in WANTED if item not in self.filled]

    async def ended(self, client: Client, stack: Stack, command_id: str, status: str) -> None:
        """Wait for a command to end with ``status``, and keep its notification."""
        ended = await client.completed(command_id, stack.event_timeout)
        check(ended == status, f"{command_id} ended {ended}, not {status}")
        self.notification(
            COMPLETED, next(p for p in client.sent(COMPLETED) if p["command_id"] == command_id)
        )


async def discovery(recorder: Recorder, client: Client, stack: Stack) -> None:
    """Connect, read the profile, and find and hold navigation."""
    await recorder.call(client, "rois.system.connect")
    await recorder.call(client, "rois.system.get_profile", condition="")
    # A refused get_profile carries a null profile, a shape no successful result has.
    await recorder.call(
        client, "rois.system.get_profile", condition="nonsense !! 1", expect="BAD_PARAMETER"
    )
    await recorder.call(
        client, "rois.command.search", condition=f"component_type = '{NAVIGATION_URN}'"
    )
    await recorder.call(client, "rois.command.bind_any", condition=ref_is(stack.navigation))
    await recorder.call(client, "rois.command.release", component_ref=stack.navigation)
    await recorder.call(client, "rois.command.bind", component_ref=stack.navigation)
    async with stack.session(handshake=False) as other:
        await recorder.call(other, "rois.command.search", condition="", expect="ERROR")
        await other.ok("rois.system.connect")
        await recorder.call(
            other, "rois.command.bind", component_ref=stack.navigation, expect="OUT_OF_RESOURCES"
        )


async def commands(recorder: Recorder, client: Client, stack: Stack) -> None:
    """Set a parameter, run one full sequence, and end commands every way but OK."""
    await client.ok("rois.command.bind", component_ref=stack.detection)
    await client.ok("rois.command.bind", component_ref=stack.fault)
    await recorder.call(client, "rois.command.get_parameter", component_ref=stack.navigation)
    changed = await recorder.call(
        client,
        "rois.command.set_parameter",
        component_ref=stack.navigation,
        parameters=[{"name": "target_positions", "data_type_ref": "string[]", "value": '["home"]'}],
    )
    await client.completed(changed["command_id"], stack.event_timeout)
    # The interface packages read the execute params as one sequence that shows a command and
    # a group, so everything an execute can carry goes into this one call.
    result = await recorder.call(
        client,
        "rois.command.execute",
        command_unit_list=[
            {"component_ref": stack.detection, "command_type": "start", "delay_time": 1},
            {
                "branch_list": [
                    {
                        "command_list": [
                            {"component_ref": stack.detection, "command_type": "suspend"},
                            {"component_ref": stack.detection, "command_type": "resume"},
                        ]
                    },
                    {"command_list": [{"component_ref": stack.navigation, "command_type": "stop"}]},
                ],
                "delay_time": 1,
            },
            {
                "component_ref": stack.fault,
                "command_type": "echo",
                "arguments": [text_argument("text", "hello")],
            },
        ],
    )
    ids = command_ids(result)
    for command_id in ids[1:]:
        status = await client.completed(command_id, stack.event_timeout)
        check(status == "OK", f"{command_id} ended {status}")
    await recorder.ended(client, stack, ids[0], "OK")
    await recorder.call(client, "rois.command.get_command_result", command_id=ids[0], condition="")
    await recorder.call(client, "rois.command.get_command_result", command_id=ids[-1], condition="")
    for status in FAILURES:
        [failed] = await client.execute(
            {
                "component_ref": stack.fault,
                "command_type": "end_with",
                "arguments": [text_argument("status", status)],
            }
        )
        await recorder.ended(client, stack, failed, status)
    [running] = await client.execute({"component_ref": stack.navigation, "command_type": "start"})
    await client.ok("rois.command.release", component_ref=stack.navigation)
    await recorder.ended(client, stack, running, "ABORT")


async def queries_and_events(recorder: Recorder, client: Client, stack: Stack) -> None:
    """Run a query, have one refused, and receive and read one event."""
    await recorder.call(
        client,
        "rois.query.query",
        query_type="robot_position",
        condition=ref_is(stack.information),
    )
    await recorder.call(
        client,
        "rois.query.query",
        query_type="no_such_query",
        condition="",
        expect="UNSUPPORTED",
    )
    await recorder.call(
        client, "rois.query.query", query_type="echo", condition="text = 'hello'"
    )
    subscribed = await recorder.call(
        client,
        "rois.event.subscribe",
        event_type="person_detected",
        condition=ref_is(stack.detection),
    )
    event = await client.notification(
        NOTIFY_EVENT,
        lambda p: p["subscribe_id"] == subscribed["subscribe_id"],
        stack.event_timeout,
    )
    recorder.notification(NOTIFY_EVENT, event)
    await recorder.call(
        client, "rois.event.get_event_detail", event_id=event["event_id"], condition=""
    )
    await recorder.call(client, "rois.event.unsubscribe", subscribe_id=subscribed["subscribe_id"])


async def faults(recorder: Recorder, client: Client, stack: Stack) -> None:
    """Make a profile change, then an error, through mock/fault."""
    # An engine refuses every command of a component in ERROR, so the profile change comes
    # first and nothing has to wait for the error to clear.
    [joined] = await client.execute({"component_ref": stack.fault, "command_type": "peer_join"})
    await client.until(
        lambda: len(client.sent(PROFILE_CHANGED)) >= 2,
        stack.event_timeout,
        "second profile_changed",
    )
    recorder.notification(PROFILE_CHANGED, client.sent(PROFILE_CHANGED)[0])
    await client.completed(joined, stack.event_timeout)
    await client.execute({"component_ref": stack.fault, "command_type": "raise_error"})
    error = await client.notification(NOTIFY_ERROR, lambda _: True, stack.event_timeout)
    recorder.notification(NOTIFY_ERROR, error)
    await recorder.call(
        client, "rois.system.get_error_detail", error_id=error["error_id"], condition=""
    )


async def capture(stack: Stack, timeout: float, output: Path) -> None:
    """Run the session and write the fixture."""
    await wait_for_stack(stack, timeout)
    recorder = Recorder()
    async with stack.session(handshake=False) as client:
        await discovery(recorder, client, stack)
        await commands(recorder, client, stack)
        await queries_and_events(recorder, client, stack)
        await faults(recorder, client, stack)
        await recorder.call(client, "rois.system.disconnect")
    missing = recorder.missing()
    check(not missing, f"not recorded: {', '.join(missing)}")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(recorder.entries, indent=2, ensure_ascii=False) + "\n")
    print(f"Wrote {len(recorder.entries)} entries to {output}")


def main() -> None:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--url", default="ws://127.0.0.1:8765")
    parser.add_argument("--engine-id", default="mock", help="engine id of the mock adapter")
    parser.add_argument("--timeout", type=float, default=60.0, help="seconds to wait for the stack")
    parser.add_argument("--event-timeout", type=float, default=20.0)
    parser.add_argument("--output", type=Path, default=OUTPUT, help="the file to write")
    args = parser.parse_args()
    stack = Stack(args.url, args.engine_id, args.event_timeout)
    try:
        asyncio.run(capture(stack, args.timeout, args.output))
    except (CheckFailed, OSError, TimeoutError) as exc:
        print(f"FAIL {exc or type(exc).__name__}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
