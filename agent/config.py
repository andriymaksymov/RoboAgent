"""Agent configuration.

LLM settings (API key, endpoint, model) come from the environment / ``.env`` (``LLM_*``
variables) on top of the preset of the selected ``provider``, see ``agent.llm.presets``.
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

from .llm.base import DEFAULT_CONTEXT_WARNING_TOKENS, LLMSettings
from .llm.presets import DEFAULT_PROVIDER, resolve_settings

DEFAULTS: dict[str, Any] = {
    "provider": DEFAULT_PROVIDER,
    "workdir": "./workspace",
    "system_prompt": "./prompts/system.md",
    "max_iterations": 20,
    "protected_branches": ["main"],
    "allowed_commands": ["pytest", "pip", "ruff"],
    "enable_run_command": False,
    "context_warning_tokens": DEFAULT_CONTEXT_WARNING_TOKENS,
    "enable_subagents": False,
    "max_subagents": 3,
    "subagent_token_budget": 2_000_000,
    "subagent_time_budget": 1800,
}
OPTIONAL_KEYS = {"model", "agent_dir"}

# Nesting level of the current agent process: 0 for a top-level run, 1 for a sub-agent
# started by delegate_tasks. Sub-agents may not delegate further and only read the memory.
DEPTH_ENV = "ROBOAGENT_DEPTH"
MAX_DEPTH = 1


def agent_depth() -> int:
    """Return the nesting level from ``ROBOAGENT_DEPTH`` (0 when unset or invalid)."""
    try:
        return max(int(os.environ.get(DEPTH_ENV, "0")), 0)
    except ValueError:
        return 0


@dataclass(frozen=True)
class AgentConfig:
    llm: LLMSettings
    workdir: Path
    system_prompt: Path
    max_iterations: int
    protected_branches: tuple[str, ...]
    allowed_commands: tuple[str, ...]
    # The agent's own repository, reachable by the tools as '@agent/...'; None disables it.
    agent_dir: Path | None = None
    # When True the agent runs in verbose/debug mode; tools use this flag to emit
    # extra artefacts (e.g. saving executed code to @agent/logs/).
    verbose: bool = False
    # Offer the generic run_command tool. Off by default: the dedicated tools (run_tests,
    # lint, format_code, pip_*) cover the usual needs, and the agent can add plugins.
    enable_run_command: bool = False
    # A request whose prompt exceeds this many tokens logs a large-context warning.
    context_warning_tokens: int = DEFAULT_CONTEXT_WARNING_TOKENS
    # Offer the delegate_tasks tool (sub-agents in separate processes). Off by default.
    enable_subagents: bool = False
    # How many sub-agents may run at the same time.
    max_subagents: int = 3
    # Total tokens (input + output) all sub-agents of one delegate_tasks call may use.
    subagent_token_budget: int = 2_000_000
    # Total wall-clock seconds one delegate_tasks call may take.
    subagent_time_budget: int = 1800

    @property
    def provider(self) -> str:
        return self.llm.provider

    @property
    def model(self) -> str:
        return self.llm.model


def _read_config_file(config_file: Path) -> dict[str, Any]:
    with config_file.open("rb") as handle:
        data = tomllib.load(handle)

    allowed_keys = set(DEFAULTS) | OPTIONAL_KEYS
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


def _positive_int(value: Any, key: str) -> int:
    # bool is an int subclass; 'true' is not a valid count.
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"'{key}' must be a positive integer")
    return value


def _bool(value: Any, key: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"'{key}' must be true or false")  # noqa: TRY004 - CLI reports ValueError
    return value


def load_config(
    config_file: Path | None = None,
    *,
    verbose: bool = False,
    workdir: Path | None = None,
    agent_dir: Path | None = None,
    max_iterations: int | None = None,
) -> AgentConfig:
    """Load the run config; ``workdir``, ``agent_dir`` and ``max_iterations`` override it.

    The overrides come from the command line (relative paths resolve against the current
    directory), so a sub-agent can be started without a generated config file.
    """
    load_dotenv()

    settings = dict(DEFAULTS)
    base_dir = Path.cwd()
    if config_file is not None:
        config_file = Path(config_file).resolve()
        settings.update(_read_config_file(config_file))
        base_dir = config_file.parent
    if workdir is not None:
        settings["workdir"] = str(Path(workdir).resolve())
    if agent_dir is not None:
        settings["agent_dir"] = str(Path(agent_dir).resolve())
    if max_iterations is not None:
        settings["max_iterations"] = max_iterations

    max_iterations = _positive_int(settings["max_iterations"], "max_iterations")
    context_warning_tokens = _positive_int(settings["context_warning_tokens"], "context_warning_tokens")
    max_subagents = _positive_int(settings["max_subagents"], "max_subagents")
    subagent_token_budget = _positive_int(settings["subagent_token_budget"], "subagent_token_budget")
    subagent_time_budget = _positive_int(settings["subagent_time_budget"], "subagent_time_budget")

    provider = settings["provider"]
    if not isinstance(provider, str):
        raise ValueError("'provider' must be a string")  # noqa: TRY004 - CLI reports ValueError
    model = settings.get("model")
    if model is not None and not isinstance(model, str):
        raise ValueError("'model' must be a string")
    llm = resolve_settings(provider.strip().lower(), model or None)

    workdir = (base_dir / settings["workdir"]).resolve()
    workdir.mkdir(parents=True, exist_ok=True)

    enable_run_command = _bool(settings["enable_run_command"], "enable_run_command")
    enable_subagents = _bool(settings["enable_subagents"], "enable_subagents")

    agent_dir = settings.get("agent_dir")
    if agent_dir is not None:
        if not isinstance(agent_dir, str):
            raise ValueError("'agent_dir' must be a string")
        agent_dir = (base_dir / agent_dir).resolve()
        if not agent_dir.is_dir():
            raise ValueError(f"'agent_dir' is not a directory: {agent_dir}")

    return AgentConfig(
        llm=llm,
        workdir=workdir,
        system_prompt=(base_dir / settings["system_prompt"]).resolve(),
        max_iterations=max_iterations,
        protected_branches=_string_tuple(settings["protected_branches"], "protected_branches"),
        allowed_commands=_string_tuple(settings["allowed_commands"], "allowed_commands"),
        agent_dir=agent_dir,
        verbose=verbose,
        enable_run_command=enable_run_command,
        context_warning_tokens=context_warning_tokens,
        enable_subagents=enable_subagents,
        max_subagents=max_subagents,
        subagent_token_budget=subagent_token_budget,
        subagent_time_budget=subagent_time_budget,
    )

