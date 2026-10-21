"""Provider presets and settings resolution.

Each provider has a predefined API key, endpoint and model. They are resolved, first
match wins, from:

1. ``model`` in the TOML run config (model only)
2. provider-specific environment variables: ``<PROVIDER>_API_KEY``,
   ``<PROVIDER>_BASE_URL``, ``<PROVIDER>_MODEL`` (e.g. ``ANTHROPIC_API_KEY``)
3. generic environment variables: ``LLM_API_KEY``, ``LLM_BASE_URL``, ``LLM_MODEL``
4. the preset defaults below. An empty API key lets the provider SDK fall back to its
   own variable (``OPENAI_API_KEY``, ``ANTHROPIC_API_KEY``, ``GEMINI_API_KEY``).
"""

import os
from collections.abc import Mapping
from dataclasses import dataclass

from .base import LLMSettings


@dataclass(frozen=True)
class ProviderPreset:
    name: str
    client: str  # "<module>:<class>" inside agent.llm, imported lazily
    model: str | None
    base_url: str | None = None


PROVIDERS: dict[str, ProviderPreset] = {
    preset.name: preset
    for preset in (
        ProviderPreset("openai", "openai_client:OpenAIClient", model="gpt-5.4"),
        ProviderPreset("anthropic", "claude_client:ClaudeClient", model="claude-sonnet-4-6"),
        ProviderPreset("gemini", "gemini_client:GeminiClient", model="gemini-2.5-pro"),
        # Any OpenAI-compatible server (vLLM, Ollama, llama.cpp, LM Studio, ...).
        ProviderPreset(
            "local", "local_client:LocalClient", model=None, base_url="http://localhost:8000/v1"
        ),
    )
}

DEFAULT_PROVIDER = "claude"


def _env(env: Mapping[str, str], provider: str, key: str) -> str | None:
    return env.get(f"{provider.upper()}_{key}") or env.get(f"LLM_{key}") or None


def resolve_settings(
    provider: str,
    model: str | None = None,
    env: Mapping[str, str] | None = None,
) -> LLMSettings:
    env = os.environ if env is None else env
    preset = PROVIDERS.get(provider)
    if preset is None:
        raise ValueError(
            f"Unknown provider '{provider}'. Available: {', '.join(sorted(PROVIDERS))}."
        )

    resolved_model = model or _env(env, provider, "MODEL") or preset.model
    if not resolved_model:
        raise ValueError(
            f"No model configured for provider '{provider}'. Set 'model' in the config file, "
            f"{provider.upper()}_MODEL or LLM_MODEL."
        )

    return LLMSettings(
        provider=provider,
        model=resolved_model,
        api_key=_env(env, provider, "API_KEY") or "",
        base_url=_env(env, provider, "BASE_URL") or preset.base_url,
    )
