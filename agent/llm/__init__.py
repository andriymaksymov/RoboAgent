"""Switchable LLM backends.

``create_client(settings)`` returns an ``LLMClient`` for the configured provider
("openai", "claude", "gemini" or "local"). Provider SDKs are imported lazily, so only
the SDK of the selected provider has to be installed.

To add or tune a provider, edit its ``*_client.py`` module and register a preset in
``presets.PROVIDERS``.
"""

import importlib

from .base import (
    LLMClient,
    LLMError,
    LLMResponse,
    LLMSettings,
    ToolCall,
    ToolResult,
    ToolSpec,
    parse_arguments,
)
from .presets import DEFAULT_PROVIDER, PROVIDERS, ProviderPreset, resolve_settings


def create_client(settings: LLMSettings) -> LLMClient:
    preset = PROVIDERS.get(settings.provider)
    if preset is None:
        raise ValueError(
            f"Unknown provider '{settings.provider}'. Available: {', '.join(sorted(PROVIDERS))}."
        )
    module_name, class_name = preset.client.split(":")
    try:
        module = importlib.import_module(f".{module_name}", __name__)
    except ImportError as exc:
        raise LLMError(
            f"SDK for provider '{settings.provider}' is not installed: {exc}. "
            "Install the dependencies from requirements.txt."
        ) from exc
    return getattr(module, class_name)(settings)


__all__ = [
    "DEFAULT_PROVIDER",
    "PROVIDERS",
    "LLMClient",
    "LLMError",
    "LLMResponse",
    "LLMSettings",
    "ProviderPreset",
    "ToolCall",
    "ToolResult",
    "ToolSpec",
    "create_client",
    "parse_arguments",
    "resolve_settings",
]
