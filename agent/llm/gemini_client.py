"""Google Gemini backend using the ``google-genai`` SDK.

Best practices applied:
- the system prompt goes in ``system_instruction``.
- tool schemas are passed as raw JSON schema (``parameters_json_schema``).
- automatic function calling is disabled; the agent runs the tools itself.
- the model's ``Content`` is appended unchanged, so thought signatures are returned on the
  next turn. Gemini thinking models need them to keep reasoning across tool calls.
- temperature is left at the model default, which Google recommends for Gemini 3.
"""

import logging
import uuid
from collections.abc import Sequence
from typing import Any

from google import genai
from google.genai import types

from .base import LLMClient, LLMError, LLMResponse, LLMSettings, ToolCall, ToolResult, ToolSpec

logger = logging.getLogger(__name__)


class GeminiClient(LLMClient):
    temperature: float | None = None
    thinking_config: types.ThinkingConfig | None = None

    def __init__(self, settings: LLMSettings) -> None:
        super().__init__(settings)
        http_options = types.HttpOptions(base_url=settings.base_url) if settings.base_url else None
        self._client = genai.Client(api_key=settings.api_key or None, http_options=http_options)
        self._contents: list[types.Content] = []
        self._config = types.GenerateContentConfig()
        # Call ids generated locally because the model sent none; not echoed back to Gemini.
        self._local_ids: set[str] = set()

    def start(self, system_prompt: str, user_prompt: str, tools: Sequence[ToolSpec]) -> None:
        self._contents = [types.Content(role="user", parts=[types.Part(text=user_prompt)])]
        self._local_ids = set()
        options: dict[str, Any] = {}
        if self.temperature is not None:
            options["temperature"] = self.temperature
        if self.thinking_config is not None:
            options["thinking_config"] = self.thinking_config
        self._config = types.GenerateContentConfig(
            system_instruction=system_prompt,
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
            **options,
        )
        self.set_tools(tools)

    def set_tools(self, tools: Sequence[ToolSpec]) -> None:
        declarations = [
            types.FunctionDeclaration(
                name=spec.name,
                description=spec.description,
                parameters_json_schema=spec.parameters,
            )
            for spec in tools
        ]
        self._config = self._config.model_copy(
            update={"tools": [types.Tool(function_declarations=declarations)]}
        )

    def _complete(self) -> LLMResponse:
        response = self._client.models.generate_content(
            model=self.model, contents=self._contents, config=self._config
        )
        if response.usage_metadata:
            self._add_token_usage(
                response.usage_metadata.prompt_token_count,
                response.usage_metadata.candidates_token_count,
            )
        if not response.candidates or response.candidates[0].content is None:
            raise LLMError(f"Gemini returned no content (feedback: {response.prompt_feedback})")

        candidate = response.candidates[0]
        content = candidate.content
        self._contents.append(content)
        if candidate.finish_reason and candidate.finish_reason.name not in ("STOP", "FINISH_REASON_UNSPECIFIED"):
            logger.warning("Gemini finish reason: %s", candidate.finish_reason.name)

        text_parts = []
        tool_calls = []
        for part in content.parts or ():
            if part.function_call:
                call = part.function_call
                call_id = call.id
                if not call_id:
                    call_id = f"call_{uuid.uuid4().hex[:12]}"
                    self._local_ids.add(call_id)
                tool_calls.append(
                    ToolCall(
                        id=call_id,
                        name=call.name or "",
                        arguments=dict(call.args or {}),
                    )
                )
            elif part.text and not part.thought:
                text_parts.append(part.text)
        return LLMResponse(text="".join(text_parts), tool_calls=tuple(tool_calls))

    def add_tool_results(self, results: Sequence[ToolResult]) -> None:
        parts = [
            types.Part(
                function_response=types.FunctionResponse(
                    # Gemini matches responses by name/order when it sent no call id.
                    id=None if result.call.id in self._local_ids else result.call.id,
                    name=result.call.name,
                    response={"error" if result.is_error else "output": result.output},
                )
            )
            for result in results
        ]
        self._contents.append(types.Content(role="user", parts=parts))
