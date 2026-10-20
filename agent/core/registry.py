"""Tool registry and the ``@tool`` decorator.

A tool is a plain function. The decorator derives the JSON schema from its signature and
docstring and registers it in ``REGISTRY``:

    @tool
    def read_file(path: str, workdir: Path) -> str:
        \"\"\"Read a local file from the workdir.

        Args:
            path: File path relative to the workdir.
        \"\"\"

Parameters named ``config`` or like an ``AgentConfig`` field (e.g. ``workdir``,
``allowed_commands``) are injected from the configuration and hidden from the model.
Tools signal expected failures by raising ``ToolError``; any exception is turned into an
``[Error]: ...`` message for the model, so tools need no try/except of their own.
"""

import dataclasses
import inspect
import json
import logging
import re
import types
import typing
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterable

from ..config import AgentConfig

logger = logging.getLogger(__name__)

INJECTABLE = {f.name for f in dataclasses.fields(AgentConfig)} | {"config"}
LOG_VALUE_CHARS = 60
LOG_OUTPUT_CHARS = 120


class ToolError(Exception):
    """Expected tool failure; the message is returned to the model as-is."""


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    func: Callable[..., str]
    properties: Dict[str, Any] = field(default_factory=dict)
    required: tuple[str, ...] = ()
    injected: tuple[str, ...] = ()

    @property
    def schema(self) -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": self.properties,
                    "required": list(self.required),
                    "additionalProperties": False,
                },
            },
        }

    def invoke(self, arguments: Dict[str, Any], config: AgentConfig) -> str:
        logger.info("-> %s(%s)", self.name, _short_args(arguments))
        logger.debug("%s arguments: %s", self.name, json.dumps(arguments, default=str))
        try:
            missing = [name for name in self.required if name not in arguments]
            if missing:
                raise ToolError(f"Missing required argument(s): {', '.join(missing)}.")

            unknown = set(arguments) - set(self.properties)
            if unknown:
                logger.warning("%s: ignoring unknown argument(s) %s", self.name, sorted(unknown))

            kwargs = {name: value for name, value in arguments.items() if name in self.properties}
            for name in self.injected:
                kwargs[name] = config if name == "config" else getattr(config, name)

            output = self.func(**kwargs)
        except (ToolError, OSError) as exc:
            # Expected failures (bad input, missing files): no traceback needed.
            logger.warning("<- %s failed: %s", self.name, _shorten(str(exc), LOG_OUTPUT_CHARS))
            return f"[Error]: {exc}"
        except Exception as exc:
            logger.error("<- %s raised %s: %s", self.name, type(exc).__name__, _shorten(str(exc), LOG_OUTPUT_CHARS))
            logger.debug("%s traceback", self.name, exc_info=True)
            return f"[Error]: Tool '{self.name}' failed: {exc}"

        logger.info("<- %s: %s", self.name, _short_output(output))
        logger.debug("%s output:\n%s", self.name, output)
        return output


class ToolRegistry:
    def __init__(self, tools: Iterable[Tool] = ()) -> None:
        self._tools: Dict[str, Tool] = {}
        for item in tools:
            self.register(item)

    def register(self, item: Tool) -> None:
        if item.name in self._tools:
            raise ValueError(f"Tool '{item.name}' is already registered")
        self._tools[item.name] = item

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def invoke(self, name: str, arguments: Dict[str, Any], config: AgentConfig) -> str:
        item = self.get(name)
        if item is None:
            logger.warning("Unknown tool requested: %s", name)
            return f"[Error]: Unknown tool '{name}'."
        return item.invoke(arguments, config)

    @property
    def schemas(self) -> list[Dict[str, Any]]:
        return [item.schema for item in self._tools.values()]

    def __contains__(self, name: str) -> bool:
        return name in self._tools

    def __iter__(self):
        return iter(self._tools.values())


REGISTRY = ToolRegistry()


def tool(
    func: Callable[..., str] | None = None,
    *,
    name: str | None = None,
    registry: ToolRegistry = REGISTRY,
):
    """Register ``func`` as a tool. Usable as ``@tool`` or ``@tool(name=...)``."""

    def decorate(f: Callable[..., str]) -> Callable[..., str]:
        registry.register(build_tool(f, name=name))
        return f

    return decorate(func) if func is not None else decorate


def build_tool(func: Callable[..., str], name: str | None = None) -> Tool:
    description, param_docs = _parse_docstring(inspect.getdoc(func) or "")
    hints = typing.get_type_hints(func)

    properties: Dict[str, Any] = {}
    required = []
    injected = []
    for param in inspect.signature(func).parameters.values():
        if param.name in INJECTABLE:
            injected.append(param.name)
            continue

        prop = _json_type(hints.get(param.name, str))
        if param.name in param_docs:
            prop["description"] = param_docs[param.name]
        properties[param.name] = prop
        if param.default is inspect.Parameter.empty:
            required.append(param.name)

    return Tool(
        name=name or func.__name__,
        description=description,
        func=func,
        properties=properties,
        required=tuple(required),
        injected=tuple(injected),
    )


_SCALAR_TYPES = {str: "string", int: "integer", float: "number", bool: "boolean"}


def _json_type(annotation: Any) -> Dict[str, Any]:
    origin = typing.get_origin(annotation)
    args = [arg for arg in typing.get_args(annotation) if arg is not type(None)]

    if origin in (typing.Union, types.UnionType) and len(args) == 1:
        return _json_type(args[0])
    if origin in (list, tuple) or annotation in (list, tuple):
        schema: Dict[str, Any] = {"type": "array"}
        if args:
            schema["items"] = _json_type(args[0])
        return schema
    if origin is dict or annotation is dict:
        return {"type": "object"}
    if annotation in _SCALAR_TYPES:
        return {"type": _SCALAR_TYPES[annotation]}
    raise TypeError(f"Unsupported tool parameter type: {annotation!r}")


_ARGS_HEADER = re.compile(r"^\s*Args:\s*$", re.MULTILINE)
_ARG_LINE = re.compile(r"^\s{2,}(\w+)\s*(?:\([^)]*\))?:\s*(.*)$")


def _parse_docstring(doc: str) -> tuple[str, Dict[str, str]]:
    """Split a Google-style docstring into (description, {param: description})."""
    match = _ARGS_HEADER.search(doc)
    if not match:
        return doc.strip(), {}

    description = doc[: match.start()].strip()
    params: Dict[str, str] = {}
    current = None
    for line in doc[match.end():].splitlines():
        if not line.strip():
            continue
        arg = _ARG_LINE.match(line)
        if arg:
            current = arg.group(1)
            params[current] = arg.group(2).strip()
        elif current and line.startswith(" " * 4):
            params[current] += " " + line.strip()
        else:
            break
    return description, params


def _shorten(text: str, limit: int) -> str:
    text = " ".join(str(text).split())
    return text if len(text) <= limit else text[: limit - 3] + "..."


def _short_args(arguments: Dict[str, Any]) -> str:
    return ", ".join(f"{key}={_shorten(repr(value), LOG_VALUE_CHARS)}" for key, value in arguments.items())


def _short_output(output: str) -> str:
    first_line = output.strip().splitlines()[0] if output.strip() else ""
    return f"{_shorten(first_line, LOG_OUTPUT_CHARS)} ({len(output)} chars)"
