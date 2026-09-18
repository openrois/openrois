# Adapter Template

A starting point for connecting your own robot, avatar, or service to OpenRoIS.

An adapter is a sub HRI Engine: it hosts an `Engine`, registers the components it
implements, and connects out to a gateway with `WsClient`. The gateway then presents your
platform to every RoIS client through the same standard interfaces as any other.

## Install

The Python packages are not published yet, so install them from a clone of the
repository:

```bash
pip install -e ./interfaces/python
pip install -e ./components/core
pip install -e ./core
```

## Use the Template

1. Copy this directory onto the machine that can reach your robot's API.

2. Copy the profile and declare your engine and components:

```bash
cp openrois-profile.yaml.example openrois-profile.yaml
```

```yaml title="openrois-profile.yaml"
engine:
  id: my_robot
  platform: my_platform
  gateway_url: "ws://127.0.0.1:8765"

components: {}
```

The `components` mapping passes per-component configuration (an API host, a topic name, a
device path) to each component constructor. Leave it empty if there is nothing to
configure.

3. Edit `my_adapter.py`. Each `@component` class has `@query`, `@invoke`, and `@subscribe`
   methods marked `# IMPLEMENT YOUR CODE HERE #`. Replace the `NotImplementedError` with
   calls to your platform's native API (ROS 2 topics and services, HTTP, gRPC, serial) and
   return `Result` lists built with the `results` helpers.

```python
@query("robot_position")
async def robot_position(self):
    pose = await self._api.get_position()
    return results.position(x=pose.x, y=pose.y, theta=pose.theta)
```

4. Start a gateway, then run the adapter:

```bash
python my_adapter.py --config openrois-profile.yaml
```

The adapter connects to the gateway, registers its components, and answers RoIS calls.
Verify it with [`examples/hri-client`](../hri-client/README.md), which lists every
registered component and lets you run its queries, commands, and events.

## How Registration Works

```python
for cls in COMPONENT_CLASSES:
    meta = meta_from_decorators(cls)
    engine.register_component(meta.ref, cls(component_config(profile, meta.ref)), meta)
```

`meta_from_decorators` reads the decorators and builds the component profile the gateway
publishes, so the declaration in your code is the single source of truth. Components own
their backend connections: open them in `connect()`, close them in `disconnect()`.

## Keep It Conformant

Use the normative RoIS component names, and the message and parameter names from the RoIS
component profiles. An adapter that invents its own names still runs, but applications
written against the standard will not find what they expect. See
[components and adapters](https://openrois.org/docs/guides/components-and-adapters) and
the [component reference](https://openrois.org/docs/reference/components).

## Learn More

- [Component framework](../../components/core/README.md)
- [Engine core](../../core/README.md)
- [Working example](../mock-adapter/README.md)
