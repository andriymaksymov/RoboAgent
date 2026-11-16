"""Shared helpers for tools that run developer tools (pytest, ruff, pip) in a subprocess.

Every invocation runs as ``python -m <module>`` with the agent's own interpreter, so the
tools resolve from the same environment. In verbose mode (``verbose`` and ``agent_dir``
set) each invocation is logged to ``{agent_dir}/logs/``. ``next_seq`` numbers those log
files and is shared with ``execute_python``.
"""

import logging
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

from ..console_log import file_only
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


def run_module(
    tool_name: str,
    command: list[str],
    *,
    run_cwd: Path,
    cwd_label: str,
    timeout: int | None,
    verbose: bool,
    agent_dir: Path | None,
) -> subprocess.CompletedProcess[str]:
    """Run ``python -m <command[0]> <command[1:]>`` in *run_cwd* and return the result.

    *command* is the logical command (e.g. ``["pytest", "-q"]``); *cwd_label* is the
    model-facing cwd used in logs.
    """
    program, *program_args = command
    seconds = effective_timeout(timeout)

    if verbose and agent_dir:
        try:
            log_path = log_command_to_file(tool_name, command, cwd_label, seconds, agent_dir)
            logger.debug("%s: command saved to %s", tool_name, log_path)
        except Exception as exc:  # noqa: BLE001  # pragma: no cover
            logger.debug("%s: could not write log file: %s", tool_name, exc)

    argv = [sys.executable, "-m", program, *program_args]
    logger.info(
        "%s: running %s\n  interpreter: %s\n  argv: %s\n  cwd: %s (%s)\n  timeout: %ss",
        tool_name, " ".join(command), sys.executable, argv, run_cwd, cwd_label, seconds,
        extra=file_only(),
    )
    started = time.perf_counter()
    try:
        result = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=seconds,
            cwd=str(run_cwd),
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        logger.info("%s: timed out after %ss", tool_name, seconds, extra=file_only())
        raise ToolError(f"Command timed out after {seconds}s.") from exc

    log_process_result(tool_name, result, time.perf_counter() - started, full_output=program == "pytest")
    return result


def log_process_result(
    tool_name: str,
    result: subprocess.CompletedProcess[str],
    elapsed: float,
    *,
    full_output: bool = False,
) -> None:
    """Record a finished subprocess in the log file (not on the console).

    Always logs exit code, duration and output sizes. With *full_output* (e.g. pytest
    test results) stdout and stderr are logged in full; otherwise only stderr of a failed
    run is logged, truncated.
    """
    stdout, stderr = result.stdout or "", result.stderr or ""
    logger.info(
        "%s: exit code %s after %.2fs (stdout %d chars, stderr %d chars)",
        tool_name, result.returncode, elapsed, len(stdout), len(stderr),
        extra=file_only(),
    )
    if full_output:
        if stdout.strip():
            logger.info("%s: stdout:\n%s", tool_name, stdout.rstrip(), extra=file_only())
        if stderr.strip():
            logger.info("%s: stderr:\n%s", tool_name, stderr.rstrip(), extra=file_only())
    elif result.returncode != 0 and stderr.strip():
        logger.info("%s: stderr:\n%s", tool_name, truncate(stderr.rstrip(), 4000), extra=file_only())


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
