"""format_code – format Python code with ruff (``python -m ruff format`` via :func:`run_module`)."""

from pathlib import Path

from .process import format_result, run_module
from .registry import tool
from .utils import relative_paths, run_dir


@tool
def format_code(
    workdir: Path,
    agent_dir: Path | None,
    verbose: bool,
    paths: list[str] | None = None,
    check: bool = False,
    cwd: str = ".",
) -> str:
    """Format Python code with ruff (ruff format). With check=true, change nothing and show the diff that formatting would apply.

    Args:
        paths: Files or directories relative to cwd (default: the whole cwd).
        check: Only report (as a diff) what would be reformatted; do not modify files.
        cwd: Directory to run in, relative to the workdir ('@agent' for the agent's own repository).
    """
    run_cwd = run_dir(workdir, cwd, agent_dir)
    command = ["ruff", "format", "--no-cache"]
    if check:
        command.append("--diff")
    command += relative_paths(run_cwd, paths) or ["."]

    result = run_module(
        "format_code", command, run_cwd=run_cwd, cwd_label=cwd, timeout=None,
        verbose=verbose, agent_dir=agent_dir, save_to_memory=False,
    )
    if check:
        status = {0: "already formatted", 1: "files would be reformatted"}.get(result.returncode, "ruff error")
    else:
        status = "formatted" if result.returncode == 0 else "ruff error"
    return format_result(result, status)
