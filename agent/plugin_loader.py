"""Hot-reloading loader for plugin tools in ``agent/plugin/``.

``refresh()`` rescans the plugin directory and applies what changed since the last scan:
new and modified modules are (re)loaded, deleted ones are unloaded. The runner calls it
after every batch of tool calls, so a tool the agent writes for itself becomes usable in
the same run, without a restart.

A module goes live only after it passes validation: it must compile, execute without
raising, and define tools with a description and a unique name. The loaded code is never
touched until then, so a broken module is logged and skipped while its previous version
(if any) stays active. Every outcome is returned as a ``PluginEvent`` so the runner can
tell the model and report failed self-improvement attempts in its final answer.
"""

import hashlib
import importlib.util
import logging
import sys
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Literal

from .core.registry import REGISTRY, Tool, ToolRegistry

logger = logging.getLogger(__name__)

PLUGIN_DIR = Path(__file__).parent / "plugin"
PLUGIN_PACKAGE = "agent.plugin"

Status = Literal["loaded", "reloaded", "removed", "failed"]


class PluginValidationError(Exception):
    """A plugin module executed but defines unusable tools."""


@dataclass(frozen=True)
class PluginEvent:
    module: str
    status: Status
    tools: tuple[str, ...] = ()
    error: str = ""
    # For failures: whether an earlier version of the module is still active.
    kept_previous: bool = False

    def describe(self) -> str:
        tools = ", ".join(self.tools) or "none"
        if self.status == "failed":
            fallback = "the previous version stays active" if self.kept_previous else "not loaded"
            return f"'{self.module}' failed to load ({fallback}): {self.error}"
        if self.status == "removed":
            return f"'{self.module}' removed; tools no longer available: {tools}"
        return f"'{self.module}' {self.status}; tools available now: {tools}"


@dataclass
class _Loaded:
    module: ModuleType
    tools: tuple[str, ...]


class PluginLoader:
    def __init__(
        self,
        directory: Path = PLUGIN_DIR,
        package: str = PLUGIN_PACKAGE,
        registry: ToolRegistry = REGISTRY,
    ) -> None:
        self.directory = directory
        self.package = package
        self.registry = registry
        self._hashes: dict[str, str] = {}  # module stem -> hash of the last seen source
        self._loaded: dict[str, _Loaded] = {}
        self._failures: dict[str, str] = {}  # module stem -> error of its latest version

    @property
    def failures(self) -> dict[str, str]:
        """Modules whose latest version failed to load, with the error."""
        return dict(self._failures)

    def refresh(self) -> list[PluginEvent]:
        """Load new or changed plugin modules and unload deleted ones."""
        sources = {
            path.stem: path for path in sorted(self.directory.glob("*.py")) if path.stem != "__init__"
        }
        events = [self._unload(stem) for stem in sorted(set(self._hashes) - set(sources))]
        for stem, path in sources.items():
            try:
                source = path.read_bytes()
            except OSError as exc:
                logger.warning("Cannot read plugin %s: %s", path, exc)
                continue
            digest = hashlib.sha256(source).hexdigest()
            if self._hashes.get(stem) != digest:
                self._hashes[stem] = digest
                events.append(self._load(stem, path, source))
        return events

    def _load(self, stem: str, path: Path, source: bytes) -> PluginEvent:
        previous = self._loaded.get(stem)
        name = f"{self.package}.{stem}"
        try:
            module, tools = self._execute(name, path, source)
            self._validate(stem, tools)
        except BaseException as exc:  # also SystemExit raised by a plugin
            if isinstance(exc, KeyboardInterrupt):
                raise
            error = f"{type(exc).__name__}: {exc}"
            self._failures[stem] = error
            logger.warning("Failed to load plugin %s: %s", name, error)
            logger.debug("%s traceback", name, exc_info=True)
            return PluginEvent(stem, "failed", error=error, kept_previous=previous is not None)

        # Validated: swap the old version's tools for the new ones.
        for tool_name in previous.tools if previous else ():
            self.registry.unregister(tool_name)
        for item in tools:
            self.registry.register(item)
        sys.modules[name] = module
        package = sys.modules.get(self.package)
        if package is not None:
            setattr(package, stem, module)

        names = tuple(item.name for item in tools)
        self._loaded[stem] = _Loaded(module, names)
        self._failures.pop(stem, None)
        status: Status = "reloaded" if previous else "loaded"
        logger.info("Plugin %s %s: %s", name, status, ", ".join(names) or "no tools")
        return PluginEvent(stem, status, tools=names)

    def _execute(self, name: str, path: Path, source: bytes) -> tuple[ModuleType, list[Tool]]:
        """Run the module in a fresh namespace and collect the tools it defines."""
        # Compiling the source ourselves avoids stale bytecode from __pycache__ after a
        # quick rewrite, and leaves the currently loaded module untouched on failure.
        code = compile(source, str(path), "exec")
        spec = importlib.util.spec_from_file_location(name, path)
        if spec is None:
            raise ImportError(f"Cannot create a module spec for {path}")
        module = importlib.util.module_from_spec(spec)
        with self.registry.capture() as tools:
            exec(code, module.__dict__)  # noqa: S102 - loading plugin code is the point
        return module, tools

    def _validate(self, stem: str, tools: list[Tool]) -> None:
        own = set(self._loaded[stem].tools) if stem in self._loaded else set()
        seen: set[str] = set()
        for item in tools:
            if not item.description:
                raise PluginValidationError(f"tool '{item.name}' has no docstring description")
            if item.name in seen:
                raise PluginValidationError(f"tool '{item.name}' is defined twice")
            if item.name in self.registry and item.name not in own:
                raise PluginValidationError(f"tool '{item.name}' is already registered elsewhere")
            seen.add(item.name)

    def _unload(self, stem: str) -> PluginEvent:
        self._hashes.pop(stem, None)
        self._failures.pop(stem, None)
        loaded = self._loaded.pop(stem, None)
        tools = loaded.tools if loaded else ()
        for tool_name in tools:
            self.registry.unregister(tool_name)
        sys.modules.pop(f"{self.package}.{stem}", None)
        logger.info("Plugin %s.%s removed", self.package, stem)
        return PluginEvent(stem, "removed", tools=tools)


class PluginReport:
    """Collects the plugin events of one agent run for its final summary."""

    def __init__(self, failures_at_start: dict[str, str] | None = None) -> None:
        self._startup_failures = dict(failures_at_start or {})
        self._events: list[PluginEvent] = []

    def add(self, events: list[PluginEvent]) -> None:
        self._events.extend(events)

    def summary(self, current_failures: dict[str, str]) -> str:
        """One line per plugin touched in this run, with its final state."""
        last: dict[str, PluginEvent] = {}
        failed_attempts: dict[str, int] = {}
        for event in self._events:
            last[event.module] = event
            if event.status == "failed":
                failed_attempts[event.module] = failed_attempts.get(event.module, 0) + 1

        lines = []
        for module, event in last.items():
            line = f"- {event.describe()}"
            attempts = failed_attempts.get(module, 0)
            if event.status != "failed" and attempts:
                line += f" (after {attempts} failed attempt(s))"
            lines.append(line)
        for module, error in self._startup_failures.items():
            if module not in last and module in current_failures:
                lines.append(f"- '{module}' failed to load at startup (not loaded): {error}")

        if not lines:
            return ""
        header = "[Self-improvement]: plugin tools changed during this run"
        if current_failures:
            header += f"; {len(current_failures)} plugin(s) are still broken"
        return header + ":\n" + "\n".join(lines)


PLUGINS = PluginLoader()
