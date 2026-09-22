# Mixed-Paradigm Demonstration

A physical robot and a virtual agent behind one gateway, controlled by one application
that does not know which is which.

`demo.py` starts a gateway in-process, connects the [mock robot adapter](../mock-adapter/README.md)
(engine `robot_1`, a simulated robot with `Navigation`, `SpeechSynthesis`, and more) and the
[avatar adapter](../avatar-adapter/README.md) (engine `avatar_1`, a text-based virtual agent
with `SpeechSynthesis` and `Reaction`), then plays a service application that discovers the
components of both, queries both positions, and makes both say the same sentence with
identical `set_parameter` and `execute` calls, waiting for both `rois.command.completed`.

```bash
# From the repository root, after installing the Python packages from source.
python examples/mixed-paradigm/demo.py
```

```
demo: Components: robot_1/SystemInformation, robot_1/Navigation, ..., avatar_1/SpeechSynthesis, avatar_1/Reaction
demo: robot_1/SystemInformation is at {'x': '3.2', 'y': '1.8', 'theta': '0.5'}
demo: avatar_1/SystemInformation is at {'x': '0.0', 'y': '0.0', 'theta': '0.0'}
mock: [robot] says: Hello from OpenRoIS
avatar: [Mia] says (volume 100): Hello from OpenRoIS
demo: robot_1/SpeechSynthesis completed say-1: OK
demo: avatar_1/SpeechSynthesis completed say-1: OK
```

The application's code addresses components by ref only. Swap the mock robot for the
Kachaka adapter, or the text avatar for a Unity character, and the application does not
change. Both sides here are simulated, which is the point of a demonstration that runs on
any laptop; the same script runs against real adapters connected to a real gateway.

To see it in the browser, start `openrois-gateway`, run the two adapters against it, and
open [`examples/hri-client`](../hri-client/README.md): two engine groups appear, and the
same `SpeechSynthesis` panel drives either.
