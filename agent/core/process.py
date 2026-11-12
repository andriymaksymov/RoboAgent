"""Shared helpers for tools that run developer tools (pytest, ruff, pip) in a subprocess.

Every invocation runs as ``python -m <module>`` with the agent's own interpreter, so the
tools resolve from the same environment. In verbose mode (``verbose`` and ``agent_dir``
set) each invocation is logged to ``{agent_dir}/logs/``; a successful one (exit code 0)
is optionally persisted to the vector memory store via :mod:`agent.memory_backend`.
"""

import logging
import subprocess
import sys
import threading
from datetime import datetime
from pathlib import Path

from .. import memory_backend as _memory_backend
from .registry import ToolError

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 120
MAX_TIMEOUT = 600
MAX_OUTPUT_CHARS = 20_000

_counter_lock = threading.Lock()
_cmd_counter: int = 0


def next_seq() -> int:
    """Return the next process-wide invocation number (thread-safe, never resets)."""
    global _cmd_counter
    with _counter_lock:
        _cmd_counter += 1
        return _cmd_counter


def truncate(text: str, limit: int = MAX_OUTPUT_CHARS) -> str:
    """Keep the tail of *text* (where test/lint summaries are), marking what was dropped."""
    if len(text) <= limit:
        return text
    return f"[... truncated {len(text) - limit} chars ...]\n" + text[-limit:]


def effective_timeout(timeout: int | None, default: int = DEFAULT_TIMEOUT) -> int:
    return min(max(int(timeout or default), 1), MAX_TIMEOUT)


def log_command_to_file(
    tool_name: str,
    command: list[str],
    cwd: str,
    timeout: int,
    agent_dir: Path,
) -> Path:
    """Write a human-readable record of *command* to ``{agent_dir}/logs/`` and return the path."""
    logs_dir = agent_dir / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    seq = next_seq()
    prefix = "run_cmd" if tool_name == "run_command" else tool_name
    log_path = logs_dir / f"{prefix}_{ts}_{seq:04d}.txt"
    content = (
        f"# === {tool_name} ===\n"
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


def auto_save_to_memory(tool_name: str, command: list[str], cwd: str, timeout: int) -> None:
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
                f"Auto-saved command that completed successfully (exit 0) via {tool_name}. "
                f"Tool: {command[0]}. CWD: {cwd}."
            ),
            code=code,
            tags=["auto-saved", tool_name, command[0]],
        )
        logger.debug("%s: command auto-saved to memory (%r)", tool_name, title)
    except Exception as exc:  # noqa: BLE001  # pragma: no cover – best-effort, never block
        logger.debug("%s: auto-save to memory failed: %s", tool_name, exc)


def run_module(
    tool_name: str,
    command: list[str],
    *,
    run_cwd: Path,
    cwd_label: str,
    timeout: int | None,
    verbose: bool,
    agent_dir: Path | None,
    save_to_memory: bool = True,
) -> subprocess.CompletedProcess[str]:
    """Run ``python -m <command[0]> <command[1:]>`` in *run_cwd* and return the result.

    *command* is the logical command (e.g. ``["pytest", "-q"]``); *cwd_label* is the
    model-facing cwd used in logs and memory.
    """
    program, *program_args = command
    seconds = effective_timeout(timeout)

    if verbose and agent_dir:
        try:
            log_path = log_command_to_file(tool_name, command, cwd_label, seconds, agent_dir)
            logger.debug("%s: command saved to %s", tool_name, log_path)
        except Exception as exc:  # noqa: BLE001  # pragma: no cover
            logger.debug("%s: could not write log file: %s", tool_name, exc)

    try:
        result = subprocess.run(
            [sys.executable, "-m", program, *program_args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=seconds,
            cwd=str(run_cwd),
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise ToolError(f"Command timed out after {seconds}s.") from exc

    if result.returncode == 0 and save_to_memory:
        auto_save_to_memory(tool_name, command, cwd_label, seconds)
    return result


def format_result(result: subprocess.CompletedProcess[str], status: str | None = None) -> str:
    """Render exit code, an optional one-line status and the (truncated) stdout/stderr."""
    output = f"[Exit code]: {result.returncode}\n"
    if status:
        output += f"[Status]: {status}\n"
    if result.stdout:
        output += f"[stdout]:\n{truncate(result.stdout)}\n"
    if result.stderr:
        output += f"[stderr]:\n{truncate(result.stderr)}\n"
    return output
