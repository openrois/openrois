# openrois-components-common

Platform-independent components for OpenRoIS adapters. They implement RoIS component
interfaces with simulated data, which makes them useful for testing, for bringing an
adapter up before the robot is ready, and as templates for platform-specific packages.

| Component | Provides |
|-----------|----------|
| `MockSystemInformation` | Queries `robot_position` (the origin, identified by the engine id) and `engine_status` (always `READY`) |

More will be added with the full component library in
[Phase 10](https://openrois.org/docs/project/roadmap).

## Install

Not published to PyPI yet. From a clone of the repository:

```bash
pip install -e ./interfaces/python -e ./components/core -e ./components/common
```

## Usage

Register the component with the engine of your adapter, like one of your own. It reports
the engine id of the adapter as its robot:

```python
from openrois.components.common import MockSystemInformation

system_information = MockSystemInformation()
```

See [`examples/adapter-template`](../../examples/adapter-template/README.md) for a full
adapter, and [`components/core`](../core/README.md) for writing your own components.

## Test

```bash
pip install -e ./interfaces/python -e ./components/core -e "./components/common[dev]"
cd components/common && pytest && mypy && ruff check src/ tests/
```

## License

Apache-2.0.
