import subprocess
import sys
from pathlib import Path
from typing import Iterable

from .registry import ToolError, tool
from .utils import resolve_dir

DEFAULT_TIMEOUT = 120
MAX_TIMEOUT = 600
MAX_OUTPUT_CHARS = 20_000


def _truncate(text: str) -> str:
    if len(text) <= MAX_OUTPUT_CHARS:
        return text
    return f"[... truncated {len(text) - MAX_OUTPUT_CHARS} chars ...]\n" + text[-MAX_OUTPUT_CHARS:]


def _strip_python_module_prefix(command: list[str]) -> list[str]:
    """Accept 'python -m pytest ...' as an alias of 'pytest ...'."""
    if len(command) >= 3 and command[0] in ("python", "python3", "py") and command[1] == "-m":
        return command[2:]
    return command


@tool
def run_command(
    command: list[str],
    workdir: Path,
    agent_dir: Path | None,
    allowed_commands: Iterable[str],
    cwd: str = ".",
    timeout: int | None = None,
) -> str:
    """Run an allowed developer tool (e.g. pytest, pip, ruff) in the workdir without a shell. Returns the exit code, stdout and stderr.

    Args:
        command: Command as a list of arguments, e.g. ["pytest", "-q"] or ["ruff", "check", "."].
        cwd: Working directory relative to the workdir (default '.').
        timeout: Timeout in seconds (default 120, max 600).
    """
    if not isinstance(command, list) or not command or not all(isinstance(part, str) for part in command):
        raise ToolError("'command' must be a non-empty list of strings, e.g. [\"pytest\", \"-q\"].")

    program, *program_args = _strip_python_module_prefix(command)
    allowed = set(allowed_commands)
    if program not in allowed:
        raise ToolError(f"Command '{program}' is not allowed. Allowed commands: {', '.join(sorted(allowed))}.")

    run_cwd = resolve_dir(workdir, cwd or ".", agent_dir)
    effective_timeout = min(max(int(timeout or DEFAULT_TIMEOUT), 1), MAX_TIMEOUT)

    try:
        # Run through the agent's interpreter so tools resolve from the same environment.
        result = subprocess.run(
            [sys.executable, "-m", program, *program_args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=effective_timeout,
            cwd=str(run_cwd),
        )
    except subprocess.TimeoutExpired as exc:
        raise ToolError(f"Command timed out after {effective_timeout}s.") from exc

    output = f"[Exit code]: {result.returncode}\n"
    if result.stdout:
        output += f"[stdout]:\n{_truncate(result.stdout)}\n"
    if result.stderr:
        output += f"[stderr]:\n{_truncate(result.stderr)}\n"
    return output
