# OpenRoIS Adapter Template

A starting point for writing your own OpenRoIS adapter.

## Quick start

1. Install the adapter SDK:

```bash
pip install openrois-adapter-sdk
```

2. Copy this directory to your robot's machine.

3. Copy `profile.yaml.example` to `profile.yaml` and edit it to declare
   your robot's components.

4. Edit `my_adapter.py` and fill in the `# IMPLEMENT YOUR CODE HERE #`
   blocks with your robot's API calls.

5. Run the adapter:

```bash
python my_adapter.py --config profile.yaml
```

The adapter connects to the avatar's WebSocket server, registers its
components, and starts responding to RoIS JSON-RPC requests from
operators.

## What to fill in

Each `@component` class has `@query`, `@invoke`, and `@subscribe` methods
marked with `# IMPLEMENT YOUR CODE HERE #`. Replace the
`NotImplementedError` with calls to your robot's native API (ROS 2
topics/services, HTTP endpoints, gRPC, serial, etc.) and return `Result`
lists using the `results` helpers.

For example, to implement `robot_position`:

```python
@query("robot_position")
async def robot_position(self):
    # IMPLEMENT YOUR CODE HERE
    # Call your robot's API to get the position.
    pose = await self.parent.robot_api.get_position()
    return results.position(x=pose.x, y=pose.y, theta=pose.theta)
```

## Config file

The `profile.yaml` file declares your robot's components, their access
policies, and the connection info for the avatar. See
`profile.yaml.example` for the format.

## Learn more

- [openrois-adapter-sdk README](../../sdk/python/README.md)
- [Adapter implementation plan](../../openrois-internal/latest/adapter-implementation-plan.md)