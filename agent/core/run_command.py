"""run_command – execute an allow-listed developer tool in a subprocess.

VERBOSE mode extras
-------------------
When ``AgentConfig.verbose`` is ``True`` **and** ``agent_dir`` is set, every
invocation is recorded as a text file inside ``{agent_dir}/logs/`` so the full
history of commands can be reviewed after a run.

Auto-save to vector memory
--------------------------
When a command exits with code 0 it is automatically persisted to the shared
ChromaDB vector store via :mod:`agent.memory_backend`.  Stored entries capture
the exact command, working-directory, and effective timeout, which helps the
model recall proven build/test incantations for similar tasks in the future.
"""

import logging
import subprocess
import sys
import threading
from collections.abc import Iterable
from datetime import datetime
from pathlib import Path

from .. import memory_backend as _memory_backend
from .registry import ToolError, tool
from .utils import resolve_dir

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 120
MAX_TIMEOUT = 600
MAX_OUTPUT_CHARS = 20_000

# ---------------------------------------------------------------------------
# Module-level sequence counter – thread-safe, never resets within a process.
# ---------------------------------------------------------------------------
_counter_lock = threading.Lock()
_cmd_counter: int = 0


def _next_seq() -> int:
    global _cmd_counter
    with _counter_lock:
        _cmd_counter += 1
        return _cmd_counter


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _truncate(text: str) -> str:
    if len(text) <= MAX_OUTPUT_CHARS:
        return text
    return f"[... truncated {len(text) - MAX_OUTPUT_CHARS} chars ...]\n" + text[-MAX_OUTPUT_CHARS:]


def _strip_python_module_prefix(command: list[str]) -> list[str]:
    """Accept 'python -m pytest ...' as an alias of 'pytest ...'."""
    if len(command) >= 3 and command[0] in ("python", "python3", "py") and command[1] == "-m":
        return command[2:]
    return command


def _log_command_to_file(
    command: list[str],
    cwd: str,
    timeout: int,
    agent_dir: Path,
) -> Path:
    """Write a human-readable record of *command* to ``{agent_dir}/logs/`` and return the path."""
    logs_dir = agent_dir / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    seq = _next_seq()
    log_path = logs_dir / f"run_cmd_{ts}_{seq:04d}.txt"
    content = (
        f"# === run_command ===\n"
        f"# Timestamp : {datetime.now().isoformat(timespec='seconds')}\n"
        f"# Sequence  : {seq}\n"
        f"# CWD       : {cwd}\n"
        f"# Timeout   : {timeout}s\n"
        f"# ---\n"
        + " ".join(command)
        + "\n"
    )
    log_path.write_text(content, encoding="utf-8")
    return log_path


def _auto_save_to_memory(command: list[str], cwd: str, timeout: int) -> None:
    """Silently persist a successful command to the vector memory store; never raises."""
    try:
        mem = _memory_backend.get_memory()
        cmd_str = " ".join(command)
        title = f"Auto cmd: {cmd_str[:80]}"
        code = (
            f"# Command  : {cmd_str}\n"
            f"# CWD      : {cwd}\n"
            f"# Timeout  : {timeout}s\n"
            f"{cmd_str}\n"
        )
        mem.save_snippet(
            title=title,
            description=(
                f"Auto-saved command that completed successfully (exit 0) via run_command. "
                f"Tool: {command[0]}. CWD: {cwd}."
            ),
            code=code,
            tags=["auto-saved", "run_command", command[0]],
        )
        logger.debug("run_command: command auto-saved to memory (%r)", title)
    except Exception as exc:  # noqa: BLE001  # pragma: no cover – best-effort, never block
        logger.debug("run_command: auto-save to memory failed: %s", exc)


# ---------------------------------------------------------------------------
# Tool
# ---------------------------------------------------------------------------


@tool
def run_command(
    command: list[str],
    workdir: Path,
    agent_dir: Path | None,
    allowed_commands: Iterable[str],
    verbose: bool,
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

    # --- VERBOSE: persist command to @agent/logs/ ---
    if verbose and agent_dir:
        try:
            log_path = _log_command_to_file(command, cwd, effective_timeout, agent_dir)
            logger.debug("run_command: command saved to %s", log_path)
        except Exception as exc:  # noqa: BLE001  # pragma: no cover
            logger.debug("run_command: could not write log file: %s", exc)

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
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise ToolError(f"Command timed out after {effective_timeout}s.") from exc

    output = f"[Exit code]: {result.returncode}\n"
    if result.stdout:
        output += f"[stdout]:\n{_truncate(result.stdout)}\n"
    if result.stderr:
        output += f"[stderr]:\n{_truncate(result.stderr)}\n"

    # --- AUTO-SAVE successful commands to vector memory ---
    if result.returncode == 0:
        _auto_save_to_memory(command, cwd, effective_timeout)

    return output
