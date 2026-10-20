"""Agent configuration.

General settings (API key, endpoint, model) come from the environment / ``.env``.
Run settings come from an optional TOML config file; relative paths in it are resolved
against the config file's directory. Without a config file the defaults below apply,
relative to the current directory.
"""

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

DEFAULTS: dict[str, Any] = {
    "workdir": "./workspace",
    "system_prompt": "./prompts/system.md",
    "max_iterations": 20,
    "protected_branches": ["main"],
    "allowed_commands": ["pytest", "pip", "ruff"],
}


@dataclass(frozen=True)
class AgentConfig:
    api_key: str
    base_url: str
    model: str
    workdir: Path
    system_prompt: Path
    max_iterations: int
    protected_branches: tuple[str, ...]
    allowed_commands: tuple[str, ...]


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

    workdir = (base_dir / settings["workdir"]).resolve()
    workdir.mkdir(parents=True, exist_ok=True)

    return AgentConfig(
        api_key=os.getenv("OPENAI_API_KEY", ""),
        base_url=os.getenv("OPENAI_BASE_URL", "http://localhost:8000/v1"),
        model=settings.get("model") or os.getenv("OPENAI_MODEL", "gpt-5.4"),
        workdir=workdir,
        system_prompt=(base_dir / settings["system_prompt"]).resolve(),
        max_iterations=max_iterations,
        protected_branches=_string_tuple(settings["protected_branches"], "protected_branches"),
        allowed_commands=_string_tuple(settings["allowed_commands"], "allowed_commands"),
    )

