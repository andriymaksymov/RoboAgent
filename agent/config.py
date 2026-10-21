"""Agent configuration.

LLM settings (API key, endpoint, model) come from the environment / ``.env`` (``LLM_*``
variables) on top of the preset of the selected ``provider``, see ``agent.llm.presets``.
Run settings come from an optional TOML config file; relative paths in it are resolved
against the config file's directory. Without a config file the defaults below apply,
relative to the current directory.
"""

import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from .llm.base import LLMSettings
from .llm.presets import DEFAULT_PROVIDER, resolve_settings

DEFAULTS: dict[str, Any] = {
    "provider": DEFAULT_PROVIDER,
    "workdir": "./workspace",
    "system_prompt": "./prompts/system.md",
    "max_iterations": 20,
    "protected_branches": ["main"],
    "allowed_commands": ["pytest", "pip", "ruff"],
}


@dataclass(frozen=True)
class AgentConfig:
    llm: LLMSettings
    workdir: Path
    system_prompt: Path
    max_iterations: int
    protected_branches: tuple[str, ...]
    allowed_commands: tuple[str, ...]

    @property
    def provider(self) -> str:
        return self.llm.provider

    @property
    def model(self) -> str:
        return self.llm.model


def _read_config_file(config_file: Path) -> dict[str, Any]:
    with config_file.open("rb") as handle:
        data = tomllib.load(handle)

    allowed_keys = set(DEFAULTS) | {"model"}
    unknown = set(data) - allowed_keys
    if unknown:
        raise ValueError(
            f"Unknown key(s) in {config_file}: {', '.join(sorted(unknown))}. "
            f"Allowed: {', '.join(sorted(allowed_keys))}."
        )
    return data


def _string_tuple(value: Any, key: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError(f"'{key}' must be a list of strings")
    return tuple(value)


def load_config(config_file: Path | None = None) -> AgentConfig:
    load_dotenv()

    settings = dict(DEFAULTS)
    base_dir = Path.cwd()
    if config_file is not None:
        config_file = Path(config_file).resolve()
        settings.update(_read_config_file(config_file))
        base_dir = config_file.parent

    max_iterations = settings["max_iterations"]
    if not isinstance(max_iterations, int) or max_iterations <= 0:
        raise ValueError("'max_iterations' must be a positive integer")

    provider = settings["provider"]
    if not isinstance(provider, str):
        raise ValueError("'provider' must be a string")  # noqa: TRY004 - CLI reports ValueError
    model = settings.get("model")
    if model is not None and not isinstance(model, str):
        raise ValueError("'model' must be a string")
    llm = resolve_settings(provider.strip().lower(), model or None)

    workdir = (base_dir / settings["workdir"]).resolve()
    workdir.mkdir(parents=True, exist_ok=True)

    return AgentConfig(
        llm=llm,
        workdir=workdir,
        system_prompt=(base_dir / settings["system_prompt"]).resolve(),
        max_iterations=max_iterations,
        protected_branches=_string_tuple(settings["protected_branches"], "protected_branches"),
        allowed_commands=_string_tuple(settings["allowed_commands"], "allowed_commands"),
    )

