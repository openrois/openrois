# openrois-Interfaces

![Python](https://img.shields.io/badge/Python-3.12+-3776AB?logo=python&logoColor=white)

Transport-independent [RoIS Framework 2.0](https://www.omg.org/spec/RoIS/2.0) interface
types for Python.

This package is the **single source of truth** for all OpenRoIS types. The Pydantic models
authored here are exported to JSON Schema (`interfaces/schema/`) and generated into
[C#](../csharp/README.md) and [TypeScript](../typescript/README.md). Never edit the
generated stacks by hand.

## Install

Not published to PyPI yet. From a clone of the repository:

```bash
pip install -e ./interfaces/python
```

## Usage

```python
from openrois.interfaces.hri import Result, ReturnCode

result = Result(name="number", data_type_ref="int", value="3")
code = ReturnCode.OK
```

The `ComponentContract` protocol is the only boundary between the engine and a concrete
transport. Implement its five methods and the engine can drive your platform without
knowing anything about it:

```python
from openrois.interfaces.bus import ComponentContract


class MyContract(ComponentContract):
    async def discover(self, request): ...
    async def invoke(self, request): ...
    async def query(self, request): ...
    async def subscribe(self, request, sink): ...
    async def unsubscribe(self, subscribe_id): ...
```

Most adapter authors do not implement it directly: `ComponentRegistry` and `SubEngine` in
[`openrois-core`](../../core/README.md) play this role (aligning their signatures with the
protocol exactly is part of Phase 4), and components are written with the
decorators in [`openrois-components-core`](../../components/core/README.md).

## Module Structure

| Module | Contents |
|--------|----------|
| `openrois.interfaces.hri` | Core HRI types: `ReturnCode`, `Result`, `Parameter`, `Argument`, `CommandUnit`, `CommandUnitSequence` |
| `openrois.interfaces.common` | `ComponentStatus`, `StreamStatus` |
| `openrois.interfaces.service` | `CompletedStatus`, `ErrorType`, `CompletedEvent`, `NotifyErrorEvent`, `NotifyEventPayload` |
| `openrois.interfaces.profiles` | Component and engine profile models |
| `openrois.interfaces.bus` | `ComponentContract` protocol, request and response models, `EventEnvelope`, error classes |
| `openrois.interfaces.components` | Per-component typed message models |

## Development

```bash
pip install -e ".[dev]"
pytest                           # tests, including the schema drift check
mypy src/                        # type check
ruff check src/                  # lint
python scripts/export_schema.py  # regenerate the JSON Schema
```

Some tests cross-check the models against the normative RoIS machine-readable files, which
are not redistributed here. Those tests fail without them.

After regenerating the schema, regenerate the other two stacks as described in
[AGENTS.md](../../AGENTS.md).

## License

Apache-2.0.
