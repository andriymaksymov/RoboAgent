"""execute_python – run ad-hoc Python code in a subprocess.

VERBOSE mode extras
-------------------
When ``AgentConfig.verbose`` is ``True`` **and** ``agent_dir`` is set, the
source code passed by the model is written to a timestamped ``.py`` file inside
``{agent_dir}/logs/`` so it can be reviewed or replayed later.

Nothing is saved to vector memory automatically; the model saves deliberately with
the ``memory_save`` tool.
"""

import ast
import logging
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

from ..console_log import file_only
from .process import log_process_result, next_seq
from .registry import ToolError, tool

logger = logging.getLogger(__name__)

_SANDBOX = Path(__file__).with_name("_sandbox.py")


def _log_code_to_file(code: str, agent_dir: Path) -> Path:
    """Write *code* to a timestamped file in ``{agent_dir}/logs/`` and return the path."""
    logs_dir = agent_dir / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    seq = next_seq()
    log_path = logs_dir / f"exec_python_{ts}_{seq:04d}.py"
    header = (
        f"# === execute_python ===\n"
        f"# Timestamp : {datetime.now().isoformat(timespec='seconds')}\n"
        f"# Sequence  : {seq}\n"
        f"# ---\n"
    )
    log_path.write_text(header + code, encoding="utf-8")
    return log_path


# ---------------------------------------------------------------------------
# "Pure computation" guard
# ---------------------------------------------------------------------------
#
# Two layers. The static check gives the model a clear, early error for the obvious
# cases. The audit hook (installed in the child before the snippet runs, and impossible
# to remove from Python code) catches indirect routes such as asyncio subprocesses,
# __import__ tricks or third-party wrappers; it lives in ``_sandbox.py``. It is a guard
# rail, not a sandbox: native code (ctypes, C extensions) can still bypass it.

_FORBIDDEN_MODULES = frozenset({"subprocess", "multiprocessing", "pty", "pexpect", "sh", "plumbum"})
_FORBIDDEN_OS_ATTRS = frozenset({"system", "popen", "startfile", "fork", "forkpty"})
_FORBIDDEN_OS_PREFIXES = ("exec", "spawn", "posix_spawn")


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

    logger.info(
        "execute_python: running snippet (%d lines)\n  interpreter: %s\n  cwd: %s\n  timeout: 20s\n"
        "--- code ---\n%s\n--- end code ---",
        len(code.splitlines()), sys.executable, workdir, code.rstrip(),
        extra=file_only(),
    )
    started = time.perf_counter()
    # The snippet is passed on stdin and run under an audit hook that blocks process creation.
    result = subprocess.run(
        [sys.executable, str(_SANDBOX)],
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

    log_process_result("execute_python", result, time.perf_counter() - started)

    output = result.stdout
    if result.stderr:
        output += f"\n[stderr]:\n{result.stderr}"

    if result.returncode != 0:
        return f"[Exit code]: {result.returncode}\n{output.lstrip()}"
    return output if output else "[Code executed successfully without output]"
