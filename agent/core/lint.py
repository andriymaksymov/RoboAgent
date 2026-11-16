"""lint – lint Python code with ruff (``python -m ruff check`` via :func:`run_module`)."""

from pathlib import Path

from .process import format_result, run_module
from .registry import tool
from .utils import relative_paths, run_dir


@tool
def lint(
    workdir: Path,
    agent_dir: Path | None,
    verbose: bool,
    paths: list[str] | None = None,
    fix: bool = False,
    cwd: str = ".",
) -> str:
    """Lint Python code with ruff (ruff check) and return one line per issue: file:line:col code message.

    Args:
        paths: Files or directories relative to cwd (default: the whole cwd).
        fix: Apply ruff's safe automatic fixes and report the remaining issues.
        cwd: Directory to run in, relative to the workdir ('@agent' for the agent's own repository).
    """
    run_cwd = run_dir(workdir, cwd, agent_dir)
    command = ["ruff", "check", "--output-format", "concise", "--no-cache"]
    if fix:
        command.append("--fix")
    command += relative_paths(run_cwd, paths) or ["."]

    result = run_module(
        "lint", command, run_cwd=run_cwd, cwd_label=cwd, timeout=None,
        verbose=verbose, agent_dir=agent_dir, save_to_memory=False,
    )
    status = {0: "no issues", 1: "issues found"}.get(result.returncode, "ruff error")
    return format_result(result, status)
