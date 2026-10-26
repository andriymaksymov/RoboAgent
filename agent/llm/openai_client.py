"""OpenAI backend using the Responses API.

Why Responses instead of Chat Completions:
- reasoning models (GPT-5.x) keep their reasoning between tool calls when reasoning items
  are passed back. Because we run stateless (``store=False``), the reasoning comes back
  encrypted (``include=["reasoning.encrypted_content"]``) and we return it on the next turn.
- function calls and their outputs are first-class items linked by ``call_id``.

``temperature`` is not sent because reasoning models reject it. ``reasoning.effort``
controls how much reasoning the model does.
"""

import logging
from collections.abc import Sequence
from typing import Any

from openai import OpenAI

from .base import (
    LLMClient,
    LLMResponse,
    LLMSettings,
    ToolCall,
    ToolResult,
    ToolSpec,
    parse_arguments,
)

logger = logging.getLogger(__name__)


class OpenAIClient(LLMClient):
    reasoning_effort: str | None = "medium"
    max_output_tokens: int | None = None

    def __init__(self, settings: LLMSettings) -> None:
        super().__init__(settings)
        self._client = OpenAI(api_key=settings.api_key or None, base_url=settings.base_url)
        self._instructions = ""
        self._input: list[Any] = []
        self._tools: list[dict[str, Any]] = []

    def start(self, system_prompt: str, user_prompt: str, tools: Sequence[ToolSpec]) -> None:
        self._instructions = system_prompt
        self._input = [{"role": "user", "content": user_prompt}]
        self.set_tools(tools)

    def set_tools(self, tools: Sequence[ToolSpec]) -> None:
        self._tools = [
            {
                "type": "function",
                "name": spec.name,
                "description": spec.description,
                "parameters": spec.parameters,
                # Optional parameters are not in "required", so strict mode does not fit.
                "strict": False,
            }
            for spec in tools
        ]

    def _request_options(self) -> dict[str, Any]:
        options: dict[str, Any] = {"store": False}
        if self.reasoning_effort:
            options["reasoning"] = {"effort": self.reasoning_effort}
            options["include"] = ["reasoning.encrypted_content"]
        if self.max_output_tokens:
            options["max_output_tokens"] = self.max_output_tokens
        return options

    def _complete(self) -> LLMResponse:
        response = self._client.responses.create(
            model=self.model,
            instructions=self._instructions,
            input=self._input,
            tools=self._tools,
            **self._request_options(),
        )
        if response.usage:
            self._add_token_usage(response.usage.input_tokens, response.usage.output_tokens)
        if response.status == "incomplete":
            logger.warning("Response incomplete: %s", response.incomplete_details)

        tool_calls = []
        for item in response.output:
            # Return every output item (reasoning, messages, calls) unchanged next turn.
            self._input.append(item.model_dump(exclude_none=True, mode="json"))
            if item.type == "function_call":
                tool_calls.append(
                    ToolCall(id=item.call_id, name=item.name, arguments=parse_arguments(item.arguments))
                )
        return LLMResponse(text=response.output_text or "", tool_calls=tuple(tool_calls))

    def add_tool_results(self, results: Sequence[ToolResult]) -> None:
        for result in results:
            self._input.append(
                {"type": "function_call_output", "call_id": result.call.id, "output": result.output}
            )
