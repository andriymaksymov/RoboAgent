"""Provider-neutral LLM interface.

The runner talks only to ``LLMClient``. Each provider subclass keeps the conversation in
its *native* format (e.g. Responses API items, Claude content blocks, Gemini ``Content``)
so provider-specific data such as reasoning items, thinking blocks or thought signatures
is passed back unchanged on the next turn.
"""

import json
import logging
from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


class LLMError(Exception):
    """An LLM request failed or returned an unusable response."""


@dataclass(frozen=True)
class LLMSettings:
    provider: str
    model: str
    api_key: str = ""
    base_url: str | None = None


@dataclass(frozen=True)
class ToolSpec:
    """A tool definition: name, description and JSON schema of its parameters."""

    name: str
    description: str
    parameters: dict[str, Any]

    @classmethod
    def from_schema(cls, schema: dict[str, Any]) -> "ToolSpec":
        """Build from an OpenAI Chat Completions style ``{"type": "function", ...}`` schema."""
        function = schema.get("function", schema)
        return cls(
            name=function["name"],
            description=function.get("description", ""),
            parameters=function.get("parameters") or {"type": "object", "properties": {}},
        )


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ToolResult:
    call: ToolCall
    output: str

    @property
    def is_error(self) -> bool:
        return self.output.startswith("[Error]")


@dataclass(frozen=True)
class LLMResponse:
    text: str
    tool_calls: tuple[ToolCall, ...] = ()


@dataclass(frozen=True)
class TokenUsage:
    input_tokens: int = 0
    output_tokens: int = 0


class LLMClient(ABC):
    """A single agent conversation with a model.

    Usage: ``start()`` once, then alternate ``complete()`` and ``add_tool_results()``
    until ``complete()`` returns a response without tool calls. ``set_tools()`` may be
    called between turns to change the tools offered from the next request on.
    """

    # A single request whose prompt (the whole conversation sent) exceeds this many tokens
    # logs a warning: a hint that the context should be compacted or the task split.
    context_warning_tokens: int = 32_768

    def __init__(self, settings: LLMSettings) -> None:
        self.settings = settings
        self._token_usage = TokenUsage()
        self.last_context_tokens = 0

    @property
    def model(self) -> str:
        return self.settings.model

    @property
    def token_usage(self) -> TokenUsage:
        return self._token_usage

    def _add_token_usage(
        self,
        input_tokens: int | None,
        output_tokens: int | None,
        context_tokens: int | None = None,
    ) -> None:
        """Accumulate usage of one request.

        ``context_tokens`` is the full prompt size of this request; it defaults to
        ``input_tokens`` and only differs where the provider reports cached tokens apart.
        """
        input_tokens = max(0, input_tokens or 0)
        self._token_usage = TokenUsage(
            input_tokens=self._token_usage.input_tokens + input_tokens,
            output_tokens=self._token_usage.output_tokens + max(0, output_tokens or 0),
        )
        self.last_context_tokens = max(0, context_tokens if context_tokens is not None else input_tokens)
        if self.last_context_tokens > self.context_warning_tokens:
            logger.warning(
                "!!! LARGE CONTEXT !!! request used %d input tokens (warning threshold %d)",
                self.last_context_tokens,
                self.context_warning_tokens,
            )

    @abstractmethod
    def start(self, system_prompt: str, user_prompt: str, tools: Sequence[ToolSpec]) -> None:
        """Reset the conversation with a system prompt, the task and the available tools."""

    @abstractmethod
    def set_tools(self, tools: Sequence[ToolSpec]) -> None:
        """Replace the tools offered to the model; the conversation is kept."""

    def complete(self) -> LLMResponse:
        """Send the conversation, record the model's turn in it and return that turn."""
        try:
            return self._complete()
        except LLMError:
            raise
        except Exception as exc:
            logger.debug("%s request failed", self.settings.provider, exc_info=True)
            raise LLMError(f"{self.settings.provider} request failed: {exc}") from exc

    @abstractmethod
    def _complete(self) -> LLMResponse:
        """Provider-specific request; exceptions are wrapped into ``LLMError``."""

    @abstractmethod
    def add_tool_results(self, results: Sequence[ToolResult]) -> None:
        """Append the outputs of the tool calls from the last ``complete()``."""


def parse_arguments(raw: str | None) -> dict[str, Any]:
    """Leniently parse JSON tool arguments; malformed input yields ``{}``."""
    try:
        parsed = json.loads(raw or "{}")
    except (json.JSONDecodeError, TypeError):
        logger.warning("Could not parse tool arguments: %r", raw)
        return {}
    if isinstance(parsed, list):
        parsed = parsed[0] if parsed else {}
    return parsed if isinstance(parsed, dict) else {}
