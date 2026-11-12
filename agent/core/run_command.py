"""run_command – execute an allow-listed developer tool in a subprocess.

Disabled by default (``enable_run_command = false``): the dedicated tools ``run_tests``,
``lint``, ``format_code`` and the ``pip_*`` tools cover the usual needs. When a run
profile enables it, the tool is offered to the model and limited to ``allowed_commands``.

Verbose logging and auto-save of successful commands are handled by
:mod:`agent.core.process`.
"""

from collections.abc import Iterable
from pathlib import Path

from .process import format_result, run_module
from .registry import ToolError, tool
from .utils import resolve_dir


def _strip_python_module_prefix(command: list[str]) -> list[str]:
    """Accept 'python -m pytest ...' as an alias of 'pytest ...'."""
    if len(command) >= 3 and command[0] in ("python", "python3", "py") and command[1] == "-m":
        return command[2:]
    return command


@tool(enabled_by="enable_run_command")
def run_command(
    command: list[str],
    workdir: Path,
    agent_dir: Path | None,
    allowed_commands: Iterable[str],
    verbose: bool,
    cwd: str = ".",
    timeout: int | None = None,
) -> str:
    """Run an allowed developer tool in the workdir without a shell. Prefer the dedicated tools (run_tests, lint, format_code, pip_*); use this only for what they cannot do. Returns the exit code, stdout and stderr.

    Args:
        command: Command as a list of arguments, e.g. ["pytest", "-q"] or ["ruff", "check", "."].
        cwd: Working directory relative to the workdir (default '.').
        timeout: Timeout in seconds (default 120, max 600).
    """
    if not isinstance(command, list) or not command or not all(isinstance(part, str) for part in command):
        raise ToolError("'command' must be a non-empty list of strings, e.g. [\"pytest\", \"-q\"].")

    stripped = _strip_python_module_prefix(command)
    allowed = set(allowed_commands)
    if stripped[0] not in allowed:
        raise ToolError(
            f"Command '{stripped[0]}' is not allowed. Allowed commands: {', '.join(sorted(allowed))}."
        )

    result = run_module(
        "run_command",
        stripped,
        run_cwd=resolve_dir(workdir, cwd or ".", agent_dir),
        cwd_label=cwd,
        timeout=timeout,
        verbose=verbose,
        agent_dir=agent_dir,
    )
    return format_result(result)
