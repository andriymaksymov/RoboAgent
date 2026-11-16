"""pip_list – list the packages installed in the agent's Python environment."""

from pathlib import Path

from .process import format_result, run_module
from .registry import tool


@tool
def pip_list(workdir: Path, verbose: bool, agent_dir: Path | None, outdated: bool = False) -> str:
    """List the packages installed in the agent's Python environment.

    Args:
        outdated: Only list packages with a newer version available (queries the package index).
    """
    command = ["pip", "list", "--format", "columns", "--disable-pip-version-check"]
    if outdated:
        command.append("--outdated")
    result = run_module(
        "pip_list", command, run_cwd=workdir, cwd_label=".", timeout=None,
        verbose=verbose, agent_dir=agent_dir,
    )
    return format_result(result)
