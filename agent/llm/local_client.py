"""Local / self-hosted backend using the OpenAI-compatible Chat Completions API.

Chat Completions is what local servers support best (vLLM, Ollama, llama.cpp,
LM Studio, ...), so this backend stays on it instead of the Responses API.
"""

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


class LocalClient(LLMClient):
    temperature: float | None = 0.1

    def __init__(self, settings: LLMSettings) -> None:
        super().__init__(settings)
        # Local servers usually ignore the key, but the SDK requires a non-empty one.
        self._client = OpenAI(api_key=settings.api_key or "unused", base_url=settings.base_url)
        self._messages: list[dict[str, Any]] = []
        self._tools: list[dict[str, Any]] = []

    def start(self, system_prompt: str, user_prompt: str, tools: Sequence[ToolSpec]) -> None:
        self._messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        self._tools = [
            {
                "type": "function",
                "function": {
                    "name": spec.name,
                    "description": spec.description,
                    "parameters": spec.parameters,
                },
            }
            for spec in tools
        ]

    def _complete(self) -> LLMResponse:
        options: dict[str, Any] = {}
        if self.temperature is not None:
            options["temperature"] = self.temperature
        response = self._client.chat.completions.create(
            model=self.model,
            messages=self._messages,  # type: ignore[arg-type]
            tools=self._tools,  # type: ignore[arg-type]
            **options,
        )
        message = response.choices[0].message

        tool_calls = tuple(
            ToolCall(
                id=call.id,
                name=call.function.name,
                arguments=parse_arguments(call.function.arguments),
            )
            for call in message.tool_calls or ()
            if call.type == "function"
        )

        assistant: dict[str, Any] = {"role": "assistant", "content": message.content or ""}
        if tool_calls:
            assistant["tool_calls"] = [
                {
                    "id": call.id,
                    "type": "function",
                    "function": {"name": call.function.name, "arguments": call.function.arguments},
                }
                for call in message.tool_calls or ()
                if call.type == "function"
            ]
        self._messages.append(assistant)
        return LLMResponse(text=message.content or "", tool_calls=tool_calls)

    def add_tool_results(self, results: Sequence[ToolResult]) -> None:
        for result in results:
            self._messages.append(
                {
                    "role": "tool",
                    "tool_call_id": result.call.id,
                    "name": result.call.name,
                    "content": result.output,
                }
            )
