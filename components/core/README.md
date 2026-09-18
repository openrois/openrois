# openrois-components-core

The component framework for OpenRoIS: the decorators you write components with, the
metadata extractor that turns them into a RoIS component profile, and the helpers that
build spec-compliant `Result` lists.

This is what an adapter author imports. It has no transport and no robot in it.

## Install

Not published to PyPI yet. From a clone of the repository:

```bash
pip install -e ./interfaces/python
pip install -e ./components/core
```

## Usage

```python
from openrois_components_core import component, invoke, query, results, subscribe


@component("Navigation", function="actuation")
class Navigation:
    def __init__(self, config: dict) -> None:
        self._api = None

    @query("component_status")
    async def status(self):
        return results.status("READY")

    @invoke("execute")
    async def execute(self, parameters):
        ...

    @subscribe("reached_target")
    async def on_reached(self):
        ...
```

The declaration is the source of truth. `meta_from_decorators` reads the class and returns
the `ComponentMeta` that the engine publishes in the engine profile, so a client discovers
exactly what you declared:

```python
from openrois_components_core import meta_from_decorators

meta = meta_from_decorators(Navigation)
engine.register_component(meta.ref, Navigation(config), meta)
```

## API

| Name | Purpose |
|------|---------|
| `@component(name, function=...)` | Declare a class as a RoIS HRI Component |
| `@query(name)` | Declare a Query Interface message |
| `@invoke(name)` | Declare a Command Interface message |
| `@subscribe(name)` | Declare an Event Interface message |
| `meta_from_decorators(cls)` | Build the `ComponentMeta` and profile from the decorators |
| `ComponentMeta` | The component reference, function, and message profiles |
| `results` | Builders for spec-compliant `Result` lists, for example `results.position`, `results.status` |

Use the normative RoIS component and message names. A component that invents its own names
still runs, but applications written against the standard will not find it. See the
[component reference](https://openrois.org/docs/reference/components).

## License

Apache-2.0.
