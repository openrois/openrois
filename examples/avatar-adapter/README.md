# Avatar Adapter

A virtual agent behind the same RoIS interfaces as a robot. It has no body and no camera:
`SpeechSynthesis` speaks by logging the text and completes the command when the speech
would end, `Reaction` performs an expression the same way, and `SystemInformation` reports
a virtual position.

Its purpose is the mixed-paradigm demonstration: an application that drives a robot's
`SpeechSynthesis` drives this one with the same calls, and cannot tell which is which. See
[`examples/mixed-paradigm`](../mixed-paradigm/README.md).

## Install

```bash
# From the repository root. The packages are not published yet.
pip install -e ./interfaces/python
pip install -e ./components/core
pip install -e ./core
```

## Run

```bash
# 1. Start a gateway:  openrois-gateway
# 2. Then, in another terminal:
python avatar_adapter.py --config openrois-profile.yaml
```

Point [`examples/hri-client`](../hri-client/README.md) at the gateway: the avatar appears as
engine `avatar_1` with its three components. Set `speech_text` on `SpeechSynthesis`,
execute, and watch the adapter log the speech and the client receive
`rois.command.completed`.

## Components

| Component | Behavior |
|-----------|----------|
| `SpeechSynthesis` | `set_parameter` stores `speech_text` and `volume`, `execute` or `start` speaks (logs) and completes after 50 ms per character, `component_status` is `BUSY` meanwhile |
| `Reaction` | `set_parameter` stores `reaction_ref`, `execute` performs it (logs) and completes after half a second, `get_parameter` returns it |
| `SystemInformation` | `robot_position` at the origin, `engine_status` and `component_status` `READY` |

All three pass the [conformance suite](../../components/core/README.md#check-conformance).

A graphical avatar (Unity, Godot, or a browser) replaces the logging with rendering and
keeps everything else.
