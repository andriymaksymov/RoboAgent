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

import ast
import logging
import os
import subprocess
import sys
import threading
from datetime import datetime
from pathlib import Path

from .. import memory_backend as _memory_backend
from .registry import ToolError, tool

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
# "Pure computation" guard
# ---------------------------------------------------------------------------
#
# Two layers. The static check gives the model a clear, early error for the obvious
# cases. The audit hook (installed in the child before the snippet runs, and impossible
# to remove from Python code) catches indirect routes such as asyncio subprocesses,
# __import__ tricks or third-party wrappers. It is a guard rail, not a sandbox: native
# code (ctypes, C extensions) can still bypass it.

_FORBIDDEN_MODULES = frozenset({"subprocess", "multiprocessing", "pty", "pexpect", "sh", "plumbum"})
_FORBIDDEN_OS_ATTRS = frozenset({"system", "popen", "startfile", "fork", "forkpty"})
_FORBIDDEN_OS_PREFIXES = ("exec", "spawn", "posix_spawn")
_BLOCKED_AUDIT_EVENTS = (
    "subprocess.Popen",
    "os.system",
    "os.exec",
    "os.spawn",
    "os.posix_spawn",
    "os.startfile",
    "os.fork",
    "os.forkpty",
    "_winapi.CreateProcess",
)

_PRELUDE = f"""
import sys

def _roboagent_guard(event, args, _blocked=frozenset({_BLOCKED_AUDIT_EVENTS!r})):
    if event in _blocked:
        raise PermissionError(
            f"execute_python is for pure computation; '{{event}}' (starting a process) is blocked."
        )

sys.addaudithook(_roboagent_guard)
del _roboagent_guard
_code = sys.stdin.buffer.read().decode("utf-8")
exec(compile(_code, "<execute_python>", "exec"), {{"__name__": "__main__", "__builtins__": __builtins__}})
"""


def _is_forbidden_os_attr(name: str) -> bool:
    return name in _FORBIDDEN_OS_ATTRS or name.startswith(_FORBIDDEN_OS_PREFIXES)


def _module_root(name: str) -> str:
    return name.split(".", 1)[0]


def find_forbidden_calls(code: str) -> list[str]:
    """Return a description of every process-starting construct found in *code*.

    Code that does not parse is not rejected here; running it reports the SyntaxError.
    """
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return []

    found: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found += [f"import {a.name}" for a in node.names if _module_root(a.name) in _FORBIDDEN_MODULES]
        elif isinstance(node, ast.ImportFrom) and node.module:
            if _module_root(node.module) in _FORBIDDEN_MODULES:
                found.append(f"from {node.module} import ...")
            elif node.module == "os":
                found += [f"from os import {a.name}" for a in node.names if _is_forbidden_os_attr(a.name)]
        elif isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
            if node.value.id == "os" and _is_forbidden_os_attr(node.attr):
                found.append(f"os.{node.attr}")
        elif isinstance(node, ast.Call) and node.args and isinstance(node.args[0], ast.Constant):
            func = node.func
            name = func.id if isinstance(func, ast.Name) else func.attr if isinstance(func, ast.Attribute) else ""
            target = node.args[0].value
            if (
                name in ("__import__", "import_module")
                and isinstance(target, str)
                and _module_root(target) in _FORBIDDEN_MODULES
            ):
                found.append(f"{name}({target!r})")
    return list(dict.fromkeys(found))


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
    """Run a short, pure-computation Python snippet (calculations, parsing, quick checks of the project's own functions) and return its output. Starting processes is blocked (subprocess, multiprocessing, os.system, os.popen, os.exec*/spawn*); use run_tests, lint, format_code, pip_* or git_* instead, or add a plugin tool when none fits. Timeout: 20 seconds.

    Args:
        code: Python source to run with the agent's interpreter in the workdir.
    """
    violations = find_forbidden_calls(code)
    if violations:
        raise ToolError(
            "execute_python is for pure computation; starting processes is not allowed ("
            + "; ".join(violations)
            + "). Use the dedicated tools (run_tests, lint, format_code, pip_*, git_*) "
            "or add a plugin tool in @agent/agent/plugin/."
        )

    # --- VERBOSE: persist source to @agent/logs/ ---
    if verbose and agent_dir:
        try:
            log_path = _log_code_to_file(code, agent_dir)
            logger.debug("execute_python: code saved to %s", log_path)
        except Exception as exc:  # noqa: BLE001  # pragma: no cover
            logger.debug("execute_python: could not write log file: %s", exc)

    # The snippet is passed on stdin and run under an audit hook that blocks process creation.
    result = subprocess.run(
        [sys.executable, "-c", _PRELUDE],
        input=code,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=20,
        cwd=str(workdir),
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        check=False,
    )

    output = result.stdout
    if result.stderr:
        output += f"\n[stderr]:\n{result.stderr}"

    # --- AUTO-SAVE successful, non-trivial snippets to vector memory ---
    if result.returncode == 0:
        _auto_save_to_memory(code)

    return output if output else "[Code executed successfully without output]"
