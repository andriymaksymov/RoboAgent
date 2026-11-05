"""execute_python – run ad-hoc Python code in a subprocess.

VERBOSE mode extras
-------------------
When ``AgentConfig.verbose`` is ``True`` **and** ``agent_dir`` is set, the
source code passed by the model is written to a timestamped ``.py`` file inside
``{agent_dir}/logs/`` so it can be reviewed or replayed later.

Auto-save to vector memory
--------------------------
Every time a snippet executes successfully (exit code 0) and the code is
non-trivial (≥ 3 lines or ≥ 80 non-whitespace characters), it is
automatically persisted to the shared ChromaDB vector store via
:mod:`agent.memory_backend`.  This lets future runs find and reuse proven
patterns without the model having to regenerate them from scratch.
"""

import logging
import subprocess
import sys
import threading
from datetime import datetime
from pathlib import Path

from .. import memory_backend as _memory_backend
from .registry import tool

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module-level sequence counter – thread-safe, never resets within a process.
# ---------------------------------------------------------------------------
_counter_lock = threading.Lock()
_exec_counter: int = 0


def _next_seq() -> int:
    global _exec_counter
    with _counter_lock:
        _exec_counter += 1
        return _exec_counter


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_MIN_LINES = 3
_MIN_NONWS_CHARS = 80


def _is_nontrivial(code: str) -> bool:
    """Return True when *code* is worth storing (not a one-liner throw-away)."""
    lines = [ln for ln in code.splitlines() if ln.strip()]
    nonws = len(code.replace(" ", "").replace("\n", "").replace("\t", ""))
    return len(lines) >= _MIN_LINES or nonws >= _MIN_NONWS_CHARS


def _derive_title(code: str) -> str:
    """Return a short, human-readable title derived from *code*."""
    for line in code.splitlines():
        stripped = line.strip()
        if stripped.startswith("#") and len(stripped) > 2:
            return stripped[1:].strip()[:80]
        if stripped and not stripped.startswith("#"):
            return stripped[:80]
    return "Python snippet"


def _log_code_to_file(code: str, agent_dir: Path) -> Path:
    """Write *code* to a timestamped file in ``{agent_dir}/logs/`` and return the path."""
    logs_dir = agent_dir / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    seq = _next_seq()
    log_path = logs_dir / f"exec_python_{ts}_{seq:04d}.py"
    header = (
        f"# === execute_python ===\n"
        f"# Timestamp : {datetime.now().isoformat(timespec='seconds')}\n"
        f"# Sequence  : {seq}\n"
        f"# ---\n"
    )
    log_path.write_text(header + code, encoding="utf-8")
    return log_path


def _auto_save_to_memory(code: str) -> None:
    """Silently persist *code* to the vector memory store; never raises."""
    try:
        if not _is_nontrivial(code):
            return
        mem = _memory_backend.get_memory()
        title = f"Auto: {_derive_title(code)}"
        mem.save_snippet(
            title=title,
            description=(
                "Auto-saved Python snippet that was executed successfully via "
                "execute_python. Reuse as a starting point for similar tasks."
            ),
            code=code,
            tags=["auto-saved", "execute_python"],
        )
        logger.debug("execute_python: snippet auto-saved to memory (%r)", title)
    except Exception as exc:  # noqa: BLE001  # pragma: no cover – best-effort, never block
        logger.debug("execute_python: auto-save to memory failed: %s", exc)


# ---------------------------------------------------------------------------
# Tool
# ---------------------------------------------------------------------------


@tool
def execute_python(
    code: str,
    workdir: Path,
    verbose: bool,
    agent_dir: Path | None,
) -> str:
    """Execute Python code in a subprocess.

    Args:
        code: Python source to run with the agent's interpreter in the workdir.
    """
    # --- VERBOSE: persist source to @agent/logs/ ---
    if verbose and agent_dir:
        try:
            log_path = _log_code_to_file(code, agent_dir)
            logger.debug("execute_python: code saved to %s", log_path)
        except Exception as exc:  # noqa: BLE001  # pragma: no cover
            logger.debug("execute_python: could not write log file: %s", exc)

    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        timeout=20,
        cwd=str(workdir),
        check=False,
    )

    output = result.stdout
    if result.stderr:
        output += f"\n[stderr]:\n{result.stderr}"

    # --- AUTO-SAVE successful, non-trivial snippets to vector memory ---
    if result.returncode == 0:
        _auto_save_to_memory(code)

    return output if output else "[Code executed successfully without output]"
