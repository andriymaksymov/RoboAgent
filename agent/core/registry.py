from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterable

from ..config import AgentConfig

ToolHandler = Callable[[Dict[str, Any], AgentConfig], str]


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    handler: ToolHandler
    properties: Dict[str, Any] = field(default_factory=dict)
    required: tuple[str, ...] = ()
    log_arg: str | None = None

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


class ToolRegistry:
    def __init__(self, tools: Iterable[Tool] = ()) -> None:
        self._tools: Dict[str, Tool] = {}
        for tool in tools:
            self.register(tool)

    def register(self, tool: Tool) -> None:
        if tool.name in self._tools:
            raise ValueError(f"Tool '{tool.name}' is already registered")
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    @property
    def schemas(self) -> list[Dict[str, Any]]:
        return [tool.schema for tool in self._tools.values()]

    def __contains__(self, name: str) -> bool:
        return name in self._tools

    def __iter__(self):
        return iter(self._tools.values())
