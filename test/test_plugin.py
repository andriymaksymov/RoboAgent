"""Tests for the plugin auto-discovery system and the echo example tool."""

from pathlib import Path

import pytest

import agent.runner  # noqa: F401  importing runner triggers plugin registration as a side effect
from agent.core.registry import REGISTRY, ToolError

# ---------------------------------------------------------------------------
# Auto-discovery
# ---------------------------------------------------------------------------


class TestPluginDiscovery:
    """The plugin package must auto-import every .py file it contains."""

    def test_echo_tool_is_registered(self):
        assert "echo" in REGISTRY, "echo tool should be registered after plugin import"

    def test_plugin_tools_appear_in_schemas(self):
        names = {s["function"]["name"] for s in REGISTRY.schemas}
        assert "echo" in names


# ---------------------------------------------------------------------------
# echo tool — schema / JSON contract
# ---------------------------------------------------------------------------


class TestEchoSchema:
    """The JSON schema derived from the echo docstring must be correct."""

    @pytest.fixture
    def echo_tool(self):
        return REGISTRY.get("echo")

    def test_tool_exists(self, echo_tool):
        assert echo_tool is not None

    def test_required_params(self, echo_tool):
        assert list(echo_tool.required) == ["message"]

    def test_optional_param_present(self, echo_tool):
        assert "repeat" in echo_tool.properties

    def test_workdir_is_injected_not_exposed(self, echo_tool):
        assert "workdir" in echo_tool.injected
        assert "workdir" not in echo_tool.properties

    def test_message_is_string_type(self, echo_tool):
        assert echo_tool.properties["message"]["type"] == "string"

    def test_repeat_is_integer_type(self, echo_tool):
        assert echo_tool.properties["repeat"]["type"] == "integer"


# ---------------------------------------------------------------------------
# echo tool — runtime behaviour
# ---------------------------------------------------------------------------


class TestEchoRuntime:
    """The echo function must behave correctly when invoked directly."""

    @pytest.fixture
    def workdir(self, tmp_path):
        return tmp_path

    def test_basic_echo(self, workdir):
        from agent.plugin.echo import echo

        result = echo(message="hello", workdir=workdir)
        assert "hello" in result

    def test_repeat(self, workdir):
        from agent.plugin.echo import echo

        result = echo(message="hi", workdir=workdir, repeat=3)
        assert result.count("hi") == 3

    def test_workdir_name_appears_in_output(self, workdir):
        from agent.plugin.echo import echo

        result = echo(message="x", workdir=workdir)
        assert workdir.name in result

    def test_repeat_zero_raises_tool_error(self, workdir):
        from agent.plugin.echo import echo

        with pytest.raises(ToolError):
            echo(message="x", workdir=workdir, repeat=0)

    def test_repeat_eleven_raises_tool_error(self, workdir):
        from agent.plugin.echo import echo

        with pytest.raises(ToolError):
            echo(message="x", workdir=workdir, repeat=11)

    def test_repeat_string_raises_tool_error(self, workdir):
        from agent.plugin.echo import echo

        with pytest.raises(ToolError):
            echo(message="x", workdir=workdir, repeat="lots")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Resilience — a broken plugin must not crash the agent
# ---------------------------------------------------------------------------


class TestPluginResilience:
    """A plugin that raises on import must be skipped gracefully."""

    def test_broken_plugin_is_skipped(self, tmp_path, monkeypatch):
        import importlib
        import sys

        # Plant a broken module inside the plugin package directory.
        plugin_dir = Path(__file__).parent.parent / "agent" / "plugin"
        broken = plugin_dir / "_broken_test_plugin.py"
        broken.write_text("raise RuntimeError('intentional import error')\n", encoding="utf-8")

        try:
            # Remove any cached import so the loader re-runs.
            mod_name = "agent.plugin._broken_test_plugin"
            sys.modules.pop(mod_name, None)

            # Re-importing the plugin package must not raise.
            import agent.plugin as plugin_pkg

            importlib.reload(plugin_pkg)  # reload triggers re-discovery
        finally:
            broken.unlink(missing_ok=True)
            sys.modules.pop("agent.plugin._broken_test_plugin", None)
