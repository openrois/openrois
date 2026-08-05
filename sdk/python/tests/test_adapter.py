"""Tests for the adapter base class and decorators."""

from __future__ import annotations

from openrois.sdk.adapter import RobotAdapter, component, invoke, query, subscribe


class SampleAdapter(RobotAdapter):
    """Sample adapter with two components for unit testing."""

    @component("SystemInformation", bind_required=False)
    class SystemInformation:
        @query("robot_position")
        async def robot_position(self):
            return []

        @query("component_status")
        async def status(self):
            return []

    @component("Navigation", bind_required=True)
    class Navigation:
        @query("waypoints")
        async def get_waypoints(self):
            return []

        @invoke("EXECUTE")
        async def navigate(self, parameters):
            pass

        @invoke("STOP")
        async def stop(self, parameters):
            pass

        @subscribe("reached_target")
        async def on_reached(self):
            pass


def test_component_list_has_two_components():
    """get_component_list returns both registered components."""
    adapter = SampleAdapter(config={})
    components = adapter.get_component_list()
    refs = [c["ref"] for c in components]
    assert "SystemInformation" in refs
    assert "Navigation" in refs
    assert len(components) == 2


def test_bind_required_flags():
    """bind_required is correctly propagated from the decorator."""
    adapter = SampleAdapter(config={})
    components = adapter.get_component_list()
    by_ref = {c["ref"]: c for c in components}
    assert by_ref["SystemInformation"]["bind_required"] is False
    assert by_ref["Navigation"]["bind_required"] is True


def test_queries_collected():
    """@query methods are collected in the component metadata."""
    adapter = SampleAdapter(config={})
    components = adapter.get_component_list()
    by_ref = {c["ref"]: c for c in components}
    assert "robot_position" in by_ref["SystemInformation"]["queries"]
    assert "component_status" in by_ref["SystemInformation"]["queries"]
    assert "waypoints" in by_ref["Navigation"]["queries"]


def test_commands_collected():
    """@invoke methods are collected in the component metadata."""
    adapter = SampleAdapter(config={})
    components = adapter.get_component_list()
    by_ref = {c["ref"]: c for c in components}
    assert "EXECUTE" in by_ref["Navigation"]["commands"]
    assert "STOP" in by_ref["Navigation"]["commands"]
    assert by_ref["SystemInformation"]["commands"] == []


def test_events_collected():
    """@subscribe methods are collected in the component metadata."""
    adapter = SampleAdapter(config={})
    components = adapter.get_component_list()
    by_ref = {c["ref"]: c for c in components}
    assert "reached_target" in by_ref["Navigation"]["events"]
    assert by_ref["SystemInformation"]["events"] == []


def test_handler_instances_created():
    """Each component class is instantiated and stored."""
    adapter = SampleAdapter(config={})
    handler = adapter.get_handler("Navigation")
    assert handler is not None
    assert hasattr(handler, "navigate")


def test_parent_reference_set():
    """Handler instances have .parent set to the adapter."""
    adapter = SampleAdapter(config={})
    handler = adapter.get_handler("Navigation")
    assert handler is not None
    assert handler.parent is adapter


def test_metadata_accessible():
    """get_metadata returns ComponentMetadata for a ref."""
    adapter = SampleAdapter(config={})
    meta = adapter.get_metadata("Navigation")
    assert meta is not None
    assert meta.ref == "Navigation"
    assert meta.bind_required is True
    assert "waypoints" in meta.queries
    assert "EXECUTE" in meta.invokes
    assert "reached_target" in meta.subscribes


def test_unknown_component_returns_none():
    """get_handler and get_metadata return None for unknown refs."""
    adapter = SampleAdapter(config={})
    assert adapter.get_handler("Unknown") is None
    assert adapter.get_metadata("Unknown") is None


def test_config_stored():
    """The config dict is stored on the adapter instance."""
    config = {"fleet_id": "test", "connection": {"ws": {"host": "localhost", "port": 8765}}}
    adapter = SampleAdapter(config=config)
    assert adapter.config is config
