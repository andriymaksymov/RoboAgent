"""Tests for hot-reloading plugin tools while the agent runs."""

from collections.abc import Sequence
from pathlib import Path

import pytest

import agent.runner
from agent.config import AgentConfig
from agent.core.registry import REGISTRY, ToolRegistry
from agent.llm.base import LLMClient, LLMResponse, LLMSettings, ToolCall, ToolResult, ToolSpec
from agent.plugin_loader import PluginLoader, PluginReport

GREET_V1 = '''
from agent.core.registry import tool


@tool
def greet(name: str) -> str:
    """Greet someone.

    Args:
        name: Who to greet.
    """
    return f"hello {name}"
'''

GREET_V2 = GREET_V1.replace('f"hello {name}"', 'f"hi {name}"')
BROKEN = "def oops(:\n"


@pytest.fixture
def plugin_dir(tmp_path):
    directory = tmp_path / "plugins"
    directory.mkdir()
    return directory


@pytest.fixture
def registry():
    return ToolRegistry()


@pytest.fixture
def loader(plugin_dir, registry, monkeypatch):
    # Plugins register through the global ``@tool`` decorator, i.e. into REGISTRY;
    # route those registrations to the test registry instead.
    monkeypatch.setattr(REGISTRY, "register", registry.register)
    return PluginLoader(plugin_dir, "test_plugins", registry)


def call(registry, name, /, **arguments):
    return registry.invoke(name, arguments, config=None)  # type: ignore[arg-type]


class TestLoader:
    def test_new_plugin_is_loaded(self, loader, plugin_dir, registry):
        assert loader.refresh() == []
        (plugin_dir / "greet.py").write_text(GREET_V1, encoding="utf-8")

        [event] = loader.refresh()

        assert (event.module, event.status, event.tools) == ("greet", "loaded", ("greet",))
        assert call(registry, "greet", name="bob") == "hello bob"

    def test_unchanged_plugin_is_not_reloaded(self, loader, plugin_dir):
        (plugin_dir / "greet.py").write_text(GREET_V1, encoding="utf-8")
        loader.refresh()
        assert loader.refresh() == []

    def test_changed_plugin_is_reloaded(self, loader, plugin_dir, registry):
        path = plugin_dir / "greet.py"
        path.write_text(GREET_V1, encoding="utf-8")
        loader.refresh()
        path.write_text(GREET_V2, encoding="utf-8")

        [event] = loader.refresh()

        assert event.status == "reloaded"
        assert call(registry, "greet", name="bob") == "hi bob"

    def test_broken_plugin_is_skipped(self, loader, plugin_dir, registry):
        (plugin_dir / "bad.py").write_text(BROKEN, encoding="utf-8")

        [event] = loader.refresh()

        assert event.status == "failed"
        assert "SyntaxError" in event.error
        assert not event.kept_previous
        assert "bad" in loader.failures

    def test_broken_update_keeps_previous_version(self, loader, plugin_dir, registry):
        path = plugin_dir / "greet.py"
        path.write_text(GREET_V1, encoding="utf-8")
        loader.refresh()
        path.write_text(GREET_V1 + "\nraise RuntimeError('boom')\n", encoding="utf-8")

        [event] = loader.refresh()

        assert event.status == "failed"
        assert event.kept_previous
        assert "RuntimeError: boom" in event.error
        assert call(registry, "greet", name="bob") == "hello bob"

    def test_fixed_plugin_clears_failure(self, loader, plugin_dir):
        path = plugin_dir / "greet.py"
        path.write_text(BROKEN, encoding="utf-8")
        loader.refresh()
        path.write_text(GREET_V1, encoding="utf-8")

        [event] = loader.refresh()

        assert event.status == "loaded"
        assert loader.failures == {}

    def test_system_exit_on_import_is_contained(self, loader, plugin_dir):
        (plugin_dir / "quit.py").write_text("import sys\nsys.exit(1)\n", encoding="utf-8")
        [event] = loader.refresh()
        assert event.status == "failed"

    def test_unsupported_parameter_type_fails(self, loader, plugin_dir):
        source = GREET_V1.replace("name: str", "name: object")
        (plugin_dir / "greet.py").write_text(source, encoding="utf-8")
        [event] = loader.refresh()
        assert event.status == "failed"
        assert "Unsupported tool parameter type" in event.error

    def test_missing_description_fails(self, loader, plugin_dir):
        source = "from agent.core.registry import tool\n\n@tool\ndef bare() -> str:\n    return ''\n"
        (plugin_dir / "bare.py").write_text(source, encoding="utf-8")
        [event] = loader.refresh()
        assert event.status == "failed"
        assert "no docstring" in event.error

    def test_name_conflict_with_other_module_fails(self, loader, plugin_dir, registry):
        (plugin_dir / "a_greet.py").write_text(GREET_V1, encoding="utf-8")
        (plugin_dir / "b_greet.py").write_text(GREET_V2, encoding="utf-8")

        events = {event.module: event for event in loader.refresh()}

        assert events["a_greet"].status == "loaded"
        assert events["b_greet"].status == "failed"
        assert "already registered" in events["b_greet"].error
        assert call(registry, "greet", name="bob") == "hello bob"

    def test_deleted_plugin_is_unloaded(self, loader, plugin_dir, registry):
        path = plugin_dir / "greet.py"
        path.write_text(GREET_V1, encoding="utf-8")
        loader.refresh()
        path.unlink()

        [event] = loader.refresh()

        assert (event.status, event.tools) == ("removed", ("greet",))
        assert "greet" not in registry


class TestReport:
    def test_no_events_no_summary(self):
        assert PluginReport().summary({}) == ""

    def test_failure_then_success_is_reported(self, loader, plugin_dir):
        report = PluginReport()
        path = plugin_dir / "greet.py"
        path.write_text(BROKEN, encoding="utf-8")
        report.add(loader.refresh())
        path.write_text(GREET_V1, encoding="utf-8")
        report.add(loader.refresh())

        summary = report.summary(loader.failures)

        assert "'greet' loaded" in summary
        assert "after 1 failed attempt(s)" in summary
        assert "still broken" not in summary

    def test_unresolved_failure_is_reported(self, loader, plugin_dir):
        report = PluginReport()
        (plugin_dir / "bad.py").write_text(BROKEN, encoding="utf-8")
        report.add(loader.refresh())

        summary = report.summary(loader.failures)

        assert "1 plugin(s) are still broken" in summary
        assert "'bad' failed to load" in summary

    def test_startup_failure_is_reported(self):
        report = PluginReport({"old": "SyntaxError: x"})
        assert "'old' failed to load at startup" in report.summary({"old": "SyntaxError: x"})


class ScriptedClient(LLMClient):
    """Plays back fixed responses and records what the runner sends."""

    def __init__(self, responses: list[LLMResponse]) -> None:
        super().__init__(LLMSettings(provider="test", model="test"))
        self.responses = list(responses)
        self.tool_names: list[set[str]] = []
        self.results: list[ToolResult] = []

    def start(self, system_prompt: str, user_prompt: str, tools: Sequence[ToolSpec]) -> None:
        self.set_tools(tools)

    def set_tools(self, tools: Sequence[ToolSpec]) -> None:
        self.tool_names.append({spec.name for spec in tools})

    def _complete(self) -> LLMResponse:
        return self.responses.pop(0)

    def add_tool_results(self, results: Sequence[ToolResult]) -> None:
        self.results.extend(results)


def tool_turn(name: str, /, **arguments) -> LLMResponse:
    return LLMResponse(text="", tool_calls=(ToolCall(id=name, name=name, arguments=arguments),))


@pytest.fixture
def run_config(tmp_path):
    system_prompt = tmp_path / "system.md"
    system_prompt.write_text("test", encoding="utf-8")
    return AgentConfig(
        llm=LLMSettings(provider="test", model="test"),
        workdir=tmp_path,
        system_prompt=system_prompt,
        max_iterations=5,
        protected_branches=(),
        allowed_commands=(),
    )


@pytest.fixture
def run_loader(plugin_dir, monkeypatch):
    loader = PluginLoader(plugin_dir, "test_run_plugins", REGISTRY)
    monkeypatch.setattr(agent.runner, "PLUGINS", loader)
    yield loader
    for path in plugin_dir.glob("*.py"):
        path.unlink()
    loader.refresh()  # unregister the test tools from the global registry


class TestRunnerHotReload:
    def test_tool_written_mid_run_is_usable_in_same_run(self, run_config, run_loader):
        client = ScriptedClient(
            [
                tool_turn("write_file", path="plugins/greet.py", content=GREET_V1),
                tool_turn("greet", name="bob"),
                LLMResponse(text="done"),
            ]
        )

        answer = agent.runner.run_agent("task", run_config, client)

        assert "greet" not in client.tool_names[0]
        assert "greet" in client.tool_names[-1]
        write_result, greet_result = client.results
        assert "[Plugins reloaded]" in write_result.output
        assert greet_result.output == "hello bob"
        assert answer.startswith("done")
        assert "'greet' loaded" in answer

    def test_broken_tool_keeps_agent_running_and_is_reported(self, run_config, run_loader):
        client = ScriptedClient(
            [
                tool_turn("write_file", path="plugins/bad.py", content=BROKEN),
                tool_turn("bad"),
                LLMResponse(text="done"),
            ]
        )

        answer = agent.runner.run_agent("task", run_config, client)

        write_result, bad_result = client.results
        assert "'bad' failed to load" in write_result.output
        assert bad_result.output == "[Error]: Unknown tool 'bad'."
        assert answer.startswith("done")
        assert "still broken" in answer
        assert "SyntaxError" in answer


def test_real_plugin_dir_is_loaded():
    from agent.plugin_loader import PLUGIN_DIR, PLUGINS

    assert PLUGINS.directory == PLUGIN_DIR
    assert Path(PLUGIN_DIR / "echo.py").exists()
    assert "echo" in REGISTRY
