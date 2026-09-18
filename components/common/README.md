# openrois-components-common

Platform-independent components for OpenRoIS adapters. They implement RoIS component
interfaces with simulated data, which makes them useful for testing, for bringing an
adapter up before the robot is ready, and as templates for platform-specific packages.

| Component | Provides |
|-----------|----------|
| `MockSystemInformation` | Queries `robot_position` (fixed origin) and `engine_status` (always `READY`) |

More will be added with the full component library in
[Phase 10](https://openrois.org/docs/project/roadmap).

## Install

Not published to PyPI yet. From a clone of the repository:

```bash
pip install -e ./interfaces/python
pip install -e ./components/core
pip install -e ./components/common
```

## Usage

Register the component with the `Engine` of your adapter, exactly like one of your own:

```python
from openrois_components.common import MockSystemInformation
from openrois_components_core import meta_from_decorators
from openrois_core import Engine

engine = Engine(engine_id="my_robot", platform="my_platform")

meta = meta_from_decorators(MockSystemInformation)
engine.register_component(meta.ref, MockSystemInformation(), meta)
```

See [`examples/adapter-template`](../../examples/adapter-template/README.md) for a full
adapter, and [`components/core`](../core/README.md) for the decorators used to write your
own components.

## License

Apache-2.0.
