import logging
import subprocess
import sys
from pathlib import Path
from typing import Iterable

from .utils import resolve_in_workdir

logger = logging.getLogger(__name__)

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


def run_command(
    command: list[str],
    workdir: Path,
    allowed_commands: Iterable[str],
    cwd: str = ".",
    timeout: int | None = None,
) -> str:
    """Run an allowed tool (e.g. pytest, pip, ruff) as a subprocess under AGENT_WORKDIR."""
    logger.debug("Running command=%s cwd=%s timeout=%s", command, cwd, timeout)

    effective_timeout = min(max(int(timeout or DEFAULT_TIMEOUT), 1), MAX_TIMEOUT)
    try:
        if not isinstance(command, list) or not command or not all(isinstance(part, str) for part in command):
            return "[Error]: 'command' must be a non-empty list of strings, e.g. [\"pytest\", \"-q\"]."

        command = _strip_python_module_prefix(command)
        tool, *tool_args = command
        allowed = set(allowed_commands)
        if tool not in allowed:
            return f"[Error]: Command '{tool}' is not allowed. Allowed commands: {', '.join(sorted(allowed))}."

        run_cwd = resolve_in_workdir(workdir, cwd or ".")
        if not run_cwd.is_dir():
            return f"[Error]: Path is not a directory: '{cwd}'."

        # Run through the agent's interpreter so tools resolve from the same environment.
        result = subprocess.run(
            [sys.executable, "-m", tool, *tool_args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=effective_timeout,
            cwd=str(run_cwd),
        )

        output = f"[Exit code]: {result.returncode}\n"
        if result.stdout:
            output += f"[stdout]:\n{_truncate(result.stdout)}\n"
        if result.stderr:
            output += f"[stderr]:\n{_truncate(result.stderr)}\n"
        return output
    except subprocess.TimeoutExpired:
        logger.exception("Command timed out: %s", command)
        return f"[Error]: Command timed out after {effective_timeout}s."
    except Exception as exc:
        logger.exception("Failed to run command: %s", command)
        return f"[Command error]: {exc}"
