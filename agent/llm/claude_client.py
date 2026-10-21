"""Anthropic Claude backend using the native Messages API.

Best practices applied:
- the system prompt goes in the ``system`` parameter, not as a message.
- prompt caching: top-level ``cache_control`` caches the growing conversation, so each
  agent iteration only pays full price for the new turn.
- adaptive thinking: the model decides when and how much to think. Thinking blocks are
  passed back unchanged (with their signatures), which tool use with thinking requires.
  ``temperature`` is not sent because thinking does not allow changing it.
- all tool results of one turn go back in a single user message, with ``is_error`` set
  for failed tools.

Adaptive thinking needs a recent model (e.g. Claude Sonnet/Opus 4.6+). For older models
set ``thinking = None`` in a subclass or here.
"""

import logging
from collections.abc import Sequence
from typing import Any, ClassVar

import anthropic

from .base import LLMClient, LLMResponse, LLMSettings, ToolCall, ToolResult, ToolSpec

logger = logging.getLogger(__name__)


class ClaudeClient(LLMClient):
    # Non-streaming requests: keep max_tokens moderate so the SDK does not refuse them.
    max_tokens: int = 16000
    thinking: ClassVar[dict[str, Any] | None] = {"type": "adaptive"}
    cache_control: ClassVar[dict[str, Any] | None] = {"type": "ephemeral"}

    def __init__(self, settings: LLMSettings) -> None:
        super().__init__(settings)
        self._client = anthropic.Anthropic(api_key=settings.api_key or None, base_url=settings.base_url)
        self._system = ""
        self._messages: list[dict[str, Any]] = []
        self._tools: list[dict[str, Any]] = []

    def start(self, system_prompt: str, user_prompt: str, tools: Sequence[ToolSpec]) -> None:
        self._system = system_prompt
        self._messages = [{"role": "user", "content": user_prompt}]
        self._tools = [
            {"name": spec.name, "description": spec.description, "input_schema": spec.parameters}
            for spec in tools
        ]

    def _request_options(self) -> dict[str, Any]:
        options: dict[str, Any] = {}
        if self.thinking:
            options["thinking"] = self.thinking
        if self.cache_control:
            options["cache_control"] = self.cache_control
        return options

    def _complete(self) -> LLMResponse:
        response = self._client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            system=self._system,
            messages=self._messages,  # type: ignore[arg-type]
            tools=self._tools,  # type: ignore[arg-type]
            **self._request_options(),
        )
        if response.stop_reason == "max_tokens":
            logger.warning("Claude response truncated at max_tokens=%s", self.max_tokens)
        logger.debug("Claude usage: %s", response.usage)

        # Keep all blocks (thinking, text, tool_use) exactly as returned.
        self._messages.append({"role": "assistant", "content": response.content})

        text = "".join(block.text for block in response.content if block.type == "text")
        tool_calls = tuple(
            ToolCall(id=block.id, name=block.name, arguments=dict(block.input or {}))
            for block in response.content
            if block.type == "tool_use"
        )
        return LLMResponse(text=text, tool_calls=tool_calls)

    def add_tool_results(self, results: Sequence[ToolResult]) -> None:
        self._messages.append(
            {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": result.call.id,
                        "content": result.output,
                        "is_error": result.is_error,
                    }
                    for result in results
                ],
            }
        )
